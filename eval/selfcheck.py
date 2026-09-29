"""Reference-free check for acts without HTML (2025+): does the Markdown keep the PDF's words?

For each act: word tokens of the whole PDF text layer vs word tokens of the Markdown body
(front matter, markers and headings markup removed). Reports the share of PDF tokens found in
the output (multiset overlap, order ignored) and the share of output tokens found in the PDF.
The masthead and running headers are removed from the PDF side, as the output drops them too.
Low values point at dropped text (e.g. text wrongly treated as hidden); scanned pages (no text layer)
are invisible to this check.
Usage: python eval/selfcheck.py DATA_ROOT [--limit N] [--out FILE] [--jobs N]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber
from pdfplumber.utils import extract_words

CACHE = Path.home() / "cache" / "eli"
TOKEN = re.compile(r"\w+")
CID = re.compile(r"\(cid:\d+\)")
HEADER = re.compile(r"(?:Dziennik Ustaw|Monitor Polski)\s*[–-]\s*\d+\s*[–-]\s*Poz\.\s*\d+")
# the converter writes small digits as ¹/₂ (Art. 41¹); extract_words glues them to the word ("411")
SCRIPTS = {ord(c): str(i % 10) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉")}


def tokens(text: str) -> Counter:
    """Tokens keyed by their sorted letters: plain extract_words reads text on rotated pages
    (landscape tables) backwards ("isw" for "wsi"), which the converter reads correctly."""
    return Counter("".join(sorted(t.lower())) for t in TOKEN.findall(text.translate(SCRIPTS)))


def _angle(c: dict) -> int:
    return round(math.degrees(math.atan2(c["matrix"][1], c["matrix"][0])) / 90) % 4 * 90


def _upright(c: dict, rot: int, w: float, h: float) -> dict:
    """The char's box in a frame where text written at `rot` degrees runs left-to-right."""
    x0, x1, t, b = c["x0"], c["x1"], c["top"], c["bottom"]
    if rot == 90:
        x0, x1, t, b = h - b, h - t, x0, x1
    elif rot == 270:
        x0, x1, t, b = t, b, w - x1, w - x0
    elif rot == 180:
        x0, x1, t, b = w - x1, w - x0, h - b, h - t
    return {**c, "x0": x0, "x1": x1, "top": t, "bottom": b, "upright": True}


def page_text(p) -> str:
    """Words of a page. On a page of mostly rotated text (landscape tables in small print) extract_words
    joins lines of neighbouring table columns (it clusters lines transitively within 3pt) and interleaves
    their letters (MP/2025/541 p. 47: "WY P P O O D SA M Ż ..."); such a page is read upright in stream
    order (on pp. 46-49 there 3602 words; pdfium's text of those pages has 3600)."""
    angles = Counter(_angle(c) for c in p.chars)
    if not angles or angles.most_common(1)[0][0] == 0:
        return " ".join(w["text"] for w in p.extract_words())
    w, h = float(p.width), float(p.height)
    return " ".join(x["text"] for rot in angles for x in extract_words(
        [_upright(c, rot, w, h) for c in p.chars if _angle(c) == rot], use_text_flow=True))


def md_body(md: str) -> str:
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    md = re.sub(r"\A\s*# .*\n", "", md)  # title from metadata; the PDF has it in the body already
    md = re.sub(r"\[\^\w+\]:?", " ", md)
    md = re.sub(r"^> \[(Stron[ay]|Na stronie) .*\]$", "", md, flags=re.M)  # notes on non-text content
    md = re.sub(r"^> .*$", "", md, flags=re.M)  # OCR text (0.6.0): its pages have no text layer to compare with
    return re.sub(r"^#+ ", "", md, flags=re.M)


def ocr_pages(md: str) -> set[int]:
    """Pages the output read by OCR (front matter `pages_ocr: "2-23, 30"`): their text layer is unreadable
    ("(cid:N)" glyphs), and their OCR text is left out of the output side, so they are left out of both."""
    m = re.search(r'^pages_ocr: "([^"]*)"', md, re.M)
    pages: set[int] = set()
    for part in (m.group(1).split(",") if m else []):
        a, _, b = part.strip().partition("-")
        if a:
            pages.update(range(int(a), int(b or a) + 1))
    return pages


def watermark(o: dict) -> bool:
    """The invisible diagonal "www.rcl.gov.pl" over MP 2012 pages (same test as eli2md.pdf._watermark, kept
    here so that the check runs against any converter version): not text of the act."""
    if o.get("object_type") != "char" or o.get("tag") != "Artifact" or "matrix" not in o:
        return False
    deg = math.degrees(math.atan2(o["matrix"][1], o["matrix"][0])) % 90
    return 10 < deg < 80


def check(md_file: Path, pdf_file: Path) -> dict:
    md = md_file.read_text(encoding="utf-8")
    skip = ocr_pages(md)
    with pdfplumber.open(pdf_file) as pdf:
        parts = []
        for n, p in enumerate(pdf.pages, start=1):
            if n in skip:
                parts.append("")
            else:
                q = p.filter(lambda o: not watermark(o)) if any(watermark(c) for c in p.chars) else p
                parts.append(page_text(q))
            p.close()
    # the output deliberately drops the masthead (page 1, up to "Poz. N", in early MP 2012 "Pozycja N")
    # and running headers
    parts[0] = re.sub(r"\A.*?Poz(?:\.|ycja)\s*\d+", "", parts[0], count=1, flags=re.S)
    raw = CID.sub(" ", HEADER.sub(" ", "\n".join(parts)))  # unmapped glyphs are not words (dropped since 0.6.1)
    tp, tm = tokens(raw), tokens(md_body(md))
    common = sum((tp & tm).values())
    return {"pdf_tokens": sum(tp.values()), "md_tokens": sum(tm.values()),
            "kept": common / max(1, sum(tp.values())), "grounded": common / max(1, sum(tm.values()))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--publisher", choices=("DU", "MP"), default="DU")
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(a.root / "index.csv", encoding="utf-8")) if r["status"] == "ok"]
    if a.limit:
        rows = rows[: a.limit]
    pub = a.publisher
    files = [(a.root / pub / r["year"] / f"{pub}-{r['year']}-{r['pos']}.md",
              CACHE / pub / r["year"] / r["pos"] / "text.pdf") for r in rows]
    with ProcessPoolExecutor(max(1, a.jobs)) as ex:
        res = [{"eli": r["eli"], "type": r["type"], "pages": int(r["pages"]), **c}
               for r, c in zip(rows, ex.map(check, *zip(*files), chunksize=8))]
    res.sort(key=lambda x: x["kept"])
    for x in res[:25]:
        print(f"{x['eli']:14} {x['type'][:14]:14} kept={x['kept']:.3f} grounded={x['grounded']:.3f} "
              f"pdf={x['pdf_tokens']} md={x['md_tokens']}")
    tp = sum(x["pdf_tokens"] for x in res)
    kept = sum(x["kept"] * x["pdf_tokens"] for x in res)
    print(f"n={len(res)} micro kept={kept / max(1, tp):.4f}; kept<0.95: {sum(x['kept'] < 0.95 for x in res)}")
    if a.out:
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
