#!/usr/bin/env node
const fs = require("fs");
const Module = require("module");
const path = require("path");
const { execFileSync } = require("child_process");

function officeRaccoonPrefix() {
  if (process.env.BOX_AGENT_NODE_PREFIX) return process.env.BOX_AGENT_NODE_PREFIX;
  if (process.env.BOX_AGENT_RUNTIME_PREFIX) return process.env.BOX_AGENT_RUNTIME_PREFIX;
  const home = process.env.HOME || "";
  if (process.platform === "darwin") {
    return path.join(home, "Library", "Application Support", "office-raccoon");
  }
  if (process.platform === "win32") {
    return path.join(process.env.APPDATA || home, "office-raccoon");
  }
  return path.join(home, ".config", "office-raccoon");
}

const managedNodeModules = path.join(officeRaccoonPrefix(), "node_modules");
process.env.NODE_PATH = process.env.NODE_PATH
  ? `${managedNodeModules}${path.delimiter}${process.env.NODE_PATH}`
  : managedNodeModules;
Module._initPaths();

function usage() {
  console.log(
    "Usage: html_to_editable_pptx.js deck.html output.pptx [--out slides] [--width 1920] [--height 1080] [--svg-vector true|false] [--allow-self-check-issues] (default: false for pixel fidelity)"
  );
}

function failUsage() {
  usage();
  process.exit(2);
}

function parseArgs(argv) {
  if (argv.includes("--help") || argv.includes("-h")) {
    usage();
    process.exit(0);
  }
  if (argv.length < 2) failUsage();
  const opts = {
    html: argv[0],
    pptx: argv[1],
    out: "slides",
    width: 1920,
    height: 1080,
    svgVector: false,
    allowSelfCheckIssues: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = argv[i + 1];
    if (arg === "--out" && value) {
      opts.out = value;
      i += 1;
    } else if (arg === "--width" && value) {
      opts.width = Number(value);
      i += 1;
    } else if (arg === "--height" && value) {
      opts.height = Number(value);
      i += 1;
    } else if (arg === "--svg-vector" && value) {
      opts.svgVector = value !== "false";
      i += 1;
    } else if (arg === "--allow-self-check-issues") {
      opts.allowSelfCheckIssues = true;
    } else {
      failUsage();
    }
  }
  if (!Number.isFinite(opts.width) || !Number.isFinite(opts.height)) failUsage();
  return opts;
}

function requireModule(name, installHint) {
  try {
    return require(name);
  } catch (error) {
    if (error && error.code === "MODULE_NOT_FOUND") {
      console.error(`Missing dependency: ${name}`);
      console.error(installHint);
      console.error("Without a browser host, ask the user to choose HTML delivery or native PptxGenJS PPTX.");
      process.exit(1);
    }
    throw error;
  }
}

function printBrowserInstallHint() {
  const prefix = officeRaccoonPrefix();
  console.error("Playwright Chromium is not available.");
  console.error(`Install/download it with: "${path.join(prefix, "node_modules", ".bin", "playwright")}" install chromium`);
  console.error("Without a browser host, ask the user to choose HTML delivery or native PptxGenJS PPTX.");
}

function resolveBrowserBundle() {
  const bundlePath = path.join(__dirname, "dom-to-pptx.bundle.js");
  if (!fs.existsSync(bundlePath)) {
    console.error(`Missing bundled converter: ${bundlePath}`);
    console.error("This skill requires scripts/dom-to-pptx.bundle.js for HTML editable export.");
    process.exit(1);
  }
  return bundlePath;
}

function runSelfCheck(htmlPath, width, height, reportPath, allowIssues) {
  const checker = path.join(__dirname, "html_self_check.js");
  try {
    execFileSync(
      process.execPath,
      [
        checker,
        htmlPath,
        "--width",
        String(width),
        "--height",
        String(height),
        "--dom-to-pptx",
        "--report",
        reportPath,
      ],
      {
        stdio: "inherit",
        env: process.env,
      }
    );
  } catch (error) {
    if (!allowIssues || !fs.existsSync(reportPath)) {
      throw error;
    }
    let report;
    try {
      report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
    } catch {
      throw error;
    }
    const issueCount = Array.isArray(report.issues) ? report.issues.length : 0;
    console.error(
      `HTML self-check still has ${issueCount} issue(s); continuing because --allow-self-check-issues was set.`
    );
  }
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const htmlPath = path.resolve(opts.html);
  const pptxPath = path.resolve(opts.pptx);
  const outDir = path.resolve(opts.out);
  const qaDir = path.join(path.dirname(pptxPath), "qa");
  const selfCheckReport = path.join(qaDir, "html_self_check.json");

  if (!fs.existsSync(htmlPath)) {
    console.error(`HTML file not found: ${htmlPath}`);
    process.exit(1);
  }

  fs.mkdirSync(qaDir, { recursive: true });
  runSelfCheck(htmlPath, opts.width, opts.height, selfCheckReport, opts.allowSelfCheckIssues);

  const { chromium } = requireModule(
    "playwright",
    `Install in Office Raccoon with: \${BOX_AGENT_NPM:-npm} install --prefix "${officeRaccoonPrefix()}" playwright; then download Chromium with "${path.join(officeRaccoonPrefix(), "node_modules", ".bin", "playwright")}" install chromium`
  );
  const bundlePath = resolveBrowserBundle();

  fs.mkdirSync(path.dirname(pptxPath), { recursive: true });
  fs.mkdirSync(outDir, { recursive: true });

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (error) {
    printBrowserInstallHint();
    throw error;
  }
  const page = await browser.newPage({
    viewport: { width: opts.width, height: opts.height },
    deviceScaleFactor: 2,
  });

  await page.exposeFunction("__writePptxBase64", base64 => {
    fs.writeFileSync(pptxPath, Buffer.from(base64, "base64"));
  });

  await page.goto(`file://${htmlPath}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await page.addScriptTag({ path: bundlePath });

  const slides = await page.locator(".slide").elementHandles();
  if (!slides.length) {
    await browser.close();
    console.error("No .slide elements found in HTML.");
    process.exit(1);
  }

  const previews = [];
  for (let i = 0; i < slides.length; i += 1) {
    const imagePath = path.join(outDir, `slide-${String(i + 1).padStart(2, "0")}.png`);
    await slides[i].screenshot({ path: imagePath });
    previews.push(imagePath);
  }

  const exportResult = await page.evaluate(
    async ({ fileName, svgVector }) => {
      const api = window.domToPptx;
      if (!api || typeof api.exportToPptx !== "function") {
        throw new Error("dom-to-pptx browser API was not loaded.");
      }
      const slideElements = Array.from(document.querySelectorAll(".slide"));
      const blob = await api.exportToPptx(slideElements, {
        fileName,
        skipDownload: true,
        autoEmbedFonts: true,
        svgAsVector: svgVector,
        layout: "LAYOUT_WIDE",
        width: 13.333,
        height: 7.5,
      });
      const base64 = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(reader.error || new Error("Failed to read PPTX blob."));
        reader.readAsDataURL(blob);
      });
      await window.__writePptxBase64(base64);
      return {
        slideCount: slideElements.length,
        bytes: blob.size,
      };
    },
    { fileName: path.basename(pptxPath), svgVector: opts.svgVector }
  );

  await browser.close();

  console.log(
    JSON.stringify(
      {
        pptx: pptxPath,
        slideCount: exportResult.slideCount,
        bytes: exportResult.bytes,
        previews,
        htmlSelfCheck: selfCheckReport,
        editableExport: "dom-to-pptx",
      },
      null,
      2
    )
  );
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
