"""Quality of the consolidated text (annexes[0]) in dziennik-ustaw-md against the PDF text layer, per act.
Results: eval/tj_pdf_layer_2025_2026.md.

    python3 eval/tj_pdf_layer.py ELI_FILE OUT.jsonl [--jobs J]     ELI_FILE: one "DU/2025/1214" per line

DATA: a clone of PolskiAgentW/dziennik-ustaw-md (env TJ_DATA); PDFs from the ELI API in ~/cache/eli/<eli>/text.pdf
(eli2md.eli.fetch).

Per act: C = share of PDF tokens (multiset; page header lines dropped, line-end hyphens joined when the joined word is
in the JSON) found in the JSON texts (title, body, annexes, footnotes); P = share of JSON tokens found in the PDF;
art_pdf = distinct "Art. N." at a line start after the first "Załącznik do obwieszczenia" line; art_json = `art` nodes
in annexes[0] (art numbers compared after NFKC, without spaces, "-" as "–"); missing/extra = article labels only in the PDF / only in the JSON."""
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

CACHE = Path.home() / "cache/eli"
DATA = Path(os.environ.get("TJ_DATA") or Path.home() / "data/dziennik-ustaw-md")
HEADER = re.compile(r"^(Dziennik Ustaw|–\s*\d+\s*–|Poz\. \d+)$")
N = r"\d(?:[\da-ząćęłńóśźż]|\[\d+[a-z]*\])*"  # 22ł, 15g1 / 1013[2] (superscript in the text layer), 87¹ᵃ = 871a
ART = re.compile(rf"^Art\.\s*({N}(?:\s*[–-]\s*{N})?)\s*\.")
TOK = re.compile(r"\w+")


def texts(node, out):
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for x in node:
            texts(x, out)
    elif isinstance(node, dict):
        if node.get("type") == "art":
            out.append("Art.")
        for k, v in node.items():
            if k not in ("type", "path") and not (k == "num" and node.get("type") == "tir"):
                texts(v, out)
    return out


def arts(nodes, out):
    for x in nodes or []:
        if isinstance(x, dict):
            if x.get("type") == "art":
                out.append(norm(str(x.get("num") or "")))
            for k in ("body", "children"):
                if isinstance(x.get(k), list):
                    arts(x[k], out)
    return out


def norm(s):
    return re.sub(r"[\s\[\]]+", "", unicodedata.normalize("NFKC", s)).replace("-", "–")


def measure(eli):
    pub, year, pos = eli.split("/")
    d = json.loads((DATA / pub / year / f"{pub}-{year}-{pos}.json").read_text())
    jtoks = Counter(unicodedata.normalize("NFKC", t).lower() for s in texts([d.get("title"), d.get("body"), d.get("annexes"), d.get("footnotes")], [])
                    for t in TOK.findall(s))
    raw = subprocess.run(["pdftotext", str(CACHE / eli / "text.pdf"), "-"], capture_output=True, text=True).stdout
    lines = [ln for ln in raw.splitlines() if not HEADER.match(ln.strip())]
    text = "\n".join(lines)
    text = re.sub(r"(\w+)-\n(\w+)",
                  lambda m: m.group(1) + m.group(2) if (m.group(1) + m.group(2)).lower() in jtoks else m.group(0), text)
    ptoks = Counter(t.lower() for t in TOK.findall(text))
    common = sum((ptoks & jtoks).values())
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("Załącznik do obwieszczenia")), None)
    pdf_arts = [] if start is None else [norm(m.group(1)) for ln in lines[start:] if (m := ART.match(ln.strip()))]
    ann = (d.get("annexes") or [{}])[0]
    json_arts = arts(ann.get("body"), [])
    sp, sj = set(pdf_arts), set(json_arts)
    return {"eli": eli, "C": round(common / max(1, sum(ptoks.values())), 4),
            "P": round(common / max(1, sum(jtoks.values())), 4),
            "pdf_words": sum(ptoks.values()), "json_words": sum(jtoks.values()),
            "annex_found": start is not None, "art_pdf": len(sp), "art_pdf_lines": len(pdf_arts), "art_json": len(json_arts),
            "missing": sorted(sp - sj), "extra": sorted(sj - sp),
            "body_words": len(TOK.findall(" ".join(texts(d.get("body"), [])))),
            "annex0_words": len(TOK.findall(" ".join(texts(ann.get("body"), []))))}


if __name__ == "__main__":
    elis = [x.strip() for x in open(sys.argv[1]) if x.strip()]
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 4
    with Pool(jobs) as p, open(sys.argv[2], "w") as f:
        for r in p.imap(measure, elis):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
