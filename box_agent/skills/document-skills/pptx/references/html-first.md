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

Route-change and self-check bypass rules live in `SKILL.md`. This reference adds
HTML authoring details; do not use it to weaken the top-level workflow.

Do not use `python-pptx` or `from pptx import Presentation` to create the final
PPTX for a new deck. Python may be used for data preparation and QA helpers, but
the deck itself should be created from `deck.html` through the editable
DOM-to-PPTX exporter.

## Contract

- Build a fixed-size HTML slide deck first. Before adding slide content, set
  every `.slide` to exactly `width: 1920px; height: 1080px;`.
- If the requested deliverable is final `.pptx`, preflight the browser export
  environment before writing the full HTML deck.
- Before writing HTML, decide whether `references/outline.md` calls for a
  separate `outline.json`. Use one for broad or structurally unclear prompts;
  skip it when the user's prompt is already a sufficient page-level outline.
  Never invent extra claims, data, or strategy just to make an outline look
  deeper.
- Use one `.slide` element per page. Do not author at `1280px × 720px`,
  `1280px × 760px`, viewport-relative sizes, or scaled wrappers unless the user
  explicitly requested a nonstandard output size.
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
assets/
  generated/
    manifest.json
    slide-03-hero.png
slides/
  slide-01.png
  slide-02.png
qa/
  html_self_check.json
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

## Fragment Drafting

For decks with 6 or more slides, dense source material, or likely large HTML,
follow the fragment rules in `SKILL.md` before writing the final `deck.html`.
The merge command is:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/merge_html_fragments.js" \
  --css drafts/common.css \
  --out deck.html \
  --title "Deck title" \
  drafts/slides_01_04.html drafts/slides_05_08.html drafts/slides_09_12.html
```

## Generated Images

Plan generated images after the outline and before writing final slide HTML.
Use image generation for visuals that should be bitmap assets, such as hero
illustrations, product mockups, scene images, textures, photo-like backgrounds,
and people-heavy visuals that should not be built from PowerPoint shapes.

Do not generate images just to make a slide look busy, but do not be overly
conservative either. Every slide must get an explicit image decision in
`assets/generated/manifest.json`; use `generate` when a bitmap visual would
make the message faster to understand or more memorable than typography,
charts, icons, or HTML/CSS alone.

### Image Decision Rules

For each slide, choose exactly one primary visual lane:

- `generate`: bitmap visual asset from `generate_image`
- `use_existing`: supplied, licensed, screenshot, brand, product, person, or
  source-backed image
- `draw_in_html`: editable chart, diagram, timeline, icon cluster, map-like
  schematic, or shape composition
- `skip`: no image because text/data/editable composition is stronger

Generate an image when two or more of these are true:

- the user explicitly asks for an illustration, scene, poster, visual metaphor,
  generated background, or image-rich style
- a cover or divider needs a strong hero visual or atmospheric scene
- an abstract concept needs a visual anchor, such as AI workflow, future city,
  product experience, or system metaphor
- a realistic or semi-realistic object, product mockup, environment, or texture
  would be costly or awkward to build from shapes
- people-heavy or portrait-like content would look poor if built from
  PowerPoint/HTML primitives
- consistent style matters more than showing a real-world source image
- the slide is a single-message emotional, campaign, launch, vision, brand, or
  closing slide where visual memorability matters
- the visual can be placed as a side hero, framed card image, spot
  illustration, or controlled background without making the main text
  unreadable

Do not generate an image when:

- the slide is primarily data, table, KPI, roadmap, architecture, or process
  content that should stay editable and information-dense
- the image would be decorative filler and deleting it would not change the
  message
- a real product, real company, real location, real chart, screenshot, or named
  person must be accurate
- a native editable chart/table/diagram is the actual deliverable
- the generated visual would sit behind body text and reduce readability
- the slide can be stronger with typography, charts, icons, or simple vector
  composition

Use this practical scoring rule when unsure:

- `+2`: cover, divider, closing, poster, launch, campaign, or vision slide
- `+2`: user requested image-rich, illustration, poster, scene, visual metaphor,
  or generated background
- `+1`: abstract concept needs a metaphor or atmospheric anchor
- `+1`: realistic object, mockup, environment, texture, or people scene
- `+1`: bitmap can sit in a clear frame/hero area without covering body text
- `-2`: primary value is editable data, table, KPI, roadmap, architecture,
  timeline, process, or matrix
- `-2`: accuracy requires a real product, screenshot, chart, person, company,
  logo, or location
- `-1`: deleting the image would not weaken the message

Choose `generate` at score `2` or higher unless a negative accuracy/editability
rule applies. Choose `draw_in_html` for editable analytical visuals. Choose
`use_existing` for real/source-backed visuals. Choose `skip` only when the score
is low and the slide is stronger without a bitmap.

### Background vs Local Visual

Prefer local visual assets over full-slide backgrounds. A local visual asset can
be a right-side hero illustration, a card image, a scene crop, a mockup, a
texture tile, or a small conceptual image placed inside the layout.

Use a generated full-slide background only for:

- cover slides
- section dividers
- poster-like single-message slides
- event or campaign pages where the image is the primary message carrier

When using a generated background, reserve a text-safe area before writing the
prompt. The background must leave enough low-detail space for the title and key
copy, and the HTML should add a controlled overlay when needed. Do not use
complex generated backgrounds behind dense body text, data labels, charts, or
tables.

For content slides, prefer:

- no generated image
- a small or medium generated visual in a fixed frame
- an HTML/CSS diagram, chart, icon cluster, or timeline
- a subtle hand-authored texture or gradient rather than a generated background

### Image Plan Manifest

Before generating images, create or update `assets/generated/manifest.json`.
Use this shape:

```json
{
  "image_plan": [
    {
      "slide": "03",
      "decision": "generate",
      "kind": "hero_illustration",
      "reason": "abstract AI workflow concept needs a visual anchor",
      "placement": "right-side visual",
      "aspect_ratio": "16:9",
      "target_size": "2848x1600",
      "prompt": "Editorial business illustration of ...",
      "avoid": "text inside image, realistic named people, busy background",
      "output_path": "assets/generated/slide-03-hero.png",
      "alt_text": "Abstract AI workflow illustration"
    },
    {
      "slide": "05",
      "decision": "skip",
      "reason": "data chart should remain the primary visual"
    }
  ]
}
```

Allowed decisions:

- `generate`: call the available `generate_image` tool and save the result.
- `use_existing`: use a supplied, licensed, or source-backed image.
- `draw_in_html`: build the visual as editable HTML/CSS/SVG/chart elements.
- `skip`: no image is needed.
- `blocked`: image generation would be appropriate, but no image-generation
  tool or required input is available.

When calling `generate_image`, use `output_path` under `assets/generated/`, pass
the `size` parameter from the supported preset list below, and include
slide/purpose/kind metadata. Do not request arbitrary dimensions such as
`1600x1024`; choose the closest supported ratio and resolution, then crop or fit
the image in HTML/CSS when placing it on the 1920x1080 slide.

Supported generated-image sizes:

- 1:1 — `2048x2048`, `3072x3072`, `4096x4096`
- 3:4 — `1728x2304`, `2592x3456`, `3520x4704`
- 4:3 — `2304x1728`, `3456x2592`, `4704x3520`
- 16:9 — `2848x1600`, `4096x2304`, `5504x3040`
- 9:16 — `1600x2848`, `2304x4096`, `3040x5504`
- 3:2 — `2496x1664`, `3744x2496`, `4992x3328`
- 2:3 — `1664x2496`, `2496x3744`, `3328x4992`
- 21:9 — `3136x1344`, `4704x2016`, `6240x2656`

For a normal 16:9 slide hero or background, prefer `2848x1600` unless the user
explicitly needs a higher-resolution asset. For square spot illustrations,
prefer `2048x2048`. If the environment does not expose an image-generation
tool, do not pretend an image was generated. Mark the relevant item `blocked` or
use `draw_in_html` / `skip`, then continue with a layout that still works
without generated assets.

Keep generated assets as normal files:

```text
assets/generated/manifest.json
assets/generated/slide-03-hero.png
assets/generated/slide-07-process-bg.png
```

The manifest should record the target slide, purpose, aspect ratio, prompt,
source model/provider when known, file path, and alt text. Reference generated
images from `deck.html` with relative paths, for example:

```html
<img src="assets/generated/slide-03-hero.png" alt="..." />
```

Do not inline large `data:image/...` strings into `deck.html` just to satisfy
the PPTX exporter. The HTML deliverable should stay readable and should open
directly in a browser. The official exporter resolves local relative `<img>`
paths and temporarily converts them to data URLs inside the browser DOM before
calling `dom-to-pptx`, without rewriting the source HTML. For generated bitmap
assets that must survive PPTX export, prefer real `<img>` elements; avoid hiding
local generated files only in CSS `background-image` unless that URL is already
remote/CORS-safe or a small data URL.

## Export

When commands need the skill directory, use the active installed skill path
rather than a machine-specific absolute path. In Office Raccoon this is usually
`$HOME/.box-agent/skills/pptx`, but a host may provide a different path:

```bash
PPTX_SKILL_DIR="${BOX_AGENT_PPTX_SKILL_DIR:-$HOME/.box-agent/skills/pptx}"
OFFICE_RACCOON_NODE_PREFIX="${BOX_AGENT_NODE_PREFIX:-${BOX_AGENT_RUNTIME_PREFIX:-$HOME/Library/Application Support/office-raccoon}}"
```

The top-level workflow runs this preflight before writing the full deck. If you
need to re-check whether CLI HTML-to-editable-PPTX export can run:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/check_html_export_env.js"
```

If this reports missing Playwright/Chromium and no host renderer is available,
follow the route choice in `SKILL.md` before authoring a full deck.

Before export, run the HTML structural self-check with the editable compatibility
profile:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_self_check.js" deck.html --dom-to-pptx --allow-local-images --report qa/html_self_check.json
```

If the command exits non-zero, inspect `qa/html_self_check.json` before deciding
what failed. Summarize concrete failing slides/selectors and fix `deck.html`.
If the deck still has a small number of accepted issues after the bounded repair
rule in `SKILL.md`, use the official export flag instead:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_to_editable_pptx.js" deck.html output.pptx --out slides --allow-self-check-issues
```

Then export:

```bash
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_to_editable_pptx.js" deck.html output.pptx --out slides
```

The export script runs self-check again, writes `qa/html_self_check.json`,
creates `slides/slide-*.png` preview images for visual QA, temporarily inlines
local `<img>` paths in the browser DOM for export, loads
`scripts/dom-to-pptx.bundle.js`, and writes `output.pptx`. It does not rewrite
`deck.html`.

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

## QA

HTML self-check is the first QA gate. Keep `qa/html_self_check.json` with the
delivery artifacts. If that report is missing or `"ok"` is not `true`, do not
claim HTML self-check passed.

After the PPTX is created, run package validation, text extraction, placeholder
scan, and render.

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
