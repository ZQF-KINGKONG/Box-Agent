# Image and manifest policy

## 1. Decision first

1. `image_plan.decision` must be one of `generate`.
2. `image_plan.decision` can be `use_existing`.
3. `image_plan.decision` can be `draw_in_html`.
4. `image_plan.decision` can be `skip`.
5. Do not create generic image-heavy decks.
6. Use generated images only when they materially improve understanding.
7. Use real or source-backed images for factual, screenshot, chart, or person-accuracy content.

## 2. Trigger rules

1. Use `generate` for cover, divider, poster, campaign, launch, vision, or visual-anchor slides.
2. Use `draw_in_html` for dense data, maps, timelines, architecture, process, and tables.
3. Use `skip` for data slides where charts and text are stronger.
4. Use `use_existing` for supplied product photos, charts, official logos, real locations, or source-captured visuals.

## 3. Manifest format

1. Keep a deck-level `assets/generated/manifest.json` with `style_anchor` and `image_plan`.
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
2. Keep `avoid` separate from `prompt`.

## 4. Style anchor reuse

1. Reuse deck `style_anchor` for every generated prompt.
2. Keep generated prompt styles consistent with deck voice and palette.
3. Avoid arbitrary dimensions.
4. Use preset `2848x1600` for 16:9 hero/background.
5. Use preset `2048x2048` for square spot.

## 5. Output placement

1. Store generated files under `assets/generated/`.
1. Reference files with relative paths inside HTML.
1. If generation tooling is unavailable, use `skip` or `draw_in_html` instead of fabricating assets.
