"""Convert a born-digital Dziennik Ustaw PDF into paragraphs + footnotes.

Layout facts this relies on (checked on 2024 acts, see eval/):
- page 1 starts with the gazette masthead ending with a line "Poz. N";
- later pages start with a running header "Dziennik Ustaw – N – Poz. N";
- footnotes sit below a thin horizontal rule (a ~144pt wide rect) in 9pt type;
- footnote markers are superscripts in ~6pt type;
- paragraphs are separated by a larger vertical gap than lines within a paragraph.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

import pdfplumber

RUNNING_HEADER = re.compile(r"^Dziennik Ustaw\s*[–-]\s*\d+\s*[–-]\s*Poz\.\s*\d+\s*$")
MASTHEAD_END = re.compile(r"^Poz\.\s*\d+\s*$")
# Lines that start a new unit even without a vertical gap (used at page breaks).
UNIT_START = re.compile(
    r"^(Art\.\s*\d|§\s*\d|\d+[a-z]*\.\s|\d+[a-z]*\)\s|[a-z]{1,3}\)\s|–\s|Rozdział\s|DZIAŁ\s|Oddział\s|Załącznik)"
)
LOWER = "a-ząćęłńóśźż"
ANNEX = re.compile(r"^Załącznik")
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


def _page_lines(page, pno: int) -> tuple[list[Line], list[Line]]:
    """Return (body_lines, footnote_lines) for one page."""
    words = page.extract_words(extra_attrs=["size"], keep_blank_chars=False)
    if not words:
        return [], []
    sizes = Counter()
    for w in words:
        sizes[round(w["size"], 1)] += len(w["text"])
    body_size = sizes.most_common(1)[0][0]
    sup_limit = body_size * 0.75

    # Cluster words into lines. Superscripts attach to the line they overlap vertically.
    normal = sorted((w for w in words if w["size"] >= sup_limit), key=lambda w: (w["top"], w["x0"]))
    sups = [w for w in words if w["size"] < sup_limit]
    rows: list[list[dict]] = []
    for w in normal:
        mid = (w["top"] + w["bottom"]) / 2
        for r in rows:
            if r[0]["top"] - 1 <= mid <= r[0]["bottom"] + 1 and abs(r[0]["size"] - w["size"]) < 2:
                r.append(w)
                break
        else:
            rows.append([w])
    for s in sups:
        best = min(rows, key=lambda r: abs((r[0]["top"] + r[0]["bottom"]) / 2 - s["bottom"]), default=None)
        if best is not None and abs((best[0]["top"] + best[0]["bottom"]) / 2 - s["bottom"]) < 12:
            best.append({**s, "sup": True})
        else:
            rows.append([{**s, "sup": True}])

    rule_top = None
    for r in page.rects:
        if r["height"] < 1.5 and 130 < r["width"] < 160 and r["x0"] < page.width * 0.2 and r["top"] > page.height * 0.3:
            rule_top = r["top"] if rule_top is None else min(rule_top, r["top"])

    body, notes = [], []
    for r in rows:
        r.sort(key=lambda w: w["x0"])
        parts: list[str] = []
        for w in r:
            if w.get("sup"):
                parts.append(f"[^{w['text'].rstrip(')')}]")
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
            pw=float(page.width),
            ph=float(page.height),
        )
        is_note = (rule_top is not None and line.top > rule_top) or (
            rule_top is None and line.size < body_size - 0.5 and line.top > page.height * 0.6
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


def to_markdown(doc: Document) -> str:
    out = []
    for b in doc.blocks:
        if b.kind == "annex":
            out.append("## " + b.text)
        elif b.kind == "signature":
            out.append("*" + b.text + "*")
        else:
            out.append(b.text)
    for f in doc.footnotes:
        m = re.match(r"^\[\^(\d+)\]\s*(.*)$", f, re.S)
        out.append(f"[^{m.group(1)}]: {m.group(2)}" if m else f)
    return "\n\n".join(out) + "\n"
