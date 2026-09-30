"""Survey of multi-character char texts in the text layer (0.6.4.dev, see math_glyphs_0.6.4.dev.md).

A glyph whose ToUnicode maps to two identical characters ("𝑘𝑘" for one 𝑘 in Cambria Math, DU/2026/1236 p. 10)
comes out doubled. This lists, per act, every char whose text has 2+ characters, with its font. It decodes the
content streams with pdfminer but builds no layout objects (a char's text is font.to_unichr(cid), as in
pdfplumber), so it reads the 64k pages of DU+MP 2025-2026 in minutes.
Usage: python eval/math_glyphs_survey.py OUT.json [--years 2025 2026] [--jobs 4]
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from pdfminer.pdfdevice import PDFDevice
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdffont import PDFUnicodeNotDefined
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

CACHE = Path.home() / "cache" / "eli"
ROOTS = {"DU": Path("/home/ai/data/dziennik-ustaw-md"), "MP": Path("/home/ai/data/monitor-polski-md")}


class _Chars(PDFDevice):
    def __init__(self, rsrcmgr):
        super().__init__(rsrcmgr)
        self.multi: Counter = Counter()  # (font, text, page) -> count
        self.fonts: set[str] = set()
        self.n = 0
        self.page = 0

    def render_string(self, textstate, seq, ncs, graphicstate):
        font = textstate.font
        name = getattr(font, "fontname", "?")
        self.fonts.add(name)
        for obj in seq:
            if not isinstance(obj, bytes):
                continue
            for cid in font.decode(obj):
                self.n += 1
                try:
                    t = font.to_unichr(cid)
                except PDFUnicodeNotDefined:
                    continue
                if isinstance(t, str) and len(t) >= 2:
                    self.multi[(name, t, self.page)] += 1


def scan(pdf: Path) -> dict:
    with open(pdf, "rb") as f:
        doc = PDFDocument(PDFParser(f))
        rm = PDFResourceManager(caching=True)
        dev = _Chars(rm)
        interp = PDFPageInterpreter(rm, dev)
        for n, page in enumerate(PDFPage.create_pages(doc), start=1):
            dev.page = n
            interp.process_page(page)
    return {"chars": dev.n, "fonts": sorted(dev.fonts),
            "multi": [[f, t, p, c] for (f, t, p), c in sorted(dev.multi.items())]}


def _job(arg):
    eli, pdf = arg
    try:
        return {"eli": eli, **scan(pdf)}
    except Exception as e:  # noqa: BLE001 - a broken PDF is reported, not fatal
        return {"eli": eli, "error": repr(e)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--years", nargs="+", default=["2025", "2026"])
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    todo = []
    for pub, root in ROOTS.items():
        for r in csv.DictReader(open(root / "index.csv", encoding="utf-8")):
            if r["year"] in a.years and r["status"] == "ok":
                todo.append((r["eli"], CACHE / pub / r["year"] / r["pos"] / "text.pdf"))
    todo.sort(key=lambda x: -x[1].stat().st_size)  # big files first: better load balance
    with ProcessPoolExecutor(a.jobs) as ex:
        res = list(ex.map(_job, todo, chunksize=4))
    a.out.write_text(json.dumps(res, ensure_ascii=False))
    print(len(res), "acts,", sum("error" in r for r in res), "errors")


if __name__ == "__main__":
    main()
