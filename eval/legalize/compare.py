"""Same act through legalize's HTML path and the PDF path, rendered by legalize's renderer; same measure for both.

Measure (on the Markdown body below the front matter and the "# title" line):
  text:  word tokens (\\w+, case-folded), aligned with difflib; R = matched / HTML tokens, P = matched / PDF tokens.
  lines: the shape of each line - heading level + text for "#" lines, indentation + list marker ("1.", "1)",
         "a)", "–") otherwise - aligned the same way; R/P as above. Says whether units sit where the HTML
         path puts them. Quote lines ("> ") are left out: the HTML gives a whole quoted provision as one line,
         the PDF path keeps its paragraphs.
Scored separately: main text (up to the first "## Załącznik" heading) and annexes. P_noref: precision with the
publication references "(Dz. U. … poz. …)" removed from the PDF side first; the Sejm HTML leaves them out.
Acts whose HTML has "[patrz oryginał]" (a part of the text only as a link to the PDF) are counted apart
("placeholder"): there the HTML is not a complete reference.
Usage: python compare.py ELI [ELI ...] [--show] [--out FILE.json]   (legalize venv)
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys

from common import act_dir, body, html_input, meta_bytes, render

DZU = re.compile(r"\((?:t\.\s?j\.\s?)?Dz\.\s?U\.[^()]*\)")
ANNEX = re.compile(r"^## Załącz", re.M)
MARK = re.compile(r"^(\s*)(\d+\w*\.|\d+\w*\)|[a-z]+\)|–|-|>)?\s")


def tokens(md: str) -> list[str]:
    return re.findall(r"\w+", md.lower())


def shapes(md: str) -> list[str]:
    out = []
    for line in md.split("\n"):
        if not line.strip():
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"h{level} " + " ".join(tokens(line)[:4]))
            continue
        if line.lstrip().startswith(">"):  # quoted text: the HTML puts a whole quote on one line
            continue
        m = MARK.match(line)
        ind = len(m.group(1)) if m else len(line) - len(line.lstrip())
        mk = m.group(2) if m and m.group(2) else "text"
        mk = re.sub(r"\d+\w*", "N", mk) if mk[0].isdigit() else ("x)" if mk.endswith(")") else mk)
        out.append(f"{ind}:{mk}")
    return out


def rp(ref: list[str], out: list[str]) -> tuple[float, float, int]:
    sm = difflib.SequenceMatcher(None, ref, out, autojunk=False)
    m = sum(b.size for b in sm.get_matching_blocks())
    return m / max(1, len(ref)), m / max(1, len(out)), m


def strip_title(md: str) -> str:
    b = body(md).lstrip("\n")
    return b.split("\n", 1)[1] if b.startswith("# ") else b


def split(md: str) -> tuple[str, str]:
    m = ANNEX.search(md)
    return (md[: m.start()], md[m.start():]) if m else (md, "")


def compare(eli: str, show: bool = False) -> dict:
    from legalize.fetcher.pl.parser import EliTextParser

    pub, year, pos = eli.split("/")
    norm_id = f"{pub}-{year}-{pos}"
    meta = json.loads(meta_bytes(eli))
    html_md = strip_title(render(eli, EliTextParser().parse_text(html_input(eli))))
    # the PDF path of the pipeline: marker + PDF, as EliClient.get_text returns it for acts without HTML
    marker = f"<!--LEGALIZE norm_id={norm_id} pub_date={meta.get('announcementDate', '')}-->\n".encode()
    pdf_md = strip_title(render(eli, EliTextParser().parse_text(marker + (act_dir(eli) / "text.pdf").read_bytes())))
    res = {"eli": eli, "placeholder": "patrz oryginał" in html_md}
    for part, (h, q) in {"main": (split(html_md)[0], split(pdf_md)[0]),
                         "annex": (split(html_md)[1], split(pdf_md)[1]),
                         "all": (html_md, pdf_md)}.items():
        th, tp, tq = tokens(h), tokens(q), tokens(DZU.sub(" ", q))
        r, p, m = rp(th, tp)
        _, pn, mn = rp(th, tq)
        lr, lp, lm = rp(shapes(h), shapes(q))
        res[part] = {"html_tokens": len(th), "pdf_tokens": len(tp), "matched": m, "R": r, "P": p,
                     "pdf_tokens_noref": len(tq), "matched_noref": mn, "P_noref": pn,
                     "html_lines": len(shapes(h)), "pdf_lines": len(shapes(q)), "lines_matched": lm,
                     "lines_R": lr, "lines_P": lp}
    if show:
        sys.stdout.writelines(difflib.unified_diff(html_md.splitlines(True), pdf_md.splitlines(True),
                                                   "html", "pdf", n=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eli", nargs="+")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = []
    for eli in a.eli:
        try:
            x = compare(eli, a.show)
        except Exception as exc:  # noqa: BLE001
            x = {"eli": eli, "error": f"{type(exc).__name__}: {exc}"}
        res.append(x)
        if "error" in x:
            print(f"{eli:14} ERROR {x['error']}")
        else:
            m, n = x["main"], x["annex"]
            print(f"{eli:14} main R={m['R']:.4f} P={m['P']:.4f} Pn={m['P_noref']:.4f} lines R={m['lines_R']:.3f} "
                  f"P={m['lines_P']:.3f} | annex tok {n['html_tokens']}/{n['pdf_tokens']} R={n['R']:.3f} "
                  f"P={n['P']:.3f}{' PLACEHOLDER' if x['placeholder'] else ''}")
    ok = [x for x in res if "error" not in x]
    for label, group in (("complete HTML", [x for x in ok if not x["placeholder"]]),
                         ("HTML with placeholders", [x for x in ok if x["placeholder"]])):
        if not group:
            continue
        for part in ("main", "annex", "all"):
            def micro(k, ref):
                return sum(x[part][k] for x in group) / max(1, sum(x[part][ref] for x in group))
            print(f"{label:24} n={len(group):3} {part:5} text R={micro('matched', 'html_tokens'):.4f} "
                  f"P={micro('matched', 'pdf_tokens'):.4f} P_noref={micro('matched_noref', 'pdf_tokens_noref'):.4f}"
                  f"  lines R={micro('lines_matched', 'html_lines'):.4f} P={micro('lines_matched', 'pdf_lines'):.4f}")
    print(f"errors: {len(res) - len(ok)}")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
