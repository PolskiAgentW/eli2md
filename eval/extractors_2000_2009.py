"""Compare general PDF text extractors with eli2md on Dz.U. 2000-2009 acts that also have the official HTML.

Why: Dz.U. 2000-2009 PDFs set Polish letters in QuarkXPress fonts "...PL" with MacCE codes that the PDF reads as
MacRoman ("ROZPORZÑDZENIE", "Si∏", "u˝ytkowej"), the pages are two columns, and each act's PDF is pages of the
whole issue, so its first and last page carry the neighbouring acts. The acts with HTML are the measurable
proxy for the PDF-only ones (same issues, same typesetting).

Tools: pdfplumber (page.extract_text), pypdf (page.extract_text), PyMuPDF (page.get_text),
opendataloader-pdf (markdown, default options; needs Java), pdftotext (poppler; default mode and -layout),
each raw and with TABLE (MacRoman->MacCE for the
Polish letters only, applied to the whole text), and eli2md (convert(), without OCR).
Reference: HTML main text + annexes that are text in the HTML + footnotes (eval/evaluate.py html_reference).
Metrics on word tokens (evaluate.tokens): aligned = difflib matching blocks (order counts: interleaved columns
and moved blocks lose words), bag = multiset intersection (order ignored).
  recall = matched / reference words, precision = matched / extracted words (neighbouring acts lower it).
Acts with a page without any text layer (scans) are left out: none of the tools reads them without OCR.
Acts in earlier 2000-2011 samples are left out (eli2md was tuned on some of them).
Usage: python eval/extractors_2000_2009.py SAMPLE_JSON [--out FILE] [--jobs N]
(run with a Python that has eli2md's dependencies plus pypdf, pymupdf, opendataloader-pdf==2.4.7)
"""
from __future__ import annotations

import argparse
import collections
import difflib
import glob
import json
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import fitz
import pdfplumber
import pypdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eli2md.pdf import convert  # noqa: E402
from evaluate import CACHE, html_reference, tokens  # noqa: E402

TABLE = str.maketrans({bytes([b]).decode("mac_roman"): bytes([b]).decode("mac_latin2")
                       for b in range(128, 256) if bytes([b]).decode("mac_latin2") in "ąćęłńśźżĄĆĘŁŃŚŹŻ"})
ODL_JAR = None  # set in main()
TOOLS = ["pdfplumber", "pypdf", "pymupdf", "opendataloader", "pdftotext", "pdftotext -layout"]


def pdftotext(pdf: Path, *opts: str) -> str | None:
    r = subprocess.run(["pdftotext", *opts, "-enc", "UTF-8", str(pdf), "-"], capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def odl_text(pdf: Path) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "a.pdf"
        shutil.copy(pdf, src)
        r = subprocess.run(["java", "-Djava.awt.headless=true", "-jar", ODL_JAR, str(src), "--output-dir",
                            str(Path(tmp) / "o"), "--format", "markdown", "--quiet"], capture_output=True)
        out = list((Path(tmp) / "o").rglob("*.md"))
        return out[0].read_text(encoding="utf-8") if r.returncode == 0 and out else None


def score(ref: list[str], hyp: list[str]) -> dict:
    m = sum(b.size for b in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks())
    bag = sum((collections.Counter(ref) & collections.Counter(hyp)).values())
    return {"ref": len(ref), "hyp": len(hyp), "aligned": m, "bag": bag}


def run_act(item: dict) -> dict:
    y, pos = item["year"], item["pos"]
    d = CACHE / "DU" / str(y) / str(pos)
    pdf = d / "text.pdf"
    row = {"year": y, "pos": pos, "type": item["type"]}
    ref = html_reference((d / "text.html").read_text(encoding="utf-8"))
    if not ref["usable"]:
        return row | {"skipped": "html_unusable"}
    with pdfplumber.open(pdf) as p:
        if any(not page.chars for page in p.pages):
            return row | {"skipped": "page_without_text_layer"}
        texts = {"pdfplumber": "\n".join(page.extract_text() or "" for page in p.pages)}
    texts["pypdf"] = "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(pdf).pages)
    texts["pymupdf"] = "\n".join(page.get_text() for page in fitz.open(pdf))
    texts["opendataloader"] = odl_text(pdf)
    texts["pdftotext"] = pdftotext(pdf)
    texts["pdftotext -layout"] = pdftotext(pdf, "-layout")
    for t in TOOLS:
        if texts[t] is not None:
            texts[t + "+table"] = texts[t].translate(TABLE)
    doc = convert(str(pdf), position=pos)
    texts["eli2md"] = "\n".join([b.text for b in doc.main_blocks()] + [b.text for b in doc.annex_blocks()]
                                + doc.footnotes)
    rt = tokens(ref["main"] + "\n" + "\n".join(t for t, link_only in ref["annexes"] if not link_only)
                + "\n" + ref["notes"])
    row["scores"] = {name: (score(rt, tokens(t)) if t is not None else None) for name, t in texts.items()}
    return row


def main() -> None:
    global ODL_JAR
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--out")
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    import opendataloader_pdf
    ODL_JAR = str(next(Path(opendataloader_pdf.__file__).parent.glob("jar/opendataloader-pdf-cli.jar")))
    here = Path(__file__).parent
    prev = {(i["year"], i["pos"]) for f in glob.glob(str(here / "sample_2000-2011_*.json"))
            for i in json.loads(Path(f).read_text())}
    items = [i for i in json.loads(Path(a.sample).read_text()) if (i["year"], i["pos"]) not in prev]
    print(f"{len(items)} acts after leaving out earlier samples", flush=True)
    with ProcessPoolExecutor(a.jobs, initializer=_init, initargs=(ODL_JAR,)) as ex:
        rows = list(ex.map(run_act, items))
    for r in rows:
        if "skipped" in r:
            print(f"{r['year']}/{r['pos']:<5} skipped: {r['skipped']}")
    done = [r for r in rows if "scores" in r]
    print(f"scored {len(done)} of {len(rows)} acts; reference words {sum(r['scores']['eli2md']['ref'] for r in done)}")
    names = list(done[0]["scores"])
    print("| tool | acts | aligned R | aligned P | bag R | bag P | words out / words in HTML |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for n in names:
        sub = [r["scores"][n] for r in done if r["scores"].get(n)]
        ref, hyp = sum(s["ref"] for s in sub), sum(s["hyp"] for s in sub)
        al, bag = sum(s["aligned"] for s in sub), sum(s["bag"] for s in sub)
        print(f"| {n} | {len(sub)} | {al / ref:.3f} | {al / hyp:.3f} | {bag / ref:.3f} | {bag / hyp:.3f} | "
              f"{hyp / ref:.2f} |")
    fails = sum(1 for r in done if r["scores"].get("opendataloader") is None)
    print(f"opendataloader failed on {fails} of {len(done)} PDFs")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


def _init(jar: str) -> None:
    global ODL_JAR
    ODL_JAR = jar


if __name__ == "__main__":
    main()
