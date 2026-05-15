#!/usr/bin/env node
const fs = require("fs");
const Module = require("module");
const path = require("path");

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
  console.error("Usage: html_self_check.js deck.html [--width W] [--height H] [--dom-to-pptx] [--allow-local-images] [--report qa/html_self_check.json] [--verbose]");
  console.error("  If --width/--height are omitted, the first .slide element's CSS size is auto-detected.");
  process.exit(2);
}

function parseArgs(argv) {
  if (argv.length < 1) usage();
  const opts = {
    html: argv[0],
    width: null,
    height: null,
    domToPptx: false,
    allowLocalImages: false,
    report: null,
    verbose: false,
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
    } else if (arg === "--dom-to-pptx") {
      opts.domToPptx = true;
    } else if (arg === "--allow-local-images") {
      opts.allowLocalImages = true;
    } else if (arg === "--report" && value) {
      opts.report = value;
      i += 1;
    } else if (arg === "--verbose") {
      opts.verbose = true;
    } else {
      usage();
    }
  }
  if (opts.width !== null && !Number.isFinite(opts.width)) usage();
  if (opts.height !== null && !Number.isFinite(opts.height)) usage();
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

async function runHtmlSelfCheck(page, expectedWidth, expectedHeight, domToPptx = false, allowLocalImages = false) {
  return page.evaluate(
    ({ expectedWidth, expectedHeight, domToPptx, allowLocalImages }) => {
      const issues = [];
      const warnings = [];
      const slideEls = Array.from(document.querySelectorAll(".slide"));
      const badTransform = /\b(?:translate|translateX|translateY|translate3d|scale|scaleX|scaleY|scale3d|skew|skewX|skewY|matrix|matrix3d)\s*\(/i;
      const badBackground = /\b(?:radial-gradient|conic-gradient)\s*\(/i;
      const badFilter = /\b(?:brightness|contrast|saturate|hue-rotate|grayscale|sepia|invert|drop-shadow)\s*\(/i;
      const viewportUnits = /\b\d*\.?\d+(?:vh|vw|vmin|vmax)\b/i;
      const pptxTextSlackPx = 12;
      const badgeTextRe = /^[\p{L}\p{N}\p{Script=Han}\s·•|+\-_/()[\].,%:：]+$/u;
      const blockedStyleRules = [
        { name: "backdrop-filter", re: /backdrop-filter\s*:/i },
        { name: "clip-path", re: /clip-path\s*:/i },
        { name: "mix-blend-mode", re: /mix-blend-mode\s*:/i },
        { name: "text-shadow", re: /text-shadow\s*:/i },
        { name: "animation", re: /(?:^|[;\s])animation(?:-\w+)?\s*:/i },
        { name: "transition", re: /(?:^|[;\s])transition(?:-\w+)?\s*:/i },
      ];
      const px = value => Number.parseFloat(String(value || "0")) || 0;
      const ratioText = (width, height) => {
        if (!width || !height) return "unknown ratio";
        return (width / height).toFixed(4);
      };
      const sizeHint = (actualWidth, actualHeight) => {
        const expectedRatio = expectedWidth / expectedHeight;
        const actualRatio = actualWidth / actualHeight;
        const ratioDelta = Math.abs(actualRatio - expectedRatio);
        const roundedWidth = Math.round(actualWidth);
        const roundedHeight = Math.round(actualHeight);
        const parts = [
          `HTML-first editable decks expect a fixed ${expectedWidth}x${expectedHeight} canvas.`,
        ];
        if (ratioDelta > 0.01) {
          parts.push(
            `The actual aspect ratio is ${ratioText(actualWidth, actualHeight)}, expected ${ratioText(expectedWidth, expectedHeight)}.`
          );
        }
        parts.push(`Set .slide { width: ${expectedWidth}px; height: ${expectedHeight}px; } and remove scaling wrappers or viewport-sized slides.`);
        return parts.join(" ");
      };
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
      const transformedAncestor = slide => {
        let current = slide.parentElement;
        while (current && current !== document.body) {
          const transform = getComputedStyle(current).transform;
          if (transform && transform !== "none") return current;
          current = current.parentElement;
        }
        return null;
      };
      const isExportableImageSrc = src => {
        if (/^(https?:\/\/|data:)/i.test(src)) return true;
        if (!allowLocalImages) return false;
        if (/^file:/i.test(src)) return true;
        if (/^[a-z][a-z0-9+.-]*:/i.test(src)) return false;
        if (/^\/\//.test(src)) return false;
        return src && !src.startsWith("/");
      };

      if (!slideEls.length) {
        issues.push("No .slide elements found.");
        return { ok: false, slideCount: 0, issues, warnings };
      }

      if (domToPptx) {
        document
          .querySelectorAll('link[rel="stylesheet"][href*="fonts.googleapis.com"]')
          .forEach(link => {
            if (link.getAttribute("crossorigin") !== "anonymous") {
              issues.push(`Google Fonts link missing crossorigin="anonymous": ${link.getAttribute("href") || ""}`);
            }
          });
      }

      slideEls.forEach((slide, slideIndex) => {
        const slideRect = slide.getBoundingClientRect();
        const slideStyle = getComputedStyle(slide);
        const slideName = `slide-${String(slideIndex + 1).padStart(2, "0")}`;
        if (Math.abs(slideRect.width - expectedWidth) > 2 || Math.abs(slideRect.height - expectedHeight) > 2) {
          issues.push(
            `${slideName}: .slide size is ${Math.round(slideRect.width)}x${Math.round(slideRect.height)}, expected ${expectedWidth}x${expectedHeight}. ${sizeHint(slideRect.width, slideRect.height)}`
          );
        }
        if (slideStyle.position === "static") {
          warnings.push(`${slideName}: .slide should usually use position: relative for stable layout.`);
        }
        if (domToPptx && slideStyle.position !== "relative" && slideStyle.position !== "absolute") {
          issues.push(`${slideName}: dom-to-pptx requires .slide position:relative or absolute.`);
        }
        if (domToPptx && slideStyle.overflow !== "hidden") {
          issues.push(`${slideName}: dom-to-pptx requires .slide overflow:hidden.`);
        }
        if (domToPptx) {
          const ancestor = transformedAncestor(slide);
          if (ancestor) {
            issues.push(`${slideName}: .slide has a transformed ancestor; move it outside transformed wrappers.`);
          }
        }
        if (!(slide.innerText || "").trim() && !slide.querySelector("img,svg,canvas,video")) {
          issues.push(`${slideName}: slide appears empty.`);
        }

        const descendants = Array.from(slide.querySelectorAll("*"));
        descendants.forEach(el => {
          const style = getComputedStyle(el);
          const inline = el.getAttribute("style") || "";
          if (domToPptx) {
            const inlineTransform = (inline.match(/transform\s*:\s*([^;]+)/i) || [])[1] || "";
            if (inlineTransform && badTransform.test(inlineTransform)) {
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx does not support transform:${inlineTransform.trim()}; use left/top or flex centering.`);
            }
            const background = style.backgroundImage || "";
            if (badBackground.test(background)) {
              warnings.push(`${labelFor(el, slideIndex)}: dom-to-pptx only reliably supports linear gradients; avoid radial/conic gradients.`);
            }
            const filter = style.filter || "";
            if (filter && filter !== "none" && !/^\s*blur\(/i.test(filter) && badFilter.test(filter)) {
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx supports blur only; bake filter "${filter}" into the image.`);
            }
            blockedStyleRules.forEach(rule => {
              if (rule.re.test(inline)) {
                issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx blocked style ${rule.name}; use a supported alternative.`);
              }
            });
            if (viewportUnits.test(inline)) {
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx export should use fixed px, not viewport units.`);
            }
            if (["VIDEO", "AUDIO", "IFRAME", "CANVAS"].includes(el.tagName)) {
              issues.push(`${labelFor(el, slideIndex)}: <${el.tagName.toLowerCase()}> is not captured by dom-to-pptx; convert it to an image/SVG first.`);
            }
          }
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
          if (domToPptx && text) {
            const bgColor = style.backgroundColor || "";
            const hasVisibleBg = bgColor && bgColor !== "transparent" && !/rgba?\([^)]*,\s*0(?:\.0+)?\s*\)$/i.test(bgColor);
            const paddingTop = px(style.paddingTop);
            const paddingBottom = px(style.paddingBottom);
            const paddingX = px(style.paddingLeft) + px(style.paddingRight);
            const paddingY = paddingTop + paddingBottom;
            const radius = Math.max(
              px(style.borderRadius),
              px(style.borderTopLeftRadius),
              px(style.borderTopRightRadius),
              px(style.borderBottomRightRadius),
              px(style.borderBottomLeftRadius)
            );
            const hasExplicitStableSize =
              (inline && /\bwidth\s*:\s*[^;]+/i.test(inline) && /\bheight\s*:\s*[^;]+/i.test(inline)) ||
              (style.width && style.width !== "auto" && style.height && style.height !== "auto" && paddingX === 0 && paddingY === 0);
            const isFlexCentered =
              style.display.includes("flex") &&
              style.alignItems === "center" &&
              style.justifyContent === "center";
            const looksLikeShortLabel =
              text.length <= 24 &&
              !text.includes("\n") &&
              badgeTextRe.test(text) &&
              !["P", "H1", "H2", "H3", "H4", "H5", "H6", "LI"].includes(el.tagName);
            const parent = el.parentElement;
            const parentStyle = parent ? getComputedStyle(parent) : null;
            const isPlainFlexLabelChild =
              parentStyle &&
              parentStyle.display.includes("flex") &&
              parentStyle.alignItems === "center" &&
              parentStyle.justifyContent === "center" &&
              looksLikeShortLabel &&
              !hasVisibleBg &&
              paddingX === 0 &&
              paddingY === 0 &&
              radius === 0;
            if (
              looksLikeShortLabel &&
              hasVisibleBg &&
              paddingY > 0 &&
              !isFlexCentered
            ) {
              warnings.push(
                `${name}: short background text uses vertical padding to simulate centering; dom-to-pptx may shift or clip it. Use a fixed width/height outer background container with display:flex; align-items:center; justify-content:center, and an inner text element with margin:0; padding:0; line-height:1.`
              );
            }

            const hasDirectText = Array.from(el.childNodes).some(
              node => node.nodeType === Node.TEXT_NODE && (node.textContent || "").trim()
            );
            if (!isPlainFlexLabelChild && hasDirectText) {
              const range = document.createRange();
              range.selectNodeContents(el);
              const lineRects = Array.from(range.getClientRects()).filter(lineRect => lineRect.width > 1 && lineRect.height > 1);
              range.detach();
              if (lineRects.length) {
                const paddingRight = px(style.paddingRight);
                const paddingBottom = px(style.paddingBottom);
                const contentRight = rect.right - paddingRight;
                const contentBottom = rect.bottom - paddingBottom;
                const minRightSlack = Math.min(...lineRects.map(lineRect => contentRight - lineRect.right));
                const minBottomSlack = Math.min(...lineRects.map(lineRect => contentBottom - lineRect.bottom));
                if (minRightSlack < pptxTextSlackPx) {
                  warnings.push(
                    `${name}: text has only ${Math.round(minRightSlack)}px right slack; PowerPoint may rewrap after dom-to-pptx. Widen the text box by 16-24px or reduce font-size.`
                  );
                }
                if (minBottomSlack < pptxTextSlackPx) {
                  warnings.push(
                    `${name}: text has only ${Math.round(minBottomSlack)}px bottom slack; leave extra vertical room for PowerPoint font metrics.`
                  );
                }
              }
            }
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
          const src = img.getAttribute("src") || "";
          if (domToPptx) {
            if (!isExportableImageSrc(src)) {
              issues.push(`${name}: dom-to-pptx images must use http(s), data:, or exporter-supported local relative/file URLs.`);
            }
            if (img.getAttribute("loading") === "lazy") {
              issues.push(`${name}: remove loading="lazy"; it can race dom-to-pptx export.`);
            }
          }
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
    { expectedWidth, expectedHeight, domToPptx, allowLocalImages }
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
    'Install in Office Raccoon with: ${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" playwright; then download Chromium with "$HOME/Library/Application Support/office-raccoon/node_modules/.bin/playwright" install chromium'
  );

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (error) {
    printBrowserInstallHint();
    throw error;
  }

  const probeViewport = { width: opts.width || 1920, height: opts.height || 1080 };
  let page = await browser.newPage({
    viewport: probeViewport,
    deviceScaleFactor: 1,
  });
  await page.goto(`file://${htmlPath}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  await page.evaluate(() => document.fonts && document.fonts.ready);

  let detectedWidth = opts.width;
  let detectedHeight = opts.height;

  if (detectedWidth === null || detectedHeight === null) {
    const detected = await page.evaluate(() => {
      const s = document.querySelector(".slide");
      if (!s) return null;
      const cs = getComputedStyle(s);
      return { w: parseFloat(cs.width) || 0, h: parseFloat(cs.height) || 0 };
    });
    if (detected && detected.w > 0 && detected.h > 0) {
      detectedWidth = detected.w;
      detectedHeight = detected.h;
    } else {
      detectedWidth = 1920;
      detectedHeight = 1080;
    }
  }

  const needsResize =
    Math.abs(probeViewport.width - detectedWidth) > 2 ||
    Math.abs(probeViewport.height - detectedHeight) > 2;
  if (needsResize) {
    await page.close();
    page = await browser.newPage({
      viewport: { width: detectedWidth, height: detectedHeight },
      deviceScaleFactor: 2,
    });
    await page.goto(`file://${htmlPath}`, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
    await page.evaluate(() => document.fonts && document.fonts.ready);
  } else {
    await page.setViewportSize({ width: detectedWidth, height: detectedHeight });
  }

  const report = await runHtmlSelfCheck(
    page,
    detectedWidth,
    detectedHeight,
    opts.domToPptx,
    opts.allowLocalImages
  );
  await browser.close();

  const reportText = JSON.stringify(report, null, 2);
  if (opts.report) {
    const reportPath = path.resolve(opts.report);
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, `${reportText}\n`);
  }
  if (!opts.report || opts.verbose) {
    console.log(reportText);
  }
  console.log(
    `HTML self-check: ${report.ok ? "PASS" : "FAIL"} (${report.slideCount} slides, ${report.issues.length} issues, ${report.warnings.length} warnings)`
  );
  if (opts.report) {
    console.log(`Report: ${path.resolve(opts.report)}`);
  }
  if (!report.ok) {
    report.issues.slice(0, 8).forEach(issue => console.log(`- ${issue}`));
    if (report.issues.length > 8) {
      console.log(`- ... ${report.issues.length - 8} more issue(s) in report`);
    }
  }
  if (!report.ok) {
    process.exit(1);
  }
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
