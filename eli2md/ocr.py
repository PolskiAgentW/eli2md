"""Optional OCR of pages without a text layer (scans), with the tesseract program.

Off by default (`eli2md --ocr`). Needs `tesseract` and its language data, e.g. on Debian/Ubuntu
`apt install tesseract-ocr tesseract-ocr-pol`. Quality and cost: eval/ocr_eval.py, eval/ocr_eval_*.txt.

Facts this relies on (pages without text in DU 2025-2026, checked 2026-09-29):
- such a page is a raster image of the whole page, the gazette header included
  ("Dziennik Ustaw – 58 – Poz. 975"), so the header is dropped from the OCR text;
- tesseract's TSV output gives blocks, paragraphs, lines and a confidence per word; maps and
  pictograms give few words with low confidence, running text many words with high confidence.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import statistics
from dataclasses import dataclass, field
from functools import lru_cache

DPI = 300
LANG = "pol+eng"
# a header line (or its pieces) at the top of the page: "Dziennik Ustaw — 58 — Poz. 975", "— 58 —"
OCR_HEADER = re.compile(r"^(Dziennik\s*Ustaw)?[\s\-–—.,|\d]*(Poz\.?\s*\d+)?$", re.I)
HEADER_BAND = 0.08  # share of the page height where the gazette header sits
MIN_WORDS, MIN_CONF = 20, 80.0  # below either, the page keeps only the note (TODO: set from data)
LOWER = "a-ząćęłńóśźżàâçéèêëîïôûùüÿñæœäöåõãíúýøα-ωά-ώ"


class OcrUnavailable(RuntimeError):
    """tesseract or a requested language is not installed."""


@dataclass
class OcrPage:
    paragraphs: list[str] = field(default_factory=list)
    words: int = 0
    confidence: float = 0.0  # median word confidence, 0-100


@lru_cache(maxsize=None)
def tesseract() -> tuple[str, str, frozenset[str]]:
    """(path, version, installed languages); raises OcrUnavailable if tesseract is missing."""
    exe = shutil.which("tesseract")
    if not exe:
        raise OcrUnavailable("OCR needs the tesseract program (e.g. apt install tesseract-ocr tesseract-ocr-pol)")
    out = subprocess.run([exe, "--version"], capture_output=True, text=True, check=True)
    version = (out.stdout or out.stderr).split()[1]  # "tesseract 5.5.0"
    langs = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, check=True).stdout
    return exe, version, frozenset(langs.split("\n", 1)[1].split())  # first line: "List of available languages ..."


def check(lang: str = LANG) -> str:
    """Tesseract version, or OcrUnavailable naming the missing language packs."""
    _, version, have = tesseract()
    missing = [l for l in lang.split("+") if l not in have]
    if missing:
        raise OcrUnavailable(f"tesseract has no language data for {', '.join(missing)} "
                             f"(e.g. apt install {' '.join('tesseract-ocr-' + l for l in missing)})")
    return version


def render(page, dpi: int = DPI):
    """A pdfplumber page as a grayscale PIL image."""
    return page.to_image(resolution=dpi).original.convert("L")


def _run(img, lang: str, fmt: str) -> str:
    exe, _, _ = tesseract()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    env = {**os.environ, "OMP_THREAD_LIMIT": os.environ.get("OMP_THREAD_LIMIT", "1")}  # one thread by default
    cmd = [exe, "stdin", "stdout", "-l", lang, "--psm", "3"] + ([fmt] if fmt != "txt" else [])
    return subprocess.run(cmd, input=buf.getvalue(), capture_output=True, env=env, check=True).stdout.decode(
        "utf-8", errors="replace")


def ocr_image(img, lang: str = LANG) -> str:
    """Plain text of an image, as tesseract prints it."""
    return _run(img, lang, "txt")


def parse_tsv(tsv: str, height: int) -> OcrPage:
    """Tesseract TSV -> paragraphs. Lines are joined (hyphenated words glued back), the gazette
    header at the top of the page is dropped."""
    lines: dict[tuple[int, int, int], list[tuple[int, str, float]]] = {}
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))  # block, paragraph, line
        lines.setdefault(key, []).append((int(f[7]), f[11].strip(), float(f[10])))
    page = OcrPage()
    confs: list[float] = []
    paras: dict[tuple[int, int], str] = {}
    for (blk, par, _), words in lines.items():
        text = " ".join(w for _, w, _ in words)
        if min(t for t, _, _ in words) < HEADER_BAND * height and OCR_HEADER.match(text):
            continue
        confs += [c for _, _, c in words]
        prev = paras.get((blk, par), "")
        if re.search(rf"[{LOWER}]-$", prev) and re.match(rf"[{LOWER}]", text):
            paras[(blk, par)] = prev[:-1] + text
        else:
            paras[(blk, par)] = text if not prev else prev + " " + text
    page.paragraphs = [p for p in paras.values() if p.strip()]
    page.words = len(confs)
    page.confidence = statistics.median(confs) if confs else 0.0
    return page


def usable(page: OcrPage) -> bool:
    """Is the OCR text worth including? Maps, pictograms and blank pages are not (see MIN_*)."""
    return page.words >= MIN_WORDS and page.confidence >= MIN_CONF


def ocr_page(page, lang: str = LANG, dpi: int = DPI) -> OcrPage:
    """OCR of a pdfplumber page: paragraphs, word count and median word confidence."""
    img = render(page, dpi)
    return parse_tsv(_run(img, lang, "tsv"), img.height)
