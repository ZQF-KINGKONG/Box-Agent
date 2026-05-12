# HTML-First Editable Decks

Use this workflow for newly created decks by default unless the user provides an
existing PowerPoint template to preserve or explicitly requires native PowerPoint
charts/tables. New decks should be authored as fixed-size HTML first, then
exported to editable PPTX with `scripts/html_to_editable_pptx.js`, which loads
the skill-bundled `scripts/dom-to-pptx.bundle.js`.

If `dom-to-pptx` export is blocked because no browser host is available, deliver
`deck.html`, mark editable PPTX export as `BLOCKED`, and tell the user how to
install/download or open the browser dependency instead of producing a weaker
deck through another generator. A host app's Electron renderer can provide the
browser environment; an agent child process still needs a bridge or Playwright.

Do not use `python-pptx` or `from pptx import Presentation` to create the final
PPTX for a new deck. Python may be used for data preparation and QA helpers, but
the deck itself should be created from `deck.html` through the editable
DOM-to-PPTX exporter.

## Contract

- Build a fixed-size HTML slide deck first.
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

Before export, run the HTML structural self-check with the editable compatibility
profile:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx/scripts/html_self_check.js deck.html --dom-to-pptx --report qa/html_self_check.json
```

Then export:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx/scripts/html_to_editable_pptx.js deck.html output.pptx --out slides
```

The export script runs self-check again, writes `qa/html_self_check.json`,
creates `slides/slide-*.png` preview images for visual QA, loads
`scripts/dom-to-pptx.bundle.js`, and writes `output.pptx`.

Do not install the npm `dom-to-pptx` package for this workflow. The editable
export must use this skill's bundled `scripts/dom-to-pptx.bundle.js`, which may
contain local fixes that are not in the published package.

If the current process has no browser host and Playwright/Chromium cannot be
installed, do not switch to an image-only PPTX fallback. Keep the finished
`deck.html` as the deliverable and report:

```text
Editable PPTX export: BLOCKED (missing browser host)
Install Playwright: ${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" playwright
Download Chromium: "$HOME/Library/Application Support/office-raccoon/node_modules/.bin/playwright" install chromium
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
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx/scripts/make_vision_inputs.js slides --out qa/vision_inputs
```

When `vision_review` is available, call it with every individual
`qa/vision_inputs/slide-*.jpg` file and set `output_path` to the deck folder's
`qa/visual_review.md`. A contact sheet may be added as overview material, but it
is not proof that review happened.

After the PPTX is created, run package validation, text extraction, placeholder
scan, render, and compare rendered PPTX images against source previews when
possible:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx/scripts/compare_slide_images.js slides rendered --out qa/diff
```

This comparison checks DOM-to-PPTX drift: missing slides, wrong order, scaling
changes, crop, text reflow, missing gradients, changed SVGs, wrong z-order, or
image mask differences. It is not the same as visual quality judgment; still
inspect the source previews and rendered PPTX images with an image-capable tool.

## When Not To Use

Use native PptxGenJS instead when:

- the user explicitly confirms direct native PPT generation
- the user provides a `.pptx` template to preserve
- the deck needs native editable PowerPoint charts or tables
- the recipient must use PowerPoint-native chart/table editing
- the task is a narrow edit to an existing deck rather than a new deck
- accessibility or template preservation is more important than HTML-authored
  layout

For a new deck, these exceptions require user confirmation before native
implementation unless the user already provided a template to preserve.
