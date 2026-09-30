"""Per-article comparison of the PDF conversion with the official HTML on consolidated texts (teksty jednolite).

For tools that quote one article of a code (e.g. legal-cite), the question is whether the article read from the
Markdown has the same words as in the HTML. Acts: the 12 consolidated texts that legal-cite
(apiotrowski-afk/legal-cite-pl) uses today, i.e. the newest one with HTML for each of its acts (checked 2026-10-01).
Reference: top-level articles of the consolidated text in the HTML (section part_2 = annex of the obwieszczenie;
quoted articles inside amendments are not top-level). Footnotes and their markers are dropped on both sides.
Markdown: `##### Art. N.` blocks after the first `## ` (annex) heading, up to the next `##### ` or `## `.
Articles are matched by number (HTML id arti_22_1_a = Markdown "Art. 22¹ᵃ."); an article number that occurs
more than once (several versions) is compared in order of occurrence.
Tokens as in evaluate.py (words, case-folded, punctuation ignored).
Usage: python eval/tj_articles.py [--out FILE] [--show ELI]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eli2md import __version__  # noqa: E402
from eli2md.pdf import SUP_CHARS, convert, to_markdown  # noqa: E402
from evaluate import tokens as _tokens  # noqa: E402
from fetch_sample import fetch_act  # noqa: E402

ACTS = {  # legal-cite code -> consolidated text it uses (newest with textHTML=true)
    "KC": (2024, 1061), "KP": (2023, 1465), "KSH": (2024, 18), "KPC": (2024, 1568), "KK": (2024, 17),
    "PrAut": (2022, 2509), "u.r.p.": (2024, 499), "u.ś.u.d.e.": (2024, 1513), "u.z.n.k.": (2022, 1233),
    "u.p.k.": (2024, 1796), "UODO": (2019, 1781), "u.k.k.": (2024, 1497),
}
NESTED = re.compile(r"(?:^|-)(?:arti|para|pass|pint|lett|slet|tire)_[^-]+-")
PLAIN = str.maketrans(SUP_CHARS, "0123456789abcdefghijklmnoprstuvwxyz")
SUP_RUN = re.compile(f"[{SUP_CHARS}]+")
# a heading of a part of the act between articles ("DZIAŁ DZIESIĄTY", "Rozdział II", "Oddział 3"): ends the article
HEADING = re.compile(r"(?s)^(?i:dział|rozdział|oddział|tytuł|księga|część)\s+(?:[IVXLC]+|\d+|[A-ZĄĆĘŁŃÓŚŹŻ]{4,})[a-zA-Z]?"
                     r"[¹²³⁴⁵⁶⁷⁸⁹⁰ᵃᵇᶜᵈᵉᶠᵍʰ]*\.?(?:\s+\S.{0,200})?$")


def tokens(text: str) -> list[str]:
    """As evaluate.tokens, but a run of small characters is one token (§ 1¹⁰ = HTML "§ 1<sup>10</sup>"), and a
    one-letter token after a short number is joined to it on both sides ("Art. 151⁹ᵃ" is "151 9a" here and
    "151 9 a" in the HTML, which puts the letter outside <sup>)."""
    out: list[str] = []
    for w in _tokens(SUP_RUN.sub(lambda m: " " + m.group().translate(PLAIN) + " ", text)):
        if out and len(w) == 1 and w.isalpha() and out[-1].isdigit() and len(out[-1]) <= 3:
            out[-1] += w
        else:
            out.append(w)
    return out


def html_articles(html: str) -> list[tuple[str, list[str]]]:
    s = BeautifulSoup(html, "html.parser")
    for sel in ["script", "style", ".tooltip-text", "ul.toc", "a.gloss-link", ".gloss-section"]:
        for t in s.select(sel):
            t.decompose()
    sections = s.select("section[id^=part_]")
    root = sections[1] if len(sections) > 1 else s
    out = []
    for u in root.select(".unit[id]"):
        m = re.search(r"(?:^|-)arti_([^-]+)$", u["id"])
        if m and not NESTED.search(u["id"]):
            out.append((m.group(1).lower(), tokens(u.get_text(" "))))
    return out


def md_key(num: str) -> str:
    """'22¹ᵃ' -> '22_1_a', '36a' -> '36a', '237¹³ᵃ' -> '237_13_a'."""
    m = re.match(rf"(\d+[a-z]*)([{SUP_CHARS}]*)", num)
    base, sup = m.group(1), m.group(2)
    if not sup:
        return base
    plain = sup.translate(PLAIN)
    digits, letters = re.match(r"(\d*)([a-z]*)", plain).groups()
    return "_".join(x for x in (base, digits, letters) if x)


def md_articles(md: str) -> list[tuple[str, list[str]]]:
    out, cur, in_annex = [], None, False
    for raw in md.split("\n\n"):
        para = raw.strip()
        if re.match(r"\[\^\w+\]:", para) or (raw.startswith("    ") and cur is None):
            cur = None  # footnote definitions (and their indented paragraphs) come after the text
            continue
        if para.startswith("## "):
            if in_annex and cur:  # the next annex ends the consolidated text
                break
            in_annex, cur = True, None
            continue
        if not in_annex or not para:
            continue
        m = re.match(rf"##### Art\. (\d+[a-z]*[{SUP_CHARS}]*)\.", para)
        if m:
            cur = [md_key(m.group(1)), ""]
            out.append(cur)
        elif para.startswith("##### ") or HEADING.match(para):
            cur = None
        if cur is not None:
            cur[1] += " " + para.lstrip("#")
    return [(k, tokens(t)) for k, t in out]


def compare(ref: list, hyp: list) -> dict:
    by_key = defaultdict(list)
    for k, t in hyp:
        by_key[k].append(t)
    seen = defaultdict(int)
    rows = []
    for k, rt in ref:
        i = seen[k]
        seen[k] += 1
        ht = by_key[k][i] if i < len(by_key[k]) else None
        if ht is None:
            rows.append({"art": k, "status": "missing", "ratio": 0.0})
            continue
        sm = difflib.SequenceMatcher(None, rt, ht, autojunk=False)
        ratio = sm.ratio()
        rows.append({"art": k, "status": "identical" if rt == ht else "differs", "ratio": round(ratio, 4),
                     "ref_tokens": len(rt), "diff": [] if rt == ht else [
                         (op, " ".join(rt[a:b])[:120], " ".join(ht[c:d])[:120])
                         for op, a, b, c, d in sm.get_opcodes() if op != "equal"][:5]})
    extra = sum(max(0, len(v) - seen.get(k, 0)) for k, v in by_key.items())
    return {"rows": rows, "extra_md_articles": extra}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--show")
    a = ap.parse_args()
    summary, tot = {}, defaultdict(int)
    for code, (year, pos) in ACTS.items():
        d = fetch_act("DU", year, pos)
        ref = html_articles((d / "text.html").read_text(encoding="utf-8"))
        md = to_markdown(convert(str(d / "text.pdf")))
        (d / f"eli2md-{__version__}.md").write_text(md, encoding="utf-8")
        res = compare(ref, md_articles(md))
        rows = res["rows"]
        c = defaultdict(int)
        for r in rows:
            c[r["status"]] += 1
            c["ge99"] += r["ratio"] >= 0.99
        n = len(rows)
        for k in ("identical", "differs", "missing", "ge99"):
            tot[k] += c[k]
        tot["n"] += n
        summary[code] = {"eli": f"DU/{year}/{pos}", "articles": n, **dict(c), "extra_md_articles": res["extra_md_articles"],
                         "worst": sorted([r for r in rows if r["status"] != "identical"], key=lambda r: r["ratio"])[:8]}
        print(f"{code:11} DU/{year}/{pos:<5} art {n:4}  identical {c['identical']:4} ({c['identical'] / max(n, 1):.1%})"
              f"  >=.99 {c['ge99']:4}  differs {c['differs']:3}  missing {c['missing']:3}"
              f"  extra {res['extra_md_articles']}", flush=True)
        if a.show == f"DU/{year}/{pos}":
            for r in rows:
                if r["status"] != "identical":
                    print(" ", r["art"], r["status"], r["ratio"], r.get("diff"))
    n = tot["n"]
    print(f"TOTAL art {n}  identical {tot['identical']} ({tot['identical'] / n:.1%})  >=.99 {tot['ge99']} "
          f"({tot['ge99'] / n:.1%})  differs {tot['differs']}  missing {tot['missing']}  (eli2md {__version__})")
    if a.out:
        Path(a.out).write_text(json.dumps({"version": __version__, "total": dict(tot), "acts": summary},
                                          ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
