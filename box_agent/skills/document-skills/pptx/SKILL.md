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
5. Visual QA requires rendering before claiming completion.
6. If QA or render is blocked, report `BLOCKED` explicitly.

## 1. Route Decision

### New deck

Use this path by default:

1. create `deck.html`
2. run HTML self-check
3. export with `scripts/html_to_editable_pptx.js`
4. render exported PPTX
5. inspect and fix visual issues

If browser host preflight blocks HTML export, ask the user to choose one route:

1. `HTML`: deliver `deck.html` first, export later after host setup
2. `PPTX`: switch to native `PptxGenJS`

### Existing deck or template

Use this path for edits:

1. copy original deck
2. extract text
3. render thumbnails
4. apply edits
5. validate package
6. render and inspect

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
| HTML self-check | `${BOX_AGENT_NODE:-node} scripts/html_self_check.js deck.html --dom-to-pptx --allow-local-images --report qa/html_self_check.json` |
| Export HTML | `${BOX_AGENT_NODE:-node} scripts/html_to_editable_pptx.js deck.html output.pptx` |
| Check local deps | `${BOX_AGENT_PYTHON:-python3} scripts/setup_check.py` |

## 3. HTML-first Requirements

1. `.slide` must be exactly `1920px × 1080px`.
2. Leave 16-24px text slack to reduce PowerPoint wrap drift.
3. Use relative asset paths.
4. Do not inline large images as data URLs.
5. Use generated images only when they improve communication.
6. Keep page numbers on non-cover slides consistent with slide order.
7. Read `references/html-first.md` and `references/html-editable.md`.
8. Keep image generation rules in `references/image-assets.md`.

## 4. QA Gates

Required for every created or modified deck:

1. package validation
2. text extraction
3. placeholder scan
4. rendered visual inspection
5. slide count and order check

For HTML-first, `qa/html_self_check.json` must exist before export.
Fix self-check failures and retry up to 3 times.
Use `--allow-self-check-issues` only after 3 repair rounds for small accepted issues.
If render QA is blocked, set `BLOCKED` instead of claiming success.

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
