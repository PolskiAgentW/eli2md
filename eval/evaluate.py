"""Compare PDF conversion against the official HTML text (2024 acts have both; older samples carry a "year").

Metric: word tokens (\\w+, case-folded, punctuation ignored), aligned with difflib.
  recall    = matched / reference tokens  (how much of the official text we recover)
  precision = matched / converted tokens  (how much extra text we produce)
Scored separately: main text (before the first annex, without signature), footnotes
(order differs between formats) and annexes. Annexes that the HTML only links to as PDF
are excluded from the annex reference (marked * in output). Acts whose HTML is a
placeholder are skipped.
Footnotes are also scored leniently ("notes*" line; the numbers above are unchanged): our footnote numbers
("[^3]") count as the HTML's "3)", and our footnote tokens that the HTML has outside its footnotes (main
text or any annex, incl. link-only ones) count as matched for precision. The HTML gives footnotes of
annexes and of consolidated texts as annex text (DU/2024/781, DU/2024/1580).
Usage: python eval/evaluate.py SAMPLE_JSON [--show POS] [--out FILE] [--ocr [LANG]] [--only POS,POS]
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
    # HTML of older acts (DU 2000-2011) has the act's text in div.block outside the sections and the sections are
    # its parts after it (DU/2008/1547: 19 262 words outside, 132 in part_1); in the 2024 HTML all text is in sections
    outside = [b for b in s.select("div.block") if not b.find_parent("section")]
    if sections and len(" ".join(b.get_text(" ") for b in outside).split()) > 50:
        main = title + " " + " ".join(b.get_text(" ") for b in outside)
        annexes = [(sec.get_text(" "), any(a.get("href", "").endswith("text.pdf") for a in sec.find_all("a")))
                   for sec in sections]
    elif sections:
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


def lenient_notes(rn: list[str], footnotes: list[str], ref: dict) -> dict:
    """Footnote score with our numbers kept and our extra tokens looked up in the rest of the HTML."""
    hn = tokens("\n".join(re.sub(r"^\[\^(\d+)(?:_\d+)?\]", r"\1 ", f) for f in footnotes))
    sm = difflib.SequenceMatcher(None, rn, hn, autojunk=False)
    m = sum(b.size for b in sm.get_matching_blocks())
    extra = [t for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal" for t in hn[j1:j2]]
    other = tokens(ref["main"] + "\n" + "\n".join(t for t, _ in ref["annexes"]))
    found = sum(b.size for b in difflib.SequenceMatcher(None, other, extra, autojunk=False).get_matching_blocks()) \
        if extra and other else 0
    return {"ref": len(rn), "hyp": len(hn), "matched": m, "matched_p": m + found}


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


def evaluate_act(pos: int, show: bool = False, year: int = 2024, ocr: str | None = None) -> dict:
    d = CACHE / "DU" / str(year) / str(pos)
    t0 = time.time()
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8")) if (d / "meta.json").exists() else {}
    doc = convert(str(d / "text.pdf"), position=pos, ocr=ocr, title=meta.get("title"))
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
    row["notes_lenient"] = lenient_notes(rn, doc.footnotes, ref)
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
    ap.add_argument("--ocr", nargs="?", const="pol+eng", help="OCR pages without a text layer (as the data sets do)")
    ap.add_argument("--only", help="comma-separated positions to score (e.g. the acts without a text layer)")
    a = ap.parse_args()
    items = json.loads(Path(a.sample).read_text())
    if a.show:
        items = [i for i in items if i["pos"] == a.show]
    if a.only:
        items = [i for i in items if str(i["pos"]) in a.only.split(",")]
    rows = []
    for it in items:
        r = evaluate_act(it["pos"], show=bool(a.show), year=it.get("year", 2024), ocr=a.ocr)  # year: other samples
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
    nl = [r["notes_lenient"] for r in done if r["notes"]["ref"]]
    if nl:
        ref, hyp = sum(x["ref"] for x in nl), sum(x["hyp"] for x in nl)
        print(f"TOTAL notes* (n={len(nl)}): micro R={sum(x['matched'] for x in nl) / max(ref, 1):.4f} "
              f"P={sum(x['matched_p'] for x in nl) / max(hyp, 1):.4f}  (lenient: footnote numbers kept, "
              f"extra tokens found in HTML main/annexes count)")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
