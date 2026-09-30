"""Convert a born-digital Dziennik Ustaw PDF into paragraphs + footnotes.

Layout facts this relies on (checked on 2024 acts, see eval/):
- page 1 starts with the gazette masthead ending with a line "Poz. N";
- later pages start with a running header "Dziennik Ustaw – N – Poz. N";
- footnotes sit below a thin horizontal rule (a ~144pt wide rect) in 9pt type;
- footnote markers are superscripts in ~6pt type;
- paragraphs are separated by a larger vertical gap than lines within a paragraph.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, replace

import pdfplumber
from pdfplumber.utils import extract_words

RUNNING_HEADER = re.compile(r"^(?:Dziennik Ustaw|Monitor Polski)\s*[–-]\s*\d+\s*[–-]\s*Poz\.\s*\d+\s*$")
# "Pozycja 19": MP 2012 up to poz. 130; ") Poz. 1024*": the last act of a year has a note "*) Ostatnia pozycja"
MASTHEAD_END = re.compile(r"^[*)\s]*Poz(?:\.|ycja)\s*\d+[*)\s]*$")
SUP_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"  # unit numbers may carry them: Art. 41¹., 5²)
# Letters of an index ("Art. 22¹ᵃ."): Unicode modifier letters a-z; there is none for q.
SUP_LETTERS = "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"
SUP_CHARS = SUP_DIGITS + SUP_LETTERS
# Lines that start a new unit even without a vertical gap (used at page breaks).
UNIT_START = re.compile(
    rf"^(Art\.\s*\d|§\s*\d|\d+[a-z]*[{SUP_CHARS}]*\.\s|\d+[a-z]*[{SUP_CHARS}]*\)\s|[a-z]{{1,3}}\)\s|–\s|Rozdział\s|DZIAŁ\s|Oddział\s|Załącznik)"
)
UNIT_START_Q = re.compile("^„?" + UNIT_START.pattern[1:])  # also a quoted unit of an amendment: „1. Treść
ITEM_START = re.compile(rf"^„?(Art\.\s*\d|§\s*\d|\d+[a-z]*[{SUP_CHARS}]*\)\s|[a-z]{{1,3}}\)\s)")  # not "1." / "–"
POINT_START = re.compile(rf"^„?(\d+[a-z]*[{SUP_CHARS}]*\)\s|[a-z]{{1,3}}\)\s)")  # "1)", "a)" only
LOWER = "a-ząćęłńóśźż"
ANNEX = re.compile(r"^Załącznik")
INK_DPI, INK_LEVEL = 100, 180  # render resolution; gray level above which a box has no ink
DUP_TOL = 0.3  # pt; a char drawn twice repeats within this distance (<= 0.1pt in DU/2025/1095; see _dedupe)
MATH = re.compile("[\U0001D400-\U0001D7FF]")
CID = re.compile(r"\(cid:\d+\)")  # a glyph the PDF font does not map to Unicode (pdfminer's placeholder)
FOOTNOTE_MARK = re.compile(r"^\d{1,3}\)?[,.;:]?$")
# Small digits without ")" are not footnote markers but unit numbers (Art. 41¹), units (m²)
# or chemical subscripts (P₂O₅). Kept as Unicode super/subscript digits.
SUPER = str.maketrans("0123456789abcdefghijklmnoprstuvwxyz", SUP_CHARS)
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
# Index of a unit number in small raised type right after the number: "22" + "1a" (2025 prints: Art. 22¹ᵃ.),
# "479" + "[30f]" (2026 prints use brackets, also for digits: "§ 4[1]", DU/2026/468). Written as superscripts
# without the brackets, so both prints give "Art. 479³⁰ᶠ." ("1" alone is a script digit, see FOOTNOTE_MARK).
INDEX = re.compile(r"^(?:\[(\d{1,3}[a-z]{0,3})\]|(\d{1,3}[a-z]{1,3}))$")
SIGNATURE = re.compile(r"^[A-ZŁŚŻ][\w ]{2,80}: (\w{1,3}\. )+[A-ZŁŚŻ][\w-]+$")
IMAGE_TEXT_CHARS = 30  # more text-layer chars than this over an image: the image is a background, not read by OCR


@dataclass
class Line:
    page: int
    top: float
    bottom: float
    x0: float
    size: float
    text: str
    pw: float = 595.0
    ph: float = 842.0
    mark: str = ""  # "notext" | "image": position marker for content that is not text; "ocr": text read by OCR
    x1: float = 0.0
    right: float = 0.0  # right edge of justified text in this frame (0 = unknown)
    lead: float = -1.0  # usual gap between lines in this frame (-1 = unknown)


@dataclass
class Block:
    kind: str  # "p" | "signature" | "annex" (annex header) | "notext" | "image" | "ocr" (see Line.mark)
    text: str
    page: int


@dataclass
class Document:
    masthead: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)
    footnote_pages: list[int] = field(default_factory=list)  # page of each footnote (numbering may restart)
    no_text_pages: list[int] = field(default_factory=list)  # e.g. scanned pages: their content is lost
    image_pages: list[int] = field(default_factory=list)  # pages with text and large images (forms, drawings)
    ocr_pages: list[int] = field(default_factory=list)  # pages without text whose OCR text is included
    unmapped_pages: list[int] = field(default_factory=list)  # text layer mostly without Unicode, kept without it
    # pages with text whose large image is a scan of text read by OCR (also in image_pages, not in ocr_pages)
    image_ocr_pages: list[int] = field(default_factory=list)
    ocr_engine: str = ""  # e.g. "tesseract 5.5.0"
    ocr_langs: dict[int, str] = field(default_factory=dict)  # page -> tesseract language(s) used

    @property
    def paragraphs(self) -> list[str]:
        return [b.text for b in self.blocks]

    def main_blocks(self) -> list[Block]:
        """Blocks before the first annex header."""
        out = []
        for b in self.blocks:
            if b.kind == "annex":
                break
            out.append(b)
        return out

    def annex_blocks(self) -> list[Block]:
        return self.blocks[len(self.main_blocks()):]


def _char_angle(c: dict) -> int:
    """Writing direction of a char in degrees (0, 90, 180, 270), from its text matrix."""
    a, b = c["matrix"][0], c["matrix"][1]
    return round(math.degrees(math.atan2(b, a)) / 90) % 4 * 90


def _watermark(c: dict) -> bool:
    """A char of the invisible diagonal stamp "www.rcl.gov.pl" over pages of MP 2012 (MP/2012/596, 988):
    marked as an Artifact and written at ~55 degrees. Its letters landed inside words and paragraphs and
    hid the running header ("l Monitor Polski – 2 – Poz. 596 p"). Text of the act is never diagonal."""
    if c.get("tag") != "Artifact" or "matrix" not in c:
        return False
    deg = math.degrees(math.atan2(c["matrix"][1], c["matrix"][0])) % 90
    return 10 < deg < 80


def _drop_watermark(page):
    if not any(_watermark(c) for c in page.chars):
        return page
    return page.filter(lambda o: not (o.get("object_type") == "char" and _watermark(o)))


def _to_frame(o: dict, rot: int, w: float, h: float) -> dict:
    """Map an object's bbox into a frame where text written at `rot` degrees runs left-to-right."""
    x0, x1, t, b = o["x0"], o["x1"], o["top"], o["bottom"]
    if rot == 90:  # text runs bottom-to-top; the landscape top is on the left
        x0, x1, t, b = h - b, h - t, x0, x1
    elif rot == 270:
        x0, x1, t, b = t, b, w - x1, w - x0
    elif rot == 180:
        x0, x1, t, b = w - x1, w - x0, h - b, h - t
    out = {**o, "x0": x0, "x1": x1, "top": t, "bottom": b, "doctop": t, "width": x1 - x0, "height": b - t}
    if "matrix" in o:  # pdfminer's size of a rotated glyph is its advance, not the font size
        out.update(upright=True, size=math.hypot(o["matrix"][0], o["matrix"][1]))
    return out


def _glyph_box(c: dict, mb_x0: float = 0.0) -> tuple[float, float, float, float]:
    """(x0, top, x1, bottom) of a char, with its box moved onto the glyph if the font's descent is implausible.

    pdfminer's box reaches from the baseline down by the font's /Descent. Cambria declares -2464/1000 (the
    FontBBox of its math glyphs), so the box of a 10.8 pt char lies 16-27 pt below the baseline, on the next
    line (MP/2025/1128). A box with more than 3/4 of it below the baseline is moved up to 0.3 below it (usual
    descents are 0.2-0.4; a lowered subscript adds its rise, which the matrix does not show).
    """
    x0, t, x1, b = c["x0"], c["top"], c["x1"], c["bottom"]
    _, _, u, v, e, f = c["matrix"]  # (u, v): the glyph's up direction on the page
    if not (u or v) or (abs(u) > 1e-3 * abs(v) and abs(v) > 1e-3 * abs(u)):
        return x0, t, x1, b  # neither upright nor turned by a multiple of 90 degrees
    if abs(v) > abs(u):
        lo, hi, base, up = c["y0"], c["y1"], f, v > 0
    else:
        lo, hi, base, up = x0 - mb_x0, x1 - mb_x0, e, u > 0
    size = hi - lo
    below = (base - lo if up else hi - base) / size if size > 0 else 0.0
    if below <= 0.75:
        return x0, t, x1, b
    d = (below - 0.3) * size  # shift towards the glyph's top
    if abs(v) > abs(u):
        return (x0, t - d, x1, b - d) if up else (x0, t + d, x1, b + d)
    return (x0 + d, t, x1 + d, b) if up else (x0 - d, t, x1 - d, b)


def _drop_hidden_placed(page):
    """Drop text of a placed PDF (annex) that is not visible on the page.

    Annexes are often placed PDFs; the gazette covers their original heading with its own and
    hides the placed copy (clipping path or white box), which pdfminer ignores (DU/2024/144, 458).
    A placed char is hidden if the rendered page has no ink in its box, or if it lies under
    the gazette's own text (then the ink test cannot tell the two copies apart).
    """
    placed = [c for c in page.chars if c.get("tag") == "PlacedPDF"]
    own = [c for c in page.chars if c.get("tag") != "PlacedPDF"]
    if not placed or not own:
        return page
    own_words = extract_words(own)
    boxes = [(w["x0"] - 3, w["top"] - 3, w["x1"] + 3, w["bottom"] + 3) for w in own_words]
    # the gazette's running header band; a placed page reaching into it is clipped there (DU/2024/1337)
    header_bottom = max((w["bottom"] for w in own_words if w["bottom"] < 0.1 * page.height), default=0)
    scale = INK_DPI / 72
    img = page.to_image(resolution=INK_DPI).original.convert("L")
    mb_x0 = page.mediabox[0]

    def hidden(c: dict) -> bool:
        gx0, gt, gx1, gb = _glyph_box(c, mb_x0)
        cx, cy = (gx0 + gx1) / 2, (gt + gb) / 2
        if cy < header_bottom or any(x0 <= cx <= x1 and t <= cy <= b for x0, t, x1, b in boxes):
            return True
        if not c["text"].strip():
            return False
        crop = img.crop((int(gx0 * scale), int(gt * scale), int(gx1 * scale) + 1, int(gb * scale) + 1))
        return crop.getextrema()[0] > INK_LEVEL

    drop = {id(c) for c in placed if hidden(c)}
    return page.filter(lambda o: id(o) not in drop) if drop else page


def _dedupe(chars: list[dict], tol: float = DUP_TOL) -> list[dict]:
    """Drop chars drawn twice (bold is sometimes drawn twice; seen on rotated table pages): the same
    glyph (text, font, size) within `tol` of a kept one in both axes. pdfplumber's dedupe_chars chains
    positions within 1pt across the page, which in small rotated print (3.9pt) merged distinct letters
    and spaces of a line (MP/2025/541: "wyposażnie", "ratownicyi personelsą"). Overlapping text of
    another size is not a copy (MP/2025/1142: "decyzję" over a 'd' of 10.9pt)."""
    kept: dict[tuple, list[dict]] = {}
    out = []
    for c in chars:
        key = (c["text"], c.get("fontname"), round(c["size"], 1), round(c["x0"]), round(c["top"]))
        near = (o for dx in (-1, 0, 1) for dy in (-1, 0, 1) for o in kept.get((*key[:3], key[3] + dx, key[4] + dy), ()))
        if not any(abs(o["x0"] - c["x0"]) <= tol and abs(o["top"] - c["top"]) <= tol for o in near):
            kept.setdefault(key, []).append(c)
            out.append(c)
    return out


def _frames(page) -> list[tuple[list[dict], float, float, list[dict]]]:
    """(words, width, height, rects) per writing direction, dominant direction first.

    Landscape tables are printed on portrait pages with text rotated by 90 degrees; such a
    page is read in a rotated frame. Pages with mostly upright text are read as before.
    """
    angles = Counter(_char_angle(c) for c in page.chars)
    if not angles or angles.most_common(1)[0][0] == 0:
        return [(page.extract_words(extra_attrs=["size"], keep_blank_chars=False),
                 float(page.width), float(page.height), page.rects)]
    frames = []
    w, h = float(page.width), float(page.height)
    for rot, _ in angles.most_common():
        chars = _dedupe([_to_frame(c, rot, w, h) for c in page.chars if _char_angle(c) == rot])
        fw, fh = (h, w) if rot in (90, 270) else (w, h)
        words = extract_words(chars, extra_attrs=["size"], keep_blank_chars=False)
        frames.append((words, fw, fh, [_to_frame(r, rot, w, h) for r in page.rects]))
    return frames


def _unmapped_share(page) -> float:
    chars = page.chars
    return sum(1 for c in chars if c["text"].startswith("(cid:")) / len(chars) if chars else 0.0


def _large_image(page, min_share: float = 0.1) -> float | None:
    """Top of the largest image if images cover at least min_share of the page, else None."""
    area, best = 0.0, None
    for im in page.images:
        w = max(0.0, min(page.width, im["x1"]) - max(0.0, im["x0"]))
        h = max(0.0, min(page.height, im["bottom"]) - max(0.0, im["top"]))
        area += w * h
        if best is None or w * h > best[0]:
            best = (w * h, max(0.0, im["top"]))
    return best[1] if best and area >= min_share * page.width * page.height else None


def _largest_image_box(page) -> tuple[float, float, float, float] | None:
    """(x0, top, x1, bottom) of the largest image, clipped to the page."""
    best = None
    for im in page.images:
        x0, x1 = max(0.0, im["x0"]), min(float(page.width), im["x1"])
        top, bottom = max(0.0, im["top"]), min(float(page.height), im["bottom"])
        if x1 > x0 and bottom > top and (best is None or (x1 - x0) * (bottom - top) > best[0]):
            best = ((x1 - x0) * (bottom - top), (x0, top, x1, bottom))
    return best[1] if best else None


def _image_text(page, ocr: str):
    """OCR of the largest image of a page that has a text layer, if that image is a scan of text.

    Page 1 of international agreements has the masthead and title as text and the preamble and first
    articles as an image of text (MP/2026/869 s.1, MP/2012/646 s.1). Returns the OcrPage, or None when
    the image is not text (forms, drawings, maps, signatures: ocr.text_image) or the text layer already
    covers the image (a form drawn as an image under its text, MP/2025/...)."""
    from . import ocr as ocr_mod
    box = _largest_image_box(page)
    if box is None:
        return None
    x0, top, x1, bottom = box
    inside = sum(1 for c in page.chars if c["text"].strip() and x0 <= (c["x0"] + c["x1"]) / 2 <= x1
                 and top <= (c["top"] + c["bottom"]) / 2 <= bottom)
    if inside > IMAGE_TEXT_CHARS:
        return None
    read = ocr_mod.ocr_page(page, ocr, bbox=box)
    return read if ocr_mod.text_image(read) else None


def _page_lines(page, pno: int) -> tuple[list[Line], list[Line]]:
    """Return (body_lines, footnote_lines) for one page."""
    body, notes = [], []
    for k, (words, fw, fh, rects) in enumerate(_frames(_drop_hidden_placed(_drop_watermark(page)))):
        b, n = _frame_lines(words, fw, fh, rects, pno)
        if k > 0:
            b = [l for l in b if not RUNNING_HEADER.match(l.text)]
        body += b
        notes += n
    return body, notes


def _rows(words: list[dict]) -> list[list[dict]]:
    """Group words into lines: vertical overlap with the line's first word and similar size."""
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        mid = (w["top"] + w["bottom"]) / 2
        for r in rows:
            if r[0]["top"] - 1 <= mid <= r[0]["bottom"] + 1 and abs(r[0]["size"] - w["size"]) < 2:
                r.append(w)
                break
        else:
            rows.append([w])
    return rows


def _index_words(r: list[dict], big: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split a row of small words into (other words, indices). An index matches INDEX, starts right after a
    normal-size word ending with a letter or digit and sits above that word's middle: "479" + "[30f]".
    Index text is returned without brackets ("30f")."""
    words: list[dict] = []
    for w in sorted(r, key=lambda w: w["x0"]):
        prev = words[-1] if words else None
        if prev and re.fullmatch(r"\[\d{1,3}[a-z]{0,3}", prev["text"]) and w["text"] == "]" \
                and w["x0"] - prev["x1"] < 1.0:  # "[92" + "]" in another size (DU/2026/468 p. 103)
            words[-1] = {**prev, "text": prev["text"] + "]", "x1": w["x1"]}
        elif m := re.fullmatch(r"(\[\d{1,3}[a-z]{0,3}\])(\d{1,3}\)[,.;:]?)", w["text"]):
            # index + footnote marker in one word: "ust. 1 i 1[1]10)" (DU/2026/913 p. 44)
            cut = w["x0"] + (w["x1"] - w["x0"]) * len(m.group(1)) / len(w["text"])
            words += [{**w, "text": m.group(1), "x1": cut}, {**w, "text": m.group(2), "x0": cut}]
        else:
            words.append(w)
    rest, idx = [], []
    for w in words:
        m = INDEX.match(w["text"])
        mid = (w["top"] + w["bottom"]) / 2
        if m and any(-1.0 < w["x0"] - n["x1"] < 1.5 and n["top"] - 1 < mid < (n["top"] + n["bottom"]) / 2
                     and n["text"][-1:].isalnum() for n in big):
            idx.append({**w, "text": m.group(1) or m.group(2)})
        else:
            rest.append(w)
    rest.sort(key=lambda w: (w["top"], w["x0"]))  # the order of _rows: attach order decides ties (DU/2024/1089)
    return rest, idx


def _frame_lines(words: list[dict], pw: float, ph: float, rects: list[dict], pno: int) -> tuple[list[Line], list[Line]]:
    if not words:
        return [], []
    sizes = Counter()
    for w in words:
        sizes[round(w["size"], 1)] += len(w["text"])
    body_size = sizes.most_common(1)[0][0]
    sup_limit = body_size * 0.75

    # Cluster words into lines. Superscripts attach to the line they overlap vertically.
    # Small words: footnote markers ("1)"), whole lines of small print, or sub/superscripts in
    # formulas. Markers and formula scripts are attached to the nearest normal line.
    normal = [w for w in words if w["size"] >= sup_limit]
    big = list(normal)
    attach: list[tuple[dict, dict]] = []  # (small word, flag) to attach to the nearest normal line
    for r in _rows([w for w in words if w["size"] < sup_limit]):
        # indices are scripts even when a line has several: "Art. 479[30f]. … art. 479[30a]–479[30e]"
        r, idx = _index_words(r, big)
        attach += [(w, {"script": True, "index": True}) for w in idx]
        if not r:
            continue
        text = [w for w in r if not FOOTNOTE_MARK.match(w["text"])]
        words_ = [w for w in text if not MATH.search(w["text"])]  # formula scripts are math italic
        if (len(r) >= 3 and words_) or sum(len(w["text"]) for w in words_) >= 15:
            normal += r
            continue
        for w in r:
            if not FOOTNOTE_MARK.match(w["text"]):
                continue
            close = next((x for x in text if x["text"] == ")" and 0 <= x["x0"] - w["x1"] < 1.5), None)
            if close is not None and ")" not in w["text"]:  # marker extracted as "1" + ")"
                text.remove(close)
                w = {**w, "text": w["text"] + ")", "x1": close["x1"]}
            attach.append((w, {"sup": True} if ")" in w["text"] else {"script": True}))
        attach += [(w, {}) for w in text]
    rows = _rows(normal)
    for s, flag in attach:
        best = min(rows, key=lambda r: abs((r[0]["top"] + r[0]["bottom"]) / 2 - s["bottom"]), default=None)
        if best is not None and abs((best[0]["top"] + best[0]["bottom"]) / 2 - s["bottom"]) < 12:
            best.append({**s, **flag})
        else:
            rows.append([{**s, **flag}])

    rule_top = None
    for r in rects:
        if r["height"] < 1.5 and 130 < r["width"] < 160 and r["x0"] < pw * 0.2 and r["top"] > ph * 0.3 \
                and _free(r, rects):
            rule_top = r["top"] if rule_top is None else min(rule_top, r["top"])

    body, notes = [], []
    for r in rows:
        r.sort(key=lambda w: w["x0"])
        parts: list[tuple[str, bool]] = []  # (text, glued to the previous word)
        base = [w for w in r if not w.get("sup") and not w.get("script")]
        mid = sum((w["top"] + w["bottom"]) / 2 for w in base) / len(base) if base else None
        for k, w in enumerate(r):
            if w.get("sup"):
                m = re.match(r"^(\d+)\)?(.*)$", w["text"])
                parts.append((f"[^{m.group(1)}]{m.group(2)}", True))
            elif w.get("index"):  # "30f" -> "³⁰ᶠ"; as printed if a char has no superscript form ("[1q]")
                sup = w["text"].translate(SUPER)
                parts.append((sup if all(c in SUP_CHARS for c in sup) else f"[{w['text']}]", True))
            elif w.get("script"):
                up = mid is None or (w["top"] + w["bottom"]) / 2 < mid
                parts.append((w["text"].translate(SUPER if up else SUB), True))
            else:  # "Art. 41¹.", "art. 63[^59]," : punctuation after a script or marker is a separate word
                after_small = k > 0 and (r[k - 1].get("script") or r[k - 1].get("sup")) \
                    and w["x0"] - r[k - 1]["x1"] < 1.0
                parts.append((w["text"], bool(after_small)))
        text = ""
        for p, glued in parts:
            text = p if not text else text + p if glued else text + " " + p
        normal_words = [w for w in r if not w.get("sup") and not w.get("script")] or r
        line = Line(
            page=pno,
            top=min(w["top"] for w in normal_words),
            bottom=max(w["bottom"] for w in normal_words),
            x0=min(w["x0"] for w in r),
            size=Counter(round(w["size"], 1) for w in normal_words).most_common(1)[0][0],
            text=" ".join(_plain_math(CID.sub(" ", text)).split()),
            pw=pw,
            ph=ph,
            x1=max(w["x1"] for w in normal_words),
        )
        is_note = (rule_top is not None and line.top > rule_top) or (
            rule_top is None and line.size < body_size - 0.5 and line.top > ph * 0.6
        )
        if line.text:  # a line of unmapped glyphs only is empty now
            (notes if is_note else body).append(line)
    body.sort(key=lambda l: l.top)
    notes.sort(key=lambda l: l.top)
    ends = Counter(round(l.x1) for l in body if len(l.text) >= 40)
    gaps = Counter(round(2 * (b.top - a.bottom)) / 2 for a, b in zip(body, body[1:])
                   if abs(a.size - b.size) < 0.5 and 0 <= b.top - a.bottom < a.size)
    for l in body:
        if ends and ends.most_common(1)[0][1] >= 3:
            l.right = ends.most_common(1)[0][0]
        if gaps and gaps.most_common(1)[0][1] >= 3:
            l.lead = gaps.most_common(1)[0][0]
    return body, notes


def _free(r: dict, rects: list[dict]) -> bool:
    """The footnote rule stands alone. A table border of the same size meets other borders at its ends."""
    for x in rects:
        if x is r or not x["top"] - 2 <= r["top"] <= x["bottom"] + 2:
            continue
        if min(abs(x["x0"] - r["x1"]), abs(x["x1"] - r["x0"]), abs(x["x0"] - r["x0"]), abs(x["x1"] - r["x1"])) < 2:
            return False
    return True


def _plain_math(text: str) -> str:
    """Map Unicode mathematical alphanumerics (e.g. 𝑊𝑌𝐷 in formulas) to plain letters."""
    return "".join(unicodedata.normalize("NFKC", c) if "\U0001D400" <= c <= "\U0001D7FF" else c for c in text)


def _join(prev: str, nxt: str) -> str:
    if re.search(rf"[{LOWER}]-$", prev) and re.match(rf"[{LOWER}]", nxt):
        return prev[:-1] + nxt
    if re.search(r"\w-$", prev) and re.match(r"-\w", nxt):  # "rolno-" "-środowiskowy": the hyphen is repeated
        return prev + nxt[1:]
    return prev + " " + nxt


def _continuation_gaps(body: list[Line]) -> dict[int, float]:
    """Per page: usual gap before a line that continues a paragraph (starts with a lower-case letter and not
    with "a) "), relative to the font size; pages with fewer than 5 such lines are left out. Most pages set
    lines at 0.2 of the size; some at 0.6–0.75 (DU/2024/853, annex of DU/2024/440), which the fixed 0.45 split
    into one block per line. Per page, because forms in annexes are spaced out (DU/2024/1542). The lower
    quartile, not the median: paragraphs may start with a lower-case word too (clauses of a court
    resolution "po rozpoznaniu…", "z udziałem…" in DU/2024/1883), and their gaps are larger."""
    ratios: dict[int, list[float]] = {}
    for a, b in zip(body, body[1:]):
        if a.page == b.page and abs(a.size - b.size) < 0.5 and 0 <= b.top - a.bottom < a.size \
                and re.match(rf"[{LOWER}]", b.text) and not UNIT_START.match(b.text):
            ratios.setdefault(b.page, []).append((b.top - a.bottom) / a.size)
    return {p: sorted(r)[len(r) // 4] for p, r in ratios.items() if len(r) >= 5}


POINT_LABEL = re.compile(r"^„?(\d+|[a-z])\)\s")


def _follows(a: str, b: str) -> bool:
    """Line b starts with the point label right after the one line a starts with: "1)" -> "2)", "a)" -> "b)"."""
    ma, mb = POINT_LABEL.match(a), POINT_LABEL.match(b)
    if not ma or not mb:
        return False
    x, y = ma.group(1), mb.group(1)
    if x.isdigit() and y.isdigit():
        return int(y) == int(x) + 1
    return not x.isdigit() and not y.isdigit() and ord(y) == ord(x) + 1


def _segment(body: list[Line]) -> list[Block]:
    """Group lines into blocks (paragraphs): by the vertical gap (relative to font size and to the usual
    gap on the page), at page breaks by content. Annex headers and signatures always start a block."""
    blocks: list[Block] = []
    # a new block needs a gap above 0.45 of the font size, or clearly above the usual continuation gap
    split = {p: max(0.45, g + 0.1) for p, g in _continuation_gaps(body).items()}
    cur: Block | None = None
    prev: Line | None = None
    for l in body:
        kind = "p"
        if l.mark:
            kind = l.mark
        elif ANNEX.match(l.text) and l.x0 > 0.4 * l.pw and l.top < 0.2 * l.ph:
            kind = "annex"
        elif SIGNATURE.match(l.text) and l.x0 > 0.45 * l.pw:
            kind = "signature"
        if prev is None or cur is None:
            new = True
        elif kind != "p" or cur.kind in ("signature", "notext", "image", "ocr", "unmapped"):
            new = not (kind == "annex" and cur.kind == "annex" and l.page == prev.page)
        elif cur.kind == "annex":
            # right-aligned continuation lines of an annex header ("z dnia ... (poz. N)")
            new = not (l.page == prev.page and l.x0 > 0.4 * l.pw and l.top - prev.bottom < 0.8 * l.size)
        elif l.page != prev.page:
            new = bool(UNIT_START.match(l.text)) or bool(re.search(r"[.:;”]$", prev.text))
        else:
            # Some PDFs set units with little extra space (2 pt over the usual gap between lines, not 6),
            # or none: then a unit starts after a line that ends short of the right margin (the last line
            # of a justified paragraph).
            # On pages set with wide line spacing units and paragraphs often have no more space than other lines
            # (DU/2024/1442, 440): there "1)", "a)", "Art. 1", "§ 1" at a line start begin a unit, "1." and "–" only
            # after a sentence end, and a line that ends short of the right margin ends its paragraph.
            gap, limit = l.top - prev.bottom, split.get(l.page, 0.45)
            short = 0 < prev.x1 < prev.right - 2 * prev.size
            # "2)", "b)" after a short line start a point even without ";" before: points in a table cell
            # set with the usual line gap (MP/2025/121). So does "2)" right below a one-line "1)" whose row
            # also holds the next cell ("1) B1.1, B1.3, B2, C   483", ibid.). Not after a hyphen ("impedan-"
            # "cji) i", MP/2025/910), nor after an overlapping line or one of another size: footnote markers
            # read as "1)" in tables (MP/2025/541).
            point = (short or (_follows(prev.text, l.text) and abs(l.x0 - prev.x0) < 1)) \
                and bool(POINT_START.match(l.text)) and gap >= 0 and abs(l.size - prev.size) < 0.5 \
                and not prev.text.endswith("-")
            new = gap > limit * l.size or (limit > 0.45 and short) or bool(UNIT_START_Q.match(l.text)) and (
                (prev.lead >= 0 and gap > prev.lead + 1.2)
                or (short and bool(re.search(r"[.:;,”]$", prev.text))) or point
                or (limit > 0.45 and (bool(ITEM_START.match(l.text)) or bool(re.search(r"[.:;,”]$", prev.text)))))
        if new:
            if cur is not None:
                blocks.append(cur)
            cur = Block(kind, l.text, l.page)
        else:
            cur.text = _join(cur.text, l.text)
        prev = l
    if cur is not None:
        blocks.append(cur)
    return blocks


def convert(path: str, ocr: str | None = None) -> Document:
    """ocr: "auto" or tesseract language(s), e.g. "pol+eng", to read pages without a text layer
    (see ocr.py); None (default) = no OCR, such pages only get a note."""
    doc = Document()
    body: list[Line] = []
    notes: list[Line] = []
    if ocr:
        from . import ocr as ocr_mod
        doc.ocr_engine = f"tesseract {ocr_mod.check(ocr)}"
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            b, n = _page_lines(page, pno)
            layer = None  # text layer of a page mostly of glyphs without Unicode (forms, DU/2025/161): OCR first
            if _unmapped_share(page) > 0.1:
                layer, b, n = (b, n), [], []
            if pno == 1:
                for i, l in enumerate(b):
                    if MASTHEAD_END.match(l.text):
                        doc.masthead = [x.text for x in b[: i + 1]]
                        b = b[i + 1 :]
                        break
            elif b and RUNNING_HEADER.match(b[0].text):
                b = b[1:]
            if not b and not n:
                read = ocr_mod.ocr_page(page, ocr) if ocr else None
                if read and ocr_mod.usable(read):
                    doc.no_text_pages.append(pno)
                    doc.ocr_pages.append(pno)
                    doc.ocr_langs[pno] = read.lang
                    b = [Line(pno, 0.0, 0.0, 0.0, 1.0, t, page.width, page.height, mark="ocr") for t in read.paragraphs]
                elif layer and (layer[0] or layer[1]):
                    # no OCR or an unreadable one: the text layer without the unmapped glyphs beats a bare note
                    doc.unmapped_pages.append(pno)
                    b, n = layer
                    if b and RUNNING_HEADER.match(b[0].text):
                        b = b[1:]
                    b = [Line(pno, 0.0, 0.0, 0.0, 1.0, "", page.width, page.height, mark="unmapped")] + b
                else:
                    doc.no_text_pages.append(pno)
                    b = [Line(pno, 0.0, 0.0, 0.0, 1.0, "", page.width, page.height, mark="notext")]
            elif (img := _large_image(page)) is not None:
                doc.image_pages.append(pno)
                m = [Line(pno, img, img, 0.0, 1.0, "", page.width, page.height, mark="image")]
                if ocr and (read := _image_text(page, ocr)):  # an image of text: its OCR text replaces the note
                    doc.image_ocr_pages.append(pno)
                    doc.ocr_langs[pno] = read.lang
                    m = [Line(pno, img, img, 0.0, 1.0, t, page.width, page.height, mark="ocr") for t in read.paragraphs]
                upright = all(l.pw == page.width and l.ph == page.height for l in b)
                i = next((k for k, l in enumerate(b) if l.top > img), len(b)) if upright else len(b)
                b = b[:i] + m + b[i:]
            body.extend(b)
            notes.extend(n)
            page.close()  # pdfplumber caches every parsed page; 867-page acts exhausted 14 GB RAM

    doc.blocks = _segment(body)

    cur, cur_page = None, 0
    for l in notes:
        if re.match(r"^\[\^\d+\]", l.text) or re.match(r"^\d+\)\s", l.text):
            if cur is not None:
                doc.footnotes.append(cur)
                doc.footnote_pages.append(cur_page)
            cur, cur_page = l.text, l.page
        else:
            cur = l.text if cur is None else _join(cur, l.text)
            cur_page = cur_page or l.page
    if cur is not None:
        doc.footnotes.append(cur)
        doc.footnote_pages.append(cur_page)
    return doc


UNIT_HEAD = {
    "Art.": re.compile(rf"^(Art\.\s*\d+[a-z]*[{SUP_CHARS}]*\.)\s*(.*)$", re.S),
    "§": re.compile(rf"^(§\s*\d+[a-z]*[{SUP_CHARS}]*\.)\s*(.*)$", re.S),
}
# A quoted unit that opens with its ust. 1 or § 1 (codes): "„Art. 21. 1. Treść" -> "„Art. 21." + "1. Treść",
# "Art. 14t. § 1. Treść" -> "Art. 14t." + "§ 1. Treść"
QUOTED_UNIT = re.compile(
    rf"^(„?(?:Art\.|§)\s*\d+[a-z]*[{SUP_CHARS}]*\.)\s+(„?(?:§\s*)?\d+[a-z]*[{SUP_CHARS}]*\.\s.*)$", re.S)
# ” after minutes is the seconds sign in coordinates (16°41’56,70”), not a closing quote
SECONDS = re.compile(r"\d[’′']\s?\d+(?:[,.]\d+)?”")
# a quote that opens a block, possibly after the unit number: "„Art. 5.", "Art. 30. „1.", "1) „a)"
QUOTE_HEAD = re.compile(rf"^(?:(?:Art\.|§)\s*\d+[a-z]*[{SUP_CHARS}]*\.\s*|\d+[a-z]*[{SUP_CHARS}]*[.)]\s*|[a-z]{{1,3}}\)\s*)?[„“]")


def quote_depths(blocks: list[Block]) -> list[int]:
    """Quotation depth (opening minus closing marks) at the start of each block. Units inside
    quotes are provisions of another act (amendments, "przepisy nieobjęte tekstem jednolitym"),
    not units of this one. Only the first quoted unit carries the opening „, so the depth has to
    be carried over. Only a quote that opens the block (after an optional unit number) may run
    into the next blocks; one opened mid-sentence and left open is a typo in the source
    („zwany dalej „kodem;”) and ends with its block. Some PDFs close with ˮ (U+02EE);
    “ opens English quotes in forms."""
    depths, d = [], 0
    for b in blocks:
        if b.kind == "annex":
            d = 0
        depths.append(d)
        if b.kind == "ocr":  # OCR misreads quotes; its text is never a heading anyway
            continue
        t = SECONDS.sub("", b.text)
        head = QUOTE_HEAD.match(t)
        carry, local = d, 0  # quotes open from earlier blocks / opened mid-block in this one
        for k, ch in enumerate(t):
            if ch in "„“":
                if head and k == head.end() - 1:
                    carry += 1
                else:
                    local += 1
            elif ch in "”ˮ":
                if local:
                    local -= 1
                else:
                    carry = max(0, carry - 1)
        d = carry
    return depths


def page_ranges(pages: list[int]) -> str:
    """[2, 3, 4, 7] -> 2-4, 7"""
    out: list[list[int]] = []
    for p in pages:
        if out and p == out[-1][1] + 1:
            out[-1][1] = p
        else:
            out.append([p, p])
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in out)


def no_text_note(pages: list[int]) -> str:
    if len(pages) == 1:
        return (f"> [Strona {pages[0]} PDF nie ma czytelnej warstwy tekstowej (np. skan lub grafika). "
                "Jej treści tu nie ma, jest tylko w PDF.]")
    return (f"> [Strony {page_ranges(pages)} PDF nie mają czytelnej warstwy tekstowej (np. skan lub grafika). "
            "Ich treści tu nie ma, jest tylko w PDF.]")


def ocr_note(page: int, engine: str) -> str:
    return (f"> [Strona {page} PDF nie ma czytelnej warstwy tekstowej. Tekst poniżej odczytał OCR ({engine}). "
            "Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]")


def image_ocr_note(page: int, engine: str) -> str:
    return (f"> [Na stronie {page} PDF jest obraz tekstu (skan). Tekst poniżej odczytał z obrazu OCR ({engine}). "
            "Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]")


def _escape_text(text: str) -> str:
    """A text-layer paragraph that starts with > or # ("> 90 dni" in a table) must not become a quote block
    (the mark of OCR text) or a heading."""
    return "\\" + text if text[:1] in ">#" else text


def _escape_ocr(text: str) -> str:
    """OCR text is plain text: a leading #, >, |, [ or bullet must not become Markdown syntax.
    ("1. Tekst" stays as it is, like ust. in the text layer.)"""
    return "\\" + text if re.match(r"^([#>|\[]|[-*+]\s)", text) else text


def frontmatter(meta: dict, source_pdf: str | None = None, no_text_pages: list[int] | None = None,
                image_pages: list[int] | None = None, ocr_pages: list[int] | None = None, ocr_engine: str = "",
                unmapped_pages: list[int] | None = None, image_ocr_pages: list[int] | None = None) -> str:
    """YAML front matter; keys follow legalize-pl where the meaning is the same."""
    from . import __version__

    eli = meta["ELI"]
    fields = {
        "title": meta.get("title"),
        "identifier": eli.replace("/", "-"),
        "country": "pl",
        "rank": (meta.get("type") or "").lower(),
        "eli": eli,
        "source": f"https://api.sejm.gov.pl/eli/acts/{eli}",
        "source_pdf": source_pdf or f"https://api.sejm.gov.pl/eli/acts/{eli}/text.pdf",
        "display_address": meta.get("displayAddress"),
        "internal_address": meta.get("address"),
        "publisher": meta.get("publisher"),
        "position": str(meta.get("pos")),
        "announcement_date": meta.get("announcementDate"),
        "promulgation_date": meta.get("promulgation"),
        "entry_into_force": meta.get("entryIntoForce"),
        "status_pl": meta.get("status"),
        "keywords": ", ".join(meta.get("keywords") or []),
        "text_source": "pdf",
        "pages_without_text": page_ranges(no_text_pages or []),
        "pages_with_images": page_ranges(image_pages or []),
        "pages_unmapped_glyphs": page_ranges(unmapped_pages or []),
        "pages_ocr": page_ranges(ocr_pages or []),
        "pages_images_ocr": page_ranges(image_ocr_pages or []),  # pages_with_images whose image text was read by OCR
        "ocr": ocr_engine if ocr_pages or image_ocr_pages else "",
        "converter": f"eli2md {__version__}",
        "disclaimer": "Nieoficjalny tekst z automatycznej konwersji PDF. Wiążący jest PDF w "
                      + ("Monitorze Polskim." if meta.get("publisher") == "MP" else "Dzienniku Ustaw."),
    }
    lines = ["---"]
    for k, v in fields.items():
        if v not in (None, "", "None"):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


FN_LABEL = re.compile(r"^\[\^(\d+)\]\s*(.*)$", re.S)


def _footnote_pages(doc: Document) -> dict[str, list[int]]:
    """Footnote number -> pages on which a footnote with that number is printed, in order."""
    occ: dict[str, list[int]] = {}
    for f, pg in zip(doc.footnotes, doc.footnote_pages or [0] * len(doc.footnotes)):
        if m := FN_LABEL.match(f):
            occ.setdefault(m.group(1), []).append(pg)
    return occ


def _fn_label(n: str, j: int) -> str:
    return n if j == 0 else f"{n}_{j + 1}"  # the 2nd footnote numbered 1 is [^1_2]


def _fix_refs(text: str, page: int, occ: dict[str, list[int]]) -> str:
    """Footnote numbering restarts in annexes and forms, so one number can label several footnotes.
    A marker refers to the one printed on the page where its block starts, or the nearest later one."""
    def sub(m: re.Match) -> str:
        pages = occ.get(m.group(1), [])
        if len(pages) < 2:
            return m.group(0)
        j = next((k for k, pg in enumerate(pages) if pg >= page), len(pages) - 1)
        return f"[^{_fn_label(m.group(1), j)}]"
    return re.sub(r"\[\^(\d+)\]", sub, text)


def to_markdown(doc: Document, meta: dict | None = None) -> str:
    """Markdown body: one block per paragraph, top-level units (Art. or, if none, §) as h5."""
    occ = _footnote_pages(doc)
    if any(len(v) > 1 for v in occ.values()):
        doc = replace(doc, blocks=[replace(b, text=_fix_refs(b.text, b.page, occ)) for b in doc.blocks])
    depths = quote_depths(doc.blocks)
    # Top-level unit per part (main text, each annex): Art. if the part has an "Art. N." at depth 0, else §.
    # A paragraph "Art. 42 ust. 1 ustawy określa…" in an annex does not count (DU/2024/553).
    part, parts = 0, []
    for b in doc.blocks:
        part += b.kind == "annex"
        parts.append(part)
    with_art = {p for b, d, p in zip(doc.blocks, depths, parts) if d == 0 and b.kind != "ocr"
                and UNIT_HEAD["Art."].match(b.text)}
    out = []
    if meta:
        out += [frontmatter(meta, no_text_pages=doc.no_text_pages, image_pages=doc.image_pages,
                            ocr_pages=doc.ocr_pages, ocr_engine=doc.ocr_engine, unmapped_pages=doc.unmapped_pages,
                            image_ocr_pages=doc.image_ocr_pages),
                "# " + meta["title"]]
    run: list[int] = []  # consecutive pages without text get one note
    for i, b in enumerate(doc.blocks):
        if b.kind == "ocr":  # each OCR page (or image of text) starts with its own note
            if i == 0 or doc.blocks[i - 1].kind != "ocr" or doc.blocks[i - 1].page != b.page:
                lang = doc.ocr_langs.get(b.page)
                note = image_ocr_note if b.page in doc.image_ocr_pages else ocr_note
                out.append(note(b.page, f"{doc.ocr_engine}, {lang}" if lang else doc.ocr_engine))
            out.append("> " + _escape_ocr(" ".join(b.text.split())))  # a quote block: not the text layer
        elif b.kind == "notext":
            run.append(b.page)
            nxt = doc.blocks[i + 1] if i + 1 < len(doc.blocks) else None
            if not (nxt and nxt.kind == "notext" and nxt.page == b.page + 1):
                out.append(no_text_note(run))
                run = []
        elif b.kind == "unmapped":
            out.append(f"> [Na stronie {b.page} PDF większość znaków nie ma kodów Unicode (np. formularz). "
                       "Tekst poniżej jest niepełny, pełna treść jest tylko w PDF.]")
        elif b.kind == "image":
            out.append(f"> [Na stronie {b.page} PDF jest obraz (np. wzór, rysunek, skan). "
                       "Jego treści tu nie ma, jest tylko w PDF.]")
        elif b.kind == "annex":
            out.append("## " + b.text)
        elif b.kind == "signature":
            out.append("*" + b.text + "*")
        elif depths[i] == 0 and (m := UNIT_HEAD["Art." if parts[i] in with_art else "§"].match(b.text)) \
                and not m.group(2).startswith("„"):
            out.append("##### " + m.group(1))
            if m.group(2):
                out.append(_escape_text(m.group(2)))
        elif m := QUOTED_UNIT.match(b.text):
            out += [m.group(1), m.group(2)]
        else:
            out.append(_escape_text(b.text))
    seen: Counter = Counter()
    for f in doc.footnotes:
        if m := FN_LABEL.match(f):
            out.append(f"[^{_fn_label(m.group(1), seen[m.group(1)])}]: {m.group(2)}")
            seen[m.group(1)] += 1
        else:
            out.append(f)
    return "\n\n".join(out) + "\n"
