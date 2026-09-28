"""CLI: python -m eli2md DU/2025/900 [-o out.md]   or   python -m eli2md file.pdf"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .eli import fetch
from .pdf import convert, to_markdown


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eli2md", description="Dziennik Ustaw PDF -> Markdown")
    ap.add_argument("act", help="ELI id (e.g. DU/2025/900) or path to a local PDF")
    ap.add_argument("-o", "--output", help="output file (default: stdout)")
    a = ap.parse_args(argv)
    if Path(a.act).suffix.lower() == ".pdf":
        meta, pdf = None, Path(a.act)
    else:
        meta, pdf = fetch(a.act)
    md = to_markdown(convert(str(pdf)), meta)
    if a.output:
        Path(a.output).write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
