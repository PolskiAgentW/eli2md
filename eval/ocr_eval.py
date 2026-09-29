"""How good is tesseract OCR on Dziennik Ustaw pages, and what does it cost? No hand-made reference.

digital: born-digital pages (with a text layer) of 2025-2026 acts are rendered at 300 dpi, OCRed and
  compared with the page's own text layer: word tokens as in evaluate.py (case-folded \\w+),
  difflib alignment. recall = text-layer words recovered in order, precision = OCR words that
  are in the text layer. Rendered digital pages are cleaner than real scans, so this is an UPPER
  bound for scans. Pages with large images (pages_with_images) are excluded, their image text
  is not in the text layer. Also reported: recall ignoring order (multiset overlap; tables and
  columns are read in another order), without accents, for number tokens only, and after
  ocr.fix_text ("ust. | pkt" -> "ust. 1 pkt"). The reference has its own artefacts: footnote
  markers glued to words ("wsi1"), which OCR drops, count as OCR misses.
scans: OCR (one language, no "auto") of every page without a text layer (pages_without_text in the
  dataset), TSV and text kept in --out; time per page (wall and tesseract CPU).
summary: survey of a `scans` directory: confidence, ocr.usable(), guessed language per act.

Usage:
  python eval/ocr_eval.py digital --root DATA --seed 7310 --agreements 60 --other 40 --langs pol pol+eng eng
  python eval/ocr_eval.py scans --root DATA --lang pol+eng --out DIR [--jobs 2] [--sample 40 --seed 5]
  python eval/ocr_eval.py summary --out DIR
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import random
import re
import resource
import statistics
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eli2md.ocr import (MIN_CONF, MIN_WORDS, _run, check, fix_text, language, ocr_image, parse_tsv,  # noqa: E402
                        render, usable)
from eli2md.pdf import _drop_hidden_placed  # noqa: E402

CACHE = Path(os.environ.get("ELI2MD_CACHE", Path.home() / "cache" / "eli"))
AGREEMENT_TYPES = {"Umowa międzynarodowa", "Oświadczenie rządowe"}
SCRIPTS = {ord(c): f" {i % 10} " for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉")}


def tokens(text: str) -> list[str]:
    """As in evaluate.py: NFC, script digits as separate tokens, case-folded \\w+."""
    text = unicodedata.normalize("NFC", text).translate(SCRIPTS)
    return re.findall(r"\w+", text.lower())


def strip_accents(toks: list[str]) -> list[str]:
    return ["".join(c for c in unicodedata.normalize("NFD", t) if not unicodedata.combining(c)) for t in toks]


def score(ref: list[str], hyp: list[str]) -> dict:
    m = sum(b.size for b in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks())
    return {"ref": len(ref), "hyp": len(hyp), "matched": m,
            "recall": m / len(ref) if ref else 1.0, "precision": m / len(hyp) if hyp else 1.0}


def expand(ranges: str) -> list[int]:
    out: list[int] = []
    for part in filter(None, (p.strip() for p in ranges.split(","))):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def front(md: Path) -> dict:
    head = md.read_text(encoding="utf-8").split("\n---\n", 1)[0]
    return {m.group(1): json.loads(m.group(2)) for m in re.finditer(r"^(\w+): (.*)$", head, re.M)}


def acts(root: Path) -> list[dict]:
    with (root / "index.csv").open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] == "ok"]
    for r in rows:
        r["pdf"] = str(CACHE / "DU" / r["year"] / r["pos"] / "text.pdf")
        r["md"] = root / "DU" / r["year"] / f"DU-{r['year']}-{r['pos']}.md"
    return rows


# ---------------------------------------------------------------- digital pages

def pick_digital(root: Path, seed: int, n_agr: int, n_other: int, min_words: int = 50) -> list[dict]:
    """One random page per randomly chosen act; the page must have >= min_words text-layer words
    and no large image. Acts are drawn without replacement from each pool."""
    rng = random.Random(seed)
    rows = acts(root)
    out = []
    for pool, n in ((True, n_agr), (False, n_other)):
        cand = [r for r in rows if (r["type"] in AGREEMENT_TYPES) == pool]
        rng.shuffle(cand)
        got = 0
        for r in cand:
            if got == n:
                break
            fm = front(r["md"])
            skip = set(expand(fm.get("pages_without_text", ""))) | set(expand(fm.get("pages_with_images", "")))
            pages = [p for p in range(1, int(r["pages"]) + 1) if p not in skip]
            rng.shuffle(pages)
            with pdfplumber.open(r["pdf"]) as pdf:
                for p in pages[:5]:  # a few tries for a page with enough text
                    page = pdf.pages[p - 1]
                    if len(tokens(page.extract_text() or "")) >= min_words:
                        out.append({"eli": r["eli"], "type": r["type"], "page": p, "pdf": r["pdf"]})
                        got += 1
                        break
    return out


def run_digital(job: tuple[dict, list[str], str]) -> dict:
    it, langs, cache = job
    with pdfplumber.open(it["pdf"]) as pdf:
        page = _drop_hidden_placed(pdf.pages[it["page"] - 1])
        # bold masthead text is drawn twice ("Poz. 1010" -> "11001100"); dedupe the reference
        ref_text = page.dedupe_chars().extract_text() or ""
        t0 = time.time()
        img = render(page)
        t_render = time.time() - t0
    ref = tokens(ref_text)
    row = {**it, "lang_text": language(ref), "render_s": round(t_render, 2), "ocr": {}}
    for lang in langs:
        f = Path(cache) / f"{it['eli'].replace('/', '-')}_p{it['page']}.{lang}.txt"
        t0 = time.time()
        if f.exists():
            hyp_text, secs = f.read_text(encoding="utf-8"), None
        else:
            hyp_text = ocr_image(img, lang)
            secs = round(time.time() - t0, 2)
            f.write_text(hyp_text, encoding="utf-8")
        for variant, text in ((lang, hyp_text), (lang + " fix_text", fix_text(hyp_text))):
            hyp = tokens(text)
            s = score(ref, hyp)
            s["recall_noacc"] = score(strip_accents(ref), strip_accents(hyp))["recall"]
            s["bag_matched"] = sum((Counter(ref) & Counter(hyp)).values())  # ignoring order (tables, columns)
            rd, hd = [t for t in ref if re.search(r"\d", t)], [t for t in hyp if re.search(r"\d", t)]
            s["digits"] = score(rd, hd)
            s["digits"]["bag_matched"] = sum((Counter(rd) & Counter(hd)).values())
            s["secs"] = secs
            row["ocr"][variant] = s
    return row


def summary(rows: list[dict], lang: str, label: str) -> str:
    if not rows:
        return f"{label:28} n=0"
    ss = [r["ocr"][lang] for r in rows]
    rec = [s["recall"] for s in ss]
    pre = [s["precision"] for s in ss]
    m, ref, hyp = sum(s["matched"] for s in ss), sum(s["ref"] for s in ss), sum(s["hyp"] for s in ss)
    dm, dr = sum(s["digits"]["matched"] for s in ss), sum(s["digits"]["ref"] for s in ss)
    db = sum(s["digits"]["bag_matched"] for s in ss)
    noacc = sum(s["recall_noacc"] * s["ref"] for s in ss) / max(ref, 1)
    bag = sum(s["bag_matched"] for s in ss) / max(ref, 1)
    return (f"{label:24} n={len(ss):3}  R median {statistics.median(rec):.4f} micro {m / max(ref, 1):.4f}  "
            f"P median {statistics.median(pre):.4f} micro {m / max(hyp, 1):.4f}  "
            f"pages R<0.99 {sum(r < 0.99 for r in rec)}, R<0.95 {sum(r < 0.95 for r in rec)}, "
            f"R<0.90 {sum(r < 0.90 for r in rec)}\n{'':24} R ignoring order {bag:.4f}, without accents {noacc:.4f}"
            f" | number tokens (n={dr}): R {dm / max(dr, 1):.4f}, ignoring order {db / max(dr, 1):.4f}")


def main_digital(a) -> None:
    for lang in a.langs:
        print(f"tesseract {check(lang)} lang {lang}")
    if a.pages:  # explicit list [{"eli", "type", "page", "pdf"}, ...] instead of a random sample
        items = [{**{k: it[k] for k in ("eli", "type", "page")}, "pdf": os.path.expanduser(it["pdf"])}
                 for it in json.loads(Path(a.pages).read_text())]
    else:
        items = pick_digital(a.root, a.seed, a.agreements, a.other)
    Path(a.cache).mkdir(parents=True, exist_ok=True)
    print(f"sample: {a.pages or f'seed {a.seed}'}, {len(items)} pages "
          f"({sum(i['type'] in AGREEMENT_TYPES for i in items)} from agreements/government statements)", flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for r in ex.map(run_digital, [(it, a.langs, a.cache) for it in items]):
            rows.append(r)
            print(f"{r['eli']:13} p{r['page']:<4} {r['type'][:12]:12} {r['lang_text']:2} ref {r['ocr'][a.langs[0]]['ref']:4}  "
                  + "  ".join(f"{l}: R {s['recall']:.3f} P {s['precision']:.3f} {s['secs'] or '-'}s"
                              for l, s in r["ocr"].items() if "fix" not in l), flush=True)
    for lang in rows[0]["ocr"]:
        print(f"\n== {lang}")
        print(summary(rows, lang, "all"))
        print(summary([r for r in rows if r["type"] in AGREEMENT_TYPES], lang, "agreements/statements"))
        print(summary([r for r in rows if r["type"] not in AGREEMENT_TYPES], lang, "other acts"))
        for lt, n in Counter(r["lang_text"] for r in rows).most_common():
            print(summary([r for r in rows if r["lang_text"] == lt], lang, f"text language {lt}"))
        secs = [r["ocr"][lang]["secs"] for r in rows if r["ocr"][lang]["secs"] is not None]
        if secs:
            print(f"OCR seconds/page (1 thread, 300 dpi): mean {statistics.mean(secs):.2f} "
                  f"median {statistics.median(secs):.2f} max {max(secs):.2f} (n={len(secs)}); "
                  f"render mean {statistics.mean(r['render_s'] for r in rows):.2f}")
    if a.json:
        Path(a.json).write_text(json.dumps(rows, ensure_ascii=False, indent=0))


# ---------------------------------------------------------------- scanned pages

def run_scan(job: tuple[str, str, list[int], str, str, bool]) -> list[dict]:
    """OCR some pages of one act (the PDF is opened once: page trees of 484-page acts are slow)."""
    eli, pdf_path, pages, lang, out, skip = job
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for p in pages:
            if skip and Path(out, f"{eli.replace('/', '-')}_p{p}.{lang}.tsv").exists():
                continue
            t0 = time.time()
            img = render(pdf.pages[p - 1])
            t1 = time.time()
            c0 = resource.getrusage(resource.RUSAGE_CHILDREN)
            tsv = _run(img, lang, "tsv")
            c1 = resource.getrusage(resource.RUSAGE_CHILDREN)
            t2 = time.time()
            page = parse_tsv(tsv, img.height)
            Path(out, f"{eli.replace('/', '-')}_p{p}.{lang}.tsv").write_text(tsv, encoding="utf-8")
            text = "\n\n".join(page.paragraphs)
            Path(out, f"{eli.replace('/', '-')}_p{p}.{lang}.txt").write_text(text, encoding="utf-8")
            toks = tokens(text)
            rows.append({"eli": eli, "page": p, "render_s": round(t1 - t0, 2), "ocr_s": round(t2 - t1, 2),
                         "ocr_cpu_s": round(c1.ru_utime + c1.ru_stime - c0.ru_utime - c0.ru_stime, 2),
                         "words": len(toks), "conf": round(page.confidence, 1), "lang": language(toks)})
            pdf.pages[p - 1].close()
    return rows


def main_scans(a) -> None:
    print(f"tesseract {check(a.lang)} lang {a.lang}")
    Path(a.out).mkdir(parents=True, exist_ok=True)
    jobs = []
    for r in acts(a.root):
        if r["no_text_pages"] in ("", "0"):
            continue
        jobs += [(r["eli"], r["pdf"], p) for p in expand(front(r["md"]).get("pages_without_text", ""))]
    if a.sample:  # a random subset of pages, e.g. for timing
        jobs = random.Random(a.seed).sample(jobs, a.sample)
    by_act: dict[tuple[str, str], list[int]] = {}
    for eli, pdf, p in jobs:
        by_act.setdefault((eli, pdf), []).append(p)
    jobs = []
    for (eli, pdf), pages in by_act.items():
        pages.sort()
        jobs += [(eli, pdf, pages[k:k + 25], a.lang, a.out, a.skip_existing) for k in range(0, len(pages), 25)]
    if a.reverse:  # a second run can start from the other end (with --skip-existing)
        jobs.reverse()
    print(f"{sum(len(j[2]) for j in jobs)} pages without text in {len({j[0] for j in jobs})} acts", flush=True)
    t0 = time.time()
    rows = []
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        for res in ex.map(run_scan, jobs):
            rows += res
            print(f"{len(rows)} pages {time.time() - t0:.0f}s", flush=True)
    wall = time.time() - t0
    Path(a.out, "pages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=0))
    ocr = [r["ocr_s"] for r in rows]
    cpu = [r["ocr_cpu_s"] for r in rows]
    print(f"wall {wall:.0f}s with {a.jobs} processes (load average at end: {os.getloadavg()[0]:.1f}); per page, "
          f"tesseract 1 thread: wall mean {statistics.mean(ocr):.2f}s median {statistics.median(ocr):.2f}s "
          f"max {max(ocr):.2f}s; CPU mean {statistics.mean(cpu):.2f}s median {statistics.median(cpu):.2f}s; "
          f"render (300 dpi) wall mean {statistics.mean(r['render_s'] for r in rows):.2f}s")
    print("pages by guessed language:", dict(Counter(r["lang"] for r in rows).most_common()))
    print("pages with < 20 words:", sum(r["words"] < 20 for r in rows))
    print("pages by median word confidence:",
          dict(sorted(Counter(int(r["conf"] // 10 * 10) for r in rows).items())))
    by: dict[str, Counter] = {}
    for r in rows:
        by.setdefault(r["eli"], Counter())[r["lang"]] += 1
    for eli, c in by.items():
        print(f"{eli:13} {sum(c.values()):4} pages  {dict(c.most_common())}")


def main_summary(a) -> None:
    """Survey of the scanned pages from the TSV files written by `scans` (and its pages.json timings).
    Language is guessed only for pages that ocr.usable() accepts: garbage from maps and upside-down
    pages is full of one-letter "words" that look like stopwords."""
    rows = []
    for f in sorted(Path(a.out).glob(f"*.{a.lang}.tsv")):
        eli_s, page_s = f.name.split(".")[0].rsplit("_p", 1)
        page = parse_tsv(f.read_text(encoding="utf-8"), 3508)  # A4 at 300 dpi (header band only)
        toks = tokens("\n".join(page.paragraphs))
        ok = usable(page)
        rows.append({"eli": eli_s.replace("-", "/"), "page": int(page_s), "words": page.words,
                     "conf": page.confidence, "usable": ok, "lang": language(toks) if ok else "-"})
    print(f"{len(rows)} pages in {len({r['eli'] for r in rows})} acts; usable() with MIN_WORDS={MIN_WORDS}, "
          f"MIN_CONF={MIN_CONF}: {sum(r['usable'] for r in rows)} pages")
    print("not usable: < MIN_WORDS words:", sum(r["words"] < MIN_WORDS for r in rows),
          "| enough words but median confidence < MIN_CONF:",
          sum(r["words"] >= MIN_WORDS and r["conf"] < MIN_CONF for r in rows))
    print("pages by median word confidence (bucket: pages):",
          dict(sorted(Counter(int(r["conf"] // 10 * 10) for r in rows).items())))
    print("usable pages by guessed language:", dict(Counter(r["lang"] for r in rows if r["usable"]).most_common()))
    timing = Path(a.out, "pages.json")
    if timing.exists():
        t = json.loads(timing.read_text())
        ocr = [r["ocr_s"] for r in t]
        print(f"timing ({len(t)} pages): tesseract wall mean {statistics.mean(ocr):.2f}s median "
              f"{statistics.median(ocr):.2f}s max {max(ocr):.2f}s; render mean "
              f"{statistics.mean(r['render_s'] for r in t):.2f}s"
              + (f"; tesseract CPU mean {statistics.mean(r['ocr_cpu_s'] for r in t):.2f}s" if "ocr_cpu_s" in t[0] else ""))
    by: dict[str, Counter] = {}
    for r in rows:
        by.setdefault(r["eli"], Counter())[r["lang"]] += 1
    for eli in sorted(by, key=lambda e: tuple(int(x) for x in e.split("/")[1:])):
        c = by[eli]
        rs = [r for r in rows if r["eli"] == eli]
        print(f"{eli:13} {len(rs):4} pages, conf median {statistics.median(r['conf'] for r in rs):5.1f}, "
              f"words median {statistics.median(r['words'] for r in rs):5.0f}  {dict(c.most_common())}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("digital")
    d.add_argument("--root", type=Path, required=True, help="dataset directory (index.csv, DU/)")
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--agreements", type=int, default=60)
    d.add_argument("--other", type=int, default=40)
    d.add_argument("--langs", nargs="+", default=["pol", "pol+eng"])
    d.add_argument("--jobs", type=int, default=1)
    d.add_argument("--cache", default="/tmp/eli2md-ocr-digital", help="OCR texts are kept here")
    d.add_argument("--pages", help="JSON list of pages to use instead of a random sample")
    d.add_argument("--json")
    s = sub.add_parser("scans")
    s.add_argument("--root", type=Path, required=True)
    s.add_argument("--lang", default="pol+eng")
    s.add_argument("--out", required=True)
    s.add_argument("--jobs", type=int, default=1)
    s.add_argument("--sample", type=int, default=0, help="only this many random pages")
    s.add_argument("--skip-existing", action="store_true", help="skip pages whose TSV is already in --out")
    s.add_argument("--reverse", action="store_true", help="last acts first")
    s.add_argument("--seed", type=int, default=1)
    m = sub.add_parser("summary")
    m.add_argument("--out", required=True, help="directory written by `scans`")
    m.add_argument("--lang", default="pol+eng")
    a = ap.parse_args()
    {"digital": main_digital, "scans": main_scans, "summary": main_summary}[a.cmd](a)


if __name__ == "__main__":
    main()
