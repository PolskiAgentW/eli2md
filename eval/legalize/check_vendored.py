"""The vendored converter (legalize.fetcher.pl.pdf) gives the same Markdown and tree as eli2md without OCR.
Usage: python check_vendored.py PDF [PDF ...]   (legalize venv with eli2md installed)"""
import sys
import time

from eli2md.pdf import convert as e_convert, to_markdown as e_md
from eli2md.tree import md_to_tree as e_tree
from legalize.fetcher.pl.pdf.convert import convert as v_convert, to_markdown as v_md
from legalize.fetcher.pl.pdf.tree import md_to_tree as v_tree

same = diff = 0
t0 = time.time()
for p in sys.argv[1:]:
    a, b = e_md(e_convert(p)), v_md(v_convert(p))
    if a == b and e_tree(a) == v_tree(b):
        same += 1
    else:
        diff += 1
        print("DIFF", p)
print(f"same {same} diff {diff} ({time.time() - t0:.0f}s)")
