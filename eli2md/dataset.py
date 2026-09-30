"""Build or update a directory of Markdown texts of Dziennik Ustaw acts that have only PDF text.

    python -m eli2md.dataset --root DIR [--years 2025 2026] [--max N] [--time-budget SEC] [--jobs N] [--all] [--json]
        [--rewrite-json] [--ocr [LANG]]

Layout: DIR/<PUB>/<year>/<PUB>-<year>-<pos>.md and DIR/index.csv (one row per act, including failures);
<PUB> is DU (Dziennik Ustaw, default) or MP (Monitor Polski, --publisher MP).
With --json also DIR/<PUB>/<year>/<PUB>-<year>-<pos>.json (tree of units, eli2md.tree) next to each .md.
An act is (re)converted when it is new, when its ELI `changeDate` differs from the index, or when
it previously failed (or always, with --all). With --ocr also acts with pages without a text layer that
were never converted with OCR (index column ocr_pages empty) and acts with image pages whose images were
never tried as images of text (column image_ocr_pages empty; it is new in 0.6.4). Downloads are sequential
and polite (see eli.fetch); conversion can be parallel.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import resource
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber

from . import __version__
from .eli import API, fetch, get
from .ocr import LANG as OCR_LANG, OcrUnavailable, check as check_ocr
from .pdf import convert, to_markdown
from .tree import md_to_tree

FIELDS = ["eli", "year", "pos", "type", "title", "announcement_date", "promulgation", "change_date",
          "pdf_sha256", "pages", "words", "no_text_pages", "image_pages", "ocr_pages", "image_ocr_pages", "status", "error",
          "converter", "converted_at"]
FIRST_PDF_ONLY_YEAR = 2025  # from 2025 the ELI API has no HTML text for DU (checked 2026-09-29)


def load_index(root: Path) -> dict[str, dict]:
    f = root / "index.csv"
    if not f.exists():
        return {}
    with f.open(newline="", encoding="utf-8") as fh:
        return {r["eli"]: r for r in csv.DictReader(fh)}


def save_index(root: Path, index: dict[str, dict]) -> None:
    rows = sorted(index.values(), key=lambda r: (int(r["year"]), int(r["pos"])))
    tmp = root / "index.csv.tmp"
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(root / "index.csv")


def md_path(root: Path, year: int, pos: int, publisher: str = "DU") -> Path:
    return root / publisher / str(year) / f"{publisher}-{year}-{pos}.md"


def _limit_memory(gb: float) -> None:
    """Worker initializer: an oversized PDF then raises MemoryError (recorded as an error row)
    instead of the kernel OOM killer taking down the whole run."""
    if gb > 0:
        lim = int(gb * 2**30)
        resource.setrlimit(resource.RLIMIT_AS, (lim, lim))


def json_path(md_file: Path) -> Path:
    return md_file.with_suffix(".json")


def write_json(md: str, md_file: Path) -> None:
    json_path(md_file).write_text(json.dumps(md_to_tree(md), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


_POISONED = False  # this worker hit its memory limit (see _convert_one)


def _convert_one(job: tuple[str, str, str, bool, str | None]) -> dict:
    """Worker: convert one downloaded act. Returns the index row fields it determines.
    After a MemoryError the worker's heap stays near the address-space limit: its next acts failed as
    "PdfminerException" and one outside the try stopped the whole run (MP/2020/1070, 2026-09-30). So such a worker
    only hands its next acts back ("retry"), and main() converts them in a fresh pool."""
    global _POISONED
    eli, pdf_path, out_path, with_json, ocr = job
    if _POISONED:
        return {"eli": eli, "status": "retry"}
    t0 = time.time()
    try:
        meta = json.loads((Path(pdf_path).parent / "meta.json").read_text())
        doc = convert(pdf_path, ocr=ocr, position=meta.get("pos"))
        md = to_markdown(doc, meta)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_text(md, encoding="utf-8")
        if with_json:
            write_json(md, Path(out_path))
        with pdfplumber.open(pdf_path) as p:
            pages = len(p.pages)
        return {"eli": eli, "status": "ok", "error": "", "pages": pages,
                "words": sum(len(b.text.split()) for b in doc.blocks), "no_text_pages": len(doc.no_text_pages),
                "image_pages": len(doc.image_pages), "ocr_pages": len(doc.ocr_pages) if ocr else "",
                "image_ocr_pages": len(doc.image_ocr_pages) if ocr else "",
                "secs": round(time.time() - t0, 1)}
    except MemoryError:
        _POISONED = True  # report below, once the frames holding the large objects are released
    except Exception as e:  # keep going; the failure is recorded in the index
        return {"eli": eli, "status": "error", "error": f"{type(e).__name__}: {e}"[:300],
                "trace": traceback.format_exc(limit=3), "secs": round(time.time() - t0, 1)}
    return {"eli": eli, "status": "error", "error": "MemoryError (over --mem-limit-gb)",
            "secs": round(time.time() - t0, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="eli2md.dataset")
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--publisher", choices=("DU", "MP"), default="DU", help="DU: Dziennik Ustaw; MP: Monitor Polski")
    ap.add_argument("--years", type=int, nargs="*",
                    default=list(range(FIRST_PDF_ONLY_YEAR, dt.date.today().year + 1)))
    ap.add_argument("--max", type=int, default=0, help="at most this many acts per run (0 = no limit)")
    ap.add_argument("--time-budget", type=float, default=0, help="stop downloading after this many seconds")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--all", action="store_true", help="reconvert every act (e.g. after a converter change)")
    ap.add_argument("--mem-limit-gb", type=float, default=3,
                    help="address-space limit per conversion worker (0 = none)")
    ap.add_argument("--json", action="store_true", help="also write the tree of units as .json next to each .md")
    ap.add_argument("--rewrite-json", action="store_true",
                    help="with --json: rebuild the .json of up-to-date acts too (after a change in eli2md.tree)")
    ap.add_argument("--ocr", nargs="?", const=OCR_LANG, metavar="LANG",
                    help=f"OCR pages without a text layer with tesseract (off by default; LANG default {OCR_LANG})")
    a = ap.parse_args(argv)
    if a.ocr:
        try:
            check_ocr(a.ocr)
        except OcrUnavailable as e:
            ap.error(str(e))
    t_start = time.time()
    a.root.mkdir(parents=True, exist_ok=True)
    index = load_index(a.root)

    todo = []
    for year in a.years:
        items = json.loads(get(f"{API}/{a.publisher}/{year}"))["items"]
        for it in sorted(items, key=lambda i: i["pos"]):
            if not it.get("textPDF") or it.get("textHTML"):
                continue
            old = index.get(it["ELI"])
            needs_ocr = bool(a.ocr and old and (int(old.get("no_text_pages") or 0) > 0 and not old.get("ocr_pages")
                                                or int(old.get("image_pages") or 0) > 0 and not old.get("image_ocr_pages")))
            if not a.all and old and old["change_date"] == it["changeDate"] and old["status"] == "ok" \
                    and md_path(a.root, year, it["pos"], a.publisher).exists() and not needs_ocr:
                mdf = md_path(a.root, year, it["pos"], a.publisher)
                if a.json and (a.rewrite_json or not json_path(mdf).exists()):  # the tree needs no reconversion
                    write_json(mdf.read_text(encoding="utf-8"), mdf)
                continue
            todo.append((it, old))
        time.sleep(1)
    print(f"to convert: {len(todo)}", flush=True)
    if a.max:
        todo = todo[: a.max]

    jobs = []
    for it, old in todo:
        if a.time_budget and time.time() - t_start > a.time_budget:
            print("time budget reached, stopping downloads", flush=True)
            break
        eli, year, pos = it["ELI"], it["year"], it["pos"]
        refresh = bool(old) and old.get("change_date") != it["changeDate"]
        try:
            meta, pdf = fetch(eli, refresh=refresh)
        except Exception as e:
            index[eli] = {**_base_row(it), "status": "error", "error": f"download: {type(e).__name__}: {e}"[:300]}
            continue
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        index[eli] = {**_base_row(it), "pdf_sha256": sha}
        jobs.append((eli, str(pdf), str(md_path(a.root, year, pos, a.publisher)), a.json, a.ocr))

    done, by_eli = 0, {j[0]: j for j in jobs}
    for attempt in range(1, 4):  # acts handed back by a worker over its memory limit go to a fresh pool
        retry = []
        with ProcessPoolExecutor(max_workers=max(1, a.jobs), initializer=_limit_memory,
                                 initargs=(a.mem_limit_gb,)) as ex:
            for res in ex.map(_convert_one, jobs):
                if res["status"] == "retry":
                    retry.append(by_eli[res["eli"]])
                    continue
                done += _record(index, res)
                if done % 50 == 0:
                    print(f"converted {done}/{len(by_eli)}", flush=True)
                    save_index(a.root, index)
        if not retry:
            break
        print(f"pass {attempt}: {len(retry)} acts handed back by a worker over its memory limit", flush=True)
        jobs = retry
    for eli, *_ in jobs if retry else []:  # still handed back after the last pass
        done += _record(index, {"eli": eli, "status": "error", "error": "MemoryError in an earlier act (not retried)"})
    save_index(a.root, index)
    ok = sum(1 for r in index.values() if r["status"] == "ok")
    print(f"done: {done} converted this run; index: {ok} ok / {len(index)} total; "
          f"{time.time() - t_start:.0f}s", flush=True)
    return 0


def _record(index: dict[str, dict], res: dict) -> int:
    """Put a worker's result into the index row of its act; 1 (acts done)."""
    row = index[res["eli"]]
    row.update({k: res[k] for k in ("status", "error", "pages", "words", "no_text_pages", "image_pages",
                                    "ocr_pages", "image_ocr_pages") if k in res})
    row.update(converter=f"eli2md {__version__}",
               converted_at=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if res["status"] != "ok":
        print(f"ERROR {res['eli']}: {res['error']}", flush=True)
    return 1


def _base_row(it: dict) -> dict:
    return {"eli": it["ELI"], "year": it["year"], "pos": it["pos"], "type": it["type"], "title": it["title"],
            "announcement_date": it.get("announcementDate", ""), "promulgation": it.get("promulgation", ""),
            "change_date": it["changeDate"]}


if __name__ == "__main__":
    sys.exit(main())
