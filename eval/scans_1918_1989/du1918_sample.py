#!/usr/bin/env python3
"""Sample for the quality protocol (journal/du1918_jakosc.md): 4 acts status=ok per decade 1910-1980 from the 0.6.39
index (/home/ai/data/du1918/index.csv), random.Random(SEED).sample on the list sorted by (year, pos), without the acts
of the EXCLUDE samples.  Usage: du1918_sample.py SEED OUT.csv [EXCLUDE.csv ...]"""
import csv
import random
import sys

seed, out, excl = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
skip = {r["eli"] for f in excl for r in csv.DictReader(open(f, encoding="utf-8"))}
rows = [r for r in csv.DictReader(open("/home/ai/data/du1918/index.csv", encoding="utf-8"))
        if r["status"] == "ok" and r["eli"] not in skip]
rows.sort(key=lambda r: (int(r["year"]), int(r["pos"])))
rnd = random.Random(seed)
pick = []
for dec in range(1910, 1990, 10):
    pick += rnd.sample([r for r in rows if dec <= int(r["year"]) < dec + 10], 4)
with open(out, "w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["eli", "year", "pos", "pages", "words", "ocr_pages", "title"])
    for r in pick:
        w.writerow([r["eli"], r["year"], r["pos"], r["pages"], r["words"], r["ocr_pages"], r["title"][:80]])
print(len(pick), "acts ->", out)
