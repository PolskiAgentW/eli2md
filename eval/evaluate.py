"""Compare PDF conversion against the official HTML text (2024 acts have both).

Metric: word tokens (\\w+, case-sensitive, punctuation ignored), aligned with difflib.
  recall    = matched / reference tokens  (how much of the official text we recover)
  precision = matched / converted tokens  (how much extra text we produce)
Body text and footnotes are scored separately (footnote order differs between formats).
Usage: python -m eval.evaluate SAMPLE_JSON [--show POS]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eli2md.pdf import convert  # noqa: E402

CACHE = Path.home() / "cache" / "eli"


def html_reference(html: str) -> tuple[str, str]:
    """Return (body_text, footnotes_text) from ELI act HTML."""
    s = BeautifulSoup(html, "html.parser")
    for sel in ["script", "style", ".tooltip-text", "ul.toc", "h2.part", ".show-all"]:
        for t in s.select(sel):
            t.decompose()
    for a in s.select("a.gloss-link"):  # footnote reference markers
        a.decompose()
    notes = []
    for g in s.select(".gloss-section"):
        notes.append(g.get_text(" "))
        g.decompose()
    return s.get_text(" "), " ".join(notes)


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[\^\w+\]", " ", text)  # our footnote markers
    return re.findall(r"\w+", text)


def score(ref: list[str], hyp: list[str]) -> dict:
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    m = sum(b.size for b in sm.get_matching_blocks())
    return {
        "ref": len(ref),
        "hyp": len(hyp),
        "matched": m,
        "recall": m / len(ref) if ref else 1.0,
        "precision": m / len(hyp) if hyp else 1.0,
    }


def show_diff(ref: list[str], hyp: list[str], limit: int = 40) -> None:
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    n = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        print(f"{op:8} REF: {' '.join(ref[i1:i2])[:150]!r}\n         PDF: {' '.join(hyp[j1:j2])[:150]!r}")
        n += 1
        if n >= limit:
            break


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--show", type=int, help="print differences for one act (pos)")
    ap.add_argument("--out", help="write per-act results JSON here")
    a = ap.parse_args()
    items = json.loads(Path(a.sample).read_text())
    if a.show:
        items = [i for i in items if i["pos"] == a.show]
    rows = []
    for it in items:
        d = CACHE / "DU" / "2024" / str(it["pos"])
        t0 = time.time()
        doc = convert(str(d / "text.pdf"))
        dt = time.time() - t0
        ref_body, ref_notes = html_reference((d / "text.html").read_text(encoding="utf-8"))
        rb, hb = tokens(ref_body), tokens("\n".join(doc.paragraphs))
        rn, hn = tokens(ref_notes), tokens("\n".join(doc.footnotes))
        body, notes = score(rb, hb), score(rn, hn)
        rows.append({"pos": it["pos"], "type": it["type"], "secs": round(dt, 2), "body": body, "notes": notes})
        print(f"{it['pos']:5} {it['type'][:14]:14} body R={body['recall']:.3f} P={body['precision']:.3f} "
              f"(ref {body['ref']}, hyp {body['hyp']})  notes R={notes['recall']:.3f} P={notes['precision']:.3f}"
              f"  {dt:.1f}s", flush=True)
        if a.show:
            show_diff(rb, hb)
            print("--- footnotes")
            show_diff(rn, hn, 15)
    for part in ("body", "notes"):
        ref = sum(r[part]["ref"] for r in rows)
        hyp = sum(r[part]["hyp"] for r in rows)
        m = sum(r[part]["matched"] for r in rows)
        macro_r = sum(r[part]["recall"] for r in rows) / len(rows)
        print(f"TOTAL {part}: micro R={m / max(ref, 1):.4f} P={m / max(hyp, 1):.4f}  macro R={macro_r:.4f}  "
              f"acts with R<0.95: {sum(1 for r in rows if r[part]['recall'] < 0.95)}/{len(rows)}")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
