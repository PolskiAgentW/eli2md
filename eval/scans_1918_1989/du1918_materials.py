#!/usr/bin/env python3
"""Materials for the quality protocol (journal/du1918_jakosc.md): for each act of SAMPLE, from MD_DIR (output of
tools/du1918_dev.py) into OUT/<DU-YYYY-POS>/: tekst_md.md, tekst_100.txt, tekst_100_numerowany.txt, strona-1.png (200 dpi: the first PDF page the text has, see below).

Usage: du1918_materials.py SAMPLE.csv MD_DIR OUT"""
import csv
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from du1918_dev import tokens  # noqa: E402

CACHE = Path.home() / "cache/eli"


def main():
    sample, md_dir, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    for r in csv.DictReader(open(sample)):
        pub, year, pos = r["eli"].split("/")
        name = f"{pub}-{year}-{pos}"
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        md = (md_dir / f"{name}.md").read_text(encoding="utf-8")
        (d / "tekst_md.md").write_text(md, encoding="utf-8")
        toks = tokens(md)[:100]
        (d / "tekst_100.txt").write_text(" ".join(toks) + "\n", encoding="utf-8")
        (d / "tekst_100_numerowany.txt").write_text("".join(f"{k}\t{t}\n" for k, t in enumerate(toks, 1)), encoding="utf-8")
        # the first page of the PDF that the text has (an act may start on page 3 of its PDF: DU/1989/257)
        first = re.search(r"^> \[Strona (\d+) PDF", md, re.M)
        page = first.group(1) if first else "1"
        subprocess.run(["pdftoppm", "-f", page, "-l", page, "-r", "200", "-png", "-singlefile",
                        str(CACHE / pub / year / pos / "text.pdf"), str(d / "strona-1")], check=True)
        print(name, len(toks))


if __name__ == "__main__":
    main()
