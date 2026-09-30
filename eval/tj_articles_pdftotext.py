"""Baseline for tj_articles.py: the same per-article comparison with `pdftotext -layout` instead of eli2md.

Tools that read the PDF of a consolidated text often do `pdftotext -layout text.pdf - | grep -n "Art. 503."`.
This measures what that gives on the 12 consolidated texts of tj_articles.py (reference = HTML, same tokens).
Baseline article = from a line starting with `Art. N.` (after "Załącznik do obwieszczenia") to the next such line
or a heading line (DZIAŁ, Rozdział, ...). Two variants:
  raw   - pdftotext output as is;
  clean - page headers ("Dziennik Ustaw – 12 – Poz. 1245") and lines with only a footnote marker removed,
          words hyphenated at line end joined. Footnote bodies stay (they are not marked in the text).
pdftotext writes a superscript as plain characters ("Art. 22¹" -> "Art. 221."), so the article number in the PDF
text is the HTML number with the superscript flattened. Articles are matched by that number in order of occurrence,
as in tj_articles.py (generous to the baseline: a reader of grep output does not know which hit is which);
"colliding" = articles whose flattened number is also another article's number.
"flat" = the same comparison after joining adjacent number tokens on both sides ("22 1" = "221"), i.e. ignoring
the lost superscripts; eli2md is measured the same way on its cached Markdown (eli2md-<version>.md).
Usage: python eval/tj_articles_pdftotext.py [--out FILE]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eli2md import __version__  # noqa: E402
from fetch_sample import fetch_act  # noqa: E402
from tj_articles import ACTS, HEADING, html_articles, md_articles, tokens  # noqa: E402

ART = re.compile(r"^\s*Art\.\s+(\d+[a-z]*\d*[a-z]*)(?:\[(\d+[a-z]*)\])?\.")
PAGE_HEADER = re.compile(r"^\s*Dziennik Ustaw\s+–\s*\d+\s*–\s+Poz\.\s*\d+\s*$")
MARKER_ONLY = re.compile(r"^\s*\d+\)\s*$")


def flat_key(key: str) -> str:
    """HTML key '22_1_a' -> '221a' (what pdftotext prints for Art. 22¹ᵃ); '36a' -> '36a'."""
    return key.replace("_", "")


def pdftotext_articles(text: str, clean: bool) -> list[tuple[str, list[str]]]:
    lines = text.split("\n")
    start = next((i for i, ln in enumerate(lines) if "Załącznik do obwieszczenia" in ln), 0)
    lines = lines[start:]
    if clean:
        lines = [ln for ln in lines if not PAGE_HEADER.match(ln) and not MARKER_ONLY.match(ln)]  # \s matches \f
        joined: list[str] = []
        for ln in lines:
            if joined and re.search(r"\w-$", joined[-1].rstrip()) and re.match(r"\s*[a-ząćęłńóśźż]", ln):
                joined[-1] = joined[-1].rstrip()[:-1] + ln.lstrip()
            else:
                joined.append(ln)
        lines = joined
    out, cur = [], None
    for ln in lines:
        m = ART.match(ln.replace("\f", ""))
        if m:
            cur = [m.group(1) + (m.group(2) or ""), ""]
            out.append(cur)
        elif HEADING.match(ln.strip().replace("\f", "")):
            cur = None
        if cur is not None:
            cur[1] += " " + ln
    return [(k, tokens(t)) for k, t in out]


def join_numbers(tok: list[str]) -> list[str]:
    out: list[str] = []
    for w in tok:
        if out and w[:1].isdigit() and out[-1][:1].isdigit():
            out[-1] += w
        else:
            out.append(w)
    return out


def compare(ref: list, hyp: list, key=lambda k: k) -> dict:
    """As tj_articles.compare: the i-th reference article with a number = the i-th hypothesis article with the
    (flattened) number. This resolves the collisions of flattened numbers in favour of the baseline."""
    by_key = defaultdict(list)
    for k, t in hyp:
        by_key[k].append(t)
    seen = defaultdict(int)
    c = defaultdict(int)
    worst = []
    for k, rt in ref:
        fk = key(k)
        i = seen[fk]
        seen[fk] += 1
        if i >= len(by_key[fk]):
            c["missing"] += 1
            continue
        ht = by_key[fk][i]
        if rt == ht:
            c["identical"] += 1
        else:
            c["differs"] += 1
            worst.append((round(difflib.SequenceMatcher(None, rt, ht, autojunk=False).ratio(), 4), k))
        c["flat_identical"] += join_numbers(rt) == join_numbers(ht)
    c["n"] = len(ref)
    return {"counts": dict(c), "worst": sorted(worst)[:5]}


def collisions(ref: list) -> list[str]:
    """Reference articles whose flattened number is also the flattened number of ANOTHER article (22¹ and 221):
    in pdftotext output both are "Art. 221.", so grep for one finds both."""
    real = defaultdict(set)
    for k, _ in ref:
        real[flat_key(k)].add(k)
    return sorted({k for k, _ in ref if len(real[flat_key(k)]) > 1})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args()
    ver = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True).stderr.split("\n")[0]
    res, tot = {}, defaultdict(lambda: defaultdict(int))
    for code, (year, pos) in ACTS.items():
        d = fetch_act("DU", year, pos)
        ref = html_articles((d / "text.html").read_text(encoding="utf-8"))
        text = subprocess.run(["pdftotext", "-layout", str(d / "text.pdf"), "-"], capture_output=True, text=True,
                              check=True).stdout
        md = (d / f"eli2md-{__version__}.md").read_text(encoding="utf-8")
        res[code] = {
            "eli": f"DU/{year}/{pos}",
            "raw": compare(ref, pdftotext_articles(text, clean=False), flat_key),
            "clean": compare(ref, pdftotext_articles(text, clean=True), flat_key),
            "eli2md": compare(ref, md_articles(md)),
            "colliding_numbers": collisions(ref),
        }
        tot["colliding"]["n"] += len(res[code]["colliding_numbers"])
        line = f"{code:11} DU/{year}/{pos:<5}"
        for v in ("raw", "clean", "eli2md"):
            cc = res[code][v]["counts"]
            for k, x in cc.items():
                tot[v][k] += x
            line += f"  {v} {cc.get('identical', 0):4}/{cc['n']:<4} flat {cc.get('flat_identical', 0):4}"
        print(line + f"  colliding {len(res[code]['colliding_numbers'])}", flush=True)
    for v in ("raw", "clean", "eli2md"):
        t = defaultdict(int, tot[v])
        print(f"TOTAL {v:6} identical {t['identical']}/{t['n']} ({t['identical'] / t['n']:.1%})  flat "
              f"{t['flat_identical']} ({t['flat_identical'] / t['n']:.1%})  differs {t['differs']}  missing "
              f"{t['missing']}")
    print(f"articles whose pdftotext number collides with another article: {tot['colliding']['n']}")
    print(f"({ver}; eli2md {__version__})")
    if a.out:
        Path(a.out).write_text(json.dumps({"pdftotext": ver, "eli2md": __version__, "total": tot, "acts": res},
                                          ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
