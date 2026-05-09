#!/usr/bin/env node
const fs = require("fs");
const Module = require("module");
const path = require("path");

const managedNodeModules = path.join(
  process.env.HOME || "",
  "Library",
  "Application Support",
  "office-raccoon",
  "node_modules"
);
process.env.NODE_PATH = process.env.NODE_PATH
  ? `${managedNodeModules}${path.delimiter}${process.env.NODE_PATH}`
  : managedNodeModules;
Module._initPaths();

function usage() {
  console.error("Usage: html_self_check.js deck.html [--width 1280] [--height 720]");
  process.exit(2);
}

function parseArgs(argv) {
  if (argv.length < 1) usage();
  const opts = {
    html: argv[0],
    width: 1280,
    height: 720,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = argv[i + 1];
    if (arg === "--width" && value) {
      opts.width = Number(value);
      i += 1;
    } else if (arg === "--height" && value) {
      opts.height = Number(value);
      i += 1;
    } else {
      usage();
    }
  }
  if (!Number.isFinite(opts.width) || !Number.isFinite(opts.height)) usage();
  return opts;
}

function requireModule(name, installHint) {
  try {
    return require(name);
  } catch (error) {
    if (error && error.code === "MODULE_NOT_FOUND") {
      console.error(`Missing dependency: ${name}`);
      console.error(installHint);
      process.exit(1);
    }
    throw error;
  }
}

async function runHtmlSelfCheck(page, expectedWidth, expectedHeight) {
  return page.evaluate(
    ({ expectedWidth, expectedHeight }) => {
      const issues = [];
      const warnings = [];
      const slideEls = Array.from(document.querySelectorAll(".slide"));
      const px = value => Number.parseFloat(String(value || "0")) || 0;
      const isVisible = (el, style = getComputedStyle(el)) => {
        const rect = el.getBoundingClientRect();
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          px(style.opacity) > 0.01 &&
          rect.width > 0.5 &&
          rect.height > 0.5
        );
      };
      const labelFor = (el, slideIndex) => {
        const classes = typeof el.className === "string" ? el.className.trim() : "";
        const id = el.id ? `#${el.id}` : "";
        const tag = el.tagName.toLowerCase();
        return `slide-${String(slideIndex + 1).padStart(2, "0")} ${tag}${id}${classes ? `.${classes.split(/\s+/).join(".")}` : ""}`;
      };

      if (!slideEls.length) {
        issues.push("No .slide elements found.");
        return { ok: false, slideCount: 0, issues, warnings };
      }

      slideEls.forEach((slide, slideIndex) => {
        const slideRect = slide.getBoundingClientRect();
        const slideStyle = getComputedStyle(slide);
        const slideName = `slide-${String(slideIndex + 1).padStart(2, "0")}`;
        if (Math.abs(slideRect.width - expectedWidth) > 2 || Math.abs(slideRect.height - expectedHeight) > 2) {
          issues.push(
            `${slideName}: .slide size is ${Math.round(slideRect.width)}x${Math.round(slideRect.height)}, expected ${expectedWidth}x${expectedHeight}.`
          );
        }
        if (slideStyle.position === "static") {
          warnings.push(`${slideName}: .slide should usually use position: relative for stable layout.`);
        }
        if (!(slide.innerText || "").trim() && !slide.querySelector("img,svg,canvas,video")) {
          issues.push(`${slideName}: slide appears empty.`);
        }

        const descendants = Array.from(slide.querySelectorAll("*"));
        descendants.forEach(el => {
          const style = getComputedStyle(el);
          if (!isVisible(el, style)) return;
          const rect = el.getBoundingClientRect();
          const name = labelFor(el, slideIndex);
          const left = rect.left - slideRect.left;
          const top = rect.top - slideRect.top;
          const right = rect.right - slideRect.left;
          const bottom = rect.bottom - slideRect.top;

          if (left < -2 || top < -2 || right > slideRect.width + 2 || bottom > slideRect.height + 2) {
            issues.push(`${name}: visible content extends outside the slide bounds.`);
          }

          const text = (el.innerText || "").trim();
          if (text && (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2)) {
            const overflowX = el.scrollWidth > el.clientWidth + 2;
            const overflowY = el.scrollHeight > el.clientHeight + 2;
            issues.push(
              `${name}: text/content overflow detected (${overflowX ? "x" : ""}${overflowY ? "y" : ""}).`
            );
          }

          const classAndRole = `${el.className || ""} ${el.getAttribute("role") || ""} ${el.getAttribute("aria-label") || ""}`;
          const looksLikeBar = /\b(fill|bar|progress|meter|概率|percent|percentage|rank)\b/i.test(classAndRole);
          if (looksLikeBar) {
            const widthStyle = el.style && el.style.width;
            const hasProgressValue =
              widthStyle ||
              el.getAttribute("aria-valuenow") ||
              el.getAttribute("data-value") ||
              el.getAttribute("data-percent");
            if (hasProgressValue && style.display === "inline") {
              issues.push(`${name}: progress/fill-like element is display:inline; width/height may not render. Use display:block or inline-block.`);
            }
            if (hasProgressValue && (rect.width < 2 || rect.height < 2)) {
              issues.push(`${name}: progress/fill-like element has near-zero rendered size.`);
            }
          }
        });

        Array.from(slide.querySelectorAll("img")).forEach(img => {
          const name = labelFor(img, slideIndex);
          if (!img.complete || img.naturalWidth === 0 || img.naturalHeight === 0) {
            issues.push(`${name}: image did not load.`);
          }
        });
      });

      return {
        ok: issues.length === 0,
        slideCount: slideEls.length,
        issues,
        warnings,
      };
    },
    { expectedWidth, expectedHeight }
  );
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const htmlPath = path.resolve(opts.html);
  if (!fs.existsSync(htmlPath)) {
    console.error(`HTML file not found: ${htmlPath}`);
    process.exit(1);
  }

  const { chromium } = requireModule(
    "playwright",
    'Install in Office Raccoon with: ${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" playwright'
  );

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: opts.width, height: opts.height },
    deviceScaleFactor: 2,
  });
  await page.goto(`file://${htmlPath}`, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts && document.fonts.ready);
  const report = await runHtmlSelfCheck(page, opts.width, opts.height);
  await browser.close();

  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) {
    process.exit(1);
  }
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
