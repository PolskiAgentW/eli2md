"""Like fetch_sample.py, but without acts of any earlier sample (eval/sample_*.json), so the result is a test
sample the converter was not tuned on.

Usage: python eval/heldout_sample.py N SEED FIRST-LAST   e.g. 70 5114 2024 -> sample_2024_n70_s5114_heldout.json
Items always carry a "year".
"""
import json
import random
import sys
import time
from pathlib import Path

from fetch_sample import API, CACHE, fetch_act, get

EVAL = Path(__file__).parent


def used() -> set[tuple[int, int]]:
    out = set()
    for f in EVAL.glob("sample_*.json"):
        default_year = int(f.name.split("_")[1]) if f.name.split("_")[1].isdigit() else None
        for i in json.loads(f.read_text()):
            out.add((i.get("year", default_year), i["pos"]))
    return out


def main() -> None:
    n, seed = int(sys.argv[1]), int(sys.argv[2])
    first, _, last = sys.argv[3].partition("-")
    years = list(range(int(first), int(last or first) + 1))
    skip = used()
    items = []
    for y in years:
        index = CACHE / "DU" / f"{y}.json"
        if not index.exists():
            index.write_bytes(get(f"{API}/DU/{y}"))
            time.sleep(1)
        items += [i for i in json.loads(index.read_text())["items"]
                  if i.get("textHTML") and i.get("textPDF") and (i["year"], i["pos"]) not in skip]
    items.sort(key=lambda i: (i["year"], i["pos"]))
    print(f"{len(items)} acts with PDF and HTML outside earlier samples ({len(skip)} excluded)", flush=True)
    out = []
    for i in random.Random(seed).sample(items, n):
        fetch_act("DU", i["year"], i["pos"])
        out.append({"year": i["year"], "pos": i["pos"], "type": i["type"], "title": i["title"]})
        print(i["year"], i["pos"], i["type"], i["title"][:70], flush=True)
    name = f"sample_{first}{'-' + last if last else ''}_n{n}_s{seed}_heldout.json"
    (EVAL / name).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("->", name)


if __name__ == "__main__":
    main()
