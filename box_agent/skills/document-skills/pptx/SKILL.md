---
name: pptx
description: Create, inspect, edit, validate, render, and QA PowerPoint decks. Use when the user mentions PowerPoint, PPT, PPTX, slide deck, presentation, template slides, speaker notes, slide images, or asks to read, generate, create, make, design, or modify a .pptx artifact. New decks default to HTML-first editable export through the bundled `dom-to-pptx` exporter.
---

# PPTX Skill

Use this skill whenever a PowerPoint deck is an input, output, or deliverable.

## 0. Non-negotiable Rules

1. New deck tasks use HTML-first editable generation by default.
2. Existing PPTX/template edits preserve the original PPTX structure.
3. `python-pptx` must not create a new deck.
4. Do not silently downgrade generation mode.
5. Visual QA via rendering is optional, not required. See §4.2 for triggers.
6. If render is attempted but blocked (missing `soffice`/PDF renderer), continue without it; do not treat it as a delivery blocker.
8. Before writing any slide HTML, invoke the `html-templates` skill to fetch the Visual DNA profile (palette / typography / decoration tokens). See §3.0. This applies to every new HTML-first deck without exception.
7. `.slide` must be exactly `1920px × 1080px`. **NEVER** pass `--width` / `--height` to `html_self_check.js` or `html_to_editable_pptx.js`; the scripts auto-detect from the `.slide` CSS. Mismatched dimensions are a hard failure, not a fixable warning.

## 1. Route Decision

### New deck

Use this path by default:

1. invoke the `html-templates` skill to fetch the Visual DNA profile (see §3.0)
2. create `deck.html` using that profile as hard style constraints
3. run HTML self-check
4. export with `scripts/html_to_editable_pptx.js`
5. run structural QA (package validation, text extraction, placeholder scan)
6. render and inspect only if §4.2 triggers apply

If browser host preflight blocks HTML export, ask the user to choose one route:

1. `HTML`: deliver `deck.html` first, export later after host setup
2. `PPTX`: switch to native `PptxGenJS`

### Existing deck or template

Use this path for edits:

1. copy original deck
2. extract text
3. apply edits
4. validate package
5. render and inspect only if §4.2 triggers apply

### Native `PptxGenJS`

Use only when the user clearly requires it:

1. native PowerPoint charts/tables are required
2. user requires PowerPoint-native structure
3. HTML-first is impossible and user accepts the tradeoff

Do not switch routes based on convenience.

## 2. Minimal Commands

| Task | Command |
|---|---|
| Extract text | `${BOX_AGENT_PYTHON:-python3} scripts/extract_text.py input.pptx` |
| Validate package | `${BOX_AGENT_PYTHON:-python3} scripts/validate_pptx_package.py input.pptx` |
| Render PPTX | `${BOX_AGENT_PYTHON:-python3} scripts/render_pptx.py input.pptx --out rendered` |
| HTML self-check | `${BOX_AGENT_NODE:-node} scripts/html_self_check.js deck.html --dom-to-pptx --allow-local-images --report qa/html_self_check.json` ⚠️ 不要追加 `--width/--height` |
| Export HTML | `${BOX_AGENT_NODE:-node} scripts/html_to_editable_pptx.js deck.html output.pptx` ⚠️ 不要追加 `--width/--height` |
| Check local deps | `${BOX_AGENT_PYTHON:-python3} scripts/setup_check.py` |
| Check HTML export env | `${BOX_AGENT_NODE:-node} scripts/check_html_export_env.js` |

⚠️ **Dependency probing**: never use bare `node -e "require.resolve('playwright')"` to check for installed packages. Box-Agent installs Node deps into the **office-raccoon managed prefix** (`~/Library/Application Support/office-raccoon/node_modules/` on macOS, `$APPDATA/office-raccoon/node_modules/` on Windows, `~/.config/office-raccoon/node_modules/` on Linux), which is **not** on the default `NODE_PATH`. A naked `node -e` process will report every managed package as `not found`. Always use `scripts/check_html_export_env.js` (Node) or `scripts/setup_check.py` (Python) — both look in the managed prefix.

## 3. HTML-first Requirements

### 3.0 Before generating slide HTML (mandatory)

Always invoke the `html-templates` skill first to obtain the visual style constraints for this deck:

```
Skill(skill="html-templates",
      args="<the user's original brief verbatim>")
```

That skill returns a structured Visual DNA profile (palette, typography, decoration tokens, style rules). Treat its output as **hard constraints** when writing the HTML. Do not generate slide HTML without running this step — model defaults to "stay in the current skill" and will not auto-route to `html-templates` unless explicitly called from here.

If `html-templates` is unavailable in this session, fall back to authoring the deck with the existing palette/typography conventions and note the absence in `Limitations`.

### 3.1 Layout constraints

1. `.slide` must be exactly `1920px × 1080px` (see §0 rule 7 — do **not** pass `--width/--height` to the scripts).
2. Leave 16-24px text slack to reduce PowerPoint wrap drift.
3. Use relative asset paths.
4. Do not inline large images as data URLs.
5. Every slide must record an explicit image decision in `assets/generated/manifest.json`; covers, dividers, posters, campaign/launch/vision pages must use `generate` via the `generate_image` tool unless the user opts out.
6. Keep page numbers on non-cover slides consistent with slide order.
7. Read `references/html-first.md` and `references/html-editable.md`.
8. Keep image generation rules in `references/image-assets.md`.

### 3.2 Visual effects scope (decoration vs text-bearing)

`html_to_editable_pptx.js` runs `bg_capture` by default (`--bg-capture always`). It screenshots every **decoration node** into a slide-level bitmap and then removes it from the export tree, so any CSS effect on a decoration node ends up as pixels — not as a live PPTX shape. The dom-to-pptx blacklist applies **only to elements that survive capture**.

**Decoration nodes (free to use any visual effect):**
- Empty `<div>` (no text inside, no `<img>` inside)
- `<svg>`, `<hr>`, `<canvas>`
- Anything nested inside an `<svg>`

**Allowed on decoration nodes and on `.slide` background:**
`transform`, `clip-path`, `text-shadow`, `backdrop-filter`, `mix-blend-mode`, `animation`, `transition`, `radial-gradient`, `conic-gradient`, `filter: drop-shadow/brightness/contrast/saturate/hue-rotate/...`.

**Still forbidden everywhere (bg_capture does not fix these):**
- Viewport units `vh/vw/vmin/vmax` — these are layout sizes, not visual effects
- `<video>`, `<audio>`, `<iframe>` — not captured at all
- Non-absolute / non-data / non-file `<img>` src on text path
- `position: static` or `overflow: visible` on `.slide`

**Still forbidden on text-bearing elements** (these survive capture as live PPTX shapes):
- `transform`, `text-shadow`, `clip-path`, `backdrop-filter`, `mix-blend-mode`, `animation`, `transition`, `radial-gradient`, `conic-gradient`, non-blur `filter`

**Practical guidance:**
- Want a glowing pill, gradient orb, blurred halo, rotated badge? Put it in an empty `<div>` (or SVG), then place the text in a **separate** sibling element on top. The decoration goes into the bitmap; the text stays sharp and editable.
- `.slide`'s own `background` can be any gradient / image / blend — it ends up in the bitmap layer.
- If `html_self_check.js` flags a visual effect on a "text-bearing element", the fix is usually to split the element: one decoration sibling for the effect, one text element for the words.

## 4. QA Gates

Required for every created or modified deck:

1. package validation
2. text extraction
3. placeholder scan
4. slide count and order check

For HTML-first, `qa/html_self_check.json` must exist before export.
Fix self-check failures and retry up to 3 times.
Use `--allow-self-check-issues` only after 3 repair rounds for small accepted issues.

Rendered visual inspection is **not** in the required list. See §4.2.

### 4.1 Visual issue triage

When rendered visual inspection surfaces a problem, classify it before reacting. Do **not** change route or strategy for cosmetic issues.

**Blocker — must fix:**
- Text overflow, content extending outside slide bounds
- Image failed to load, broken asset references
- Wrong slide order, missing pages, misaligned page numbers
- Layout collapse (overlapping blocks, zero-size containers)
- Typos in user-supplied copy, factual errors
- dom-to-pptx drift that hides a whole element

**Cosmetic — accept and move on:**
- Watermark / signature artifacts on generated images
- A single line wrap on a long title or trailing punctuation
- Minor kerning / leading drift after dom-to-pptx export
- Color shifts within the same palette family
- Subpixel alignment between adjacent blocks

**Forbidden reactions to cosmetic issues:**
- Switching `generate` → `draw_in_html` / pure vector / icons
- Switching HTML-first → `PptxGenJS` or `python-pptx`
- Abandoning the image plan and rewriting slides text-only
- Cascading "re-check after fix" loops that surface new cosmetic nits

Cosmetic issues go directly into the `Limitations` section. They do not block delivery, do not justify a route switch, and do not get a repair attempt.

### 4.2 Visual inspection is optional

Rendered visual inspection (`scripts/render_pptx.py` + reading the resulting images) is **opt-in**, not a required gate.

**Default behavior:** skip visual inspection. Structural QA (package validation, text extraction, placeholder scan, slide count) is sufficient for delivery. Do not call `render_pptx.py` for visual judgment on every deck.

**Trigger visual inspection only when:**
1. The user explicitly asks to see / review / render the deck.
2. A blocker-class issue is already suspected from structural QA (e.g. text-extract shows truncated content) and visual confirmation is needed to locate the failure.

**When visual inspection runs:**
1. One pass only. Classify findings per §4.1.
2. Fix blockers, accept cosmetics, report.
3. Do **not** re-render after the fix to verify cosmetics. Re-render only if the fix targeted a blocker.
4. Do **not** trigger a second visual pass to "double-check" your own judgment.

Rendering for the user's own preview (so they can open the PNGs) is fine and does not count as visual QA — just generate the images, do not narrate findings or self-critique.

## 5. Office Raccoon Runtime

Read this order first:

1. `references/runtime-office-raccoon.md`
2. `references/dependency-policy.md`
3. `references/shell-safety.md`

Use managed variables for all commands:

1. `$BOX_AGENT_NODE`, `$BOX_AGENT_PYTHON`, `$BOX_AGENT_NPM`
2. `$BOX_AGENT_RENDER_RUNTIME`, `$BOX_AGENT_SOFFICE`, `$BOX_AGENT_PDFTOPPM`
3. `$BOX_AGENT_RUNTIME_PREFIX`

Install only into managed Office Raccoon prefixes.
No global, Homebrew, or system-wide installs without explicit approval.
No `/tmp`, no `>/tmp`, and no writes outside workspace/output folder.

## 6. Final Response Format

Use exact sections in this order:

1. `Created`
2. `Source`
3. `QA`
4. `Fixes`
5. `Limitations`

If a QA step is blocked, write `BLOCKED` for that step.

## 7. References

1. `references/html-first.md`
2. `references/html-editable.md`
3. `references/pptxgenjs.md`
4. `references/ooxml-editing.md`
5. `references/qa.md`
6. `references/api-integration.md`
7. `references/runtime-office-raccoon.md`
8. `references/dependency-policy.md`
9. `references/shell-safety.md`
10. `references/image-assets.md`

## 8. Mode lock and fallback

1. Lock the chosen route after preflight and explicit user confirmation.
2. Do not switch from HTML-first to `PptxGenJS` to speed up completion.
3. Do not switch to `python-pptx` for new deck creation.
4. If preflight or host checks change while running, restart from current source with the new route decision.
5. Keep report language explicit: `export blocked`, `render blocked`, `dependency blocked`, `mode locked`.

## 9. Compatibility baseline

1. Support macOS, Linux, and Windows for this skill.
2. Use managed runtime binaries first, then fallback checks.
3. Keep generated files inside workspace or requested output folder.
4. Prefer editable PPTX and source files over packaged archive delivery unless requested.
5. Keep output deterministic for reruns.
