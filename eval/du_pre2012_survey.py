"""Survey: text layer of Dziennik Ustaw PDFs 1918-2011 vs tesseract OCR (eli2md 0.6.5 era).

Measurement only; eli2md code is not changed. Report: eval/du_pre2012_survey_0.6.5.md. Stages (each resumes
from files in WORK = $DU_PRE2012_WORK, default /tmp/du_pre2012):

    python eval/du_pre2012_survey.py lists     # year lists 1918-2011 from the ELI API -> counts per year
    python eval/du_pre2012_survey.py sample    # stratified random sample, 8 acts per era (seed 20260930) + EXTRA
    python eval/du_pre2012_survey.py measure   # download (eli2md.eli.fetch, shared cache), text layer, OCR (pol)
    python eval/du_pre2012_survey.py ocr2      # the same pages again with tesseract pol+eng (eli2md's first pass)
    python eval/du_pre2012_survey.py probe     # producer/fonts of fixed positions around the format changes
    python eval/du_pre2012_survey.py summary   # aggregate -> OUT json
    (relayer: recompute the layer fields of already measured pages from cached PDFs; not needed after measure)

Requests are sequential with >= 1 s between them. Quality proxy (no gold standard): share of alphabetic tokens of
length >= 3 that libhunspell (pl_PL, hunspell-pl) accepts, after joining words hyphenated at a line end. Computed
for the PDF's text layer (pdfplumber extract_text; also per column and, for Univers-PL fonts, with the encoding
remapped) and for tesseract 5.5 (psm 3) of the same page rendered at 300 dpi with pypdfium2, on at most 3 pages
per act (1, middle, last).
"""
from __future__ import annotations

import argparse
import ctypes
import difflib
import json
import os
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections import Counter
from pathlib import Path

API = "https://api.sejm.gov.pl/eli/acts"
UA = "eli2md-eval/0.1 (du_pre2012 survey; sequential, 1 req/s)"
WORK = Path(os.environ.get("DU_PRE2012_WORK", "/tmp/du_pre2012"))
OUT = Path(__file__).with_name("du_pre2012_survey_0.6.5.json")
YEARS = range(1918, 2012)
SEED = 20260930
PER_ERA = 8
ERAS = [("1918-1939", 1918, 1939), ("1940-1989", 1940, 1989), ("1990-2000", 1990, 2000), ("2001-2011", 2001, 2011)]
EXTRA = ["DU/1935/1", "DU/1964/16", "DU/1990/1", "DU/1997/78", "DU/2005/1", "DU/2010/1"]  # already cached, not random
DPI = 300
MAX_OCR_PAGES = 3
MAX_LAYER_PAGES = 150  # whole-document layer metrics on at most this many pages
TEXT_CHARS = 20  # non-space chars on a page from which it counts as having a text layer
SCAN_SHARE = 0.8  # images covering this share of the page: the page is a scan
DIACRITICS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")
WORD = re.compile(r"[^\W\d_]+")
HYPHEN_EOL = re.compile(r"(\w)[-­¬]\s*\n\s*(\w)")
ODD = re.compile(r"[^\sA-Za-z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ.,;:!?()\[\]\"'„”“’‘\-–—/§%&*+=<>°ÓéüöäÉ]")


# ---------------------------------------------------------------- hunspell (libhunspell via ctypes)
class Hunspell:
    def __init__(self, aff="/usr/share/hunspell/pl_PL.aff", dic="/usr/share/hunspell/pl_PL.dic"):
        self.lib = ctypes.CDLL("libhunspell-1.7.so.0")
        self.lib.Hunspell_create.restype = ctypes.c_void_p
        self.lib.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.h = self.lib.Hunspell_create(aff.encode(), dic.encode())
        enc = re.search(r"^SET\s+(\S+)", Path(aff).read_text(encoding="latin-1"), re.M)
        self.enc = enc.group(1) if enc else "utf-8"
        self.cache: dict[str, bool] = {}

    def ok(self, w: str) -> bool:
        if w not in self.cache:
            try:
                b = w.encode(self.enc)
            except UnicodeEncodeError:  # a letter outside ISO-8859-2 (Cyrillic, Greek, ...): not a Polish word
                self.cache[w] = False
            else:
                self.cache[w] = bool(self.lib.Hunspell_spell(self.h, b))
        return self.cache[w]


HS: Hunspell | None = None
# Spelling before the 1936 reform that hunspell (modern) rejects: "materjał", "kancelarji", "akcyj", "niniejszem",
# "pojedyńczy". A rejected token counts as valid in `valid_prewar` if one of these rewrites is accepted.
PREWAR = [(re.compile(r"([bcdfghklłmnprstwz])j(?=[aąeęioóuy])"), r"\1i"), (re.compile(r"yj$"), "ii"),
          (re.compile(r"yj$"), "ji"), (re.compile(r"em$"), "ym"), (re.compile(r"em$"), "im"), (re.compile(r"ńc"), "nc")]
PL_FONT = re.compile(r"PL$")
# a unit mark "§ 12." read as "8 12.", "$12.", "812." (seen in tesseract pol output): at a line start
PARA_MISREAD = re.compile(r"^\s*(?:[8$S5&]\s?\d{1,3}[a-z]?\.\s|81\.\s)", re.M)
HEADER_POS = re.compile(r"Poz\.?\s*(\d+)(?:\s*(?:i|—|–|-)\s*(\d+))?")
PARA = re.compile(r"§\s*\d")
ART = re.compile(r"\bArt\.\s*\d")


def prewar_ok(w: str) -> bool:
    cands = {w}
    for rx, rep in PREWAR:
        cands |= {rx.sub(rep, c) for c in cands}
    return any(HS.ok(c) for c in cands - {w})


def join_lines(t: str) -> str:
    """Join a word broken at a line end without a hyphen (the hyphen lost: "jed" / "nostek") when the joined word
    is valid and a part is not."""
    lines = t.split("\n")
    for i in range(len(lines) - 1):
        a = re.search(r"([^\W\d_]+)\s*$", lines[i])
        b = re.match(r"\s*([^\W\d_]+)", lines[i + 1])
        if a and b and HS.ok(a.group(1) + b.group(1)) and not (HS.ok(a.group(1)) and HS.ok(b.group(1))):
            lines[i] = lines[i][:a.start(1)] + a.group(1) + b.group(1)
            lines[i + 1] = lines[i + 1][b.end(1):]
    return "\n".join(lines)


def text_metrics(text: str) -> dict:
    global HS
    HS = HS or Hunspell()
    t = HYPHEN_EOL.sub(r"\1\2", text)
    toks = [w for w in WORD.findall(t) if len(w) >= 3]
    bad = [w for w in toks if not HS.ok(w)]
    joined = [w for w in WORD.findall(join_lines(t)) if len(w) >= 3]
    letters = [c for c in t if c.isalpha()]
    nonspace = [c for c in t if not c.isspace()]
    bad_prewar = [w for w in bad if not prewar_ok(w)]
    return {
        "tokens": len(toks),
        "valid": round(1 - len(bad) / len(toks), 4) if toks else None,
        "valid_prewar": round(1 - len(bad_prewar) / len(toks), 4) if toks else None,
        "valid_joined": round(sum(map(HS.ok, joined)) / len(joined), 4) if joined else None,
        "para_marks": len(PARA.findall(t)), "art_marks": len(ART.findall(t)),
        "para_misread": len(PARA_MISREAD.findall(t)),
        "header_pos": sorted({int(n) for m in HEADER_POS.finditer("\n".join(t.splitlines()[:6]))
                              for n in m.groups() if n}),
        "diacritic_share": round(sum(c in DIACRITICS for c in letters) / len(letters), 4) if letters else None,
        "odd_char_share": round(len(ODD.findall(t)) / len(nonspace), 4) if nonspace else None,
        "top_invalid": Counter(bad).most_common(12),
    }


def token_list(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(HYPHEN_EOL.sub(r"\1\2", text)) if len(w) >= 3]


# ---------------------------------------------------------------- API
_last = [0.0]


def get(url: str) -> bytes:
    wait = 1.0 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    finally:
        _last[0] = time.time()


def year_list(year: int) -> dict:
    f = WORK / "lists" / f"{year}.json"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(get(f"{API}/DU/{year}"))
    return json.loads(f.read_text())


def cmd_lists(_a) -> None:
    rows = []
    for y in YEARS:
        d = year_list(y)
        items = d.get("items", [])
        rows.append({"year": y, "count": d.get("count"), "totalCount": d.get("totalCount"), "items": len(items),
                     "textPDF": sum(bool(i.get("textPDF")) for i in items),
                     "textHTML": sum(bool(i.get("textHTML")) for i in items),
                     "pdf_no_html": sum(bool(i.get("textPDF")) and not i.get("textHTML") for i in items)})
        print(rows[-1], flush=True)
    (WORK / "year_counts.json").write_text(json.dumps(rows, indent=1))


# ---------------------------------------------------------------- sample
def cmd_sample(_a) -> None:
    rng = random.Random(SEED)
    sample = []
    for name, y0, y1 in ERAS:
        items = sorted(((i["year"], i["pos"], i) for y in range(y0, y1 + 1) for i in year_list(y).get("items", [])
                        if i.get("textPDF")), key=lambda t: (t[0], t[1]))
        for y, p, i in rng.sample(items, PER_ERA):
            sample.append({"eli": f"DU/{y}/{p}", "era": name, "random": True, "type": i.get("type"),
                           "title": i.get("title"), "textHTML": bool(i.get("textHTML")),
                           "displayAddress": i.get("displayAddress")})
    for eli in EXTRA:
        _, y, p = eli.split("/")
        it = next((i for i in year_list(int(y)).get("items", []) if i["pos"] == int(p)), {})
        era = next(n for n, y0, y1 in ERAS if y0 <= int(y) <= y1)
        sample.append({"eli": eli, "era": era, "random": False, "type": it.get("type"), "title": it.get("title"),
                       "textHTML": bool(it.get("textHTML")), "displayAddress": it.get("displayAddress")})
    (WORK / "sample.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1))
    for s in sample:
        print(s["era"], s["eli"], s["random"], s["type"], (s["title"] or "")[:70])


# ---------------------------------------------------------------- measure
def ocr_tsv(png: Path, lang: str = "pol") -> tuple[str, float | None, int, list[tuple[int, int]]]:
    """(text, median word confidence, words, word x-extents) of tesseract psm 3 (pol: no "§" in its model)."""
    env = {**os.environ, "OMP_THREAD_LIMIT": "2"}
    out = subprocess.run(["tesseract", str(png), "stdout", "-l", lang, "--psm", "3", "tsv"], capture_output=True,
                         env=env, check=True, timeout=300).stdout.decode("utf-8", "replace")
    lines: dict[tuple, list[str]] = {}
    confs, xs = [], []
    for row in out.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        lines.setdefault((int(f[2]), int(f[3]), int(f[4])), []).append(f[11])
        confs.append(float(f[10]))
        xs.append((int(f[6]), int(f[6]) + int(f[8])))
    text, prev = [], None
    for k, ws in lines.items():
        if prev is not None and k[:2] != prev[:2]:
            text.append("")  # paragraph break
        text.append(" ".join(ws))
        prev = k
    return "\n".join(text), (statistics.median(confs) if confs else None), len(confs), xs


def columns(xs: list[tuple[float, float]]) -> dict:
    """Two-column test from word x-extents: share of words crossing the middle of the text block."""
    if len(xs) < 60:
        return {"words": len(xs), "cross_mid": None, "two_col": None}
    x0, x1 = min(a for a, _ in xs), max(b for _, b in xs)
    mid, pad = (x0 + x1) / 2, (x1 - x0) * 0.005
    cross = sum(1 for a, b in xs if a < mid - pad and b > mid + pad)
    left = sum(1 for _, b in xs if b <= mid)
    right = sum(1 for a, _ in xs if a >= mid)
    share = cross / len(xs)
    return {"words": len(xs), "cross_mid": round(share, 4), "mid": round(mid, 1),
            "two_col": share < 0.03 and left > 0.25 * len(xs) and right > 0.25 * len(xs)}


def layer_texts(page, info: dict) -> None:
    """Layer text in pdfplumber's order (rows across the page, as eli2md reads it) and, for a two-column page,
    left column then right column (split at the middle of the text block), with their metrics."""
    text = page.extract_text() or ""
    cols = columns([(w["x0"], w["x1"]) for w in page.extract_words()])
    info["layer_text"], info["layer"], info["layer_cols"] = text, text_metrics(text), cols
    if cols.get("two_col"):
        mid = cols["mid"]
        half = [page.filter(lambda o, left=left: o.get("object_type") != "char"
                            or (((o["x0"] + o["x1"]) / 2) < mid) == left).extract_text() or "" for left in (True, False)]
        split = half[0] + "\n" + half[1]
    else:
        split = text
    info["layer_split_text"], info["layer_split"] = split, text_metrics(split)
    # Experiment (not in eli2md): QuarkXPress PDFs of 2000-2010 set in "Univers-PL" fonts map Polish letters
    # through MacRoman (ł -> ∏, ą -> à, ę -> ´); their codes are MacCE (mac_latin2). Remap those chars, split words
    # at gaps > 1.5 pt (spaces after one-letter words are gaps, not chars: "zdnia") and read columns in order.
    pl = [c for c in page.chars if PL_FONT.search(c.get("fontname", ""))]
    if len(pl) >= TEXT_CHARS:
        for c in pl:
            try:
                c["text"] = c["text"].encode("mac_roman").decode("mac_latin2")
            except UnicodeError:
                pass
        parts = ([lambda o: True] if not cols.get("two_col") else
                 [lambda o, left=left: o.get("object_type") != "char" or (((o["x0"] + o["x1"]) / 2) < cols["mid"]) == left
                  for left in (True, False)])
        fixed = "\n".join(page.filter(p).extract_text(x_tolerance=1.5) or "" for p in parts)
        info["layer_fixed_text"], info["layer_fixed"] = fixed, text_metrics(fixed)


def compare(info: dict) -> None:
    """Agreement of the OCR tokens with the layer tokens (in order, and as multisets)."""
    b = token_list(info["ocr_text"])
    for key, src in (("", "layer_text"), ("_split", "layer_split_text"), ("_fixed", "layer_fixed_text")):
        if src not in info:
            continue
        a = token_list(info[src])
        info["agree" + key] = round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 4) if a and b else None
        ca, cb = Counter(a), Counter(b)
        info["bag_overlap" + key] = round(sum((ca & cb).values()) / max(len(a), len(b)), 4) if a and b else None


def page_info(page) -> dict:
    chars = page.chars
    ns = [c for c in chars if c["text"].strip()]
    area = float(page.width * page.height)
    cover, big = 0.0, None
    for im in page.images:
        w = max(0.0, min(page.width, im["x1"]) - max(0.0, im["x0"]))
        h = max(0.0, min(page.height, im["bottom"]) - max(0.0, im["top"]))
        cover += w * h
        if big is None or w * h > big[0]:
            big = (w * h, im)
    info = {"chars": len(ns), "cid": sum(1 for c in ns if c["text"].startswith("(cid:")),
            "image_cover": round(min(1.0, cover / area), 3), "images": len(page.images),
            "fonts": Counter(c.get("fontname", "") for c in ns).most_common(3),
            "width_pt": round(float(page.width), 1), "height_pt": round(float(page.height), 1)}
    if big:
        im = big[1]
        src = im.get("srcsize") or (0, 0)
        wpt = max(1e-6, float(im["x1"] - im["x0"]))
        filt = im["stream"].get_any(("Filter", "F")) if hasattr(im.get("stream"), "get_any") else None
        info["scan_img"] = {"srcsize": list(src), "bits": im.get("bits"), "dpi": round(src[0] / (wpt / 72)),
                            "filter": str(filt)[:40] if filt else None}
    info["scan"] = info["image_cover"] >= SCAN_SHARE
    info["text_layer"] = info["chars"] >= TEXT_CHARS
    return info


def ocr_pages_of(n: int) -> list[int]:
    return list(range(1, n + 1)) if n <= MAX_OCR_PAGES else sorted({1, (n + 1) // 2, n})


def measure(eli: str) -> dict:
    import pdfplumber
    import pypdfium2 as pdfium
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eli2md.eli import fetch
    t0 = time.time()
    meta, pdf_path = fetch(eli)
    res: dict = {"eli": eli, "pdf_bytes": pdf_path.stat().st_size, "texts": meta.get("texts"),
                 "download_s": round(time.time() - t0, 1)}
    with pdfplumber.open(pdf_path) as pdf:
        md = pdf.metadata or {}
        res["pdf_meta"] = {k: str(md.get(k))[:80] for k in ("Producer", "Creator", "CreationDate", "ModDate") if md.get(k)}
        n = len(pdf.pages)
        res["pages"] = n
        want = ocr_pages_of(n)
        pages, layer_all = [], []
        for pno, page in enumerate(pdf.pages, start=1):
            if pno > MAX_LAYER_PAGES and pno not in want:
                page.close()
                continue
            info = page_info(page)
            info["page"] = pno
            text = page.extract_text() or ""
            layer_all.append(text)
            if pno in want:
                layer_texts(page, info)
            pages.append(info)
            page.close()
        res["layer_pages_measured"] = min(n, MAX_LAYER_PAGES)
        res["layer_doc"] = text_metrics("\n".join(layer_all))
        del res["layer_doc"]["top_invalid"]
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for info in pages:
            if info["page"] not in want:
                continue
            img = doc[info["page"] - 1].render(scale=DPI / 72, grayscale=True).to_pil()
            with tempfile.TemporaryDirectory() as td:
                png = Path(td) / "p.png"
                img.save(png)
                t1 = time.time()
                try:
                    text, conf, nw, xs = ocr_tsv(png)
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
                    info["ocr_error"] = repr(e)[:200]
                    continue
            info["ocr_s"] = round(time.time() - t1, 1)
            info["ocr_text"] = text
            info["ocr"] = text_metrics(text)
            info["ocr"]["median_conf"] = conf
            info["ocr_cols"] = columns(xs)
            compare(info)
    finally:
        doc.close()
    res["page_info"] = pages
    res["seconds"] = round(time.time() - t0, 1)
    return res


def cmd_measure(a) -> None:
    sample = json.loads((WORK / "sample.json").read_text())
    outdir = WORK / "acts"
    outdir.mkdir(exist_ok=True)
    for s in sample:
        f = outdir / (s["eli"].replace("/", "_") + ".json")
        if f.exists():
            continue
        if a.only and s["eli"] not in a.only:
            continue
        try:
            r = measure(s["eli"])
        except Exception as e:  # noqa: BLE001 - record and go on
            r = {"eli": s["eli"], "error": repr(e)[:300]}
        r.update({k: s[k] for k in ("era", "random", "type", "title", "textHTML", "displayAddress")})
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        o = [p for p in r.get("page_info", []) if "ocr" in p]
        print(s["eli"], r.get("pages"), r.get("error", ""),
              [(p["page"], p["chars"], p["image_cover"], p["layer"]["valid"], p["ocr"]["valid"]) for p in o],
              r.get("seconds"), flush=True)


def cmd_relayer(_a) -> None:
    import pdfplumber
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eli2md.eli import fetch
    for f in sorted((WORK / "acts").glob("*.json")):
        r = json.loads(f.read_text())
        if "error" in r:
            continue
        _, pdf_path = fetch(r["eli"])
        with pdfplumber.open(pdf_path) as pdf:
            for info in r["page_info"]:
                if "layer" in info:
                    page = pdf.pages[info["page"] - 1]
                    layer_texts(page, info)
                    page.close()
                    if "ocr_text" in info:
                        compare(info)
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(r["eli"], [(p["page"], p["layer"]["valid"], p["layer_split"]["valid"], p.get("agree"), p.get("agree_split"))
                         for p in r["page_info"] if "layer" in p], flush=True)


def cmd_ocr2(a) -> None:
    """Second OCR of the same pages in another language setting (default pol+eng, eli2md's first pass):
    stored as ocr_<lang> metrics; the eng model has "§", the pol model has not."""
    import pypdfium2 as pdfium
    key = "ocr_" + a.lang
    for f in sorted((WORK / "acts").glob("*.json")):
        r = json.loads(f.read_text())
        todo = [p for p in r.get("page_info", []) if "ocr" in p and key not in p]
        if not todo:
            continue
        _, y, pos = r["eli"].split("/")
        doc = pdfium.PdfDocument(str(Path(os.environ.get("ELI2MD_CACHE", Path.home() / "cache" / "eli")) / "DU" / y / pos / "text.pdf"))
        try:
            for p in todo:
                img = doc[p["page"] - 1].render(scale=DPI / 72, grayscale=True).to_pil()
                with tempfile.TemporaryDirectory() as td:
                    png = Path(td) / "p.png"
                    img.save(png)
                    text, conf, _, _ = ocr_tsv(png, a.lang)
                p[key] = text_metrics(text)
                p[key]["median_conf"] = conf
                p[key + "_text"] = text
        finally:
            doc.close()
        f.write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(r["eli"], [(p["page"], p["ocr"]["valid"], p[key]["valid"], p["layer"]["para_marks"], p[key]["para_marks"],
                          p[key]["para_misread"]) for p in todo], flush=True)


PROBES = ["DU/1999/661", "DU/1999/1322", "DU/2000/1", "DU/2000/673", "DU/2010/888", "DU/2010/1776",
          "DU/2011/1", "DU/2011/445", "DU/2011/889", "DU/2011/1334"]  # fixed positions around the transitions


def cmd_probe(_a) -> None:
    """Producer, fonts and page-1 kind of PROBES (where scans end, where the Univers-PL encoding ends)."""
    import pdfplumber
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eli2md.eli import fetch
    out = []
    for eli in PROBES:
        meta, pdf_path = fetch(eli)
        with pdfplumber.open(pdf_path) as pdf:
            md = pdf.metadata or {}
            pg = pdf.pages[0]
            info = page_info(pg)
            out.append({"eli": eli, "pages": len(pdf.pages), "producer": str(md.get("Producer"))[:45],
                        "creator": str(md.get("Creator"))[:35], "created": str(md.get("CreationDate"))[:10],
                        "p1_chars": info["chars"], "p1_image_cover": info["image_cover"], "p1_fonts": info["fonts"][:2],
                        "pl_font": any(PL_FONT.search(c.get("fontname", "")) for c in pg.chars)})
        print(json.dumps(out[-1], ensure_ascii=False), flush=True)
    (WORK / "probes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- summary
def q(v: list) -> dict:
    v = sorted(x for x in v if x is not None)
    if not v:
        return {"n": 0}
    return {"n": len(v), "median": round(statistics.median(v), 4), "min": v[0], "max": v[-1],
            "q1": round(v[len(v) // 4], 4), "q3": round(v[(3 * len(v)) // 4], 4)}


def boot_median_ci(v: list[float], seed: int = SEED, n: int = 10000) -> list[float] | None:
    """95% percentile bootstrap interval of the median of v (acts resampled with replacement)."""
    if len(v) < 3:
        return None
    rng = random.Random(seed)
    meds = sorted(statistics.median(rng.choices(v, k=len(v))) for _ in range(n))
    return [round(meds[int(0.025 * n)], 4), round(meds[int(0.975 * n) - 1], 4)]


MIN_TOKENS = 30  # a page is compared only if both texts have this many tokens


def best_layer(p: dict) -> dict:
    """The layer read as well as it can be without OCR: fixed encoding (Quark PDFs) or columns in order."""
    return p.get("layer_fixed") or p["layer_split"]


def weighted(pages: list[dict], get) -> float | None:
    """Token-weighted share over pages: get(page) -> (valid share, tokens)."""
    num = den = 0.0
    for p in pages:
        v, t = get(p)
        if v is not None and t:
            num += v * t
            den += t
    return round(num / den, 4) if den else None


def page_kind(p: dict) -> str:
    text = "text" if p["chars"] >= 100 else "little_text" if p["chars"] >= TEXT_CHARS else "no_text"
    c = p["image_cover"]
    img = "scan" if c >= SCAN_SHARE else "image" if c >= 0.1 else "none"
    return text + "+" + img


def cmd_summary(_a) -> None:
    acts = [json.loads(f.read_text()) for f in sorted((WORK / "acts").glob("*.json"))]
    counts = json.loads((WORK / "year_counts.json").read_text())
    groups: dict[str, dict] = {}
    measures = {
        "layer_as_read": lambda p: (p["layer"]["valid"], p["layer"]["tokens"]),
        "layer_best": lambda p: (best_layer(p)["valid"], best_layer(p)["tokens"]),
        "layer_best_joined": lambda p: (best_layer(p)["valid_joined"], best_layer(p)["tokens"]),
        "layer_best_prewar": lambda p: (best_layer(p)["valid_prewar"], best_layer(p)["tokens"]),
        "ocr": lambda p: (p["ocr"]["valid"], p["ocr"]["tokens"]),
        "ocr_joined": lambda p: (p["ocr"]["valid_joined"], p["ocr"]["tokens"]),
        "ocr_prewar": lambda p: (p["ocr"]["valid_prewar"], p["ocr"]["tokens"]),
        "ocr_poleng": lambda p: ((p.get("ocr_pol+eng") or {}).get("valid"), (p.get("ocr_pol+eng") or {}).get("tokens")),
    }
    for era in [e[0] for e in ERAS] + ["all", "extra_cached"]:
        sel = [x for x in acts if "error" not in x and (
            (era == "extra_cached" and not x["random"]) or
            (era != "extra_cached" and x["random"] and (era == "all" or x["era"] == era)))]
        pages = [p for x in sel for p in x["page_info"]]
        kinds = Counter(page_kind(p) for p in pages)
        op = [p for p in pages if "ocr" in p]
        comp = [p for p in op if p["layer"]["tokens"] >= MIN_TOKENS and p["ocr"]["tokens"] >= MIN_TOKENS]
        per_act = {}
        for x in sel:
            cp = [p for p in x["page_info"] if p in comp]
            if cp:
                per_act[x["eli"]] = {k: weighted(cp, g) for k, g in measures.items()}
        g = {"acts": len(sel), "acts_compared": len(per_act), "pages": len(pages), "page_kinds": dict(kinds),
             "pages_with_text_layer": sum(p["chars"] >= TEXT_CHARS for p in pages),
             "ocr_pages": len(op), "compared_pages": len(comp)}
        for k in measures:
            g["act_" + k] = q([a[k] for a in per_act.values()])
            g["page_" + k] = q([measures[k](p)[0] for p in comp])
        for k in ("layer_as_read", "layer_best", "layer_best_joined", "ocr_poleng"):
            d = [a["ocr"] - a[k] for a in per_act.values() if a["ocr"] is not None and a[k] is not None]
            g[f"ocr_minus_{k}"] = {"median": round(statistics.median(d), 4) if d else None,
                                   "ci95_boot_median": boot_median_ci(d), "ocr_higher_acts": sum(x > 0 for x in d),
                                   "n": len(d)}
        g["diacritics_layer_as_read"] = q([p["layer"]["diacritic_share"] for p in comp])
        g["diacritics_layer_best"] = q([best_layer(p)["diacritic_share"] for p in comp])
        g["diacritics_ocr"] = q([p["ocr"]["diacritic_share"] for p in comp])
        g["ocr_median_conf"] = q([p["ocr"]["median_conf"] for p in op])
        g["ocr_seconds_per_page"] = q([p.get("ocr_s") for p in op])
        g["para_marks_layer"] = sum(p["layer"]["para_marks"] for p in comp)
        g["para_marks_ocr"] = sum(p["ocr"]["para_marks"] for p in comp)
        g["para_misread_ocr"] = sum(p["ocr"]["para_misread"] for p in comp)
        g["para_marks_ocr_poleng"] = sum((p.get("ocr_pol+eng") or {}).get("para_marks", 0) for p in comp)
        g["para_misread_ocr_poleng"] = sum((p.get("ocr_pol+eng") or {}).get("para_misread", 0) for p in comp)
        g["art_marks_layer"] = sum(p["layer"]["art_marks"] for p in comp)
        g["art_marks_ocr"] = sum(p["ocr"]["art_marks"] for p in comp)
        g["two_col_pages"] = sum(1 for p in op if (p.get("layer_cols") or {}).get("two_col")
                                 or (p.get("ocr_cols") or {}).get("two_col"))
        shared = []
        for x in sel:
            own = int(x["eli"].split("/")[2])
            o = [p for p in x["page_info"] if "ocr" in p]
            for which, p in (("first", o[0]), ("last", o[-1])) if o else ():
                hp = set(p["ocr"]["header_pos"]) | set(p["layer"]["header_pos"])
                if hp - {own}:
                    shared.append(f"{x['eli']} {which} {sorted(hp)}")
        g["pages_with_other_positions_in_header"] = shared
        g["pdf_producers"] = dict(Counter((x.get("pdf_meta") or {}).get("Producer", "?")[:40] for x in sel))
        g["per_act"] = per_act
        groups[era] = g
    slim = []
    for x in acts:
        y = {k: v for k, v in x.items() if k != "page_info"}
        y["page_info"] = [{k: v for k, v in p.items() if not k.endswith("_text")} for p in x.get("page_info", [])]
        slim.append(y)
    OUT.write_text(json.dumps({"seed": SEED, "per_era": PER_ERA, "eras": ERAS, "extra_cached": EXTRA, "dpi": DPI,
                               "min_tokens_compared": MIN_TOKENS, "year_counts": counts, "groups": groups,
                               "probes": json.loads((WORK / "probes.json").read_text()) if (WORK / "probes.json").exists() else None,
                               "acts": slim}, ensure_ascii=False, indent=1) + "\n")
    for era, g in groups.items():
        print(era, json.dumps({k: v for k, v in g.items() if k != "per_act"}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("lists", "sample", "measure", "relayer", "ocr2", "probe", "summary"))
    ap.add_argument("--lang", default="pol+eng", help="ocr2: tesseract language(s)")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    {"lists": cmd_lists, "sample": cmd_sample, "measure": cmd_measure, "relayer": cmd_relayer, "ocr2": cmd_ocr2, "probe": cmd_probe,
     "summary": cmd_summary}[a.stage](a)


if __name__ == "__main__":
    main()
