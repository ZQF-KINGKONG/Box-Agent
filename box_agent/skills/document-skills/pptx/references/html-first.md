# HTML-First Editable Decks

Use this workflow for newly created decks by default unless the user provides an
existing PowerPoint template to preserve or explicitly requires native PowerPoint
charts/tables. New decks should be authored as fixed-size HTML first, then
exported to editable PPTX with `scripts/html_to_editable_pptx.js`, which loads
the skill-bundled `scripts/dom-to-pptx.bundle.js`.

Before authoring a new deck when final `.pptx` delivery is expected, preflight
the browser export environment with `scripts/check_html_export_env.js` or the
host app's renderer bridge. A host app's Electron renderer can provide the
browser environment; an agent child process still needs a bridge or Playwright.
If Playwright/Chromium and host renderer are missing, tell the user this blocks
HTML-to-editable-PPTX export and ask them to choose:

- `HTML`: deliver `deck.html` now; editable PPTX export can run later after the
  browser dependency or host renderer is available.
- `PPTX`: switch to native PptxGenJS and create a directly editable PPTX, with
  different HTML/CSS fidelity tradeoffs.

HTML self-check failures, text-slack warnings, Playwright errors, and render
drift are not reasons to switch to PptxGenJS. Fix the HTML source and rerun this
workflow, or report the specific blocker. Use native PptxGenJS for a new deck
only after explicit user confirmation or when the user supplied a template /
required native PowerPoint charts or tables.

Do not bypass the HTML self-check. Never write a custom `export_skipcheck.js`,
call `dom-to-pptx.bundle.js` directly to skip `scripts/html_self_check.js`, or
patch the exporter to ignore a failed report. If `qa/html_self_check.json` has
`"ok": false`, fix `deck.html` and rerun `scripts/html_to_editable_pptx.js`.
Run at most 3 focused self-check repair rounds. After that, if only a small
number of known, visually acceptable issues remain, continue only through the
official exporter with `--allow-self-check-issues`, then report the unresolved
issue count and complete render/visual QA. If severe blocking issues remain,
report `Editable PPTX export: BLOCKED (HTML self-check failed)`.

Do not use `python-pptx` or `from pptx import Presentation` to create the final
PPTX for a new deck. Python may be used for data preparation and QA helpers, but
the deck itself should be created from `deck.html` through the editable
DOM-to-PPTX exporter.

## Contract

- Build a fixed-size HTML slide deck first.
- If the requested deliverable is final `.pptx`, preflight the browser export
  environment before writing the full HTML deck.
- Before writing HTML, decide whether `references/outline.md` calls for a
  separate `outline.json`. Use one for broad or structurally unclear prompts;
  skip it when the user's prompt is already a sufficient page-level outline.
  Never invent extra claims, data, or strategy just to make an outline look
  deeper.
- Use one `.slide` element per page.
- Run the stricter HTML self-check profile with `--dom-to-pptx`.
- Export with `scripts/html_to_editable_pptx.js`.
- Keep the source HTML and generated preview images beside the output deck for
  QA and future edits.
- Render the exported PPTX and inspect for DOM-to-PPTX drift before delivery.
- Add a visible, consistent page number to every non-cover slide. Use one
  placement across the deck, preferably top-right or bottom-right, and keep the
  total count correct after adding/removing slides.

This produces an editable PowerPoint deck from HTML-authored slides. The output
is more editable than an image-only deck, but CSS-to-PPTX mapping can drift, so
render QA is mandatory.

## File Layout

Create these files beside the output deck:

```text
deck.html
slides/
  slide-01.png
  slide-02.png
qa/
  html_self_check.json
  visual_review.md
output.pptx
```

Use one `.slide` element per page:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body { margin: 0; background: #111; }
    .slide {
      width: 1920px;
      height: 1080px;
      position: relative;
      overflow: hidden;
      page-break-after: always;
      font-family: Aptos, Inter, Arial, sans-serif;
    }
  </style>
</head>
<body>
  <section class="slide" data-title="Title">...</section>
  <section class="slide" data-title="Agenda">...</section>
</body>
</html>
```

## Export

When commands need the skill directory, use the active installed skill path
rather than a machine-specific absolute path. In Office Raccoon this is usually
`$HOME/.box-agent/skills/pptx`, but a host may provide a different path:

```bash
PPTX_SKILL_DIR="${BOX_AGENT_PPTX_SKILL_DIR:-$HOME/.box-agent/skills/pptx}"
OFFICE_RACCOON_NODE_PREFIX="${BOX_AGENT_NODE_PREFIX:-${BOX_AGENT_RUNTIME_PREFIX:-$HOME/Library/Application Support/office-raccoon}}"
```

Before writing the full deck, check whether CLI HTML-to-editable-PPTX export can
run:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/check_html_export_env.js"
```

If this reports missing Playwright/Chromium and no host renderer is available,
do not keep going silently. Ask the user to choose `HTML` or `PPTX` using the
tradeoff above. Continue with this HTML-first workflow only if the preflight
passes or the user chooses `HTML`.

Before export, run the HTML structural self-check with the editable compatibility
profile:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_self_check.js" deck.html --dom-to-pptx --report qa/html_self_check.json
```

If the command exits non-zero, inspect `qa/html_self_check.json` before deciding
what failed. Summarize concrete failing slides/selectors and fix `deck.html`.
Do not move to another generator because the report contains text slack,
overflow, or compatibility failures.
Do not bypass the report by writing a custom exporter. If the deck still has a
small number of accepted issues after 3 repair rounds, use the official export
flag instead:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_to_editable_pptx.js" deck.html output.pptx --out slides --allow-self-check-issues
```

Then export:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_to_editable_pptx.js" deck.html output.pptx --out slides
```

The export script runs self-check again, writes `qa/html_self_check.json`,
creates `slides/slide-*.png` preview images for visual QA, loads
`scripts/dom-to-pptx.bundle.js`, and writes `output.pptx`.

Do not install the npm `dom-to-pptx` package for this workflow. The editable
export must use this skill's bundled `scripts/dom-to-pptx.bundle.js`, which may
contain local fixes that are not in the published package.

If the current process has no browser host and Playwright/Chromium cannot be
installed after the user chose HTML, keep the finished `deck.html` as the
deliverable and report:

```text
Editable PPTX export: BLOCKED (missing browser host)
Install Playwright: ${BOX_AGENT_NPM:-npm} install --prefix "$OFFICE_RACCOON_NODE_PREFIX" playwright
Download Chromium: "$OFFICE_RACCOON_NODE_PREFIX/node_modules/.bin/playwright" install chromium
```

If the host app exposes an Electron renderer conversion/import path, use that
host route instead of installing Playwright. Do not assume Electron main or a
Node child process has DOM layout APIs.

## Visual QA

HTML self-check is not a replacement for visual QA. It is the first gate. Keep
`qa/html_self_check.json` with the delivery artifacts. If that report is missing
or `"ok"` is not `true`, do not claim HTML self-check passed.

Inspect the generated `slides/slide-*.png` source previews before final PPTX
delivery. First create compressed review-size inputs:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/make_vision_inputs.js" slides --out qa/vision_inputs
```

When `vision_review` is available, call it with every individual
`qa/vision_inputs/slide-*.jpg` file and set `output_path` to the deck folder's
`qa/visual_review.md`. For decks with 10 or more slides, split the calls into
1-3 slide batches by default, then merge the batch verdicts into the final
`qa/visual_review.md`. A contact sheet may be added as overview material, but
it is not proof that review happened.

For decks with 20 or fewer slides, visual QA must inspect every slide image. If
only representative slides were reviewed, label the result as a partial visual
spot check, not a full visual QA pass.

After the PPTX is created, run package validation, text extraction, placeholder
scan, render, and compare rendered PPTX images against source previews when
possible:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/compare_slide_images.js" slides rendered --out qa/diff
```

This comparison checks DOM-to-PPTX drift: missing slides, wrong order, scaling
changes, crop, text reflow, missing gradients, changed SVGs, wrong z-order, or
image mask differences. It is not the same as visual quality judgment; still
inspect the source previews and rendered PPTX images with an image-capable tool.

## When Not To Use

Use native PptxGenJS instead when:

- the user explicitly confirms direct native PPT generation
- the user chooses `PPTX` after the browser export preflight reports missing
  Playwright/Chromium and no host renderer
- the user provides a `.pptx` template to preserve
- the deck needs native editable PowerPoint charts or tables
- the recipient must use PowerPoint-native chart/table editing
- the task is a narrow edit to an existing deck rather than a new deck
- accessibility or template preservation is more important than HTML-authored
  layout

For a new deck, these exceptions require user confirmation before native
implementation unless the user already provided a template to preserve.
