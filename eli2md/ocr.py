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

import hashlib
import io
import itertools
import os
import re
import shutil
import statistics
import subprocess
import warnings
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .pdf import COLOPHON, UNIT_START

DPI = 300
OCR_UNIT = re.compile(r"^(Artykuł|ARTYKUŁ|Article|ARTICLE|Artigo|ARTIGO|Άρθρο|Ustęp|Section|Rozdział|ROZDZIAŁ|"
                      r"CHAPTER|Chapter|CZĘŚĆ|Część|PART|Part)\s+[\dIVXLC]+\b|^\(\w{1,4}\)\s")
LANG = "auto"
BASE_LANG = "pol+eng"  # first pass of "auto"; must be installed
# a header line (or its pieces) at the top of the page: "Dziennik Ustaw — 58 — Poz. 975", "— 58 —"
OCR_HEADER = re.compile(r"^(Dziennik\s*Ustaw|Monitor\s*Polski)?[\s\-–—.,|\d]*(Poz\.?\s*\d+(?:\s*(?:i|,)\s*\d+)*)?$", re.I)
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
    tsv: str = field(default="", repr=False)  # tesseract's output, to read it again in columns (ocr_page)
    height: int = 0  # of the image read, in pixels


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
    # ocr_page gives it only on a second reading of a whole page that gave no usable text without it: on an image cut
    # out of a page tesseract then splits lines differently and a scan of text failed text_image (DU/2000/416 p. 7:
    # 42 -> 55 lines), and some pages read before fell below MIN_CONF (DU/2025/145).
    dpi = img.info.get("dpi")
    img.save(buf, format="PNG", **({"dpi": dpi} if dpi else {}))
    env = {**os.environ, "OMP_THREAD_LIMIT": os.environ.get("OMP_THREAD_LIMIT", "1")}  # one thread by default
    cmd = [exe, "stdin", "stdout", "-l", lang, "--psm", str(psm)] + ([fmt] if fmt != "txt" else [])
    # ELI2MD_OCR_CACHE=DIR keeps each reading (key: the image and the command), so a reconversion after a change in
    # what is done with the reading (order, cutting) does not read the pages again
    cache = os.environ.get("ELI2MD_OCR_CACHE")
    if cache:
        key = hashlib.sha256(buf.getvalue() + " ".join(cmd[3:] + [tesseract()[1]]).encode()).hexdigest()
        f = Path(cache) / key[:2] / key
        if f.exists():
            return f.read_text(encoding="utf-8")
    out = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, env=env, check=True,
                         timeout=TIMEOUT).stdout.decode("utf-8", errors="replace")
    if cache:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{os.getpid()}")
        tmp.write_text(out, encoding="utf-8")
        tmp.replace(f)
    return out


def ocr_image(img, lang: str = BASE_LANG) -> str:
    """Plain text of an image, as tesseract prints it."""
    return _run(img, lang, "txt")


def parse_tsv(tsv: str, height: int, page_number: int | None = None, band: float = HEADER_BAND,
              columns: bool = False) -> OcrPage:
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
    if columns:
        lines = _column_order(lines, page.width, height)
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
        if new and columns and prev is not None and top <= prev[1] and not UNIT_START.match(text) \
                and not OCR_UNIT.match(text) and re.match(rf"[{LOWER}]", text) and not re.search(r"[.:;!?]$", paras[-1]):
            new = False  # a sentence going on at the top of the next column
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


class _Speller:
    """libhunspell with the Polish dictionary (packages libhunspell-1.7-0 and hunspell-pl), through ctypes."""

    def __init__(self, aff: str = "/usr/share/hunspell/pl_PL.aff", dic: str = "/usr/share/hunspell/pl_PL.dic"):
        import ctypes
        self.lib = ctypes.CDLL("libhunspell-1.7.so.0")
        self.lib.Hunspell_create.restype = ctypes.c_void_p
        self.lib.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        enc = re.search(r"^SET\s+(\S+)", Path(aff).read_text(encoding="latin-1"), re.M)
        self.enc = enc.group(1) if enc else "utf-8"
        self.h = self.lib.Hunspell_create(aff.encode(), dic.encode())
        self.known: dict[str, bool] = {}

    def ok(self, w: str) -> bool:
        if w not in self.known:
            try:
                self.known[w] = bool(self.lib.Hunspell_spell(self.h, w.encode(self.enc)))
            except UnicodeEncodeError:
                self.known[w] = False
        return self.known[w]


@lru_cache(maxsize=None)
def speller(lang: str = "pl_PL") -> _Speller | None:
    """A speller (pl_PL; en_US to leave English words of bilingual agreements alone), or None if libhunspell or the
    dictionary is missing (then words are not corrected)."""
    try:
        return _Speller(f"/usr/share/hunspell/{lang}.aff", f"/usr/share/hunspell/{lang}.dic")
    except OSError:
        return None


SPELL_WORD = re.compile(r"[^\W\d_]{3,}")
# letters tesseract reads for Polish ones: "ł" as "t" or "l", and a letter without its diacritic ("Rozporzadzenie",
# "zycie", "pazdziernika": DU/1990/380)
DIACRITIC = {"t": "ł", "l": "ł", "a": "ą", "e": "ę", "c": "ć", "n": "ń", "o": "ó", "s": "ś", "z": "żź",
             "A": "Ą", "E": "Ę", "C": "Ć", "N": "Ń", "O": "Ó", "S": "Ś", "Z": "ŻŹ", "L": "Ł"}
# a one-letter preposition or conjunction glued to the next word ("Wrozporządzeniu", "zdnia", "wart. 5")
GLUED = ("w", "z", "o", "i", "a", "u")
GLUED_ABBR = re.compile(r"\b([wW])(art|ust|pkt|lit)\.")


def fix_words(text: str) -> str:
    """Words of a scan read by tesseract that the Polish dictionary does not know, corrected where one fix makes them
    known: one or two letters read without their diacritic, "ł" also as "t" or "l" ("ogtoszenia" -> "ogłoszenia",
    "dziata" -> "działa", "Rozporzadzenie" -> "Rozporządzenie", DIACRITIC), "ą" read for "a" ("dnią" -> "dnia") and a
    one-letter preposition glued to the next word ("Wrozporządzeniu" -> "W rozporządzeniu"; also "wart." -> "w art.",
    "zdnia" -> "z dnia"). Several possible fixes: the word stays. Words the English dictionary knows and paragraphs
    whose function words are of another language stay. Without the Polish dictionary the text is kept.
    Measured on DU 1990-1999 (eval/scans_1990_1999/): see the README, 0.6.26."""
    sp, en = speller(), speller("en_US")
    if sp is None or language(re.findall(r"\w+", text.lower())) not in ("pl", "?"):
        return text  # a paragraph in another language (an agreement printed in two languages)
    text = GLUED_ABBR.sub(r"\1 \2.", re.sub(r"\b([zZ])dnia\b", r"\1 dnia", text))

    def fix(m: re.Match) -> str:
        w = m.group()
        if sp.ok(w) or sp.ok(w.lower()) or en is not None and (en.ok(w) or en.ok(w.lower())):
            return w  # known, also as an English word ("final", "Material": not "finał", "Materiał")
        at = [i for i, c in enumerate(w) if c in DIACRITIC]
        cands = set()
        if 0 < len(at) <= 12:
            for n in (1, 2):
                for some in itertools.combinations(at, n):
                    for repl in itertools.product(*(DIACRITIC[w[i]] for i in some)):
                        v = list(w)
                        for i, r in zip(some, repl):
                            v[i] = r
                        v = "".join(v)
                        if sp.ok(v) or sp.ok(v.lower()):
                            cands.add(v)
        if not cands and "ą" in w:  # the "a" of the pre-war typeface read as "ą" ("dnią", "sprąw"; DU/1926/146), tried
            ats = [i for i, c in enumerate(w) if c == "ą"]  # alone so as not to compete with the fixes above
            for n in (1, 2):           # ("tączną": "łączną", not also "łączna")
                for some in itertools.combinations(ats, n):
                    v = "".join("a" if i in some else c for i, c in enumerate(w))
                    if sp.ok(v) or sp.ok(v.lower()):
                        cands.add(v)
        if len(cands) == 1:
            return cands.pop()
        if not cands and w[0].lower() in GLUED and len(w) >= 5 and (sp.ok(w[1:]) or sp.ok(w[1:].lower())):
            return f"{w[0]} {w[1:]}"
        return w

    return SPELL_WORD.sub(fix, text)


def _column_order(lines: dict, width: int, height: int = 0) -> dict:
    """Tesseract's lines of a two-column page in reading order. Near the middle of the text the lines of the left
    column end and those of the right column start; the gutter is the x that best keeps the ends left of it and the
    starts right of it (the middle of the best stretch: a right column with a hanging indent starts its items left of
    its other lines, DU/1997/840). A line tesseract joined across the gutter (DU/1990/390, under a table of contents
    across the page) gives an end and a start at its wide gap between two words. Lines over the whole width (a title,
    the publisher's colophon: DU/1995/68) end and start far from the middle. The words are first put as if the scan
    were straight (_deskew). A line with words on both sides of the gutter and a wide gap there is two lines, one per
    column; a line with a word over the gutter or only a narrow gap there spans the page and starts a band; within a
    band the left column comes before the right one. Tesseract's own order of blocks mixes the columns of some scans
    (DU/1995/68, DU/1993/20). lines: as in parse_tsv, (block, paragraph, line) -> words (top, bottom, text, conf,
    left, right). A page with fewer than 5 ends or starts on either side is kept as it is."""
    if width <= 0 or len(lines) < 10:
        return lines
    original = lines
    lines = _deskew(lines)
    spans = sorted((min(w[4] for w in ws), max(w[5] for w in ws)) for ws in lines.values())
    x0 = sorted(a for a, _ in spans)[len(spans) // 20]
    x1 = sorted(b for _, b in spans)[-1 - len(spans) // 20]
    step, gap = max(1, width // 300), max(2, width // 80)  # 8 and 33 px at 300 dpi; a space between words: 15-25 px
    lo, hi = ((x0 + x1) // 2 - (x1 - x0) // 16) // step, ((x0 + x1) // 2 + (x1 - x0) // 16) // step
    # ends of left-column lines and starts of right-column lines near the middle; a line tesseract joined across the
    # gutter gives both at its wide gap between two words
    ends, starts = [], []
    for ws in lines.values():
        a, b = min(w[4] for w in ws), max(w[5] for w in ws)
        ends += [b] if lo * step <= b <= hi * step else []
        starts += [a] if lo * step <= a <= hi * step else []
        for w1, w2 in zip(ws, ws[1:]):
            if w2[4] - w1[5] >= gap and (lo * step <= w1[5] <= hi * step or lo * step <= w2[4] <= hi * step):
                ends.append(w1[5])
                starts.append(w2[4])
    if len(ends) < 5 or len(starts) < 5:
        return original  # one column
    # the x that best puts the ends left of it and the starts right of it; the middle of the best stretch
    # (a right column with a hanging indent starts its items left of its other lines: DU/1997/840)
    score = {x: sum(e <= x * step for e in ends) - sum(e > x * step for e in ends)
             + sum(t >= x * step for t in starts) - sum(t < x * step for t in starts) for x in range(lo, hi + 1)}
    top = max(score.values())
    best = [x for x in range(lo, hi + 1) if score[x] == top]
    g = (best[0] + best[-1]) // 2 * step + step // 2
    if sum(e <= g for e in ends) < 5 or sum(t >= g for t in starts) < 5:
        return original
    items = []  # (top, side, words); side 0 = spans, 1 = left, 2 = right
    tol = gap // 2  # the gutter is found to a few px: a column's edge may stand just past it (the right column at
    # 1322 for g 1324, DU/1974/239 p. 1: each of its lines went as one over the page, between the left column's lines)
    for ws in lines.values():
        if min(w[4] for w in ws) >= g - tol:
            left, right = [], list(ws)
        elif max(w[5] for w in ws) <= g + tol:
            left, right = list(ws), []
        else:
            left, right = [w for w in ws if w[5] <= g], [w for w in ws if w[4] >= g]
        # the gazette header over both columns stays one line ("Dziennik Ustaw Nr 66 — 926 —" … "Poz. 380 i 381",
        # DU/1990/380 p. 2), so parse_tsv drops it whole
        joined = left and right and len(left) + len(right) == len(ws) and \
            min(w[4] for w in right) - max(w[5] for w in left) >= gap and min(w[0] for w in ws) >= HEADER_BAND * height
        # an act's number centred on the page over its title across both columns ("21" over "USTAWA", DU/1993/20 p. 2)
        # starts a band too, though it does not reach over the gutter; only a bare number of 2-4 digits: short ends of
        # paragraphs at the start of the right column stand near the middle as well ("ną.", DU/1994/415)
        a, b = min(w[4] for w in ws), max(w[5] for w in ws)
        centred = len(ws) == 1 and re.fullmatch(r"\d{2,4}", ws[0][2]) is not None \
            and abs((a + b) / 2 - (x0 + x1) / 2) < 0.015 * (x1 - x0)
        # the first line of the publisher's colophon under the columns may be short, within the left column
        # ("Egzemplarze bieżące i z lat ubiegłych oraz załączniki można nabywać:"): put after the right column,
        # it would cut it off with the colophon (DU/2000/214)
        colophon = COLOPHON.match(" ".join(w[2] for w in ws)) is not None
        if left and right and not joined or len(left) + len(right) < len(ws) or centred or colophon:
            items.append((min(w[0] for w in ws), 0, ws))
            continue
        for side, part in ((1, left), (2, right)):
            if part:
                items.append((min(w[0] for w in part), side, part))
    items = _join_rows(items)
    # a page of one column (Dz.U. 1918-1921) read with wide gaps between justified words: many lines go over the page,
    # and tesseract splits others into blocks at such gaps; its lines go then row by row (DU/1919/242 p. 1: the right
    # halves of lines 3-4 came after the paragraph). Pages of 1918-1921: 8-35 lines over the page against 11-31 parts
    # of lines; of two columns: 0-18 against 50-132 (18 against 76: the contents on an issue's first page, DU/1986/185)
    wide = sum(1 for _, side, ws in items if side == 0 and max(w[5] for w in ws) - min(w[4] for w in ws) > 0.6 * (x1 - x0))
    parts = sum(1 for _, side, _ in items if side)
    if wide >= ONE_COLUMN_WIDE * parts and parts < ONE_COLUMN_PARTS:
        return _rows(lines)
    items.sort(key=lambda i: i[0])
    out: list = []
    band: list = []
    for it in items + [(None, 0, None)]:
        if it[1] == 0:
            out += [i for i in band if i[1] == 1] + [i for i in band if i[1] == 2]
            band = []
            if it[2] is not None:
                out.append(it)
        else:
            band.append(it)
    return {(k, 0, 0): [w[6] for w in ws] for k, (_, _, ws) in enumerate(out)}


def _join_rows(items: list) -> list:
    """A line over the page that tesseract split at a wide gap between two words, joined back: the end of a centred
    title went after the left column under it ("w sprawie … zwierząt" + "przeciw wściekliźnie.", DU/1961/309 p. 1;
    "… dla funkcjonariuszów" + "i trybu postępowania" + "przed tymi sądami.", DU/1961/134 p. 1). A line of the left
    column and one of the right column in one row stand the gutter apart; pieces of one line split near the gutter
    stand closer (26-32 px against 56-60 px of the gutter at 300 dpi), and a piece of a line over the page stands next
    to it. items: (top, side, words) of _column_order; side 0 = over the page, 1 = left column, 2 = right column."""
    def mid(ws):
        return sum(w[0] + w[1] for w in ws) / (2 * len(ws))

    def row(a, b):
        return abs(mid(a) - mid(b)) < 0.5 * min(statistics.median(w[1] - w[0] for w in a),
                                                  statistics.median(w[1] - w[0] for w in b))

    def apart(a, b):  # horizontal gap between two lines (negative if they overlap)
        return max(min(w[4] for w in b) - max(w[5] for w in a), min(w[4] for w in a) - max(w[5] for w in b))
    out = list(items)
    pairs = [(i, j) for i, a in enumerate(items) if a[1] == 1 for j, b in enumerate(items) if b[1] == 2 and row(a[2], b[2])]
    gaps = [apart(items[i][2], items[j][2]) for i, j in pairs]
    if len(gaps) < 5:
        return out
    # the gutter: the lower quartile, as a short last line of a paragraph or an indented first one stand farther
    gutter = sorted(gaps)[len(gaps) // 4]
    gone: set[int] = set()

    def join(i, j):
        out[i] = (min(out[i][0], out[j][0]), 0, sorted(out[i][2] + out[j][2], key=lambda w: w[4]))
        gone.add(j)
    for i, j in pairs:
        if i not in gone and j not in gone and out[i][1] == 1 and apart(out[i][2], out[j][2]) < 0.6 * gutter:
            join(i, j)
    for j, (_, side, ws) in enumerate(out):
        if side == 0 or j in gone:
            continue
        for i, span in enumerate(out):
            if span[1] == 0 and i not in gone and row(ws, span[2]) and 0 <= apart(ws, span[2]) <= gutter:
                join(i, j)
                break
    return [it for i, it in enumerate(out) if i not in gone]


ONE_COLUMN_WIDE, ONE_COLUMN_PARTS = 0.35, 45  # see _column_order


def _rows(lines: dict) -> dict:
    """Deskewed lines (see _deskew) in rows from the top, each row's lines from the left, as original lines."""
    items = sorted(((sum(w[0] + w[1] for w in ws) / (2 * len(ws)), min(w[4] for w in ws), max(w[1] - w[0] for w in ws), ws)
                    for ws in lines.values()), key=lambda i: i[:2])
    rows: list[list] = []
    for c, x, h, ws in items:
        if rows and abs(c - rows[-1][0][0]) < 0.5 * h:
            rows[-1].append((c, x, h, ws))
        else:
            rows.append([(c, x, h, ws)])
    out = [ws for row in rows for _, _, _, ws in sorted(row, key=lambda r: r[1])]
    return {(k, 0, 0): [w[6] for w in ws] for k, ws in enumerate(out)}


def _deskew(lines: dict) -> dict:
    """The words with x moved as if the scan were straight; each word gets its original as a 7th field. The slope is
    the Theil-Sen estimate over the left edges of the lines at the page's left margin (indented ones are off it).
    A slanted scan moves a column's edge by tens of pixels from top to bottom (DU/1991/512 p. 1), more than the
    gutter is wide."""
    rows = [(sum(w[0] + w[1] for w in ws) / (2 * len(ws)), min(w[4] for w in ws)) for ws in lines.values()]
    margin = sorted(a for _, a in rows)[len(rows) // 10]
    pts = sorted((y, a) for y, a in rows if abs(a - margin) <= 40)
    slopes = [(a2 - a1) / (y2 - y1) for i, (y1, a1) in enumerate(pts) for y2, a2 in pts[i + 1:] if y2 - y1 > 200]
    slope = statistics.median(slopes) if len(slopes) >= 10 else 0.0
    if abs(slope) > 0.05:
        slope = 0.0  # not a slant: lines of other blocks at the margin
    ref = statistics.median(y for y, _ in pts) if pts else 0.0
    return {k: [(w[0], w[1], w[2], w[3], round(w[4] - slope * ((w[0] + w[1]) / 2 - ref)),
                 round(w[5] - slope * ((w[0] + w[1]) / 2 - ref)), w) for w in ws] for k, ws in lines.items()}


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
    tsv = _run(img, lang, "tsv")
    page = parse_tsv(tsv, img.height, pno, band)
    page.lang, page.rotated, page.tsv, page.height = lang, rotated, tsv, img.height
    return page


def ocr_page(page, lang: str = LANG, dpi: int = DPI, bbox: tuple | None = None, columns: bool = False) -> OcrPage:
    """OCR of a pdfplumber page: paragraphs, word count, median word confidence, language used.

    lang: tesseract language(s), or "auto" (see the module docstring). A page whose text is unusable
    is tried again turned as orientation detection says (DU/2025/15 is printed sideways: median
    confidence 47 -> 96) and, with "auto", in the detected script's language (Greek).
    bbox: (x0, top, x1, bottom) in points: read only this part of the page (an image), without
    looking for the gazette header in it.
    columns: put the lines in the order of the page's two columns (_column_order), for scans of gazette pages."""
    have = tesseract()[2]
    img = render(page.crop(bbox) if bbox else page, dpi)
    info = getattr(img, "info", {})
    info.pop("dpi", None)  # first reading as before 0.6.20: tesseract guesses the resolution (see _run)
    pno = getattr(page, "page_number", None)
    band = 0.0 if bbox else HEADER_BAND
    read = _ocr(img, lang, pno, band, have)
    if read is None:  # the page keeps only the note
        return OcrPage(lang=BASE_LANG if lang == "auto" else lang)
    if not bbox and not usable(read):
        # a whole page without usable text: once more with the resolution given (see _run). Only then: with it,
        # pages read before can fall below MIN_CONF too (DU/2025/145: 59 -> 53 pages read), so they keep their reading
        info["dpi"] = (dpi, dpi)
        again = _ocr(img, lang, pno, band, have)
        if again is not None and usable(again):
            read = again
    return in_columns(read, pno, band) if columns else read


# the header of a gazette issue of 2011 or earlier, as OCR reads it (from 2012 there are no numbered issues)
OLD_GAZETTE = re.compile(r"(?:Dziennik|DZIENNIK)\s*(?:Ustaw|USTAW)\s*(?:—\s*)?Nr\.?\s*\d+|(?:Monitor|MONITOR)\s*(?:Polski|POLSKI)"
                         r"\s*(?:—\s*)?Nr\.?\s*\d+|Warszawa,\s*dnia\s.{5,30}\d{4}\s*r\.\s*Nr\.?\s*\d+")


def old_gazette(read: OcrPage) -> bool:
    """The page read is a page of a gazette issue of 2011 or earlier: its first 80 words name the issue ("Dziennik
    Ustaw Nr 40 — 766 —", "Warszawa, dnia 19 maja 1993 r. Nr 40" under the masthead; DU/1993/181)."""
    words = [f[11] for f in (r.split("\t") for r in read.tsv.splitlines()[1:]) if len(f) >= 12 and f[0] == "5" and f[11].strip()]
    return bool(OLD_GAZETTE.search(" ".join(words[:80])))


def in_columns(read: OcrPage, pno: int | None = None, band: float = HEADER_BAND) -> OcrPage:
    """The reading again, its lines in the order of the page's two columns (parse_tsv columns=True)."""
    if not read.tsv:
        return read
    again = parse_tsv(read.tsv, read.height, pno, band, columns=True)
    again.lang, again.rotated, again.tsv, again.height = read.lang, read.rotated, read.tsv, read.height
    return again


def _ocr(img, lang: str, pno: int | None, band: float, have: frozenset[str]) -> OcrPage | None:
    """One reading of ocr_page (with _retry); None if tesseract timed out or failed on the first pass."""
    try:
        read = _read(img, BASE_LANG if lang == "auto" else lang, pno, band=band)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
        why = f"took over {TIMEOUT} s" if isinstance(e, subprocess.TimeoutExpired) else f"failed ({e.returncode})"
        warnings.warn(f"page {pno}: tesseract {why}, page skipped")
        return None
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
