"""Reference-free check for acts without HTML (2025+): does the Markdown keep the PDF's words?

For each act: word tokens of the whole PDF text layer vs word tokens of the Markdown body
(front matter, markers and headings markup removed). Reports the share of PDF tokens found in
the output (multiset overlap, order ignored) and the share of output tokens found in the PDF.
Running headers and the masthead are in the PDF but not in the output, so ~0.97-0.99 is normal;
much lower values point at dropped text (e.g. text wrongly treated as hidden).
Usage: python eval/selfcheck.py DATA_ROOT [--limit N] [--out FILE]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

import pdfplumber

CACHE = Path.home() / "cache" / "eli"
TOKEN = re.compile(r"\w+")


def tokens(text: str) -> Counter:
    return Counter(t.lower() for t in TOKEN.findall(text))


def md_body(md: str) -> str:
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)
    md = re.sub(r"\A\s*# .*\n", "", md)  # title from metadata; the PDF has it in the body already
    md = re.sub(r"\[\^\d+\]:?", " ", md)
    return re.sub(r"^#+ ", "", md, flags=re.M)


def check(md_file: Path, pdf_file: Path) -> dict:
    with pdfplumber.open(pdf_file) as pdf:
        raw = "\n".join(" ".join(w["text"] for w in p.extract_words()) for p in pdf.pages)
    tp, tm = tokens(raw), tokens(md_body(md_file.read_text(encoding="utf-8")))
    common = sum((tp & tm).values())
    return {"pdf_tokens": sum(tp.values()), "md_tokens": sum(tm.values()),
            "kept": common / max(1, sum(tp.values())), "grounded": common / max(1, sum(tm.values()))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(a.root / "index.csv", encoding="utf-8")) if r["status"] == "ok"]
    if a.limit:
        rows = rows[: a.limit]
    res = []
    for r in rows:
        md = a.root / "DU" / r["year"] / f"DU-{r['year']}-{r['pos']}.md"
        c = check(md, CACHE / "DU" / r["year"] / r["pos"] / "text.pdf")
        res.append({"eli": r["eli"], "type": r["type"], **c})
    res.sort(key=lambda x: x["kept"])
    for x in res[:25]:
        print(f"{x['eli']:14} {x['type'][:14]:14} kept={x['kept']:.3f} grounded={x['grounded']:.3f} "
              f"pdf={x['pdf_tokens']} md={x['md_tokens']}")
    tp = sum(x["pdf_tokens"] for x in res)
    kept = sum(x["kept"] * x["pdf_tokens"] for x in res)
    print(f"n={len(res)} micro kept={kept / max(1, tp):.4f}; kept<0.95: {sum(x['kept'] < 0.95 for x in res)}")
    if a.out:
        a.out.write_text(json.dumps(res, ensure_ascii=False, indent=0))


if __name__ == "__main__":
    main()
