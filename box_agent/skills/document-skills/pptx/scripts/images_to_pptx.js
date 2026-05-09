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
  console.error("Usage: images_to_pptx.js output.pptx slide-01.png slide-02.png ...");
  process.exit(2);
}

function requireModule(name) {
  try {
    return require(name);
  } catch (error) {
    if (error && error.code === "MODULE_NOT_FOUND") {
      console.error(`Missing dependency: ${name}`);
      console.error(
        'Install in Office Raccoon with: ${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" pptxgenjs'
      );
      process.exit(1);
    }
    throw error;
  }
}

async function main() {
  const [pptxArg, ...imageArgs] = process.argv.slice(2);
  if (!pptxArg || imageArgs.length === 0) usage();

  const pptxPath = path.resolve(pptxArg);
  const images = imageArgs.map(image => path.resolve(image));
  for (const image of images) {
    if (!fs.existsSync(image)) {
      console.error(`Image not found: ${image}`);
      process.exit(1);
    }
  }

  const pptxgen = requireModule("pptxgenjs");
  const pptx = new pptxgen();
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Office Raccoon";
  pptx.subject = "HTML-first visual deck";
  pptx.title = path.basename(pptxPath, ".pptx");
  pptx.company = "";
  pptx.lang = "zh-CN";

  const slideW = 13.333;
  const slideH = 7.5;
  for (let i = 0; i < images.length; i += 1) {
    const slide = pptx.addSlide();
    slide.background = { color: "FFFFFF" };
    slide.addImage({ path: images[i], x: 0, y: 0, w: slideW, h: slideH });
    slide.addNotes(`Image slide ${i + 1}: ${path.basename(images[i])}`);
  }

  await pptx.writeFile({ fileName: pptxPath });
  console.log(JSON.stringify({ pptx: pptxPath, slideCount: images.length, images }, null, 2));
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
