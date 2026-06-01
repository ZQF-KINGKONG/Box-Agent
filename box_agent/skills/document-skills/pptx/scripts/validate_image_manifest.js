#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

function usage() {
  console.error(
    "Usage: validate_image_manifest.js assets/generated/manifest.json [--mode creative_image_mode] [--min-generated 1] [--report qa/image_manifest.json]",
  );
  process.exit(2);
}

function parseArgs(argv) {
  if (argv.length < 1) usage();
  const opts = {
    manifest: argv[0],
    mode: null,
    minGenerated: 0,
    report: null,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = argv[i + 1];
    if (arg === "--mode" && value) {
      opts.mode = value;
      i += 1;
    } else if (arg === "--min-generated" && value) {
      opts.minGenerated = Number(value);
      i += 1;
    } else if (arg === "--report" && value) {
      opts.report = value;
      i += 1;
    } else {
      usage();
    }
  }
  if (!Number.isInteger(opts.minGenerated) || opts.minGenerated < 0) usage();
  return opts;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function imagePlanFromManifest(manifest) {
  if (Array.isArray(manifest)) return manifest;
  if (Array.isArray(manifest.image_plan)) return manifest.image_plan;
  return [];
}

function fileExistsForOutputPath(outputPath, manifestPath) {
  if (typeof outputPath !== "string" || !outputPath.trim()) return false;
  const normalized = outputPath.trim();
  const candidates = [
    path.resolve(normalized),
    path.resolve(path.dirname(manifestPath), normalized),
    path.resolve(path.dirname(path.dirname(manifestPath)), normalized),
  ];
  return candidates.some(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
}

function isSuccessfulGenerate(item, manifestPath) {
  if (!item || item.decision !== "generate") return false;
  const status = typeof item.status === "string" ? item.status.toLowerCase() : "";
  if (["blocked", "failed", "error", "skipped"].includes(status)) return false;
  return fileExistsForOutputPath(item.output_path, manifestPath);
}

function writeReport(reportPath, payload) {
  if (!reportPath) return;
  fs.mkdirSync(path.dirname(path.resolve(reportPath)), { recursive: true });
  fs.writeFileSync(reportPath, JSON.stringify(payload, null, 2), "utf8");
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const manifestPath = path.resolve(opts.manifest);
  const issues = [];
  const warnings = [];

  if (!fs.existsSync(manifestPath)) {
    issues.push(`manifest not found: ${manifestPath}`);
    const payload = { ok: false, manifest: manifestPath, issues, warnings };
    writeReport(opts.report, payload);
    console.error(JSON.stringify(payload, null, 2));
    process.exit(1);
  }

  const manifest = readJson(manifestPath);
  const imagePlan = imagePlanFromManifest(manifest);
  const successfulGenerated = imagePlan.filter(item => isSuccessfulGenerate(item, manifestPath));

  if (!imagePlan.length) {
    issues.push("manifest.image_plan is missing or empty.");
  }

  if (opts.mode && manifest.mode !== opts.mode) {
    issues.push(`manifest.mode must be "${opts.mode}", got ${JSON.stringify(manifest.mode)}.`);
  }

  if (successfulGenerated.length < opts.minGenerated) {
    issues.push(
      `expected at least ${opts.minGenerated} successful generated image(s), found ${successfulGenerated.length}.`,
    );
  }

  if (opts.mode === "creative_image_mode") {
    const blocked = imagePlan.filter(item => item && item.decision === "blocked");
    if (blocked.length && successfulGenerated.length === 0) {
      warnings.push("creative_image_mode has blocked image-plan entries and no successful generated assets.");
    }
  }

  const payload = {
    ok: issues.length === 0,
    manifest: manifestPath,
    mode: manifest.mode || null,
    imagePlanCount: imagePlan.length,
    successfulGeneratedCount: successfulGenerated.length,
    successfulGenerated: successfulGenerated.map(item => ({
      slide: item.slide || null,
      kind: item.kind || null,
      output_path: item.output_path || null,
    })),
    issues,
    warnings,
  };
  writeReport(opts.report, payload);
  console.log(JSON.stringify(payload, null, 2));
  process.exit(payload.ok ? 0 : 1);
}

main();
