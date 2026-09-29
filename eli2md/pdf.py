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
from dataclasses import dataclass, field

import pdfplumber
from pdfplumber.utils import extract_words

RUNNING_HEADER = re.compile(r"^Dziennik Ustaw\s*[–-]\s*\d+\s*[–-]\s*Poz\.\s*\d+\s*$")
MASTHEAD_END = re.compile(r"^Poz\.\s*\d+\s*$")
# Lines that start a new unit even without a vertical gap (used at page breaks).
UNIT_START = re.compile(
    r"^(Art\.\s*\d|§\s*\d|\d+[a-z]*\.\s|\d+[a-z]*\)\s|[a-z]{1,3}\)\s|–\s|Rozdział\s|DZIAŁ\s|Oddział\s|Załącznik)"
)
LOWER = "a-ząćęłńóśźż"
ANNEX = re.compile(r"^Załącznik")
INK_DPI, INK_LEVEL = 100, 180  # render resolution; gray level above which a box has no ink
MATH = re.compile("[\U0001D400-\U0001D7FF]")
FOOTNOTE_MARK = re.compile(r"^\d{1,3}\)?[,.;:]?$")
SIGNATURE = re.compile(r"^[A-ZŁŚŻ][\w ]{2,80}: (\w{1,3}\. )+[A-ZŁŚŻ][\w-]+$")


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


@dataclass
class Block:
    kind: str  # "p" | "signature" | "annex" (annex header)
    text: str
    page: int


@dataclass
class Document:
    masthead: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)

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

    def hidden(c: dict) -> bool:
        cx, cy = (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2
        if cy < header_bottom or any(x0 <= cx <= x1 and t <= cy <= b for x0, t, x1, b in boxes):
            return True
        if not c["text"].strip():
            return False
        crop = img.crop((int(c["x0"] * scale), int(c["top"] * scale),
                         int(c["x1"] * scale) + 1, int(c["bottom"] * scale) + 1))
        return crop.getextrema()[0] > INK_LEVEL

    drop = {id(c) for c in placed if hidden(c)}
    return page.filter(lambda o: id(o) not in drop) if drop else page


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
    page = page.dedupe_chars()  # bold is sometimes drawn twice; seen on rotated table pages
    w, h = float(page.width), float(page.height)
    for rot, _ in angles.most_common():
        chars = [_to_frame(c, rot, w, h) for c in page.chars if _char_angle(c) == rot]
        fw, fh = (h, w) if rot in (90, 270) else (w, h)
        words = extract_words(chars, extra_attrs=["size"], keep_blank_chars=False)
        frames.append((words, fw, fh, [_to_frame(r, rot, w, h) for r in page.rects]))
    return frames


def _page_lines(page, pno: int) -> tuple[list[Line], list[Line]]:
    """Return (body_lines, footnote_lines) for one page."""
    body, notes = [], []
    for k, (words, fw, fh, rects) in enumerate(_frames(_drop_hidden_placed(page))):
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
    sups, inline = [], []
    for r in _rows([w for w in words if w["size"] < sup_limit]):
        text = [w for w in r if not FOOTNOTE_MARK.match(w["text"])]
        words_ = [w for w in text if not MATH.search(w["text"])]  # formula scripts are math italic
        if (len(r) >= 3 and words_) or sum(len(w["text"]) for w in words_) >= 15:
            normal += r
        else:
            sups += [w for w in r if FOOTNOTE_MARK.match(w["text"])]
            inline += text
    rows = _rows(normal)
    for s in sups + inline:
        flag = {"sup": True} if s in sups else {}
        best = min(rows, key=lambda r: abs((r[0]["top"] + r[0]["bottom"]) / 2 - s["bottom"]), default=None)
        if best is not None and abs((best[0]["top"] + best[0]["bottom"]) / 2 - s["bottom"]) < 12:
            best.append({**s, **flag})
        else:
            rows.append([{**s, **flag}])

    rule_top = None
    for r in rects:
        if r["height"] < 1.5 and 130 < r["width"] < 160 and r["x0"] < pw * 0.2 and r["top"] > ph * 0.3:
            rule_top = r["top"] if rule_top is None else min(rule_top, r["top"])

    body, notes = [], []
    for r in rows:
        r.sort(key=lambda w: w["x0"])
        parts: list[str] = []
        for w in r:
            if w.get("sup"):
                m = re.match(r"^(\d+)\)?(.*)$", w["text"])
                parts.append(f"[^{m.group(1)}]{m.group(2)}")
            else:
                parts.append(w["text"])
        text = ""
        for p in parts:
            if not text:
                text = p
            elif p.startswith("[^"):
                text += p
            else:
                text += " " + p
        normal_words = [w for w in r if not w.get("sup")] or r
        line = Line(
            page=pno,
            top=min(w["top"] for w in normal_words),
            bottom=max(w["bottom"] for w in normal_words),
            x0=min(w["x0"] for w in r),
            size=Counter(round(w["size"], 1) for w in normal_words).most_common(1)[0][0],
            text=_plain_math(text),
            pw=pw,
            ph=ph,
        )
        is_note = (rule_top is not None and line.top > rule_top) or (
            rule_top is None and line.size < body_size - 0.5 and line.top > ph * 0.6
        )
        (notes if is_note else body).append(line)
    body.sort(key=lambda l: l.top)
    notes.sort(key=lambda l: l.top)
    return body, notes


def _plain_math(text: str) -> str:
    """Map Unicode mathematical alphanumerics (e.g. 𝑊𝑌𝐷 in formulas) to plain letters."""
    return "".join(unicodedata.normalize("NFKC", c) if "\U0001D400" <= c <= "\U0001D7FF" else c for c in text)


def _join(prev: str, nxt: str) -> str:
    if re.search(rf"[{LOWER}]-$", prev) and re.match(rf"[{LOWER}]", nxt):
        return prev[:-1] + nxt
    return prev + " " + nxt


def convert(path: str) -> Document:
    doc = Document()
    body: list[Line] = []
    notes: list[Line] = []
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            b, n = _page_lines(page, pno)
            if pno == 1:
                for i, l in enumerate(b):
                    if MASTHEAD_END.match(l.text):
                        doc.masthead = [x.text for x in b[: i + 1]]
                        b = b[i + 1 :]
                        break
            elif b and RUNNING_HEADER.match(b[0].text):
                b = b[1:]
            body.extend(b)
            notes.extend(n)
            page.close()  # pdfplumber caches every parsed page; 867-page acts exhausted 14 GB RAM

    # Block segmentation: vertical gap (relative to font size); page breaks by content;
    # annex headers and signatures always start their own block.
    cur: Block | None = None
    prev: Line | None = None
    for l in body:
        kind = "p"
        if ANNEX.match(l.text) and l.x0 > 0.4 * l.pw and l.top < 0.2 * l.ph:
            kind = "annex"
        elif SIGNATURE.match(l.text) and l.x0 > 0.45 * l.pw:
            kind = "signature"
        if prev is None or cur is None:
            new = True
        elif kind != "p" or cur.kind == "signature":
            new = not (kind == "annex" and cur.kind == "annex" and l.page == prev.page)
        elif cur.kind == "annex":
            # right-aligned continuation lines of an annex header ("z dnia ... (poz. N)")
            new = not (l.page == prev.page and l.x0 > 0.4 * l.pw and l.top - prev.bottom < 0.8 * l.size)
        elif l.page != prev.page:
            new = bool(UNIT_START.match(l.text)) or bool(re.search(r"[.:;”]$", prev.text))
        else:
            new = l.top - prev.bottom > 0.45 * l.size
        if new:
            if cur is not None:
                doc.blocks.append(cur)
            cur = Block(kind, l.text, l.page)
        else:
            cur.text = _join(cur.text, l.text)
        prev = l
    if cur is not None:
        doc.blocks.append(cur)

    cur = None
    for l in notes:
        if re.match(r"^\[\^\d+\]", l.text) or re.match(r"^\d+\)\s", l.text):
            if cur is not None:
                doc.footnotes.append(cur)
            cur = l.text
        else:
            cur = l.text if cur is None else _join(cur, l.text)
    if cur is not None:
        doc.footnotes.append(cur)
    return doc


UNIT_HEAD = {
    "Art.": re.compile(r"^(Art\.\s*\d+[a-z]*\.)\s*(.*)$", re.S),
    "§": re.compile(r"^(§\s*\d+[a-z]*\.)\s*(.*)$", re.S),
}


def frontmatter(meta: dict, source_pdf: str | None = None) -> str:
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
        "converter": f"eli2md {__version__}",
        "disclaimer": "Nieoficjalny tekst z automatycznej konwersji PDF. Wiążący jest PDF w Dzienniku Ustaw.",
    }
    lines = ["---"]
    for k, v in fields.items():
        if v not in (None, "", "None"):
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def to_markdown(doc: Document, meta: dict | None = None) -> str:
    """Markdown body: one block per paragraph, top-level units (Art. or, if none, §) as h5."""
    unit = "Art." if any(b.text.startswith("Art.") for b in doc.blocks) else "§"
    out = []
    if meta:
        out += [frontmatter(meta), "# " + meta["title"]]
    for b in doc.blocks:
        if b.kind == "annex":
            out.append("## " + b.text)
        elif b.kind == "signature":
            out.append("*" + b.text + "*")
        elif m := UNIT_HEAD[unit].match(b.text):
            out.append("##### " + m.group(1))
            if m.group(2):
                out.append(m.group(2))
        else:
            out.append(b.text)
    for f in doc.footnotes:
        m = re.match(r"^\[\^(\d+)\]\s*(.*)$", f, re.S)
        out.append(f"[^{m.group(1)}]: {m.group(2)}" if m else f)
    return "\n\n".join(out) + "\n"
