"""Diagnose footnote (notes) score differences per act.

For every act with footnotes, align reference footnote tokens (HTML .gloss-section) with
our footnotes (evaluate.py alignment) and look where the unmatched tokens are:
  extras (hurt P): our footnote tokens not matched in HTML footnotes; `extra_in_ref_other` =
    how many of them are found (difflib) in the HTML main text + annexes (all, incl. link-only)
  label_miss: a lone footnote number in the HTML footnotes (we strip "[^1]" markers from ours)
  misses (hurt R): other HTML footnote tokens not matched in our footnotes; `miss_in_hyp_other` =
    how many of them are found in our main text + annexes (incl. signature)
Also prints the unmatched runs so they can be classified by hand.
Usage: python eval/footnotes_diag.py SAMPLE_JSON --out FILE.json [--runs N]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import CACHE, html_reference, tokens  # noqa: E402
from eli2md.pdf import convert  # noqa: E402


def matched(a: list[str], b: list[str]) -> int:
    return sum(x.size for x in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())


def diag_act(pos: int, nruns: int) -> dict | None:
    d = CACHE / "DU" / "2024" / str(pos)
    doc = convert(str(d / "text.pdf"))
    ref = html_reference((d / "text.html").read_text(encoding="utf-8"))
    if not ref["usable"]:
        return None
    rn, hn = tokens(ref["notes"]), tokens("\n".join(doc.footnotes))
    if not rn and not hn:
        return None
    sm = difflib.SequenceMatcher(None, rn, hn, autojunk=False)
    miss, extra, runs = [], [], []
    label_miss = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        if i2 - i1 == 1 and j1 == j2 and re.fullmatch(r"\d+[a-z]?", rn[i1]):
            label_miss += 1  # footnote number: in the HTML text, stripped from ours ("[^1]")
            continue
        miss += rn[i1:i2]
        extra += hn[j1:j2]
        runs.append((op, " ".join(rn[i1:i2])[:200], " ".join(hn[j1:j2])[:200]))
    ref_other = tokens(ref["main"] + "\n" + "\n".join(t for t, _ in ref["annexes"]))
    hyp_other = tokens("\n".join(b.text for b in doc.main_blocks()) + "\n" + "\n".join(b.text for b in doc.annex_blocks()))
    m = len(rn) - len(miss) - label_miss
    return {
        "pos": pos, "ref": len(rn), "hyp": len(hn), "matched": m,
        "n_hyp_notes": len(doc.footnotes),
        "miss": len(miss), "label_miss": label_miss, "extra": len(extra),
        "miss_in_hyp_other": matched(miss, hyp_other) if miss else 0,
        "extra_in_ref_other": matched(extra, ref_other) if extra else 0,
        "runs": runs[:nruns],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=12)
    a = ap.parse_args()
    rows = []
    for it in json.loads(Path(a.sample).read_text()):
        r = diag_act(it["pos"], a.runs)
        if r is None:
            continue
        r["type"] = it["type"]
        rows.append(r)
        print(f"{r['pos']:5} {r['type'][:12]:12} ref {r['ref']:5} hyp {r['hyp']:5} miss {r['miss']:5} "
              f"(label {r['label_miss']:4}; rest in our main/annex {r['miss_in_hyp_other']:5})  extra {r['extra']:5} "
              f"(in HTML main/annex {r['extra_in_ref_other']:5})", flush=True)
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    rows = [r for r in rows if r["ref"]]  # evaluate.py scores notes only where the HTML has them
    R, H = sum(r["ref"] for r in rows), sum(r["hyp"] for r in rows)
    M = sum(r["matched"] for r in rows)
    MX = sum(r["extra_in_ref_other"] for r in rows)
    MM = sum(r["miss_in_hyp_other"] for r in rows)
    L = sum(r["label_miss"] for r in rows)
    print(f"TOTAL n={len(rows)} ref {R} hyp {H} matched {M} R={M / max(R, 1):.4f} P={M / max(H, 1):.4f}; "
          f"label misses {L}, other misses {R - M - L} (found in our main/annex {MM}), extras found in HTML main/annex {MX}")


if __name__ == "__main__":
    main()
