"""Footnote markers: links vs notes printed in the text, counted against the official HTML (2024 acts).

The HTML marks a reference to a footnote as a link (`a.gloss-link`) and prints the markers of notes that are
part of the text (explanations under annex tables, footnotes quoted by amendments) as plain `<sup>1)</sup>`.
The Markdown writes the first as `[^1]` (a Markdown footnote link) and, since 0.6.6, the second as `¹⁾`.
Per act: the number of each kind on both sides; scored as the sum over acts of min(ours, html) / sum of html
(recall) and / sum of ours (precision), for links and for printed notes. Counts only, no positions: a link
counted in the right number can still point to the wrong footnote. Skipped: acts whose HTML is a placeholder or
leaves content out ("patrz oryginał", an annex given only as a link to the PDF): the markers of the missing
tables and forms would count as extra.

Usage: python eval/markers_eval.py SAMPLE_JSON [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eli2md.pdf import SUP_DIGITS, convert, to_markdown  # noqa: E402

CACHE = Path.home() / "cache" / "eli" / "DU"
LINK = re.compile(r"\[\^\d+(?:_\d+)?\](?!:)")
PRINTED = re.compile(rf"[{SUP_DIGITS}]+⁾")
HTML_NOTE = re.compile(r"^\s*\d{1,3}\)\s*$")


def html_counts(html: str) -> dict | None:
    s = BeautifulSoup(html, "html.parser")
    text = " ".join(s.get_text(" ").split())
    if "null Pokaż całość" in text or "patrz oryginał" in text:
        return None
    if any(a.get("href", "").endswith("text.pdf") for sec in s.select("section[id^=part_]")[1:] for a in sec.find_all("a")):
        return None
    for t in s.select(".tooltip-text, .gloss-section, ul.toc, script, style"):
        t.decompose()
    links = s.select("a.gloss-link")
    for a in links:
        a.decompose()
    printed = [x for x in s.find_all(["sup", "SUP"]) if HTML_NOTE.match(x.get_text())]
    return {"links": len(links), "printed": len(printed)}


def md_counts(md: str) -> dict:
    body = "\n\n".join(p for p in md.split("\n\n") if not re.match(r"^\[\^\d+(?:_\d+)?\]:", p))
    return {"links": len(LINK.findall(body)), "printed": len(PRINTED.findall(body))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--out")
    a = ap.parse_args()
    rows, skipped = [], 0
    for it in json.loads(Path(a.sample).read_text()):
        d = CACHE / str(it.get("year", 2024)) / str(it["pos"])
        ref = html_counts((d / "text.html").read_text(encoding="utf-8"))
        if ref is None:
            skipped += 1
            continue
        hyp = md_counts(to_markdown(convert(str(d / "text.pdf"))))
        rows.append({"pos": it["pos"], "html": ref, "md": hyp})
        if ref != hyp:
            print(f"{it['pos']:>5} links html {ref['links']:>4} md {hyp['links']:>4}   "
                  f"printed html {ref['printed']:>4} md {hyp['printed']:>4}", flush=True)
    print(f"scored {len(rows)} acts, skipped {skipped} (HTML incomplete)")
    for k in ("links", "printed"):
        h = sum(r["html"][k] for r in rows)
        m = sum(r["md"][k] for r in rows)
        both = sum(min(r["html"][k], r["md"][k]) for r in rows)
        print(f"TOTAL {k:<8} html {h:>5}  md {m:>5}  R={both / max(h, 1):.4f}  P={both / max(m, 1):.4f}  "
              f"acts equal {sum(r['html'][k] == r['md'][k] for r in rows)}/{len(rows)}")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
