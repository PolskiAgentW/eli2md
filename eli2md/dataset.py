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
import os
import resource
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
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


def _out_of_memory(e: BaseException) -> bool:
    """A MemoryError wrapped by pdfplumber ("PdfminerException: " with the MemoryError as its cause, or "Unable to
    allocate output buffer." from the image decoder, MP/2020/235)."""
    while e is not None:
        if isinstance(e, MemoryError) or "Unable to allocate" in str(e):
            return True
        e = e.__cause__ or e.__context__
    return False


def _convert_one(job: tuple) -> dict:
    """Worker: convert one downloaded act. Returns the index row fields it determines.
    After a MemoryError the worker's heap stays near the address-space limit: its next acts failed as
    "PdfminerException" and one outside the try stopped the whole run (MP/2020/1070, 2026-09-30). So such a worker
    exits at its next act; the pool breaks and main() converts the acts not yet recorded in a fresh one. (Handing the
    acts back drained the queue into that worker; a pool per batch of acts waited for the slowest act of each batch.)"""
    global _POISONED
    eli, pdf_path, out_path, with_json, ocr, *more = job
    neighbors = more[0] if more else None  # ELI titles of the positions near the act (see pdf.convert)
    if _POISONED:
        os._exit(3)  # the pool breaks (BrokenProcessPool) and main() goes on with a fresh one
    t0 = time.time()
    try:
        meta = json.loads((Path(pdf_path).parent / "meta.json").read_text())
        doc = convert(pdf_path, ocr=ocr, position=meta.get("pos"), title=meta.get("title"), year=meta.get("year"),
                      neighbors=neighbors)
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
        if _out_of_memory(e):
            _POISONED = True
        else:
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
    titles: dict[int, dict[int, str]] = {}  # year -> {position: ELI title}, for convert(neighbors=)
    for year in a.years:
        items = json.loads(get(f"{API}/{a.publisher}/{year}"))["items"]
        titles[year] = {i["pos"]: i.get("title", "") for i in items}
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
        near = {p: t for p, t in titles.get(year, {}).items() if pos - 3 <= p <= pos + 3 and p != pos}
        jobs.append((eli, str(pdf), str(md_path(a.root, year, pos, a.publisher)), a.json, a.ocr, near))

    done = 0

    def put(res: dict) -> None:
        nonlocal done
        done += _record(index, res)
        if done % 50 == 0:
            print(f"converted {done}/{len(jobs)}", flush=True)
            save_index(a.root, index)

    # A worker that dies (os._exit after a MemoryError, see _convert_one, or killed in native code without one:
    # MP/2019/230, 270 OCR pages, at --mem-limit-gb 1.6) breaks the pool and fails every act in flight. Only --jobs
    # acts are in flight at a time, and after a break each of them is converted alone in a fresh pool, so only the
    # act that kills its worker is recorded as an error; the rest go on in parallel. (Up to 0.6.31 the acts went to
    # a new pool in the same order: the act that killed its worker came first again, and after 5 passes every act
    # after it was recorded as an error, in each later run too. Fixed in 0.6.25.1 and 0.6.32.)
    pending = list(jobs)
    while pending:
        inflight, k = {}, 0
        try:
            with ProcessPoolExecutor(max_workers=max(1, a.jobs), initializer=_limit_memory,
                                     initargs=(a.mem_limit_gb,)) as ex:
                while k < len(pending) and len(inflight) < max(1, a.jobs):
                    inflight[ex.submit(_convert_one, pending[k])] = pending[k]
                    k += 1
                while inflight:
                    for f in wait(inflight, return_when=FIRST_COMPLETED).done:
                        put(f.result())
                        del inflight[f]
                        if k < len(pending):
                            inflight[ex.submit(_convert_one, pending[k])] = pending[k]
                            k += 1
            pending = []
        except BrokenProcessPool:
            suspects = []
            for f, j in inflight.items():
                if f.done() and f.exception() is None:
                    put(f.result())
                else:
                    suspects.append(j)
            print(f"a worker died; {len(suspects)} acts in flight are converted one at a time", flush=True)
            for j in suspects:
                try:
                    with ProcessPoolExecutor(max_workers=1, initializer=_limit_memory,
                                             initargs=(a.mem_limit_gb,)) as ex1:
                        put(ex1.submit(_convert_one, j).result())
                except BrokenProcessPool:
                    put({"eli": j[0], "status": "error", "error": "worker died (over --mem-limit-gb?)"})
            if not suspects and k == 0:  # the pool breaks before any act: give up rather than loop
                for j in pending:
                    put({"eli": j[0], "status": "error", "error": "process pool broke before the act"})
                k = len(pending)
            pending = pending[k:]
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
