// Text of a PDF with pdf.js (pdfjs-dist): page.getTextContent(), items joined, newline where hasEOL; pages by "\n".
// Usage: PDFJS_DIR=<dir with node_modules/pdfjs-dist> node pdfjs_text.mjs FILE.pdf
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const base = join(process.env.PDFJS_DIR ?? ".", "node_modules/pdfjs-dist/legacy/build");
const pdfjs = await import(pathToFileURL(join(base, "pdf.mjs")).href);
globalThis.pdfjsWorker = await import(pathToFileURL(join(base, "pdf.worker.mjs")).href);
const doc = await pdfjs.getDocument({ data: new Uint8Array(readFileSync(process.argv[2])), isEvalSupported: false,
                                      disableFontFace: true, verbosity: 0 }).promise;
const pages = [];
for (let i = 1; i <= doc.numPages; i++) {
  const c = await (await doc.getPage(i)).getTextContent();
  pages.push(c.items.map((it) => it.str + (it.hasEOL ? "\n" : "")).join(""));
}
process.stdout.write(pages.join("\n"));
