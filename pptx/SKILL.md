---
name: pptx2
description: Create, inspect, edit, validate, render, and QA PowerPoint .pptx files. Use when the user mentions PowerPoint, PPT, PPTX, slide deck, presentation, template slides, speaker notes, slide images, or asks to read or modify a .pptx artifact.
compatibility: Designed for OpenAI/Codex agents with local filesystem and shell access on macOS, Linux, or Windows. Creation uses PptxGenJS and may install it into the managed Office Raccoon Node environment when missing. QA checks may use Python 3, LibreOffice, Poppler, Node pdf.js, macOS Quick Look, and python-pptx.
---

# PPTX Skill

Use this skill whenever a PowerPoint deck is an input, output, or deliverable. Prefer the smallest workflow that proves the file is correct: inspect existing decks before editing, use HTML-first visual generation for new polished decks by default, and always render visual changes before claiming completion.

## Operating Principles

- Treat `.pptx` as an Office Open XML zip package. Use libraries for normal creation, and inspect package XML only when templates, relationships, or corrupted files require it.
- Preserve the user's template, branding, slide size, theme, master layouts, notes, and media unless asked to change them.
- Do not hand-wave visual quality. Render slides to images or PDF and inspect the actual result for overflow, clipping, bad spacing, missing media, and placeholder leftovers.
- Screenshot generation is not visual QA. After screenshots or rendered images exist, open or attach every slide image to an image-capable viewer/model and judge the visible pixels. File count, dimensions, package XML, and text extraction cannot prove visual quality.
- Keep the deck source reproducible. When creating a new deck, put the generation script beside the output unless the user asked only for a one-off file.
- Maintain basic deck hygiene: every non-cover slide should have a visible page number such as `02 / 08`, consistently placed, usually top-right or bottom-right. Closing/summary slides still need page numbers unless the user asks for a no-folio style.
- Use host-provided parallel agents only for independent slide-level review or edits. Keep package-level operations, slide ordering, and final validation in one place.
- Do not install Homebrew, system packages, or global dependencies without explicit user approval. Installing npm or pip packages into the managed Office Raccoon Node/Python environment is allowed when needed for this PPTX workflow.
- Do not silently downgrade the generator. For new visual decks, default to HTML-first generation and export to PPTX with PptxGenJS full-slide images. Use native editable PptxGenJS only when the user asks for editable PowerPoint text/shapes, native charts, or template preservation. If required dependencies are unavailable, install them into the managed Office Raccoon Node runtime when possible; otherwise report the missing dependency instead of switching to `python-pptx`, unless the user explicitly approves the fallback.

## Quick Start

| Task | First action |
|---|---|
| Read deck content | `${BOX_AGENT_PYTHON:-python3} scripts/extract_text.py input.pptx` |
| Inspect package health | `${BOX_AGENT_PYTHON:-python3} scripts/validate_pptx_package.py input.pptx` |
| Visual overview | `${BOX_AGENT_PYTHON:-python3} scripts/render_pptx.py input.pptx --out rendered` |
| Create polished deck | Read `references/html-first.md` |
| Check HTML deck layout | `${BOX_AGENT_NODE:-node} scripts/html_self_check.js deck.html` |
| Compare HTML screenshots to PPTX render | `${BOX_AGENT_NODE:-node} scripts/compare_slide_images.js slides rendered --out qa/diff` |
| Prepare visual review inputs | `${BOX_AGENT_NODE:-node} scripts/make_contact_sheet.js slides --out qa/vision-contact-sheet.png` |
| Run visual review | Call `vision_review` with every `slides/slide-*.png` or `rendered/slide-*.png`; write `qa/visual_review.md` |
| Create editable deck | Read `references/pptxgenjs.md` |
| Edit a template deeply | Read `references/ooxml-editing.md` |
| QA checklist | Read `references/qa.md` |
| Check local dependencies | `${BOX_AGENT_PYTHON:-python3} scripts/setup_check.py` |

For QA, the render command is mandatory even when `soffice` appears missing;
do not replace it with a manual `which soffice` check.

## Office Raccoon Runtime Notes

Office Raccoon may expose only this `SKILL.md` through `get_skill`, so keep critical generation constraints in this file, not only in references.

- Use `$BOX_AGENT_NODE`, `$BOX_AGENT_NPM`, and `$BOX_AGENT_PYTHON` when they are available; otherwise use `node`, `npm`, and `python3`.
- Check PptxGenJS with `${BOX_AGENT_NODE:-node} -e "require.resolve('pptxgenjs')"`.
- For HTML-first decks, prefer a host-provided Playwright MCP or Browser screenshot tool if available. Use the local Node Playwright fallback only when no screenshot tool is available.
- Before taking screenshots for an HTML-first deck, run `scripts/html_self_check.js deck.html` or use `scripts/html_to_pptx.js`, which runs that self-check internally. Fix self-check failures before screenshot or export.
- If browser tools such as `browser_navigate`, `browser_snapshot`, or `browser_take_screenshot` are available, they count as the preferred screenshot path. Do not install the `playwright` npm package for screenshotting in that case.
- If PptxGenJS is missing in Office Raccoon, install into the stable app support prefix, for example `${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" pptxgenjs` on macOS. Do not install into a per-session `mnt/<session-id>` directory unless the user only needs a temporary one-session dependency.
- If Playwright npm is missing, install it only when the local Node fallback `scripts/html_to_pptx.js` is needed and no host browser screenshot tool is available. If the host Playwright MCP/Browser can capture screenshots, use `scripts/images_to_pptx.js` and do not install Playwright npm.
- Do not run `npm install` inside the deliverable project folder. Install reusable Node dependencies only into the managed Office Raccoon app support prefix, for example `${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" pptxgenjs`.
- PDF to PNG rendering uses Poppler `pdftoppm` when available. If Poppler is missing, `scripts/render_pptx.py` falls back to Node pdf.js and may install `pdfjs-dist` plus `@napi-rs/canvas` into the same managed Office Raccoon Node prefix.
- Avoid shell patterns commonly blocked by the permission engine: `rm -rf`, redirects to `/dev/null`, redirects to absolute paths, and inline heredoc scripts when a normal script file will do.
- In Office Raccoon, keep temporary logs, previews, generated images, and QA outputs inside the current workspace or the requested output folder. Do not write to `/tmp`, `/var/tmp`, or other absolute temp locations.
- Never redirect QA output to `/tmp` or another absolute path. Write reports under the current workspace, for example `qa/package_check.txt` or `rendered/`.
- Prefer writing a short `.js` or `.py` helper file with the file tool, then running it. Do not use inline heredocs such as `python - <<'PY'`. For package checks, prefer Python `zipfile` or Node `adm-zip` style reads over extracting a temp directory and deleting it.
- In Node QA helpers, do not call `execFileSync()` with a full shell command string. Use `execFileSync("unzip", ["-l", pptxPath])`, `execFileSync("unzip", ["-p", pptxPath, partPath])`, or use `execSync()` only when shell syntax is truly required.
- Prefer the provided Python QA helpers over ad-hoc `unzip` commands. If a Node helper is needed, validate PPTX package parts by invoking binaries with argument arrays or by using a zip library.
- Do not use `sed` for directory listing, script discovery, or output truncation. macOS/BSD sed and GNU sed differ, and the permission parser can misread sed expressions that contain `/.../` as absolute paths. Use `find path -maxdepth 2 -type f | sort | head -n 100`, `ls -la path`, `rg --files path`, or a small Node/Python helper instead.
- Do not manually probe Quick Look with commands such as `qlmanage -h >/dev/null`. Run `scripts/render_pptx.py`; it owns Quick Look discovery and fallback behavior.
- For visual QA, do not stop at "screenshots generated". Use the `vision_review` tool when it is available, pass the actual PNG/JPG slide images as image inputs, and require a short per-slide verdict such as `slide-03: PASS` or `slide-03: ISSUE text clipped at footer`.
- Prefer calling `vision_review` with every individual `slides/slide-*.png` or `rendered/slide-*.png`. A contact sheet may be included as an overview, but it is not a substitute for per-slide inputs when there are 20 or fewer slides.
- If `vision_review` fails with request-size errors, batch images in groups of 1-3 slides or generate lower-resolution review copies under `qa/vision_inputs/`; do not fall back to contact-sheet-only PASS.
- For visual QA, generate a contact sheet with `scripts/make_contact_sheet.js slides --out qa/vision-contact-sheet.png` as review material only. If `vision_review` is unavailable or fails, report `Visual inspection: BLOCKED` instead of claiming PASS.
- To "look at images", call `vision_review` or another real image-capable tool with the image files. Passing local image paths as normal text, shell-only checks, dimensions, histograms, OCR/text extraction, and pixel diff do not count as looking at the image.
- The contact sheet is not the verdict. After `vision_review`, write `qa/visual_review.md` in the deck output folder with `Reviewed:` image paths and per-slide PASS/ISSUE results. If `qa/visual_review.md` is missing, report `Visual inspection: BLOCKED`.
- For HTML-first decks, if both source screenshots and PPTX-rendered images exist, run `scripts/compare_slide_images.js slides rendered --out qa/diff`. This checks export fidelity and is separate from human/vision visual inspection.
- During execution, do not stream one long prose paragraph that narrates every action. Send one short status block per step, separated by a blank line. Keep each progress message to one or two sentences.
- When several steps have already happened, format them as a checklist with one result per line. Do not join setup, generation, QA, rendering, and limitations into one paragraph.
- If reporting several checks, use a compact checklist instead of a run-on paragraph.
- Office Raccoon may inject managed rendering tools through `BOX_AGENT_RENDER_RUNTIME`, `BOX_AGENT_SOFFICE`, and `BOX_AGENT_PDFTOPPM`. Use those paths when present. Do not download or install LibreOffice/Poppler yourself unless the user explicitly asks.

## Creation Workflow

Use this path when there is no existing template or the user wants a fresh deck.

1. Decide slide size, audience, visual tone, and data sources from the user request.
2. Choose mode:
   - `HTML-first visual` by default for polished decks, editorial layouts, rich visuals, and decks where exact appearance matters most.
   - `Native editable` only when the user asks for editable text/shapes/charts, a template must be preserved, or PowerPoint-native editing is the priority.
   - If both appearance and editability matter, ask which one is more important only when the request is ambiguous; otherwise choose from the decision table below and state the tradeoff briefly.
3. For HTML-first visual decks, read `references/html-first.md`, create `deck.html`, run HTML self-check, render `.slide` elements to PNG with Playwright MCP/Browser when available, call `vision_review` on every generated slide PNG, fix visible issues, then export with `scripts/images_to_pptx.js`. Use `scripts/html_to_pptx.js` only as a local Node fallback when screenshot tools are unavailable.
4. For native editable decks, read `references/pptxgenjs.md`, create a PptxGenJS script, and keep dimensions in inches.
5. Build complete slides with real content, charts, images, alt text or notes where practical, and consistent spacing.
6. Generate the `.pptx`.
7. Run the required QA gate below. Do not mark QA complete after only checking file existence, slide count, or zip integrity.
8. Inspect rendered slides or HTML-first screenshot slides and fix visual issues before final delivery.

Read `references/html-first.md` before writing a new polished deck. Read `references/pptxgenjs.md` before writing a native editable deck.

### Mode Tradeoff

- HTML-first visual PPTX: visible slide content is full-slide images, so visual quality and QA are stable. Text is not directly editable in PowerPoint. Keep the HTML source as the editable source of truth and include searchable notes/hidden text in the PPTX.
- Native editable PPTX: text and shapes are editable in PowerPoint, but layout fidelity is harder to test and depends more on PowerPoint/LibreOffice rendering.

### Mode Decision Table

Use `HTML-first visual` when:

- The user asks for a polished, beautiful, editorial, poster-like, dashboard-like, or highly designed deck.
- The deck is generated from scratch and no existing PowerPoint template must be preserved.
- Exact visual layout matters more than editing text directly inside PowerPoint.
- The deck uses complex gradients, layered cards, precise typography, icon compositions, screenshots, custom charts, maps, or infographic-style pages.
- The output is mainly for presenting, sharing, exporting, or reading, and the included `deck.html` can serve as the editable source.
- Visual QA needs to be deterministic through browser screenshots and image comparison.

Use `Native editable` PptxGenJS when:

- The user explicitly asks for editable text, shapes, tables, or charts in PowerPoint.
- The user provides a `.pptx` template, master, theme, brand deck, or existing slide layout to preserve.
- The recipient is expected to manually revise slide text, move objects, edit charts, or reuse slides in PowerPoint.
- The deliverable must use native PowerPoint charts/tables for later data edits.
- The task is a narrow edit to an existing deck rather than a new visual design.
- Accessibility/editability is more important than pixel-perfect appearance.

Do not choose mode based on convenience. Do not switch from HTML-first to
`python-pptx` or native PptxGenJS just because screenshot/render QA is harder.
Install or use the managed dependencies when allowed, or report the blocker.

### PptxGenJS Runtime Pitfalls

- Do not assume static exports such as `pptxgen.ShapeType` exist. In PptxGenJS 4.x, shape constants are often available on the presentation instance, such as `pptx.ShapeType` or `pptx._shapeType`.
- Do not assume optional methods such as `pptx.defineSection()` exist. If a method is not documented for the installed runtime or `typeof pptx.defineSection !== "function"`, omit it instead of blocking deck generation.
- Use a compatibility helper before adding shapes:

```javascript
const pptxgen = require("pptxgenjs");
const pptx = new pptxgen();
const ShapeType = pptx.ShapeType || pptx._shapeType;
if (!ShapeType) throw new Error("PptxGenJS shape constants are unavailable");
```

- Do not invent shape names. Validate custom shape constants before use, for example `ShapeType.hexagon`, `ShapeType.diamond`, `ShapeType.pentagon`, `ShapeType.chevron`, `ShapeType.arc`, `ShapeType.line`, `ShapeType.rect`, and `ShapeType.ellipse`.
- If a desired shape such as `shield` is unavailable, compose it from supported primitives instead of calling `addShape` with an unsupported value.
- If `addShape` throws `Missing/Invalid shape parameter`, inspect the runtime shape constants and replace the unsupported shape before continuing.
- Never pass an empty string as a color, fill, line, transparency, or theme value. PptxGenJS may silently coerce `""` to black. Use a valid 6-digit hex color without `#`, a documented scheme color, or omit the property entirely.
- Do not build people, faces, portraits, players, celebrities, or realistic human figures from PowerPoint shapes. Shape-composed people look poor and are hard to QA. Use a real licensed image, a generated bitmap illustration, a cropped silhouette, a jersey/nameplate/stat card, or an abstract emblem instead.

## Template Editing Workflow

Use this path when the user provides an existing `.pptx` or asks to adapt a branded deck.

1. Make a working copy of the original deck.
2. Extract text with `scripts/extract_text.py` and render thumbnails with `scripts/render_pptx.py`.
3. Map the requested content to existing layouts. Avoid using one layout for every slide when the template offers better options.
4. For simple text/image replacement in an existing deck, `python-pptx` is acceptable when it preserves the requested template behavior. Do not use it as a replacement generator for new polished decks without explicit user approval.
5. For structural edits that libraries cannot express, inspect OOXML package parts and relationships. Read `references/ooxml-editing.md` first.
6. Validate package structure, render, inspect, and iterate.

## Dependency Policy

- `setup_check.py` is diagnostic only. Its output is permission to install missing npm/pip packages only inside the managed Office Raccoon Node/Python environment, not system packages or global dependencies.
- If `pptxgenjs` is missing during creation, say exactly that and install into the managed Office Raccoon Node environment when possible. Use an already configured local project dependency if one exists.
- For full visual QA on macOS, Linux, or Windows, use LibreOffice or `soffice` to convert PPTX to PDF, then render PDF pages with Poppler `pdftoppm` when available. If Poppler is unavailable, use the Node pdf.js fallback installed in the managed Office Raccoon Node environment.
- In Office Raccoon, managed render runtimes are discovered through `BOX_AGENT_SOFFICE`, `BOX_AGENT_PDFTOPPM`, and `BOX_AGENT_RENDER_RUNTIME`; these take priority over system binaries.
- If `soffice` is missing during QA, still run package validation and text extraction. On macOS, use Quick Look thumbnail rendering as a lightweight fallback. On Windows, do not automate Microsoft PowerPoint export unless the user explicitly approves operating the app.
- `python-pptx` may be used for inspection, text extraction helpers, smoke tests, or narrow template edits. It is not the default creation engine for new high-quality decks.

## Required QA

Before final response for any created or modified deck, read `references/qa.md` and complete its checklist. Keep the detailed QA rules in that reference file so this main skill stays concise.

Hard gates that must remain visible here:

- Run package validation, text extraction, placeholder scan, render, and visual inspection.
- Confirm slide count, slide order, and visible page numbers. Page numbers must match the actual order, for example `03 / 08` on slide 3 of an 8-slide deck. Cover slides may omit a number only if the rest start at `02 / NN`.
- For HTML-first decks, run HTML self-check before screenshots. Treat it as the first QA gate, but not as a substitute for visual inspection.
- For HTML-first decks, compare source screenshots to PPTX-rendered images when rendering is available. Treat a non-empty PNG check as insufficient.
- Render with `${BOX_AGENT_PYTHON:-python3} scripts/render_pptx.py output.pptx --out rendered`; do not replace this with `command -v soffice`, `unzip -t`, slide count, or a single title extraction.
- Do not pre-check `soffice` and skip rendering yourself. Always call `render_pptx.py`; that script owns renderer discovery, Quick Look fallback, and user-facing missing-LibreOffice guidance.
- Do not pass `--format png`; PNG is the default and some host safety filters may treat `format` as a dangerous disk command.
- In Office Raccoon, call helper scripts by absolute skill path if needed, for example `${BOX_AGENT_PYTHON:-python3} /Users/malin1/.box-agent/skills/pptx2/scripts/render_pptx.py output.pptx --out rendered`.
- Treat OOXML checks as structural QA only. They cannot replace rendering or visual inspection.
- Treat screenshot existence as capture QA only. It cannot replace visual inspection of the image content.
- For visual inspection, call `vision_review` with every produced slide image whenever the tool is available. Review blank/near-blank slides, low resolution, blurry text, clipped text, overlaps, bad crop, hidden content, poor contrast, missing images/charts, and broken layout.
- Include the reviewed individual slide image paths in the QA report. A contact sheet path alone is acceptable only as an additional overview or when individual images are unavailable and the report clearly says what was blocked.
- Require `qa/visual_review.md` for completed visual QA. A generated contact sheet alone is not evidence that the images were inspected.
- Keep one final visual QA verdict at `qa/visual_review.md`. If you create batch reports such as `visual_review_01_03.md`, merge them into the final report and ensure no stale ISSUE/PASS report contradicts the final answer.
- Do not leave empty QA artifacts. If an inspect/report file is 0 bytes or failed to generate, rerun the check or delete it and report the check as `BLOCKED`.
- If no rendered slide images or preview images are produced, report visual QA as `BLOCKED` and name the missing renderer or conversion failure.
- If Quick Look is used because `soffice` is missing, report that LibreOffice is required for full rendering and include `https://www.libreoffice.org/download/download-libreoffice/`.
- Keep QA as a separate todo item with visible sub-results.

## Visual Standards

- Build the real deck, not a title page with generic bullets.
- Use a topic-specific palette with enough contrast. Avoid default-blue decks unless the brand or subject calls for it.
- Every slide should have a clear visual role: title, section divider, argument, comparison, timeline, data, summary, or appendix.
- Keep body text short enough to fit. Split dense content instead of shrinking text until it becomes unreadable.
- Prefer real charts, diagrams, screenshots, product images, tables, icons, or intentional vector artwork over decorative filler.
- For people-heavy topics, use real images, generated bitmap illustrations, silhouettes, jersey/nameplate treatments, timelines, maps, or stat cards. Do not attempt realistic human likenesses with circles, arcs, polygons, and lines.
- Avoid generic placeholder silhouettes for named people. If a real or generated portrait is unavailable, use a deliberate non-portrait treatment such as jersey number, nameplate, career timeline, quote card, heatmap, or emblem.
- Use consistent margins and alignment. Leave enough space around titles, footers, and citations.
- Clean deliverable folders before final handoff: remove `.DS_Store`, failed scratch files, empty reports, and duplicate stale QA files unless they are explicitly referenced as intermediate evidence.

## OpenAI Tooling Notes

- This skill is an Agent Skills directory, not a Responses API tool schema.
- If exposing it through the OpenAI API, wrap the workflows as explicit tools such as `inspect_pptx`, `render_pptx`, `create_pptx_from_spec`, and `edit_pptx_from_plan`.
- Keep tool parameters narrow and file-based: input file path, output file path, slide range, edit plan path, render directory, and validation mode.
- Do not assume a model can see a `.pptx` directly. Convert to text and rendered images before asking a model to reason about deck content or layout.

## Deliverable Contract

When done, report in short step-by-step form. Do not return one dense paragraph.

Use this structure:

1. `Created`: the created or modified `.pptx` path.
2. `Source`: any generation script or supporting files created.
3. `QA`: one line each for package validation, text extraction, placeholder scan, rendering, image comparison, and visual inspection.
4. `Fixes`: visual or technical issues found and corrected.
5. `Limitations`: skipped visual QA, Quick Look-only rendering, missing fonts, unsupported embedded objects, unavailable dependencies, or any remaining risk.

If any QA step is blocked, say `BLOCKED` for that step instead of folding it into a success sentence.
