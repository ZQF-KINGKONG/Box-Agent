# HTML-First Visual Decks

Use this workflow for new polished decks unless the user explicitly requires
editable PowerPoint text, native charts, or a provided PowerPoint template.

Choose this mode for from-scratch decks where visual quality, layout fidelity,
and browser-rendered QA matter more than editing visible text inside PowerPoint.
It is the default for beautiful/polished decks, editorial storytelling,
infographics, dashboards, maps, screenshots, custom charts, and immersive
topic-specific designs.

## Contract

- Build a fixed-size HTML slide deck first.
- Render every slide to PNG with an available browser renderer. Prefer the
  host-provided Playwright MCP or Browser tool when available; otherwise use
  the local Node Playwright fallback script.
- Inspect the PNGs for visual quality with an image-capable viewer/model before
  creating the PPTX. Screenshot generation alone is not visual QA.
- Create the PPTX by placing each rendered PNG as a full-slide image.
- Preserve the source HTML and write searchable text metadata into the PPTX
  when possible.
- Add a visible, consistent page number to every non-cover slide. Use one
  placement across the deck, preferably top-right or bottom-right, and keep the
  total count correct after adding/removing slides.

This produces a visually stable deck. Text in the PPTX is not directly editable
because the visible slide is a screenshot. The user edits the HTML source and
exports again.

## File Layout

Create these files beside the output deck:

```text
deck.html
slides/
  slide-01.png
  slide-02.png
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
      width: 1280px;
      height: 720px;
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

## Render And Export

Before screenshot capture, run the HTML structural self-check:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx2/scripts/html_self_check.js deck.html
```

This catches DOM/CSS bugs that are visible from computed layout before visual
comparison, such as progress bars whose `.fill` element is still `display:inline`,
zero-size chart elements, text overflow, missing images, or content outside the
slide bounds. Fix self-check failures before taking screenshots.

If Playwright MCP/Browser screenshots are available, use them to capture each
`.slide` element or each route/page state into `slides/slide-01.png`,
`slides/slide-02.png`, and so on. Browser tools such as `browser_navigate`,
`browser_snapshot`, and `browser_take_screenshot` count as this preferred path.
Then package the screenshots:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx2/scripts/images_to_pptx.js output.pptx slides/slide-01.png slides/slide-02.png
```

If no browser MCP/tool is available, run the local Node fallback:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx2/scripts/html_to_pptx.js deck.html output.pptx --out slides
```

The fallback script uses Playwright to capture each `.slide` element and
PptxGenJS to create a widescreen PPTX with each screenshot as a full-slide
image. It also runs the same HTML self-check before screenshot/export and stops
early on layout failures.

If PptxGenJS is missing in Office Raccoon, install it into the managed app
support prefix, not globally:

```bash
${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" pptxgenjs
```

Install the `playwright` npm package only when the local Node fallback is needed
and no Playwright MCP/Browser screenshot path is available. Never install Node
dependencies into the deliverable project folder; use the managed Office Raccoon
app support prefix for reusable dependencies.

## Visual QA

HTML self-check is not a replacement for visual QA. It is the first gate.
After it passes, still inspect the screenshot pixels.

Inspect the generated `slides/slide-*.png` files before final PPTX delivery.
First create a contact sheet for overview:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx2/scripts/make_contact_sheet.js slides --out qa/vision-contact-sheet.png
```

The contact sheet only prepares visual review. It is not proof that review
happened. When `vision_review` is available, call it with every individual
`slides/slide-*.png` file and set `output_path` to the deck folder's
`qa/visual_review.md`. Include the contact sheet only as an additional overview
image if useful.

Open or attach every PNG to an image-capable review tool and write a short
per-slide verdict before packaging the final deck. Do not treat file existence,
image dimensions, successful screenshot capture, OCR, histogram checks, or pixel
diff as visual inspection.
Check:

- blank or near-blank slides
- text clipping or overflow
- blurry or unreadable text
- overlapping labels, cards, charts, legends, or icons
- low contrast
- missing images
- missing charts, maps, screenshots, or icons
- bad crop or scaling
- inconsistent margins
- content hidden outside the 16:9 slide
- missing or inconsistent page numbers
- generic placeholder silhouettes for named people

If any issue is found, edit the HTML and re-render the affected PNGs before
running `images_to_pptx.js`. If no image-capable review tool is available,
report `Visual inspection: BLOCKED` and do not claim visual QA passed.

After the PPTX is created, still run package validation, text extraction, and
placeholder scan. When PPTX-rendered slide images are available, compare the
source screenshots against the rendered PPTX images:

```bash
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx2/scripts/compare_slide_images.js slides rendered --out qa/diff
```

This image comparison checks export fidelity: whether the PPTX render still
matches the HTML source screenshots, without missing slides, order changes,
scaling drift, crop, or altered pixels. It is not the same as visual quality
judgment; still inspect the source screenshots with an image-capable tool.

## When Not To Use

Use native PptxGenJS instead when:

- the user asks for editable PowerPoint text or shapes
- the user provides a `.pptx` template to preserve
- the deck needs native editable charts or tables
- the recipient is expected to make manual edits inside PowerPoint
- accessibility/editability is more important than pixel-perfect visual design
