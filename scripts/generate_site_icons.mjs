import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import sharp from "sharp";

const SourceSvgPath = join("public", "favicon.svg");
const PngOutputs = [
  [join("public", "favicon-16x16.png"), 16],
  [join("public", "favicon-32x32.png"), 32],
  [join("public", "apple-touch-icon.png"), 180],
  [join("public", "icons", "site", "icon-192.png"), 192],
  [join("public", "icons", "site", "icon-512.png"), 512],
  [join("public", "icons", "site", "icon-maskable-512.png"), 512],
];
const IcoSizes = [16, 32, 48];
const IcoPath = join("public", "favicon.ico");

function ensureParentDir(path) {
  mkdirSync(dirname(path), { recursive: true });
}

async function renderPng(size) {
  // 網站 icon 以 SVG 作為唯一設計來源，避免 favicon、Apple touch icon 與 manifest icon 長相漂移。
  return sharp(SourceSvgPath, { density: 384 })
    .resize(size, size, {
      fit: "contain",
      background: { r: 16, g: 18, b: 20, alpha: 1 },
    })
    .png({
      compressionLevel: 9,
      adaptiveFiltering: true,
      palette: size <= 48,
    })
    .toBuffer();
}

function buildIco(entries) {
  const headerSize = 6;
  const directorySize = 16 * entries.length;
  let imageOffset = headerSize + directorySize;

  const header = Buffer.alloc(headerSize);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(entries.length, 4);

  const directory = Buffer.alloc(directorySize);
  entries.forEach((entry, index) => {
    const offset = index * 16;
    directory.writeUInt8(entry.size >= 256 ? 0 : entry.size, offset);
    directory.writeUInt8(entry.size >= 256 ? 0 : entry.size, offset + 1);
    directory.writeUInt8(0, offset + 2);
    directory.writeUInt8(0, offset + 3);
    directory.writeUInt16LE(1, offset + 4);
    directory.writeUInt16LE(32, offset + 6);
    directory.writeUInt32LE(entry.buffer.length, offset + 8);
    directory.writeUInt32LE(imageOffset, offset + 12);
    imageOffset += entry.buffer.length;
  });

  return Buffer.concat([header, directory, ...entries.map((entry) => entry.buffer)]);
}

for (const [outputPath, size] of PngOutputs) {
  ensureParentDir(outputPath);
  writeFileSync(outputPath, await renderPng(size));
  console.log(`已產生 ${outputPath}`);
}

const icoEntries = await Promise.all(
  IcoSizes.map(async (size) => ({
    size,
    buffer: await renderPng(size),
  })),
);
writeFileSync(IcoPath, buildIco(icoEntries));
console.log(`已產生 ${IcoPath}`);
