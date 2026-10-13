"""Mutation test of legal-cite-pl's PDF fidelity check (control 2, `wiernosc_pdftotext` in legal_cite/pdf_tj.py):
does it refuse an article whose reading has one word changed?

    python lcp_mutation.py --legal-cite DIR --pdf A.pdf [--pdf B.pdf ...] [--md A.md ...] [--per-act 150] [--seed 7]
                           [--show]

For each PDF: the Markdown is converted as legal-cite-pl does (`to_markdown(convert(pdf))`, installed eli2md) unless
--md gives it (same order as --pdf); the text layer is read with `pdftotext -enc UTF-8`; articles come from
`jednostki_md` and the allowed words as in `odczyt()`: up to 82bd29f _STOPKA, the position number and the words of
`przypisy_md`; from b38cb09 `wyjasnienia_warstwy` (page headers and whole footnotes at their place in the layer).
Then in --per-act random articles one word (4+ letters, not the first or last) is changed: deleted, replaced with
another word of the act, or swapped with the next word, and `wiernosc_pdftotext` runs on the changed article.
The changes depend only on the seed and the articles, so two checkouts of legal-cite (--legal-cite) can be compared
on the same changes. httpx is stubbed: only downloads use it. --show prints the changes that pass.

Measured 2026-10-11 on the 8 consolidated texts legal-cite-pl reads from PDF (Dz.U. 2025 poz. 24, 383, 1362; 2026
poz. 85, 468, 795, 1244, 1245), eli2md 0.6.49, legal-cite-pl 74d31c2, pdftotext 26.01.0, --per-act 150 --seed 7:
deleted 284/317 refused, replaced 290/290, swapped 288/288. All 33 deletions that pass delete a word that occurs in
some footnote of the act (the allowed words are one set for the whole act).
Measured 2026-10-13 on the same 8 texts, eli2md 0.6.54 (their pin since baa68fd), pdftotext 26.01.0, same options:
legal-cite-pl 82bd29f deleted 283/317, replaced 291/291, swapped 284/284; b38cb09 (`wyjasnienia_warstwy`) deleted
327/327, replaced 311/311, swapped 279/279. The changes differ between the two: b38cb09 reads 30 more articles
(numbers like 59aa), so the random sample is not the same.
"""
import argparse
import random
import re
import subprocess
import sys
import tempfile
import types
from pathlib import Path

WORD = re.compile(r"[^\W\d_]{4,}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--legal-cite", required=True, help="checkout of legal-cite-pl (the dir with legal_cite/)")
    ap.add_argument("--pdf", action="append", required=True)
    ap.add_argument("--md", action="append", default=[])
    ap.add_argument("--per-act", type=int, default=150)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, a.legal_cite)
    sys.modules.setdefault("httpx", types.ModuleType("httpx"))
    from legal_cite import pdf_tj as p
    rng = random.Random(a.seed)
    tot: dict[tuple[str, bool], list[int]] = {}
    for n, pdf in enumerate(a.pdf):
        if n < len(a.md):
            md = Path(a.md[n]).read_text(encoding="utf-8")
            if md.startswith("---\n"):  # eli2md dataset file: front matter and title from metadata, else the same
                md = re.sub(r"\A\n*# [^\n]*\n", "", md[md.index("\n---\n", 4) + 5:])
        else:
            from eli2md.pdf import convert, to_markdown
            md = to_markdown(convert(pdf))
        with tempfile.NamedTemporaryFile(suffix=".txt") as t:
            subprocess.run(["pdftotext", "-enc", "UTF-8", pdf, t.name], check=True, capture_output=True)
            raw = p._tokeny_pdftotext(Path(t.name).read_text(encoding="utf-8"))
        przypisy = p.przypisy_md(md)
        jedn, _ = p.jednostki_md(md, przypisy)
        # DU_2026_1245.pdf or cache DU/2026/1245/text.pdf -> 1245, as odczyt() adds it
        pos = re.search(r"(\d+)\D*$", Path(pdf).stem) or re.search(r"(\d+)$", Path(pdf).parent.name)
        footnote_words = {w for tresc in przypisy.values() for w in p.tokeny(tresc)}
        if hasattr(p, "wyjasnienia_warstwy"):  # b38cb09+: a skipped word is explained by its place in the layer
            dozwolone = p.wyjasnienia_warstwy(raw, przypisy, pos.group(1) if pos else "")
        else:
            dozwolone = set(p._STOPKA) | ({pos.group(1)} if pos else set()) | footnote_words
        vocab = sorted({w for j in jedn for w in j.tekst.split() if WORD.fullmatch(w)})
        for i in rng.sample(range(len(jedn)), min(a.per_act, len(jedn))):
            j = jedn[i]
            words = j.tekst.split()
            cand = [k for k, w in enumerate(words) if WORD.fullmatch(w)]
            if len(cand) < 3:
                continue
            k = rng.choice(cand[1:-1])
            kind = rng.choice(["deleted", "replaced", "swapped"])
            changed = words[:]
            if kind == "deleted":
                del changed[k]
            elif kind == "replaced":
                changed[k] = rng.choice([v for v in vocab if v.lower() != words[k].lower()])
            else:
                if words[k + 1].lower() == words[k].lower():
                    continue
                changed[k], changed[k + 1] = changed[k + 1], changed[k]
            passed_before = p.wiernosc_pdftotext(j, raw, dozwolone).ok
            m = p.Jednostka(j.num, j.klucz, " ".join(changed), j.odnosniki, j.data)
            refused = not p.wiernosc_pdftotext(m, raw, dozwolone).ok
            c = tot.setdefault((kind, passed_before), [0, 0])
            c[0] += 1
            c[1] += refused
            if a.show and not refused and passed_before:
                print(f"passes: {Path(pdf).name} art. {j.num} {kind} {words[k]!r}"
                      f" (in footnote words: {words[k].lower().strip('.,;:()„”') in footnote_words})")
    for (kind, before), (n, refused) in sorted(tot.items()):
        print(f"{kind:8s} article passed unchanged: {before!s:5s}  changes {n:4d}  refused {refused:4d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
