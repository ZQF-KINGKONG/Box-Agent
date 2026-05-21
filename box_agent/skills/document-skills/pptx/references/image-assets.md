# Image and manifest policy

## 1. Decision first

1. Every slide must have one explicit `image_plan` entry.
2. `image_plan.decision` must be one of `generate`, `use_existing`, `draw_in_html`, `skip`, or `blocked`.
3. Prefer `generate` when a bitmap asset would make the slide faster to understand, more memorable, or visually credible.
4. Do not use `skip` as the default. Use it only when the reason says why typography, data, or editable shapes are stronger than any bitmap.
5. Use real or source-backed images for factual, screenshot, chart, logo, real-location, or person-accuracy content.
6. Do not create generic decorative filler; generated images need a clear narrative job.

## 2. Trigger rules

1. Use `generate` for cover, divider, poster, campaign, launch, vision, abstract concept, future-state, transformation, and emotionally led closing slides.
2. Use `generate` for realistic/semi-realistic product mockups, environments, textures, human scenes, or hero/card visuals that would be awkward or low-quality if drawn from PowerPoint shapes.
3. Use `generate` when the user asks for image-rich, illustration, scene, poster, cinematic, magazine, campaign, or visual-metaphor output.
4. Use `draw_in_html` for dense data, maps, timelines, architecture, process, and tables when editability is more important than bitmap impact.
5. Use `skip` for data slides only when charts and text are stronger and no local visual frame would help.
6. Use `use_existing` for supplied product photos, charts, official logos, real locations, screenshots, named people, or source-captured visuals.

## 3. Manifest format

1. Keep a deck-level `assets/generated/manifest.json` with `deck_context`, `style_anchor`, and `image_plan`.
1. Use this shape for each slide needing visuals:

```json
{
  "slide": "03",
  "decision": "generate",
  "kind": "hero_illustration",
  "reason": "text message needs visual anchor",
  "placement": "right hero",
  "aspect_ratio": "16:9",
  "target_size": "2848x1600",
  "prompt": {
    "deck_context": "AI Operating Model Transformation deck for executive and product leadership; theme: moving from isolated AI pilots to governed, repeatable AI workflows",
    "subject": "Three abstract data streams converging into a central node",
    "composition": "right-side hero, left text safe area",
    "style": "Editorial vector illustration, clean linework, soft gradients",
    "palette": "Deep indigo #1E2A5E, electric cyan #22D3EE, amber #F59E0B, off-white #F8FAFC",
    "lighting": "Soft directional rim light",
    "mood": "Forward-looking and calm",
    "quality": "High detail, crisp edges, 4K finish"
  },
  "avoid": "embedded text, watermark, named people, blurry output",
  "output_path": "assets/generated/slide-03-hero.png",
  "alt_text": "Abstract AI workflow illustration"
}
```

1. Use structured prompt fields for `generate`.
2. Put `deck_context` first in every `generate` prompt so the image model sees the whole PPT theme before the slide-specific subject.
3. Keep `avoid` separate from `prompt`.

## 4. Style anchor reuse

1. Reuse deck `style_anchor` for every generated prompt.
2. Keep generated prompt styles consistent with deck voice and palette.
3. Avoid arbitrary dimensions.
4. Use preset `2848x1600` for 16:9 hero/background.
5. Use preset `2048x2048` for square spot.

## 5. Output placement

1. Store generated files under `assets/generated/`.
1. Reference files with relative paths inside HTML.
1. If generation tooling is unavailable, mark appropriate image-plan entries as `blocked` or choose `draw_in_html`; do not silently convert strong `generate` candidates to `skip` just to avoid the missing tool.
