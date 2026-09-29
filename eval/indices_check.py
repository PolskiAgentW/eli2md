"""Article headings with an index (Art. 479³⁰ᶠ): PDF vs Markdown vs JSON, two converter outputs side by side.

PDF: lines of pdfplumber's extract_text starting with "Art. N." or "Art. N[x]." (the bracketed index of 2026
prints), optionally followed by a footnote marker ("Art. 18[3d].11)"). An approximation: it also counts articles
quoted in amendments or announcements when their line does not start with „, which are rightly not headings.
Markdown: "##### Art." headings; JSON: `art` nodes (main text and annexes). Symptoms of eli2md <= 0.6.2:
"Art. 479 [30f] ." paragraphs, paragraphs starting with moved indices ("[30f] [30] Art. 479 ."), and
"art. 18 [3a]" (a word, a space, a bracketed index).

Usage: python eval/indices_check.py BASE_DIR NEW_DIR ACTS_FILE   (dirs laid out as <PUB>/<year>/<PUB>-<year>-<pos>.md/.json,
ACTS_FILE: one PUB/YEAR/POS per line); prints a Markdown table.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

CACHE = Path.home() / "cache" / "eli"
PDF_ART = re.compile(r"^Art\. \d+[a-z]*(\[\d{1,3}[a-z]{0,3}\])?\.(?:\d{1,3}\))?(?:\s|$)")
SUPS = "⁰¹²³⁴⁵⁶⁷⁸⁹ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ"
MD_HEAD = re.compile(r"^##### Art\. ", re.M)
MD_HEAD_IDX = re.compile(rf"^##### Art\. \d+[a-z]*[{SUPS}]+\.", re.M)
MD_BROKEN = re.compile(r"^(?:\[\d+[a-z]*\] )*Art\. \d+[a-z]* \[\d+[a-z]*\]", re.M)
MD_LEAD = re.compile(r"^(?:\[\d+[a-z]*\] )+", re.M)
MD_SPACED = re.compile(r"\w \[\d{1,3}[a-z]{0,3}\]")


def pdf_counts(key: str) -> tuple[int, int]:
    pub, year, pos = key.split("/")
    tot = idx = 0
    with pdfplumber.open(CACHE / pub / year / pos / "text.pdf") as pdf:
        for p in pdf.pages:
            for line in (p.extract_text() or "").split("\n"):
                if m := PDF_ART.match(line):
                    tot += 1
                    idx += bool(m.group(1))
            p.close()
    return tot, idx


def _arts(nodes: list[dict], out: list[str]) -> list[str]:
    for n in nodes:
        if n.get("type") == "art":
            out.append(n["num"])
        _arts(n.get("children") or [], out)
    return out


def out_counts(root: str, key: str) -> dict[str, int]:
    pub, year, pos = key.split("/")
    f = Path(root) / pub / year / f"{pub}-{year}-{pos}.md"
    md = f.read_text(encoding="utf-8")
    t = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
    nums = _arts(t["body"], [])
    for a in t.get("annexes", []):
        nums = _arts(a["body"], nums)
    return {"head": len(MD_HEAD.findall(md)), "head_idx": len(MD_HEAD_IDX.findall(md)),
            "art": len(nums), "art_idx": sum(1 for n in nums if any(c in SUPS for c in n)),
            "broken": len(MD_BROKEN.findall(md)), "lead": len(MD_LEAD.findall(md)), "spaced": len(MD_SPACED.findall(md))}


def main() -> None:
    base, new, acts = sys.argv[1], sys.argv[2], Path(sys.argv[3]).read_text().split()
    print("| act | PDF Art. lines (with [x]) | MD `##### Art.` base → new (with index) | JSON art base → new (with index) "
          "| „Art. N [x] .” paragraphs | paragraphs starting with „[x]” | „w [x]” (spaced) |")
    print("|---|---|---|---|---|---|---|")
    tot: dict[str, int] = {}
    for k in acts:
        p = pdf_counts(k)
        b, n = out_counts(base, k), out_counts(new, k)
        for name, v in [("pdf", p[0]), ("pdf_idx", p[1])] + [("b" + x, v) for x, v in b.items()] \
                + [("n" + x, v) for x, v in n.items()]:
            tot[name] = tot.get(name, 0) + v
        print(f"| {k} | {p[0]} ({p[1]}) | {b['head']} ({b['head_idx']}) → {n['head']} ({n['head_idx']}) "
              f"| {b['art']} ({b['art_idx']}) → {n['art']} ({n['art_idx']}) | {b['broken']} → {n['broken']} "
              f"| {b['lead']} → {n['lead']} | {b['spaced']} → {n['spaced']} |")
    t = tot
    print(f"| **sum** | {t['pdf']} ({t['pdf_idx']}) | {t['bhead']} ({t['bhead_idx']}) → {t['nhead']} ({t['nhead_idx']}) "
          f"| {t['bart']} ({t['bart_idx']}) → {t['nart']} ({t['nart_idx']}) | {t['bbroken']} → {t['nbroken']} "
          f"| {t['blead']} → {t['nlead']} | {t['bspaced']} → {t['nspaced']} |")


if __name__ == "__main__":
    main()
