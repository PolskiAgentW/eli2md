"""Compare PDF conversion against the official HTML text (2024 acts have both).

Metric: word tokens (\\w+, case-folded, punctuation ignored), aligned with difflib.
  recall    = matched / reference tokens  (how much of the official text we recover)
  precision = matched / converted tokens  (how much extra text we produce)
Scored separately: main text (before the first annex, without signature), footnotes
(order differs between formats) and annexes. Annexes that the HTML only links to as PDF
are excluded from the annex reference (marked * in output). Acts whose HTML is a
placeholder are skipped.
Usage: python eval/evaluate.py SAMPLE_JSON [--show POS] [--out FILE]
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
from eli2md.pdf import SUP_CHARS, SUP_LETTERS, convert  # noqa: E402

CACHE = Path.home() / "cache" / "eli"
# the converter writes small digits as ¹/₂ (Art. 41¹); the HTML has <sup>1</sup>, i.e. a separate token
SCRIPTS = {ord(c): f" {i % 10} " for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉")}
# an index with letters (Art. 22¹ᵃ) is one token, as <sup>1a</sup> in the HTML
SUP_LETTER_RUN = re.compile(f"[{SUP_CHARS}]*[{SUP_LETTERS}][{SUP_CHARS}]*")
PLAIN = str.maketrans(SUP_CHARS, "0123456789abcdefghijklmnoprstuvwxyz")


def tokens(text: str) -> list[str]:
    """Word tokens, case-folded (HTML titles are title-case, PDF titles are upper-case)."""
    text = SUP_LETTER_RUN.sub(lambda m: " " + m.group().translate(PLAIN) + " ", unicodedata.normalize("NFC", text))
    text = text.translate(SCRIPTS)
    text = re.sub(r"\[\^\w+\]", " ", text)  # our footnote markers
    return re.findall(r"\w+", text.lower())


def html_reference(html: str) -> dict:
    """Split ELI act HTML into main text, annexes and footnotes.

    Returns {"usable", "main", "annexes": [(text, link_only)], "notes"}.
    link_only: the annex in HTML is (partly) just a link to the PDF, so it is not a
    complete reference for the text we extract from the PDF.
    """
    s = BeautifulSoup(html, "html.parser")
    placeholder = "null Pokaż całość" in " ".join(s.get_text(" ").split())
    for sel in ["script", "style", ".tooltip-text", "ul.toc", "h2.part", ".show-all"]:
        for t in s.select(sel):
            t.decompose()
    for a in s.select("a.gloss-link"):  # footnote reference markers
        a.decompose()
    notes = []
    for g in s.select(".gloss-section"):
        notes.append(g.get_text(" "))
        g.decompose()
    h1 = s.find("h1")
    title = h1.get_text(" ") if h1 else ""
    sections = s.select("section[id^=part_]")
    if sections:
        main = title + " " + sections[0].get_text(" ")
        annexes = [(sec.get_text(" "), any(a.get("href", "").endswith("text.pdf") for a in sec.find_all("a")))
                   for sec in sections[1:]]
    else:
        main, annexes = s.get_text(" "), []
    usable = not placeholder and len(tokens(main)) >= 10
    # "patrz oryginał" = HTML omits content (usually a table/graphic) that the PDF has
    complete = "patrz oryginał" not in " ".join(main.split())
    return {"usable": usable, "complete": complete, "main": main, "annexes": annexes, "notes": " ".join(notes)}


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


def evaluate_act(pos: int, show: bool = False) -> dict:
    d = CACHE / "DU" / "2024" / str(pos)
    t0 = time.time()
    doc = convert(str(d / "text.pdf"))
    dt = time.time() - t0
    ref = html_reference((d / "text.html").read_text(encoding="utf-8"))
    if not ref["usable"]:
        return {"pos": pos, "skipped": "html_unusable"}
    rb = tokens(ref["main"])
    hb = tokens("\n".join(b.text for b in doc.main_blocks() if b.kind != "signature"))
    rn, hn = tokens(ref["notes"]), tokens("\n".join(doc.footnotes))
    text_annexes = [t for t, link_only in ref["annexes"] if not link_only]
    ra = tokens("\n".join(text_annexes))
    ha = tokens("\n".join(b.text for b in doc.annex_blocks()))
    row = {"pos": pos, "secs": round(dt, 2), "body": score(rb, hb), "notes": score(rn, hn), "annex": score(ra, ha)}
    row["body"]["complete_ref"] = ref["complete"]
    row["annex"]["complete_ref"] = len(text_annexes) == len(ref["annexes"])
    row["annex"]["n_annex_html"] = len(ref["annexes"])
    if show:
        show_diff(rb, hb)
        print("--- footnotes")
        show_diff(rn, hn, 15)
        print("--- annexes")
        show_diff(ra, ha, 15)
    return row


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
        r = evaluate_act(it["pos"], show=bool(a.show))
        r["type"] = it["type"]
        rows.append(r)
        if "skipped" in r:
            print(f"{it['pos']:5} SKIPPED: HTML reference unusable (placeholder/empty)")
            continue
        b, n, an = r["body"], r["notes"], r["annex"]
        ann = (f"annex R={an['recall']:.3f}{'' if an['complete_ref'] else '*'}") if an["n_annex_html"] else ""
        print(f"{it['pos']:5} {it['type'][:14]:14} main R={b['recall']:.3f} P={b['precision']:.3f} "
              f"(ref {b['ref']}, hyp {b['hyp']})  notes R={n['recall']:.3f} P={n['precision']:.3f} "
              f"{ann}  {r['secs']:.1f}s", flush=True)
    done = [r for r in rows if "skipped" not in r]
    print(f"scored {len(done)}/{len(rows)} acts")
    for part, subset in (("body", done), ("notes", [r for r in done if r["notes"]["ref"]]),
                         ("annex", [r for r in done if r["annex"]["ref"]])):
        if not subset:
            continue
        ref = sum(r[part]["ref"] for r in subset)
        hyp = sum(r[part]["hyp"] for r in subset)
        m = sum(r[part]["matched"] for r in subset)
        macro_r = sum(r[part]["recall"] for r in subset) / len(subset)
        comp = [r for r in subset if r[part].get("complete_ref", True)]
        cp = sum(r[part]["matched"] for r in comp) / max(sum(r[part]["hyp"] for r in comp), 1)
        print(f"TOTAL {part:5} (n={len(subset)}): micro R={m / max(ref, 1):.4f} P={m / max(hyp, 1):.4f}  "
              f"macro R={macro_r:.4f}  R<0.95: {sum(1 for r in subset if r[part]['recall'] < 0.95)}  "
              f"| P on complete refs (n={len(comp)}): {cp:.4f}")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
