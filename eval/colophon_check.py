"""Which acts of old issues change with the colophon rule, and how: converts again every act whose last PDF page
names an ISSN (the last page of an issue) and compares its Markdown with the one in the dataset, paragraph by
paragraph. Prints the removed and the added paragraphs, so that one can check that only the colophon goes.
Usage: python eval/colophon_check.py ROOT YEAR [YEAR ...] [--jobs N] [--out FILE]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eli2md.dataset import md_path  # noqa: E402
from eli2md.ocr import LANG as OCR_LANG  # noqa: E402
from eli2md.pdf import ISSN, convert, to_markdown  # noqa: E402

CACHE = Path.home() / "cache" / "eli" / "DU"


def last_page_has_issn(pdf: Path) -> bool:
    n = int(next(l.split()[1] for l in subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
                 .stdout.splitlines() if l.startswith("Pages:")))
    text = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), str(pdf), "-"], capture_output=True,
                          text=True).stdout
    return bool(ISSN.search(text))


def paragraphs(md: str) -> list[str]:
    return [p.strip() for p in md.split("---", 2)[-1].split("\n\n") if p.strip()]


def check(job: tuple[str, str, str]) -> dict:
    eli, root, ocr = job
    _, year, pos = eli.split("/")
    pdf = CACHE / year / pos / "text.pdf"
    if not last_page_has_issn(pdf):
        return {"eli": eli, "issn": False}
    meta = json.loads((pdf.parent / "meta.json").read_text())
    new = to_markdown(convert(str(pdf), ocr=ocr or None, position=meta.get("pos")), meta)
    old = md_path(Path(root), int(year), int(pos)).read_text(encoding="utf-8")
    po, pn = paragraphs(old), paragraphs(new)
    so, sn = set(po), set(pn)
    return {"eli": eli, "issn": True, "same": po == pn, "removed": [p for p in po if p not in sn],
            "added": [p for p in pn if p not in so]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("years", nargs="+")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out")
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(Path(a.root) / "index.csv", encoding="utf-8"))
            if r["year"] in a.years and r["status"] == "ok"]
    jobs = [(r["eli"], a.root, OCR_LANG) for r in rows]  # as the dataset: --ocr for every act
    with ProcessPoolExecutor(a.jobs) as ex:
        res = list(ex.map(check, jobs, chunksize=8))
    issn = [r for r in res if r["issn"]]
    changed = [r for r in issn if not r["same"]]
    print(f"acts {len(res)}  last page with ISSN {len(issn)}  changed {len(changed)}  "
          f"with added paragraphs {sum(bool(r['added']) for r in changed)}")
    if a.out:
        Path(a.out).write_text(json.dumps(changed, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
