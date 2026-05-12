# HTML-First Editable Export

Use this path for newly generated decks. Author the deck as `deck.html`, then
export the same `.slide` DOM elements to editable PowerPoint objects with the
skill-bundled `scripts/dom-to-pptx.bundle.js`.

This is the standard HTML-first path for new decks.

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
${BOX_AGENT_NODE:-node} /Users/malin1/.box-agent/skills/pptx/scripts/html_to_editable_pptx.js deck.html output.pptx --out slides
```

The script runs HTML self-check with `--dom-to-pptx`, creates
`slides/slide-*.png` preview images for visual QA, loads the skill-local
`scripts/dom-to-pptx.bundle.js`, writes `qa/html_self_check.json`, and writes
`output.pptx`. It passes `autoEmbedFonts: true` and defaults `svgAsVector: false` so SVGs are rasterized for pixel fidelity, closer to the in-browser button export path. Pass `--svg-vector true` only when PowerPoint vector editability is more important than visual fidelity. If `qa/html_self_check.json` is missing, do not say HTML
self-check passed.

Do not install the npm `dom-to-pptx` package for this workflow. The editable
export must use this skill's bundled `scripts/dom-to-pptx.bundle.js`, which may
contain local fixes that are not in the published package.

If there is no browser host, `dom-to-pptx` cannot run from the CLI. Finish and
deliver `deck.html`, report editable PPTX export as `BLOCKED`, and include the
install/download commands:

```text
Install Playwright: ${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" playwright
Download Chromium: "$HOME/Library/Application Support/office-raccoon/node_modules/.bin/playwright" install chromium
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
- Render the exported PPTX and compare it to the source previews when possible.
- Check especially for text reflow, missing gradients, missing images,
  incorrect SVG conversion, wrong z-order, and shifted card/chart positions.
- If render comparison or visual review shows drift, fix `deck.html` and rerun
  `html_to_editable_pptx.js`.

Do not claim full fidelity from `dom-to-pptx` without render QA. It is the
standard editable export path, not a replacement for visual inspection. Keep the default SVG rasterization unless the user explicitly wants editable vector SVGs.
