"""Reproducible dev/test samples of international agreements (treaties) that have both PDF and HTML, 2012-2025.

Treaties number their units "Artykuł N" on a line of their own; the HTML marks them as arti_N (pass_N, lett_x), so
tree_eval.py can score them like any other act. One shuffled pool, split into disjoint dev and test samples.
Usage: python fetch_treaties.py [N] [SEED]   -> treaties_dev_n{N}_s{SEED}.json, treaties_test_n{N}_s{SEED}.json
"""
import json
import random
import sys
import time
from pathlib import Path

from fetch_sample import API, CACHE, fetch_act, get

TYPES = ("Umowa międzynarodowa", "Konwencja", "Protokół", "Traktat", "Porozumienie", "Układ")


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 6001
    items = []
    for y in range(2012, 2026):
        index = CACHE / "DU" / f"{y}.json"
        if not index.exists():
            index.write_bytes(get(f"{API}/DU/{y}"))
            time.sleep(1)
        items += [i for i in json.loads(index.read_text())["items"]
                  if i.get("type") in TYPES and i.get("textHTML") and i.get("textPDF")]
    items.sort(key=lambda i: (i["year"], i["pos"]))
    print(f"pool: {len(items)} treaties with HTML and PDF, 2012-2025", flush=True)
    pool = random.Random(seed).sample(items, 2 * n)
    for split, part in (("dev", pool[:n]), ("test", pool[n:])):
        out = []
        for i in part:
            fetch_act("DU", i["year"], i["pos"])
            out.append({"year": i["year"], "pos": i["pos"], "type": i["type"], "title": i["title"]})
        Path(__file__).with_name(f"treaties_{split}_n{n}_s{seed}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1))
        print(split, len(out), flush=True)


if __name__ == "__main__":
    main()
