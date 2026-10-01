"""pdf.js (pdfjs-dist) on the acts scored by extractors_2000_2009.py, with the same reference and metrics.

Separate from extractors_2000_2009.py because it needs Node.js: pdfjs_text.mjs, with pdfjs-dist installed in
PDFJS_DIR (`npm install pdfjs-dist@4.10.38`). Reads the per-act JSON of extractors_2000_2009.py (which acts were
scored) and prints the rows for pdf.js and pdf.js+table.
Usage: PDFJS_DIR=... python eval/extractors_2000_2009_pdfjs.py eval/extractors_2000_2009_s5207.json
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import CACHE, html_reference, tokens  # noqa: E402
from extractors_2000_2009 import TABLE, score  # noqa: E402

HERE = Path(__file__).resolve().parent


def run(r: dict) -> dict:
    d = CACHE / "DU" / str(r["year"]) / str(r["pos"])
    ref = html_reference((d / "text.html").read_text(encoding="utf-8"))
    rt = tokens(ref["main"] + "\n" + "\n".join(t for t, lo in ref["annexes"] if not lo) + "\n" + ref["notes"])
    t = subprocess.run(["node", str(HERE / "pdfjs_text.mjs"), str(d / "text.pdf")], capture_output=True, text=True,
                       check=True).stdout
    return {"pdf.js": score(rt, tokens(t)), "pdf.js+table": score(rt, tokens(t.translate(TABLE)))}


def main() -> None:
    rows = [r for r in json.loads(Path(sys.argv[1]).read_text()) if "scores" in r]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(run, rows))
    print(f"{len(res)} acts")
    print("| tool | in order R (LCS) | in order P (LCS) | bag R | bag P | words out / words in HTML |")
    for n in res[0]:
        ref, hyp = sum(x[n]["ref"] for x in res), sum(x[n]["hyp"] for x in res)
        lcs, bag = sum(x[n]["lcs"] for x in res), sum(x[n]["bag"] for x in res)
        print(f"| {n} | {lcs / ref:.3f} | {lcs / hyp:.3f} | {bag / ref:.3f} | {bag / hyp:.3f} | {hyp / ref:.2f} |")


if __name__ == "__main__":
    main()
