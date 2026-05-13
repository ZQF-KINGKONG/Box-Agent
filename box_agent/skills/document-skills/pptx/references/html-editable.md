# HTML-First Editable Export

Use this path for newly generated decks. Author the deck as `deck.html`, then
export the same `.slide` DOM elements to editable PowerPoint objects with the
skill-bundled `scripts/dom-to-pptx.bundle.js`.

This is the standard HTML-first path for new decks.

If final `.pptx` output is expected, run the browser export environment
preflight before writing the full HTML deck. If Playwright/Chromium and host
renderer are missing, tell the user this blocks HTML-to-editable-PPTX export and
ask them to choose `HTML` or `PPTX`: `HTML` means deliver `deck.html` now and
export later after setup; `PPTX` means switch to native PptxGenJS with different
HTML/CSS fidelity tradeoffs.

## Authoring Profile

Before export, create `deck.html` with one `.slide` element per page. Prefer this
`dom-to-pptx` authoring profile:

- Use `1920px × 1080px` slides with fixed pixel dimensions.
- Put `.slide` directly under `<body>` or a plain non-transformed wrapper.
- Set every `.slide` to `position: relative; overflow: hidden`.
- Prefer inline styles for slide content; keep `<style>` for page chrome only.
- Use fixed `px` units on slide content; avoid `vh`, `vw`, `vmin`, `vmax`.
- Use absolute `left/top/width/height` or flex/grid final layout. Do not use
  `transform: translate/scale/skew/matrix`; `rotate()` is acceptable.
- Use `linear-gradient`; avoid radial/conic gradients.
- Do not use `backdrop-filter`, `clip-path`, `mix-blend-mode`, animations,
  transitions, or text-shadow on slide content.
- Images must be `https://...` with CORS or `data:image/...`; avoid relative
  paths, `file://`, `srcset`, and `loading="lazy"`.
- Google Fonts links must include `crossorigin="anonymous"` and should have a
  web-safe fallback such as `Arial, sans-serif`.
- Leave text safety slack. Browser text that fits by only 1-2px may wrap in
  PowerPoint because PPT and Chrome use different font metrics. Make text boxes
  at least 16-24px wider than the browser line needs, or reduce font size
  slightly. Do not rely on exact-fit single-line text.
- For badges, pills, buttons, tags, or other short text with a background color,
  never use vertical padding (`padding-top`, `padding-bottom`, or
  `padding: Ypx Xpx`) to simulate vertical centering. This commonly shifts or
  clips text after dom-to-pptx conversion. Use a fixed `width`/`height` outer
  container with the background, radius, and `display:flex; align-items:center;
  justify-content:center`; put the label in an inner text element with
  `margin:0; padding:0; line-height:1`.
- For Chinese text, prefer fonts that exist or embed reliably across Office
  environments, for example `Microsoft YaHei`, `Noto Sans CJK SC`, then
  `Arial, sans-serif`. If a web font is used, ensure it embeds; fallback fonts
  can change line width and cause unexpected wraps.

Recommended badge pattern:

```html
<div
  style="
    width: 160px;
    height: 48px;
    background: #0066cc;
    border-radius: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
  "
>
  <span style="margin: 0; padding: 0; line-height: 1; font-size: 18px; color: #ffffff;">
    进行中
  </span>
</div>
```

## Command

Run:

```bash
PPTX_SKILL_DIR="${BOX_AGENT_PPTX_SKILL_DIR:-$HOME/.box-agent/skills/pptx}"
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/check_html_export_env.js"
${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/html_to_editable_pptx.js" deck.html output.pptx --out slides
```

If `check_html_export_env.js` reports missing Playwright/Chromium and no host
renderer is available, ask the user to choose before authoring or exporting:
`HTML` keeps `deck.html` as the deliverable; `PPTX` switches to native
PptxGenJS.

The script runs HTML self-check with `--dom-to-pptx`, creates
`slides/slide-*.png` preview images for visual QA, loads the skill-local
`scripts/dom-to-pptx.bundle.js`, writes `qa/html_self_check.json`, and writes
`output.pptx`. It passes `autoEmbedFonts: true` and defaults `svgAsVector: false` so SVGs are rasterized for pixel fidelity, closer to the in-browser button export path. Pass `--svg-vector true` only when PowerPoint vector editability is more important than visual fidelity. If `qa/html_self_check.json` is missing, do not say HTML
self-check passed.

If self-check or export fails after the route has been chosen, read the
generated report and fix the HTML source. Do not switch to native PptxGenJS
because of text slack, overflow, Playwright, or DOM-to-PPTX compatibility errors.
Route changes for a new deck require explicit user confirmation unless the user
supplied a template, required native PowerPoint charts/tables, or chose `PPTX`
at the missing-browser preflight.

Do not bypass the self-check. Never write a custom `export_skipcheck.js`, call
`dom-to-pptx.bundle.js` directly to skip `scripts/html_self_check.js`, or patch
the exporter to ignore a failed `qa/html_self_check.json`. If the report has
`"ok": false`, fix `deck.html` and rerun the official exporter. Run at most 3
focused repair rounds. After that, if only a small number of known, visually
acceptable issues remain, continue only with the official
`--allow-self-check-issues` flag, then report unresolved issues and complete
render/visual QA. If severe blocking issues remain, report
`Editable PPTX export: BLOCKED (HTML self-check failed)`.

Do not install the npm `dom-to-pptx` package for this workflow. The editable
export must use this skill's bundled `scripts/dom-to-pptx.bundle.js`, which may
contain local fixes that are not in the published package.

If there is no browser host after the user chose HTML, `dom-to-pptx` cannot run
from the CLI. Finish and deliver `deck.html`, report editable PPTX export as
`BLOCKED`, and include the install/download commands:

```text
OFFICE_RACCOON_NODE_PREFIX="${BOX_AGENT_NODE_PREFIX:-${BOX_AGENT_RUNTIME_PREFIX:-$HOME/Library/Application Support/office-raccoon}}"
Install Playwright: ${BOX_AGENT_NPM:-npm} install --prefix "$OFFICE_RACCOON_NODE_PREFIX" playwright
Download Chromium: "$OFFICE_RACCOON_NODE_PREFIX/node_modules/.bin/playwright" install chromium
```

If the host app exposes an Electron renderer conversion/import path, that can
serve as the browser host. Do not assume Electron main or a Node child process
has DOM layout APIs.

## QA Requirements

Run the same package/text/render/visual QA as other PPTX outputs.

Additional editable-export checks:

- Confirm `qa/html_self_check.json` exists, is non-empty, and has `"ok": true`.
- Treat text slack failures as real blockers. They usually predict the exact
  issue where HTML text looks fine but the editable PPTX wraps one word or one
  CJK character onto a new line.
- Create compressed `qa/vision_inputs/slide-*.jpg` from `slides/slide-*.png`, then inspect those review-size JPGs with `vision_review`.
- For decks with 10 or more slides, inspect every individual slide image in 1-3 slide batches by default, then merge batch reports into `qa/visual_review.md`.
- For decks with 20 or fewer slides, inspect every individual slide image. If
  only representative slides are reviewed, call it a partial visual spot check,
  not a full QA pass.
- Render the exported PPTX and compare it to the source previews when possible.
- Check especially for text reflow, missing gradients, missing images,
  incorrect SVG conversion, wrong z-order, and shifted card/chart positions.
- If render comparison or visual review shows drift, fix `deck.html` and rerun
  `html_to_editable_pptx.js`.

Do not claim full fidelity from `dom-to-pptx` without render QA. It is the
standard editable export path, not a replacement for visual inspection. Keep the default SVG rasterization unless the user explicitly wants editable vector SVGs.
