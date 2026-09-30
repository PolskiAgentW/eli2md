"""Download a reproducible random sample of Dz.U. acts that have both PDF and HTML (default: 2024).

The HTML (official, from the ELI API) is the reference text for evaluating PDF conversion.
Usage: python fetch_sample.py [N] [SEED] [FIRST-LAST]   e.g. 50 7 2000-2011 -> sample_2000-2011_n50_s7.json
(items then have a "year"; the 2024 sample files have none).
"""
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

API = "https://api.sejm.gov.pl/eli/acts"
CACHE = Path.home() / "cache" / "eli"
UA = "eli2md-eval/0.1 (open-source research; polite, 1 req/s)"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_act(publisher: str, year: int, pos: int) -> Path:
    d = CACHE / publisher / str(year) / str(pos)
    d.mkdir(parents=True, exist_ok=True)
    for name in ("text.pdf", "text.html"):
        f = d / name
        if not f.exists() or f.stat().st_size == 0:
            f.write_bytes(get(f"{API}/{publisher}/{year}/{pos}/{name}"))
            time.sleep(1)
    return d


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    first, _, last = (sys.argv[3] if len(sys.argv) > 3 else "2024").partition("-")
    years = list(range(int(first), int(last or first) + 1))
    items = []
    for y in years:
        index = CACHE / "DU" / f"{y}.json"
        index.parent.mkdir(parents=True, exist_ok=True)
        if not index.exists():
            index.write_bytes(get(f"{API}/DU/{y}"))
            time.sleep(1)
        items += [i for i in json.loads(index.read_text())["items"] if i.get("textHTML") and i.get("textPDF")]
    items.sort(key=lambda i: (i["year"], i["pos"]))
    sample = random.Random(seed).sample(items, n)
    out = []
    for i in sample:
        fetch_act("DU", i["year"], i["pos"])
        out.append({"pos": i["pos"], "type": i["type"], "title": i["title"]} if years == [2024]
                   else {"year": i["year"], "pos": i["pos"], "type": i["type"], "title": i["title"]})
        print(i["year"], i["pos"], i["type"], i["title"][:70], flush=True)
    name = f"sample_2024_n{n}_s{seed}.json" if years == [2024] else f"sample_{first}-{last or first}_n{n}_s{seed}.json"
    Path(__file__).with_name(name).write_text(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
