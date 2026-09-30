"""Measure document structure of the Markdown output against the unit tree in the official HTML.

evaluate.py scores words only. This scores where paragraphs and headings are. The HTML of
2024 acts marks every editorial unit (id ...-arti_N, para_N (§), pass_N (ust.), pint_N (pkt),
lett_x (lit.), slet_x (tiret), chpt_N, bran_X). Reference and Markdown are tokenized as in
evaluate.py and aligned with difflib; a unit counts only where its first token is aligned.

  heading R/P  top-level Art. (or § in acts without Art.) that start a `##### ` heading;
               P = share of `##### ` headings that sit on a top-level unit start.
               A quoted unit inside an amendment ("„Art. 5. ...") is not top-level.
  sub R        units of a given type (ust., pkt, lit., ...) that start a Markdown paragraph.
  break P      share of Markdown paragraph starts that fall on any block start in the HTML
               (unit, text block, table cell, title). A miss is a break inside running text.
  break R      share of HTML block starts outside tables (units, paragraphs, headings; not the title)
               where a Markdown paragraph starts. A miss is two paragraphs run together. Table cells
               are left out (tables are flattened row by row), and so is the start of a unit's text
               right after its number, which the HTML puts in a block of its own.
Scored separately for the main text and for annexes (as in evaluate.py, annexes that the HTML
only links to as PDF are left out). Breaks inside the act title are counted apart ("title"):
the PDF prints the title on several lines. Footnotes are dropped.
Usage: python eval/structure.py SAMPLE_JSON [--show POS] [--out FILE]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eli2md.pdf import convert, to_markdown  # noqa: E402
from evaluate import CACHE, tokens  # noqa: E402

UNIT_ID = re.compile(r"(?:^|-)([a-z]+)_[^-]+$")
NESTING = {"arti", "para", "pass", "pint", "lett", "slet", "tire"}  # units that make a child "quoted"
BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "td", "th", "li", "tr", "table"}
SUB_TYPES = ("pass", "pint", "lett", "slet", "arti_q", "para_q", "chpt")


def unit_type(tag: Tag) -> str | None:
    if "unit" not in tag.get("class", []) or not tag.get("id"):
        return None
    m = UNIT_ID.search(tag["id"])
    return m.group(1) if m else None


def _walk(roots: list[Tag]) -> dict:
    toks: list[str] = []
    units: list[tuple[int, str, bool]] = []  # (token index, type, top-level)
    starts: set[int] = set()
    text_starts: set[int] = set()  # block starts outside tables
    for root in roots:
        starts.add(len(toks))
        text_starts.add(len(toks))
        for node in root.descendants:
            if isinstance(node, NavigableString):
                toks.extend(tokens(str(node)))
                continue
            if not isinstance(node, Tag):
                continue
            if node.name in BLOCK_TAGS:
                starts.add(len(toks))
                if node.name not in ("td", "th", "tr", "table") and node.find_parent("table") is None:
                    text_starts.add(len(toks))
            ut = unit_type(node)
            if ut:
                nested = any(unit_type(p) in NESTING for p in node.parents if isinstance(p, Tag))
                units.append((len(toks), ut, not nested))
    return {"tokens": toks, "units": units, "starts": starts, "text_starts": text_starts}


def html_structure(html: str) -> dict | None:
    """Main text and annexes: token stream with unit starts and block starts (token indices)."""
    s = BeautifulSoup(html, "html.parser")
    if "null Pokaż całość" in " ".join(s.get_text(" ").split()):
        return None
    for sel in ["script", "style", ".tooltip-text", "ul.toc", "h2.part", ".show-all", "a.gloss-link",
                ".gloss-section"]:
        for t in s.select(sel):
            t.decompose()
    h1 = s.find("h1")
    sections = s.select("section[id^=part_]")
    # older acts (DU 2000-2011): the act's text in div.block outside the sections, which are its parts (as evaluate.py)
    outside = [b for b in s.select("div.block") if not b.find_parent("section")]
    old_layout = bool(sections) and len(" ".join(b.get_text(" ") for b in outside).split()) > 50
    main = _walk(([h1] if h1 else []) + (outside if old_layout else sections[:1]))
    if len(main["tokens"]) < 10:
        return None
    main["title_end"] = len(tokens(h1.get_text(" "))) if h1 else 0
    annex = _walk([sec for sec in (sections if old_layout else sections[1:])
                   if not any(a.get("href", "").endswith("text.pdf") for a in sec.find_all("a"))])
    annex["title_end"] = 0
    return {"main": main, "annex": annex}


def md_structure(md: str) -> dict:
    """Main text and annexes of the Markdown: token stream with paragraph and heading starts."""
    parts = {k: {"tokens": [], "starts": [], "heads": set()} for k in ("main", "annex")}
    cur = parts["main"]
    for para in md.split("\n\n"):
        para = para.strip()
        if para.startswith("## "):
            cur = parts["annex"]
        if not para or para.startswith("[^"):
            continue
        t = tokens(para.lstrip("#").strip("*"))
        if not t:
            continue
        cur["starts"].append(len(cur["tokens"]))
        if para.startswith("##### "):
            cur["heads"].add(len(cur["tokens"]))
        cur["tokens"].extend(t)
    return parts


def align(ref: list[str], hyp: list[str]) -> tuple[list[int], list[int]]:
    r2h, h2r = [-1] * len(ref), [-1] * len(hyp)
    for a, b, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(n):
            r2h[a + k], h2r[b + k] = b + k, a + k
    return r2h, h2r


def score_part(ref: dict, hyp: dict, head_type: str, c: Counter, show: bool, label: str) -> None:
    """Add counts for one part (main text or annexes) to c; keys are prefixed with label."""
    r2h, h2r = align(ref["tokens"], hyp["tokens"])
    hstarts = set(hyp["starts"])
    bad: list[tuple[str, int]] = []
    top_starts = set()
    for i, t, top in ref["units"]:
        if t == head_type and top:
            key = "head"
            top_starts.add(i)
        elif t in ("arti", "para"):
            key = t if top else t + "_q"  # a top-level § in an act with Art. counts under "para"
        elif t in SUB_TYPES:
            key = t
        else:
            continue
        j = r2h[i] if i < len(r2h) else -1
        if j < 0:
            c[f"{label}.{key}_unaligned"] += 1
            continue
        ok = j in hyp["heads"] if key == "head" else j in hstarts
        c[f"{label}.{key}_n"] += 1
        c[f"{label}.{key}_hit"] += ok
        if not ok:
            bad.append((f"missed {key}", i))
    for j in sorted(hyp["heads"]):
        i = h2r[j]
        if i < 0:
            c[f"{label}.headp_unaligned"] += 1
            continue
        c[f"{label}.headp_n"] += 1
        c[f"{label}.headp_hit"] += i in top_starts
        if i not in top_starts:
            bad.append(("false heading", i))
    for j in hyp["starts"][1:]:
        i = h2r[j]
        if i < 0:
            c[f"{label}.break_unaligned"] += 1
            continue
        key = "title" if i < ref["title_end"] else "break"
        c[f"{label}.{key}_n"] += 1
        c[f"{label}.{key}_hit"] += i in ref["starts"]
        if i not in ref["starts"] and key == "break":
            bad.append(("break inside text", i))
    unit_starts = {u for u, _, _ in ref["units"]}
    for i in sorted(ref["text_starts"]):
        if i == 0 or i < ref["title_end"] or i >= len(r2h):
            continue
        if i not in unit_starts and (i - 1 in unit_starts or i - 2 in unit_starts):
            continue  # the HTML puts a unit's number ("1)", "Art. 5.") and its text in separate blocks
        j = r2h[i]
        if j < 0:
            continue
        c[f"{label}.breakr_n"] += 1
        c[f"{label}.breakr_hit"] += j in hstarts
        if j not in hstarts:
            bad.append(("missed break", i))
    if show:
        rt = ref["tokens"]
        for kind, i in bad[:60]:
            print(f"{label:5} {kind:18} ...{' '.join(rt[max(0, i - 8):i])} | {' '.join(rt[i:i + 10])}")


def evaluate_act(pos: int, show: bool = False, year: int = 2024) -> dict:
    d = CACHE / "DU" / str(year) / str(pos)
    ref = html_structure((d / "text.html").read_text(encoding="utf-8"))
    if ref is None:
        return {"pos": pos, "skipped": "html_unusable"}
    hyp = md_structure(to_markdown(convert(str(d / "text.pdf"))))
    # to_markdown picks one heading unit per act: Art. if there is any, else §
    has_arti = any(t == "arti" and top for part in ref.values() for _, t, top in part["units"])
    head_type = "arti" if has_arti else "para"
    c: Counter = Counter()
    for label in ("main", "annex"):
        score_part(ref[label], hyp[label], head_type, c, show, label)
    return {"pos": pos, "head_type": head_type, "counts": dict(c)}


def rate(c: Counter, key: str) -> str:
    n = c[key + "_n"]
    return f"{c[key + '_hit'] / n:.4f} ({c[key + '_hit']}/{n})" if n else "-"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--show", type=int, help="print misses for one act (pos)")
    ap.add_argument("--out", help="write per-act results JSON here")
    a = ap.parse_args()
    items = json.loads(Path(a.sample).read_text())
    if a.show:
        items = [i for i in items if i["pos"] == a.show]
    rows, total = [], Counter()
    for it in items:
        r = evaluate_act(it["pos"], show=bool(a.show), year=it.get("year", 2024))
        r["type"] = it["type"]
        rows.append(r)
        if "skipped" in r:
            print(f"{it['pos']:5} SKIPPED: HTML reference unusable", flush=True)
            continue
        c = Counter(r["counts"])
        total.update(c)
        print(f"{it['pos']:5} {it['type'][:14]:14} {r['head_type']}  " + "  ".join(
            f"{p}: head R={rate(c, p + '.head')} P={rate(c, p + '.headp')} break P={rate(c, p + '.break')}"
            f" R={rate(c, p + '.breakr')}"
            for p in ("main", "annex") if c[p + ".break_n"]), flush=True)
    done = [r for r in rows if "skipped" not in r]
    print(f"scored {len(done)}/{len(rows)} acts")
    for p in ("main", "annex"):
        print(f"TOTAL {p:5} heading  R={rate(total, p + '.head')}  P={rate(total, p + '.headp')}  "
              f"unaligned: ref {total[p + '.head_unaligned']}, md {total[p + '.headp_unaligned']}")
        for t in SUB_TYPES + ("para",):
            if total[f"{p}.{t}_n"] or total[f"{p}.{t}_unaligned"]:
                print(f"TOTAL {p:5} sub {t:6} R={rate(total, f'{p}.{t}')}  unaligned {total[f'{p}.{t}_unaligned']}")
        print(f"TOTAL {p:5} break    P={rate(total, p + '.break')}  R={rate(total, p + '.breakr')}  unaligned {total[p + '.break_unaligned']}"
              + (f"  (title breaks, not in P: {total[p + '.title_n']})" if total[p + ".title_n"] else ""))
    for p in ("main", "annex"):
        heads = [r["counts"] for r in done if r["counts"].get(p + ".head_n")]
        worse = sum(1 for c in heads if c[p + ".head_hit"] < c[p + ".head_n"])
        if heads:
            print(f"acts with {p} heading R<1: {worse}/{len(heads)}")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
