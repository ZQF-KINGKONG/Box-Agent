#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function usage() {
  console.error("Usage: validate_outline.js outline.json [--min-slides N] [--max-slides N]");
  process.exit(2);
}

function parseArgs(argv) {
  if (argv.length < 1) usage();
  const opts = {
    outlinePath: argv[0],
    minSlides: 3,
    maxSlides: 40,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = argv[i + 1];
    if (arg === "--min-slides" && value) {
      opts.minSlides = Number(value);
      i += 1;
    } else if (arg === "--max-slides" && value) {
      opts.maxSlides = Number(value);
      i += 1;
    } else {
      usage();
    }
  }
  if (!Number.isInteger(opts.minSlides) || opts.minSlides < 1) usage();
  if (!Number.isInteger(opts.maxSlides) || opts.maxSlides < opts.minSlides) usage();
  return opts;
}

function readOutline(outlinePath) {
  const resolved = path.resolve(outlinePath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`Outline file not found: ${resolved}`);
  }
  try {
    return { outline: JSON.parse(fs.readFileSync(resolved, "utf8")), resolved };
  } catch (error) {
    throw new Error(`Invalid JSON in ${resolved}: ${error.message}`);
  }
}

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function wordLikeLength(value) {
  return Array.from(text(value)).length;
}

function normalize(value) {
  return text(value).toLowerCase().replace(/\s+/g, " ");
}

function includesAny(value, needles) {
  const normalized = normalize(value);
  return needles.some(needle => normalized.includes(needle));
}

function hasEvidence(slide) {
  return Array.isArray(slide.evidence) && slide.evidence.some(item => text(item));
}

function validate(outline, opts) {
  const issues = [];
  const warnings = [];

  for (const field of ["deck_goal", "audience", "storyline"]) {
    if (!text(outline[field])) issues.push(`Missing top-level field: ${field}`);
  }

  const slides = Array.isArray(outline.slides) ? outline.slides : null;
  if (!slides) {
    issues.push("Missing or invalid top-level field: slides must be an array");
    return { ok: false, issues, warnings, slideCount: 0 };
  }

  if (slides.length < opts.minSlides) {
    issues.push(`Too few slides: ${slides.length}; expected at least ${opts.minSlides}`);
  }
  if (slides.length > opts.maxSlides) {
    issues.push(`Too many slides: ${slides.length}; expected at most ${opts.maxSlides}`);
  }

  const seenTitles = new Map();
  const seenMessages = new Map();
  const dataHeavyTerms = [
    "market",
    "市场",
    "tam",
    "sam",
    "som",
    "growth",
    "增长",
    "traction",
    "收入",
    "revenue",
    "financial",
    "融资",
    "成本",
    "cost",
    "roi",
    "chart",
    "图表",
    "benchmark",
    "竞品",
    "competition",
  ];

  slides.forEach((slide, index) => {
    const label = `slide-${String(index + 1).padStart(2, "0")}`;
    const expectedPage = index + 1;

    if (!slide || typeof slide !== "object" || Array.isArray(slide)) {
      issues.push(`${label}: slide must be an object`);
      return;
    }

    if (slide.page !== expectedPage) {
      issues.push(`${label}: page must be ${expectedPage}, got ${JSON.stringify(slide.page)}`);
    }

    for (const field of ["title", "message", "layout", "visual"]) {
      if (!text(slide[field])) issues.push(`${label}: missing ${field}`);
    }

    if (!Array.isArray(slide.evidence)) {
      issues.push(`${label}: evidence must be an array, use [] for non-evidence slides`);
    }

    const title = text(slide.title);
    const message = text(slide.message);
    const titleKey = normalize(title);
    const messageKey = normalize(message);

    if (wordLikeLength(title) > 42) {
      warnings.push(`${label}: title is long (${wordLikeLength(title)} chars); make it presentation-ready`);
    }
    if (wordLikeLength(message) > 120) {
      warnings.push(`${label}: message is long (${wordLikeLength(message)} chars); keep one core claim`);
    }
    if (message && message === title) {
      issues.push(`${label}: message duplicates title; use a claim, not a topic label`);
    }

    if (titleKey) {
      const firstSeen = seenTitles.get(titleKey);
      if (firstSeen) warnings.push(`${label}: title duplicates ${firstSeen}`);
      else seenTitles.set(titleKey, label);
    }
    if (messageKey) {
      const firstSeen = seenMessages.get(messageKey);
      if (firstSeen) issues.push(`${label}: message duplicates ${firstSeen}`);
      else seenMessages.set(messageKey, label);
    }

    const combined = [slide.title, slide.message, slide.layout, slide.visual, slide.notes].map(text).join(" ");
    if (includesAny(combined, dataHeavyTerms) && !hasEvidence(slide)) {
      warnings.push(`${label}: appears data/evidence-heavy but evidence is empty`);
    }

    if (includesAny(message, [" and ", "；", ";", "、"]) && wordLikeLength(message) > 60) {
      warnings.push(`${label}: message may contain multiple claims; consider splitting`);
    }
  });

  const storyline = text(outline.storyline);
  if (slides.length >= 6 && wordLikeLength(storyline) < 20) {
    warnings.push("storyline is very short for a multi-slide deck; make the narrative arc explicit");
  }

  return { ok: issues.length === 0, issues, warnings, slideCount: slides.length };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const { outline, resolved } = readOutline(opts.outlinePath);
  const result = validate(outline, opts);
  const output = { ...result, outline: resolved };
  console.log(JSON.stringify(output, null, 2));
  if (!result.ok) process.exit(1);
}

try {
  main();
} catch (error) {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}
