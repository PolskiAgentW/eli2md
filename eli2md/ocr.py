"""Optional OCR of pages without a text layer (scans), with the tesseract program.

Off by default (`eli2md --ocr`). Needs `tesseract` and its language data, e.g. on Debian/Ubuntu
`apt install tesseract-ocr tesseract-ocr-pol`. Quality and cost: eval/ocr_eval.py, eval/ocr_eval_*.txt.

Facts this relies on (the 1734 pages without text in DU 2025-2026, checked 2026-09-29):
- such a page is a raster image of the whole page, the gazette header included
  ("Dziennik Ustaw – 58 – Poz. 975"), so the header is dropped from the OCR text;
- most are Polish or English text; bilateral agreements also have the other party's version
  (seen: Portuguese, French, Swedish, Greek). pol+eng reads Polish and English; others lose their
  diacritics (não -> nao) or, for Greek, come out as garbage. Hence "auto": pol+eng first, then the
  page's own language if its stopwords (or, for other scripts, orientation/script detection) say so
  and its language data is installed;
- tesseract's TSV output gives blocks, paragraphs, lines and a confidence per word. Maps, sheet
  music and sideways or upside-down pages give a low median confidence; running text gives ~96.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import statistics
import subprocess
import warnings
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from .pdf import UNIT_START

DPI = 300
OCR_UNIT = re.compile(r"^(Artykuł|ARTYKUŁ|Article|ARTICLE|Artigo|ARTIGO|Άρθρο|Ustęp|Section|Rozdział|ROZDZIAŁ|"
                      r"CHAPTER|Chapter|CZĘŚĆ|Część|PART|Part)\s+[\dIVXLC]+\b|^\(\w{1,4}\)\s")
LANG = "auto"
BASE_LANG = "pol+eng"  # first pass of "auto"; must be installed
# a header line (or its pieces) at the top of the page: "Dziennik Ustaw — 58 — Poz. 975", "— 58 —"
OCR_HEADER = re.compile(r"^(Dziennik\s*Ustaw|Monitor\s*Polski)?[\s\-–—.,|\d]*(Poz\.?\s*\d+)?$", re.I)
HEADER_BAND = 0.08  # share of the page height where the gazette header sits
MIN_WORDS, MIN_CONF = 20, 80.0  # below either, the page keeps only the note (eval/ocr_eval_scans_*.txt)
# seconds per tesseract call. Pages take ~2 s, but a guilloche background (DU/2026/14 p19, excise
# stamp form) kept tesseract busy for over 10 minutes; such a page keeps only the note.
TIMEOUT = 120
LOWER = "a-ząćęłńóśźżàâçéèêëîïôûùüÿñæœäöåõãíúýøα-ωά-ώ"
# An image on a page that has a text layer (page 1 of agreements: title as text, preamble as a scan, MP/2026/869)
# is read as text only if its OCR looks like a scan of running text: high confidence, function words, word-like
# tokens, and mostly long lines across the image. Forms, ID cards, charts, maps and tables drawn as images have
# short lines, labels or symbols. Thresholds from the 824 image pages of DU and MP 2025-2026, where text scans
# read at a median confidence >= 96 (eval/image_text_ocr_0.6.4.dev.md).
IMAGE_MIN_CONF = 95.0
IMAGE_MIN_LINES = 5
IMAGE_LONG_CHARS = 45  # a line of running text has more characters than this; labels and form fields fewer
IMAGE_LONG_WIDTH = 0.6  # ... and spans this share of the image width
IMAGE_MIN_LONG = 0.5  # share of such lines (both measures)
IMAGE_MIN_WORDLIKE = 0.75  # share of tokens that are words (letters with a vowel, or a one-letter Polish word)
IMAGE_MAX_SYMBOLS = 0.05  # per word: | = % « @ ... are table rules, chart labels, form boxes
SYMBOLS = re.compile(r"[|«»=<>®©™@#$%^*~_\[\]{}]")
VOWEL = re.compile(r"[aeiouyąęóаеиоуыэюяαεηιουωάέήίόύώ]")
ONE_LETTER_WORDS = {"a", "i", "o", "u", "w", "z"}
FIGURE_CAPTION = re.compile(r"(?:Tabela|Wykres|Rysunek|Mapa|Schemat|Legenda|LEGENDA|Źródło)\b|(?:Tab|Rys)\.")

# tesseract (pol) often reads a lone "1" as "|": "ust. | pkt 2", "Ustęp |". Fixed only after a unit
# word or before "i 2", where a table rule "|" cannot stand (eval/ocr_eval_digital_*.txt: fix_text).
LONE_ONE = re.compile(r"((?:\b(?:art|ust|pkt|poz|nr|lit|rozdz|par|str|ustęp|ustępie|ustępu|ustępach|artykuł|artykułu|"
                      r"artykule|punkt|punkcie|punktu|załącznik|załącznika|załączniku|rozdział|rozdziału|część|"
                      r"części|article|paragraph|section)\.?|§)) \|(?=$|[\s,.;:)–-])", re.I)
ONE_IN_LIST = re.compile(r"(?<=\s)\|(?=(?:,| i| lub| oraz| and| or| [-–]) \d)")  # "strefach | i 2", "|, 2 i 3"

# very frequent function words; enough to tell the language of a page of running text
STOP = {k: set(v.split()) for k, v in {
    "pl": "i w z na się do że nie jest oraz lub przez dla od o który która które być może jego ich zgodnie art",
    "en": "the of and to in a is that for by or be shall as with this any on which are from",
    "fr": "le la les de des et du un une est en par pour dans que qui sur au aux ou être",
    "de": "der die das und zu den des von mit ist im nicht auf für eine ein dem sich oder",
    "pt": "o a os as de do da dos das e em um uma que para por com não ou no na se ao",
    "es": "el la los las de del y en un una que por para con no o se al lo sus",
    "sv": "och att det som en på är av för med till den har de inte om ett eller",
    "it": "il di che e la per un in non una sono della del le si alla dei gli",
    "el": "και το της του να των τα η ο με σε για που την στο οι από",
}.items()}
TESS = {"pl": "pol", "en": "eng", "fr": "fra", "de": "deu", "pt": "por", "es": "spa", "sv": "swe", "it": "ita",
        "el": "ell"}
SCRIPT_TESS = {"Greek": "ell"}  # tesseract OSD script -> language data (Cyrillic is ambiguous: rus, ukr, bul...)


def fix_text(text: str) -> str:
    return ONE_IN_LIST.sub("1", LONE_ONE.sub(r"\1 1", text))


def language(words: list[str]) -> str:
    """ISO 639-1 code by stopword counts, or "?" (tables, lists, too little text)."""
    c = Counter({lang: sum(1 for t in words if t in stop) for lang, stop in STOP.items()})
    lang, n = c.most_common(1)[0]
    return lang if n >= 5 and n >= 0.1 * len(words) else "?"


class OcrUnavailable(RuntimeError):
    """tesseract or a requested language is not installed."""


@dataclass
class OcrPage:
    paragraphs: list[str] = field(default_factory=list)
    words: int = 0
    confidence: float = 0.0  # median word confidence, 0-100
    lang: str = ""  # tesseract language(s) used, e.g. "pol+eng", "por+eng"
    rotated: int = 0  # degrees the page image was turned before OCR
    width: int = 0  # of the image read, in pixels (0 = unknown)
    line_widths: list[int] = field(default_factory=list)  # of the lines kept, in pixels
    line_chars: list[int] = field(default_factory=list)  # characters of the lines kept


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
    missing = [l for l in (BASE_LANG if lang == "auto" else lang).split("+") if l not in have]
    if missing:
        raise OcrUnavailable(f"tesseract has no language data for {', '.join(missing)} "
                             f"(e.g. apt install {' '.join('tesseract-ocr-' + l for l in missing)})")
    return version


def render(page, dpi: int = DPI):
    """A pdfplumber page as a grayscale PIL image, with its resolution in img.info["dpi"] (see _run)."""
    img = page.to_image(resolution=dpi).original.convert("L")
    img.info["dpi"] = (dpi, dpi)
    return img


def _run(img, lang: str, fmt: str = "txt", psm: int = 3) -> str:
    exe, _, _ = tesseract()
    buf = io.BytesIO()
    # the PNG carries the resolution: without it tesseract guesses one from the text height ("Estimating resolution
    # as 384") and on table pages loses the spaces between words, so the page fell below MIN_CONF (DU/2007/1006 p. 3:
    # "UrządCelnywkatowicach", confidence 62 -> 96 with the resolution). eval/ocr_dpi_check_2000_2007.json,
    # eval/ocr_eval_digital_s7310_v0.6.20.txt
    img.save(buf, format="PNG", dpi=img.info.get("dpi", (DPI, DPI)))
    env = {**os.environ, "OMP_THREAD_LIMIT": os.environ.get("OMP_THREAD_LIMIT", "1")}  # one thread by default
    cmd = [exe, "stdin", "stdout", "-l", lang, "--psm", str(psm)] + ([fmt] if fmt != "txt" else [])
    return subprocess.run(cmd, input=buf.getvalue(), capture_output=True, env=env, check=True,
                          timeout=TIMEOUT).stdout.decode("utf-8", errors="replace")


def ocr_image(img, lang: str = BASE_LANG) -> str:
    """Plain text of an image, as tesseract prints it."""
    return _run(img, lang, "txt")


def parse_tsv(tsv: str, height: int, page_number: int | None = None, band: float = HEADER_BAND) -> OcrPage:
    """Tesseract TSV -> paragraphs. Lines are joined (hyphenated words glued back), the gazette
    header at the top of the page is dropped (also when read in another script: a short line in the
    header band with the page number). band: share of the image height searched for the header
    (0 for an image cut out of a page: it has no header)."""
    lines: dict[tuple[int, int, int], list[tuple[int, int, str, float, int, int]]] = {}
    page = OcrPage()
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) >= 12 and f[0] == "1":
            page.width = int(f[8])
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))  # block, paragraph, line
        lines.setdefault(key, []).append((int(f[7]), int(f[7]) + int(f[9]), f[11].strip(), float(f[10]),
                                          int(f[6]), int(f[6]) + int(f[8])))
    confs: list[float] = []
    kept = []  # (block, top, bottom, text) without the header
    for (blk, _, _), words in lines.items():
        text = " ".join(w[2] for w in words)
        top, bottom = min(w[0] for w in words), max(w[1] for w in words)
        if top < band * height and (
                OCR_HEADER.match(text) or (len(words) <= 8 and str(page_number) in re.findall(r"\d+", text))):
            continue
        confs += [w[3] for w in words]
        page.line_widths.append(max(w[5] for w in words) - min(w[4] for w in words))
        page.line_chars.append(len(text))
        kept.append((blk, top, bottom, fix_text(text)))
    # tesseract's own paragraphs and blocks split 1.5-spaced justified text at random lines (DU/2025/360);
    # a new paragraph starts where the reading order goes back up (next column, table cell), after a gap
    # clearly larger than the page's usual line gap, or with a unit number ("2.", "b)", "Artykuł 3", "(a)")
    gaps = [b[1] - a[2] for a, b in zip(kept, kept[1:]) if b[1] > a[2]]
    gap = statistics.median(gaps) if gaps else 0
    paras: list[str] = []
    prev = None
    for blk, top, bottom, text in kept:
        new = (prev is None or top <= prev[1] or top - prev[2] > 1.5 * gap + 0.2 * (bottom - top)
               or UNIT_START.match(text) or OCR_UNIT.match(text))
        if new:
            paras.append(text)
        elif re.search(rf"[{LOWER}]-$", paras[-1]) and re.match(rf"[{LOWER}]", text):
            paras[-1] = paras[-1][:-1] + text
        else:
            paras[-1] += " " + text
        prev = (blk, top, bottom)
    page.paragraphs = [p for p in paras if p.strip()]
    page.words = len(confs)
    page.confidence = statistics.median(confs) if confs else 0.0
    return page


def usable(page: OcrPage) -> bool:
    """Is the OCR text worth including? Maps, pictograms and blank pages are not (see MIN_*)."""
    return page.words >= MIN_WORDS and page.confidence >= MIN_CONF


def text_image(page: OcrPage) -> bool:
    """Is the OCR text of an image on a page with a text layer running text (a scan of text)? See IMAGE_*.
    False acceptance is worse than a miss: a title set in short centred lines (DU/2026/204 s.1) keeps the note."""
    lines = len(page.line_chars)
    if not usable(page) or page.confidence < IMAGE_MIN_CONF or lines < IMAGE_MIN_LINES or not page.width:
        return False
    text = " ".join(page.paragraphs)
    tokens = re.findall(r"\w+", text.lower())
    wordlike = sum(1 for t in tokens if t.isalpha() and (len(t) >= 2 and VOWEL.search(t) or t in ONE_LETTER_WORDS))
    return (language(tokens) != "?"
            and wordlike >= IMAGE_MIN_WORDLIKE * len(tokens)
            and sum(c >= IMAGE_LONG_CHARS for c in page.line_chars) >= IMAGE_MIN_LONG * lines
            and sum(w >= IMAGE_LONG_WIDTH * page.width for w in page.line_widths) >= IMAGE_MIN_LONG * lines
            and len(SYMBOLS.findall(text)) <= IMAGE_MAX_SYMBOLS * page.words
            and not any(FIGURE_CAPTION.match(p) for p in page.paragraphs))


def osd(img) -> tuple[int, str]:
    """(degrees clockwise the image must be turned by, script) from tesseract's orientation and script
    detection; (0, "") if unknown (no osd data, too little text)."""
    if "osd" not in tesseract()[2]:
        return 0, ""
    try:
        out = _run(img, "osd", psm=0)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):  # "Too few characters. Skipping this page"
        return 0, ""
    rot, script = re.search(r"^Rotate: (\d+)", out, re.M), re.search(r"^Script: (\w+)", out, re.M)
    return (int(rot.group(1)) if rot else 0), (script.group(1) if script else "")


def _read(img, lang: str, pno: int | None, rotated: int = 0, band: float = HEADER_BAND) -> OcrPage:
    page = parse_tsv(_run(img, lang, "tsv"), img.height, pno, band)
    page.lang, page.rotated = lang, rotated
    return page


def ocr_page(page, lang: str = LANG, dpi: int = DPI, bbox: tuple | None = None) -> OcrPage:
    """OCR of a pdfplumber page: paragraphs, word count, median word confidence, language used.

    lang: tesseract language(s), or "auto" (see the module docstring). A page whose text is unusable
    is tried again turned as orientation detection says (DU/2025/15 is printed sideways: median
    confidence 47 -> 96) and, with "auto", in the detected script's language (Greek).
    bbox: (x0, top, x1, bottom) in points: read only this part of the page (an image), without
    looking for the gazette header in it."""
    have = tesseract()[2]
    img = render(page.crop(bbox) if bbox else page, dpi)
    pno = getattr(page, "page_number", None)
    band = 0.0 if bbox else HEADER_BAND
    try:
        read = _read(img, BASE_LANG if lang == "auto" else lang, pno, band=band)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:  # the page keeps only the note
        why = f"took over {TIMEOUT} s" if isinstance(e, subprocess.TimeoutExpired) else f"failed ({e.returncode})"
        warnings.warn(f"page {pno}: tesseract {why}, page skipped")
        return OcrPage(lang=BASE_LANG if lang == "auto" else lang)
    try:
        return _retry(read, img, pno, lang, have, band)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):  # keep the first reading
        return read


def _retry(read: OcrPage, img, pno: int | None, lang: str, have: frozenset[str],
           band: float = HEADER_BAND) -> OcrPage:
    """Second readings for ocr_page: turned page, other script, the page's own language."""
    if not usable(read):
        rot, script = osd(img)
        if rot:
            turned = img.rotate(-rot, expand=True)
            again = _read(turned, read.lang, pno, rot, band)
            if again.confidence > read.confidence:
                read, img = again, turned
        code = SCRIPT_TESS.get(script)
        if lang == "auto" and not usable(read) and code in have:
            again = _read(img, code, pno, read.rotated, band)
            if again.confidence > read.confidence:
                read = again
    if lang == "auto" and usable(read) and read.lang == BASE_LANG:
        guess = language(re.findall(r"\w+", " ".join(read.paragraphs).lower()))
        code = TESS.get(guess)
        if code and code not in ("pol", "eng"):
            if code in have:
                again = _read(img, f"{code}+eng", pno, read.rotated, band)
                if again.confidence >= read.confidence:
                    read = again
            else:
                warnings.warn(f"page {pno}: text looks {guess}, but tesseract has no '{code}' data; read as {BASE_LANG}")
    return read
