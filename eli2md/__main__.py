"""CLI: python -m eli2md DU/2025/900 [-o out.md] [--ocr [LANG]]   or   python -m eli2md file.pdf"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .eli import fetch
from .ocr import LANG, OcrUnavailable, check
from .pdf import convert, to_markdown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eli2md", description="Dziennik Ustaw PDF -> Markdown")
    ap.add_argument("act", help="ELI id (e.g. DU/2025/900) or path to a local PDF")
    ap.add_argument("-o", "--output", help="output file (default: stdout)")
    ap.add_argument("--ocr", nargs="?", const=LANG, metavar="LANG",
                    help=f"read pages without a text layer with tesseract OCR (off by default; LANG default {LANG})")
    a = ap.parse_args(argv)
    if a.ocr:
        try:
            check(a.ocr)
        except OcrUnavailable as e:
            ap.error(str(e))
    if Path(a.act).suffix.lower() == ".pdf":
        meta, pdf = None, Path(a.act)
    else:
        meta, pdf = fetch(a.act)
    md = to_markdown(convert(str(pdf), ocr=a.ocr), meta)
    if a.output:
        Path(a.output).write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
