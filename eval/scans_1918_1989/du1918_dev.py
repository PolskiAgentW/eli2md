#!/usr/bin/env python3
"""Reconvert DU acts (1918-1989 scans) with the eli2md code in CODE (OCR from ~/ocrcache) and show how each starts.

Usage: du1918_dev.py CODE OUT ELI... | --sample CSV   [--jobs N] [--tokens N]
CODE: directory with the eli2md package (e.g. /home/ai/wt/du1918-fix/eli2md). OUT: directory for .md files.
Prints per act: the first N tokens of the text as in the quality protocol (journal/du1918_jakosc.md):
body after front matter, without the "# title" line and "> " notes, without "#", "**", "|"."""
import argparse
import csv
import json
import os
import inspect
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

CACHE = Path.home() / "cache/eli"
LISTS = Path.home() / "ext/eli_lists_20261008"  # ELI year lists (tools/eli_lists_fetch.py)


def tokens(md: str) -> list[str]:
    body = md.split("\n---\n", 1)[1] if md.startswith("---\n") else md
    lines = [l for l in body.splitlines() if not l.startswith("# ") and not l.startswith(">")]
    text = re.sub(r"[#|]|\*\*", " ", "\n".join(lines))
    return text.split()


def one(job):
    code, out, eli = job
    sys.path.insert(0, code)
    from eli2md.pdf import convert, to_markdown
    pub, year, pos = eli.split("/")
    d = CACHE / pub / year / pos
    meta = json.loads((d / "meta.json").read_text())
    try:
        params = inspect.signature(convert).parameters
        extra = {"year": meta.get("year")} if "year" in params else {}
        if "neighbors" in params:  # ELI titles of the positions near the act, from the year's list (as eli2md.dataset)
            lst = LISTS / f"{pub}-{year}.json"
            items = json.loads(lst.read_text())["items"] if lst.exists() else []
            p0 = int(pos)
            extra["neighbors"] = {i["pos"]: i.get("title", "") for i in items if p0 - 3 <= i["pos"] <= p0 + 3 and i["pos"] != p0}
        md = to_markdown(convert(str(d / "text.pdf"), ocr="auto", position=meta.get("pos"), title=meta.get("title"),
                                 **extra), meta)
    except Exception as e:  # noqa: BLE001
        return eli, f"ERROR {type(e).__name__}: {e}", []
    f = Path(out) / f"{pub}-{year}-{pos}.md"
    f.write_text(md, encoding="utf-8")
    return eli, "", tokens(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("out")
    ap.add_argument("eli", nargs="*")
    ap.add_argument("--sample")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--tokens", type=int, default=40)
    a = ap.parse_args()
    os.environ.setdefault("ELI2MD_OCR_CACHE", "/home/ai/ocrcache")
    elis = list(a.eli)
    if a.sample:
        elis += [r["eli"] for r in csv.DictReader(open(a.sample))]
    Path(a.out).mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(a.jobs) as ex:
        for eli, err, toks in ex.map(one, [(a.code, a.out, e) for e in elis]):
            print(f"{eli}\t{err or len(toks)}\t{' '.join(toks[:a.tokens])}")


if __name__ == "__main__":
    main()
