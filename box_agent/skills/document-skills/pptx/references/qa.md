# PPTX QA Reference

Use this checklist after creating or editing a `.pptx`. Do not claim visual QA
is complete unless rendered slide images or preview images were produced and
reviewed by `vision_review` or another real image-capable tool. Producing
screenshots is not enough; visual QA means sending the visible pixels as image
input and recording a per-slide verdict.

## Required Checks

Keep every temporary report, helper script, extracted text file, and rendered
image inside the current workspace or requested output folder. Do not write to
`/tmp`, `/var/tmp`, or another absolute temp path.

For HTML-first decks exported with `scripts/html_to_editable_pptx.js` and
`dom-to-pptx`, inspect both the source HTML preview PNGs and the rendered PPTX
output. Editable export can reflow text, shift layers, or lose CSS effects, so
source previews alone are not enough.

0. HTML self-check for HTML-first decks:
   - Run `${BOX_AGENT_NODE:-node} scripts/html_self_check.js deck.html --dom-to-pptx --report qa/html_self_check.json` before export, or rely on `scripts/html_to_editable_pptx.js` which writes the same check internally.
   - Always use the stricter `--dom-to-pptx` compatibility profile for new HTML-first decks.
   - Confirm `qa/html_self_check.json` exists, is non-empty, and has `"ok": true`. If it is missing, report HTML self-check as `BLOCKED`.
   - Fix failures before export. This catches DOM/CSS layout bugs such as progress `.fill` elements left as `display:inline`, zero-size bars/charts, text overflow, missing images, and content outside the slide.
   - This is a preflight gate, not visual QA. Passing it does not mean the slide looks good.

1. Package validation:
   - Run `${BOX_AGENT_PYTHON:-python3} scripts/validate_pptx_package.py output.pptx`.
   - Fix zip, relationship, missing part, or invalid XML errors before delivery.

2. Text extraction:
   - Run `${BOX_AGENT_PYTHON:-python3} scripts/extract_text.py output.pptx`.
   - Verify slide count, slide order, expected titles, and requested content.
   - Verify visible page numbers against actual slide order. Use a consistent
     `NN / TOTAL` style such as `03 / 08`; non-cover slides should not silently
     omit folios. A cover may omit the page number only when the deck uses that
     convention intentionally and the next slide starts at `02 / TOTAL`.

3. Placeholder scan:
   - Check for `lorem`, `ipsum`, `todo`, `placeholder`, `xxxx`, and template instructions.
   - Treat hits in notes, masters, and layouts as warnings unless the user asked to edit them.
   - Reject empty or failed QA files. A 0-byte JSON/TXT/MD report is not a pass;
     rerun the check, replace it with a real report, or mark that check `BLOCKED`.

4. Render:
   - Run `${BOX_AGENT_PYTHON:-python3} scripts/render_pptx.py output.pptx --out rendered`.
   - For HTML-first decks, this PPTX render is used for source-preview-vs-output image comparison. If LibreOffice is missing, report PPTX render comparison as `BLOCKED` but do not discard the HTML preview QA.
   - Do not pre-check `soffice` and skip this command. The render script owns renderer discovery, Quick Look fallback, and missing-LibreOffice messaging.
   - Do not pass `--format png` for visual-model inputs unless a PNG is explicitly required; the default JPG output is intentionally compressed to reduce request size.
   - The preferred path is `soffice` PPTX-to-PDF plus `pdftoppm` PDF-to-PNG.
   - If Poppler is unavailable, the script may use Node pdf.js with `pdfjs-dist` and `@napi-rs/canvas`.
   - On macOS, Quick Look is only a lightweight fallback.

5. Image comparison for HTML-first decks:
   - When both source preview images and PPTX-rendered slide images exist, compare them with `${BOX_AGENT_NODE:-node} scripts/compare_slide_images.js slides rendered --out qa/diff`.
   - This checks whether DOM-to-PPTX export/rendering changed the slide image: missing slides, wrong order, scaling changes, cropping, text wrapping, gradients, SVGs, shadows, z-order, or image masks.
   - Treat non-empty image checks as insufficient. A PNG can be non-empty while the chart, bar, or image is missing.
   - If PPTX-rendered images are blocked, report `Image comparison: BLOCKED` and name the renderer limitation.
   - Pixel comparison only proves fidelity to the source previews. It does not judge whether the original slide is well-designed or semantically correct.

6. Visual inspection:
   - Use `vision_review` when it is available. Pass actual image files, not only their paths in normal chat text.
   - Before calling `vision_review`, create compressed review-size copies of the slide images: `${BOX_AGENT_NODE:-node} scripts/make_vision_inputs.js slides --out qa/vision_inputs`. Use `rendered` instead of `slides` when reviewing rendered PPTX images. Keep original full-size images for export and image comparison; `qa/vision_inputs` is only for vision-model review.
   - For HTML-first decks, prefer every generated `qa/vision_inputs/slide-*.jpg` derived from `html_to_editable_pptx.js` source previews.
   - For rendered PPTX decks, prefer every generated review-size copy of `rendered/slide-*.png` or preview image, emitted as compressed JPG by default.
   - For decks with 20 or fewer slides, pass every individual `qa/vision_inputs/slide-*.jpg` image to `vision_review`. For larger decks, pass every changed, title, section, data-heavy, and image-heavy slide, and say which range was sampled.
   - Generate a contact sheet for overview, for example `${BOX_AGENT_NODE:-node} scripts/make_contact_sheet.js slides --out qa/vision-contact-sheet.png`. Include it as an additional image if useful, but do not use it as the only input when individual compressed slide images are available.
   - Treat the contact sheet as review material, not as the review result. The script also writes `qa/vision-review-prompt.txt`; use that prompt in the `vision_review` instructions.
   - Use an image-viewing or vision-capable tool. Do not count file existence, image dimensions, package XML, text extraction, OCR, histogram checks, or pixel diff as visual inspection.
   - Check blank or near-blank slides, clipped text, blurry or unreadable text, overlap, bad spacing, missing media, wrong slide order, low contrast, bad crop/scaling, missing charts, and low-quality shape-built people.
   - Record a short per-slide verdict before final delivery, for example `slide-01: PASS`, `slide-02: ISSUE title overlaps chart`, or `slide-03: BLOCKED image could not be opened`.
   - Write the verdict to the deck output folder's `qa/visual_review.md`. If the deck lives in `future_weather_deck/`, the report should be `future_weather_deck/qa/visual_review.md`, not workspace-root `qa/visual_review.md`.
   - If only OOXML checks were possible, do not call visual inspection complete.
   - If `vision_review` is unavailable, fails, or no image-capable review was performed, report `Visual inspection: BLOCKED`, even if HTML self-check, image comparison, and non-empty PNG checks passed.

## How To Perform Vision Review

Use `vision_review` as the preferred image-capable path. The required input is
the individual compressed review-size `qa/vision_inputs/slide-*.jpg` files whenever they
exist; the contact sheet is an overview image, not the primary evidence.

- If the `vision_review` tool is available, call it with all individual
  review-size slide JPG/PNG paths and `output_path` set to the deck folder's `qa/visual_review.md`.
  Include `qa/vision-contact-sheet.png` only as an additional overview image.
- If all individual review-size images exceed the model request limit, split the
  review into small batches of 1-3 slides or rerun `make_vision_inputs.js` with
  `--max-width 720 --quality 0.76`. Merge the batch reports into the final
  `qa/visual_review.md`. Never downgrade to a contact-sheet-only PASS because
  of a request-size error.
- If another agent host provides a vision/image tool, call that tool with the
  individual slide images first. Then use the contact sheet for cross-slide
  consistency and order.
- If the host supports multimodal messages, attach the contact sheet image in a
  message to the vision-capable model only as a fallback; inspect individual
  individual compressed slide images if the sheet is too small to judge text, charts, or bars.
- If running in Codex with local image viewing, use the local image viewer for
  `qa/vision-contact-sheet.png`, then inspect individual slide files as needed.
- If only shell, text extraction, image dimensions, histogram, pixel diff, or
  non-empty checks are available, vision review has not happened. Report
  `Visual inspection: BLOCKED`.

Suggested `vision_review` call:

```json
{
  "image_paths": [
    "qa/vision_inputs/slide-01.jpg",
    "qa/vision_inputs/slide-02.jpg",
    "qa/vision_inputs/slide-03.jpg"
  ],
  "output_path": "qa/visual_review.md",
  "instructions": "Review every slide image for blank output, clipped or overlapping text, unreadable small text, missing charts/bars/images, low contrast, bad crop/scaling, wrong order, and poor shape-built people. Return per-slide PASS/ISSUE with concrete fixes."
}
```

Use this review prompt in `instructions`:

```text
Review these slide images for a PPT QA pass. For each slide, return PASS or
ISSUE. Check whether charts/bars are visible, text is readable, no content is
clipped or overlapping, images are present, contrast is acceptable, crop/scaling
is correct, and the slide is not blank. Mention the slide number for each issue.
```

The QA report must say which image was reviewed, for example:

```text
Visual inspection: PASS
Reviewed: qa/vision_inputs/slide-01.jpg; qa/vision_inputs/slide-02.jpg; qa/vision_inputs/slide-03.jpg
Verdict: slide-01 PASS; slide-02 PASS; slide-03 ISSUE probability bars missing
```

Write this same information to `qa/visual_review.md`. If this file is missing,
the final report must not say visual inspection passed.

If batch reports are created, the final `qa/visual_review.md` must summarize all
batches and include the final overall verdict. Do not leave contradictory files
such as one `visual_review.md` with ISSUE and another `visual_review_final.md`
with PASS unless the final report explicitly explains what was fixed and which
report is authoritative.

## Visual Quality Gate

The visual quality gate passes only when all produced slide images have been
opened or attached to an image-capable review tool and each slide has a verdict.
The report must include the contact sheet path or the individual image paths
that were reviewed by vision.
For decks with 20 or fewer slides, inspect every slide. For larger decks, inspect
every changed slide plus title, section, data-heavy, and image-heavy slides; say
which slide range was sampled.

Fail and iterate when any slide has:

- blank or mostly blank output
- resolution below 1280x720 for a 16:9 deck, or obvious blur at normal viewing size
- text clipped by the slide edge, footer, image, chart, or card container
- overlapping labels, charts, legends, or icons
- unreadable contrast or tiny dense paragraphs
- important content cropped off, hidden outside the slide, or covered by another layer
- missing expected images, charts, logos, maps, screenshots, or icons
- generated/shape-built people that look visibly poor
- generic placeholder silhouettes used for named people when a more deliberate
  non-portrait design would be better
- missing, inconsistent, or wrong page numbers on non-cover slides

If no image-viewing or vision-capable tool is available, report:

```text
Visual inspection: BLOCKED
Reason: slide images were generated, but no image-capable review tool was available
```

## Blocked Rendering

If no per-slide image or preview is produced, report:

```text
Rendering: BLOCKED
Reason: missing soffice, missing PDF renderer, or conversion failure
```

Still report package validation, text extraction, and placeholder scan results.
Do not say "OOXML checks ensure quality" or "rendering is complete" when
`render_pptx.py` was not run. OOXML checks are structural checks only.
If `soffice` is missing, tell the user that LibreOffice is required for
PPTX-to-PDF conversion and provide this official download page:
`https://www.libreoffice.org/download/download-libreoffice/`.
Do not imply that Node pdf.js can replace LibreOffice; Node pdf.js only handles
PDF-to-PNG after a PDF already exists.
This requirement also applies when macOS Quick Look succeeds, because Quick
Look is only a lightweight fallback and does not provide full per-slide QA.

## Office Raccoon Command Safety

The permission engine may block common shell habits. Avoid them.

- Do not write QA logs to `/tmp`, `/dev/null`, `/var/tmp`, or absolute output paths.
- Do not use shell redirects for QA output. The permission engine can block
  redirects before it proves whether the path is safe, especially for absolute
  paths. Instead, run helpers that write files directly or pass explicit output
  arguments such as `--out rendered`, `--out qa/diff`, or
  `output_path: "qa/visual_review.md"`.
- Do not use inline heredocs such as `python3 - <<'PY'`.
- Do not chain a long command that mixes `unzip`, `cat`, `tail`, and inline Python.
- Do not call Node `execFileSync()` with a full shell command string such as
  `execFileSync("unzip -l deck.pptx")`; Node treats the whole string as the
  executable name. Use `execFileSync("unzip", ["-l", "deck.pptx"])` or the
  provided Python helper scripts.
- Do not manually probe Quick Look with `qlmanage -h >/dev/null`; run
  `scripts/render_pptx.py` and let it decide whether Quick Look is available.
- Prefer the provided helper scripts. If custom logic is needed, create a short
  `.py` or `.js` helper file inside the workspace, run it, and let that helper
  write outputs to paths such as `qa/package_check.txt`,
  `qa/text_extract.txt`, or `rendered/`.

For package tests, prefer Python `zipfile` or Node zip readers over extracting
the deck to a temporary directory.

## Deliverable Package Hygiene

Before final handoff, inspect the output folder.

- Remove `.DS_Store`, editor caches, temporary scratch scripts, failed downloads,
  and unreferenced intermediate files.
- Remove or replace empty QA artifacts such as 0-byte `.json`, `.txt`, or `.md`
  files.
- Keep the final deck, source file(s), rendered previews, and final QA reports.
  Intermediate batch visual reports are okay only when the final
  `qa/visual_review.md` references them and no contradiction remains.
- If README or final answer says `PASS`, make sure the latest authoritative QA
  file also says `PASS` and names the images actually reviewed.

## Reporting Format

Use short sections. Put each result on its own line and leave a blank line
between progress blocks; do not concatenate all QA steps into one paragraph.

1. `Created`: output `.pptx` path.
2. `Source`: generator script and asset paths.
3. `QA`: package validation, text extraction, placeholder scan, rendering, visual inspection.
4. `Fixes`: issues found and corrected.
5. `Limitations`: blocked renderers, blocked image comparison, Quick Look-only checks, missing fonts, or unsupported objects.
