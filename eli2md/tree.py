"""Tree of editorial units (Art., §, ust., pkt, lit., tiret) built from eli2md Markdown.

The tree is built from the Markdown (not from the converter's internal blocks), so that the
JSON can be rebuilt from the published .md files alone. The Markdown keeps what is needed: one
paragraph per unit start, top-level units as `##### ` headings, annexes as `## `, footnotes as
`[^n]: `. Quotation depth is recomputed from the paragraphs with the converter's rules
(pdf.quote_depths) plus two rules for quotes the source does not open or close cleanly
(see tree_depths). Art. nodes come only from `##### Art.` headings: a bare "Art. N." paragraph at
depth 0 is always the number of a quoted article that the converter split off ("Art. 25." + "„1. …").

    {"eli": ..., "title": ..., "converter": ...,         # from the front matter, if present
     "body": [node, ...],                                  # main text
     "annexes": [{"heading": "Załącznik nr 1 ...", "body": [node, ...]}],
     "footnotes": {"1": "..."}}

Unit node: {"type": "art"|"par"|"ust"|"pkt"|"lit"|"tir", "num": "41¹", "path": "art_41¹/ust_2",
            "text": "text after the number", "children": [...]}
Other nodes: {"type": "text", "text": ..., "quoted": true?}   paragraph that is not a unit start
             {"type": "heading", "label": "Rozdział 2", "text": "title"}   dział/rozdział/oddział/...
             {"type": "signature", "text": ...}   {"type": "note", "text": ...}  (content missing in PDF text)

Rules:
- A unit is only recognised at quotation depth 0. Units quoted in amendments ("„Art. 5. …",
  "1) …" after "otrzymuje brzmienie:") are `text` nodes with "quoted": true under the unit
  that contains them.
- Ranks: art > par (§) > ust > pkt > lit > tir (> tir under tir for "– –"). A unit becomes a child of
  the nearest open unit of a higher rank, so an article without ust. can hold pkt directly and
  § in codes sits under Art.
- Numbers keep letters and superscripts as printed: "41¹", "2a". Tirets have no number; `num` is
  their ordinal within the parent.
- A paragraph that is not a unit start becomes a `text` child of the deepest open unit (except the
  first one after a bare number such as `##### Art. N.` or `##### § N.`, which is that unit's own text). So a closing
  sentence after a list of pkt ("część wspólna") ends up under the last pkt: the Markdown has no
  indentation to tell them apart.
- Headings of systematising units (DZIAŁ, Rozdział, Oddział, ...) are flat `heading` nodes between
  the articles (articles are not nested in chapters); the next non-unit paragraph is their title.
- Footnote markers stay in the text as `[^n]`.
- Each annex has its own tree (texts announced as consolidated texts have their own Art./§).
"""
from __future__ import annotations

import json
import re

from .pdf import QUOTE_HEAD, SECONDS, SUP_DIGITS

SUP = SUP_DIGITS
UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
NOTE = r"(?:\[\^\d+\])*"  # footnote markers glued to a unit number: "1a)[^2] treść", "Art. 5.[^3]"
LEAD_NOTES = re.compile(r"^((?:\[\^\d+\]\s*)+)(.*)$", re.S)  # "[^7] 1. Treść" (marker of the Art. heading)
UNIT_RES = [  # (type, regex); groups: number, footnote markers, rest
    ("art", re.compile(rf"^Art\.\s*(\d+[a-z]*[{SUP}]*)\.({NOTE})\s*(.*)$", re.S)),
    ("par", re.compile(rf"^§\s*(\d+[a-z]*[{SUP}]*)\.({NOTE})\s*(.*)$", re.S)),
    # "2.Ustala się" (no space in the PDF) is a unit too, "1.1. Cel" is not
    ("ust", re.compile(rf"^(\d+[a-z]*[{SUP}]*)\.({NOTE})(?:\s+|(?=[{UPPER}]))(\S.*)$", re.S)),
    ("pkt", re.compile(rf"^(\d+[a-z]*[{SUP}]*)\)({NOTE})\s+(\S.*)$", re.S)),
    ("lit", re.compile(rf"^([a-z]{{1,3}}[{SUP}]*)\)({NOTE})\s+(\S.*)$", re.S)),
]
TIRET = re.compile(r"^((?:–\s*)+)\s(\S.*)$", re.S)  # "– tekst", "– – tekst"
RANK = {"art": 0, "par": 1, "ust": 2, "pkt": 3, "lit": 4, "tir": 5}
HEADING = re.compile(
    r"^((?:DZIAŁ|Dział|ROZDZIAŁ|Rozdział|ODDZIAŁ|Oddział|TYTUŁ|Tytuł|KSIĘGA|Księga|CZĘŚĆ|Część)"
    rf"\s+(?:[0-9]+[a-z]*[{SUP}]*|[IVXLC]+[a-z]*[{SUP}]*))(?:\s+(.*))?$", re.S)
FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
ANNOUNCES_QUOTE = re.compile(r"(?:brzmienie|brzmieniu)\s*:\s*$")  # "… otrzymuje brzmienie:", "… w brzmieniu:"


def parse_unit(text: str) -> tuple[str, str, str] | None:
    """(type, num, text) if the paragraph starts a unit, else None. Tirets: num is the dash count."""
    for typ, rx in UNIT_RES:
        m = rx.match(text)
        if m:
            rest = m.group(3)
            return typ, m.group(1), (m.group(2) + " " + rest).strip() if m.group(2) else rest
    m = TIRET.match(text)
    if m:
        return "tir", str(m.group(1).count("–")), m.group(2)
    return None


def _closed_later(blocks: list[tuple[str, str]], i: int, limit: int = 60) -> bool:
    """True if a block after i closes a quote it did not open, before anything that starts a
    new top-level unit, opens a quote at its start or announces a new quote."""
    for kind, text in blocks[i + 1:i + 1 + limit]:
        if kind in ("annex", "head"):
            return False
        t = SECONDS.sub("", text)
        if QUOTE_HEAD.match(t):
            return False
        local = 0
        for ch in t:
            if ch in "„“":
                local += 1
            elif ch in "”ˮ":
                if not local:
                    return True
                local -= 1
        if ANNOUNCES_QUOTE.search(t):
            return False
    return False


def tree_depths(blocks: list[tuple[str, str]]) -> list[int]:
    """Quotation depth at the start of each block, as pdf.quote_depths, with three changes:
    - depth is 0 at every `##### ` heading (the converter made it only at its depth 0);
    - after a block ending with "brzmienie:"/"brzmieniu:" the next blocks are quoted even if the
      source left out the opening „ (DU/2024/859: "dodaje się ust. 1a–1c w brzmieniu:" /
      "1a. Jeżeli …" / … "…”,"), but only if a later block closes the quote (_closed_later); tables
      replaced in amendments have no quotes at all (DU/2024/1141);
    - a quote opened mid-block and still open at a block ending with ":" runs into the next blocks
      ("zastępuje się wyrazami „…, w terminach:" / "1) …;" / "2) …”,", DU/2024/859), again only if a
      later block closes it.
    The pdf.quote_depths rule that other mid-block quotes end with their block is kept."""
    out, d, announced = [], 0, False
    for i, (kind, text) in enumerate(blocks):
        if kind in ("annex", "head"):
            d = 0
        t = SECONDS.sub("", text)
        head = QUOTE_HEAD.match(t)
        if announced and d == 0 and kind == "p" and not head and _closed_later(blocks, i - 1):
            d = 1
        out.append(d)
        carry, local = d, 0
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
        if local and t.rstrip().endswith(":") and _closed_later(blocks, i):
            carry += local
        d = carry
        announced = d == 0 and kind == "p" and bool(ANNOUNCES_QUOTE.search(t))
    return out


class _Builder:
    def __init__(self) -> None:
        self.body: list[dict] = []
        self.stack: list[tuple[int, dict]] = []  # (rank, node) of open units
        self.fresh: dict | None = None  # unit with a bare number ("##### § 5.") still waiting for its text
        self.heading: dict | None = None  # heading still waiting for its title

    def _parent_list(self) -> list[dict]:
        return self.stack[-1][1]["children"] if self.stack else self.body

    def close(self) -> None:
        self.stack.clear()
        self.fresh = self.heading = None

    def add_unit(self, typ: str, num: str, text: str) -> None:
        rank = RANK[typ]
        if typ == "tir":
            rank += int(num) - 1  # "– –" nests under "–"
        while self.stack and self.stack[-1][0] >= rank:
            self.stack.pop()
        siblings = self._parent_list()
        if typ == "tir":
            num = str(1 + sum(1 for s in siblings if s["type"] == "tir"))
        seg = {"art": "art", "par": "par", "ust": "ust", "pkt": "pkt", "lit": "lit", "tir": "tir"}[typ]
        path = (self.stack[-1][1]["path"] + "/" if self.stack else "") + f"{seg}_{num}"
        node = {"type": typ, "num": num, "path": path, "text": text, "children": []}
        siblings.append(node)
        self.stack.append((rank, node))
        self.fresh = node if not text else None
        self.heading = None

    def add_text(self, text: str, quoted: bool) -> None:
        if self.fresh is not None and not quoted:
            self.fresh["text"] = text
            self.fresh = None
            return
        if self.heading is not None and not quoted and not self.heading["text"]:
            self.heading["text"] = text
            self.heading = None
            return
        self.fresh = self.heading = None
        node = {"type": "text", "text": text}
        if quoted:
            node["quoted"] = True
        self._parent_list().append(node)

    def add_heading(self, label: str, text: str) -> None:
        self.close()
        node = {"type": "heading", "label": " ".join(label.split()), "text": text}
        self.body.append(node)
        self.heading = node if not text else None

    def add_flat(self, typ: str, text: str) -> None:
        """Signature (ends the units) or a note about content missing from the text layer (in place)."""
        if typ == "signature":
            self.close()
            self.body.append({"type": typ, "text": text})
        else:
            self.fresh = self.heading = None
            self._parent_list().append({"type": typ, "text": text})


def md_to_tree(md: str) -> dict:
    """Build the unit tree from eli2md Markdown (with or without front matter)."""
    out: dict = {"eli": None, "title": None, "converter": None, "source_pdf": None}
    m = FRONT.match(md)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(": ")
            if k in out:
                out[k] = json.loads(v)
        md = md[m.end():]
    paras = [p.strip() for p in md.split("\n\n")]
    paras = [p for p in paras if p]
    if paras and paras[0].startswith("# "):
        out["title"] = out["title"] or paras[0][2:].strip()
        paras = paras[1:]
    footnotes: dict[str, str] = {}
    blocks: list[tuple[str, str]] = []  # (kind, text) in the converter's block kinds
    for p in paras:
        fm = re.match(r"^\[\^(\d+)\]:\s*(.*)$", p, re.S)
        if fm:
            footnotes[fm.group(1)] = fm.group(2)
        elif p.startswith("## "):
            blocks.append(("annex", p[3:].strip()))
        elif p.startswith("##### "):
            blocks.append(("head", p[6:].strip()))
        elif p.startswith("> [") and p.endswith("]"):
            blocks.append(("note", p[2:].strip()))
        elif p.startswith("*") and p.endswith("*") and len(p) > 2:
            blocks.append(("signature", p[1:-1]))
        else:
            blocks.append(("p", p))
    depths = tree_depths(blocks)

    parts = [("main", None, _Builder())]
    for n, ((kind, text), d) in enumerate(zip(blocks, depths)):
        b = parts[-1][2]
        if kind == "annex":
            parts.append(("annex", text, _Builder()))
            continue
        if kind in ("signature", "note"):
            b.add_flat(kind, text)
            continue
        notes, body = "", text
        if kind == "p" and (m := LEAD_NOTES.match(text)):
            notes, body = m.group(1).strip(), m.group(2)
        u = parse_unit(body) if d == 0 or kind == "head" else None
        if u and kind == "p" and u[0] == "art":
            # Art. N. at depth 0 that is not a heading: the converter split "Art. 25. „1. …" into
            # "Art. 25." + "„1. …" (a quoted article) or kept "Art. 30. „1. …" whole
            u = None
            d = 1
        if u and kind == "p" and u[0] == "par" and not u[2] and n + 1 < len(blocks) \
                and blocks[n + 1][1].startswith(("„", "“")):
            u, d = None, 1  # "§ 5." + "„1. …": the same split for a quoted §
        if u:
            if notes and b.fresh is not None:  # "##### Art. 15c." + "[^7] 1. …": the marker belongs to Art.
                b.fresh["text"] = notes
            elif notes:
                u = (u[0], u[1], (notes + " " + u[2]).strip())
            b.add_unit(*u)
        elif d == 0 and (h := HEADING.match(text)) and len(text) < 300:
            b.add_heading(h.group(1), (h.group(2) or "").strip())
        else:
            b.add_text(text, quoted=d > 0 or text.startswith(("„", "“")))
    out["body"] = parts[0][2].body
    out["annexes"] = [{"heading": h, "body": b.body} for _, h, b in parts[1:]]
    out["footnotes"] = footnotes
    return out


def iter_units(nodes: list[dict]):
    """All unit nodes (not text/heading/...) in document order."""
    for n in nodes:
        if n["type"] in RANK:
            yield n
        yield from iter_units(n.get("children", []))
