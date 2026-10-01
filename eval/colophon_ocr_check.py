"""0.6.19 check: acts whose last page is read by OCR and holds the colophon of the issue (DU 2000-2011).

    python eval/colophon_ocr_check.py INDEX.csv CACHE_DIR OLD_ELI2MD_DIR OUT.json [--jobs 6]

INDEX.csv: index.csv of the published data (rows with ocr_pages > 0 are candidates); CACHE_DIR: <CACHE>/DU/<year>/<pos>/
text.pdf; OLD_ELI2MD_DIR: a checkout of the package before the fix (the directory holding eli2md/). An act is affected if
its last page has no text layer (pdftotext: under 5 words) and eli2md's OCR of that page has a colophon line and an ISSN;
those are converted with the old code and with this one (eli2md.ocr.LANG, as eli2md.dataset --ocr) and their words
counted as in index.csv (words of the blocks).
"""
import csv
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def _words(args):
    root, pdf, pos = args
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from eli2md import pdf as P, ocr as O; "
            "d = P.convert(sys.argv[2], O.LANG, int(sys.argv[3])); print(sum(len(b.text.split()) for b in d.blocks))")
    return int(subprocess.run([sys.executable, "-c", code, root, pdf, pos], capture_output=True, text=True,
                              check=True).stdout)


def _last_page(pdf):
    import pdfplumber
    sys.path.insert(0, str(HERE))
    from eli2md import ocr as O, pdf as P
    with pdfplumber.open(pdf) as p:
        n = len(p.pages)
        if len(subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), pdf, "-"], capture_output=True,
                              text=True).stdout.split()) >= 5:
            return False, False
        read = O.ocr_page(p.pages[-1], O.LANG)
        paras = read.paragraphs if read and O.usable(read) else []
    return True, any(P.COLOPHON.match(t) for t in paras) and any(P.ISSN.search(t) for t in paras)


def main():
    index, cache, old, out = sys.argv[1:5]
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 6
    rows = [r for r in csv.DictReader(open(index, encoding="utf-8")) if r["ocr_pages"] not in ("", "0")]
    pdfs = [f"{cache}/{r['eli']}/text.pdf" for r in rows]
    with ProcessPoolExecutor(jobs) as ex:
        last = list(ex.map(_last_page, pdfs))
    hit = [(r, f) for r, f, (no_layer, col) in zip(rows, pdfs, last) if col]
    with ProcessPoolExecutor(jobs) as ex:
        before = list(ex.map(_words, [(old, f, r["pos"]) for r, f in hit]))
        after = list(ex.map(_words, [(str(HERE), f, r["pos"]) for r, f in hit]))
    acts = [{"eli": r["eli"], "published_words": int(r["words"]), "published_converter": r["converter"],
             "words_without_fix": b, "words_0.6.19": a} for (r, _), b, a in zip(hit, before, after)]
    json.dump({"acts_with_ocr_pages": len(rows), "last_page_without_text_layer": sum(x for x, _ in last),
               "last_page_colophon_and_issn": len(hit), "acts": acts}, open(out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
