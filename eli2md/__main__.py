"""CLI: python -m eli2md DU/2025/900 [-o out.md] [--json] [--ocr [LANG]]   or   python -m eli2md file.pdf"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .eli import fetch
from .ocr import LANG, OcrUnavailable, check
from .pdf import convert, to_markdown
from .tree import md_to_tree


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eli2md", description="Dziennik Ustaw PDF -> Markdown")
    ap.add_argument("act", help="ELI id (e.g. DU/2025/900) or path to a local PDF")
    ap.add_argument("-o", "--output", help="output file (default: stdout)")
    ap.add_argument("--format", choices=("md", "json"), default="md",
                    help="md: Markdown; json: tree of units (art., §, ust., pkt, lit., tiret), see eli2md.tree")
    ap.add_argument("--json", action="store_const", const="json", dest="format", help="same as --format json")
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
    if a.format == "json":
        md = json.dumps(md_to_tree(md), ensure_ascii=False, indent=1) + "\n"
    if a.output:
        Path(a.output).write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
