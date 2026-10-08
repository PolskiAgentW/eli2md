import shutil
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from eli2md import ocr
from eli2md.pdf import (ANNEX_OCR, Block, Document, _fix_section_sign, _hidden_ocr_scan, _ocr_lines, _quoted_scan_annexes,
                        _segment, to_markdown)

META = {"ELI": "DU/2025/1", "title": "Umowa", "type": "Umowa międzynarodowa", "pos": 1, "publisher": "DU"}
HEAD = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def tsv(words):
    """words: (block, par, line, top, conf, text)"""
    rows = [HEAD, "1\t1\t0\t0\t0\t0\t0\t0\t2481\t3508\t-1\t"]
    for k, (b, p, l, top, conf, text) in enumerate(words):
        rows.append(f"5\t1\t{b}\t{p}\t{l}\t{k}\t{100 + k}\t{top}\t50\t30\t{conf}\t{text}")
    return "\n".join(rows) + "\n"


class Ocr(unittest.TestCase):
    def test_resolution_goes_to_tesseract(self):
        # without it tesseract guesses the resolution and loses word spaces on table pages (DU/2007/1006 p. 3)
        import io
        from PIL import Image
        sent = {}

        def run(cmd, input, **kw):
            sent["dpi"] = Image.open(io.BytesIO(input)).info.get("dpi")
            return mock.Mock(stdout=b"")
        with mock.patch.object(ocr, "tesseract", return_value=("t", "5.5.0", frozenset({"pol", "eng"}))), \
                mock.patch.object(ocr.subprocess, "run", run):
            img = Image.new("L", (10, 10), 255)
            img.info["dpi"] = (300, 300)  # as render() sets it for a whole page
            ocr._run(img, "pol")
            self.assertEqual(tuple(round(x) for x in sent["dpi"]), (300, 300))
            del img.info["dpi"]  # an image cut out of a page (ocr_page with bbox): no resolution, as before 0.6.20
            ocr._run(img, "pol")
            self.assertIsNone(sent["dpi"])

    def test_resolution_only_on_second_reading(self):
        # a whole page is read as before 0.6.20 (no resolution); only if that gives no usable text, once more with it
        from PIL import Image
        good = ocr.OcrPage(paragraphs=["tekst"], words=300, confidence=95.0)
        bad = ocr.OcrPage(paragraphs=["UrządCelny"], words=300, confidence=62.0)
        for first, second, bbox, want, dpis in ((good, None, None, good, [None]), (bad, good, None, good, [None, (300, 300)]),
                                                (bad, bad, None, bad, [None, (300, 300)]), (bad, good, (0, 0, 9, 9), bad, [None])):
            seen, answers = [], [first, second]

            def one(img, *a):
                seen.append(img.info.get("dpi"))
                return answers[len(seen) - 1]
            page = mock.Mock(page_number=3)
            page.crop.return_value = page
            img = Image.new("L", (10, 10), 255)
            img.info["dpi"] = (300, 300)
            with mock.patch.object(ocr, "tesseract", return_value=("t", "5.5.0", frozenset({"pol", "eng"}))), \
                    mock.patch.object(ocr, "render", return_value=img), mock.patch.object(ocr, "_ocr", one):
                self.assertIs(ocr.ocr_page(page, bbox=bbox), want)
            self.assertEqual(seen, dpis)

    def test_parse_tsv(self):
        page = ocr.parse_tsv(tsv([
            (1, 1, 1, 207, 95, "Dziennik"), (1, 1, 1, 207, 96, "Ustaw"), (1, 1, 1, 225, 88, "—"),
            (1, 1, 1, 207, 91, "58"), (1, 1, 1, 225, 87, "—"), (1, 1, 1, 207, 96, "Poz."), (1, 1, 1, 207, 96, "975"),
            (2, 1, 1, 400, 90, "Informacje"), (2, 1, 1, 400, 92, "niejaw-"),
            (2, 1, 2, 440, 94, "ne"), (2, 1, 2, 440, 60, "są"),
            (2, 2, 1, 500, 97, "2."), (2, 2, 1, 500, 99, "Dalej."),
            (3, 1, 1, 3000, 40, "   "),
        ]), 3508)
        self.assertEqual(page.paragraphs, ["Informacje niejawne są", "2. Dalej."])
        self.assertEqual(page.words, 6)  # header dropped, empty word ignored
        self.assertEqual(page.confidence, 93.0)

    def test_header_only_at_top(self):
        # a line "12" low on the page is content, not the header
        page = ocr.parse_tsv(tsv([(1, 1, 1, 150, 90, "–"), (1, 1, 1, 150, 90, "3"), (1, 1, 1, 150, 90, "–"),
                                  (2, 1, 1, 2000, 90, "12")]), 3508)
        self.assertEqual(page.paragraphs, ["12"])

    def test_usable(self):
        self.assertFalse(ocr.usable(ocr.OcrPage(["a"], words=5, confidence=95)))
        self.assertFalse(ocr.usable(ocr.OcrPage(["a"], words=500, confidence=30)))
        self.assertTrue(ocr.usable(ocr.OcrPage(["a"], words=500, confidence=95)))

    def test_missing_tesseract(self):
        ocr.tesseract.cache_clear()
        try:
            with mock.patch.object(shutil, "which", return_value=None):
                with self.assertRaisesRegex(ocr.OcrUnavailable, "apt install tesseract-ocr"):
                    ocr.check("pol")
        finally:
            ocr.tesseract.cache_clear()

    def test_missing_language(self):
        with mock.patch.object(ocr, "tesseract", return_value=("/usr/bin/tesseract", "5.5.0", frozenset({"eng"}))):
            with self.assertRaisesRegex(ocr.OcrUnavailable, "tesseract-ocr-pol"):
                ocr.check("pol+eng")
            with self.assertRaisesRegex(ocr.OcrUnavailable, "tesseract-ocr-pol"):
                ocr.check("auto")  # auto starts with pol+eng
            self.assertEqual(ocr.check("eng"), "5.5.0")

    def test_header_other_script(self):
        # the Greek model reads "Dziennik Ustaw – 15 – Poz. 968" as "ὨὈζίοηπίς Ὀδίανν 15 -- Ῥο7. 965"
        page = ocr.parse_tsv(tsv([(1, 1, 1, 207, 90, "ὨὈζίοηπίς"), (1, 1, 1, 207, 90, "Ὀδίανν"), (1, 1, 1, 207, 90, "15"),
                                  (1, 1, 1, 207, 90, "--"), (1, 1, 1, 207, 90, "Ῥο7."), (1, 1, 1, 207, 90, "965"),
                                  (2, 1, 1, 400, 90, "Άρθρο"), (2, 1, 1, 400, 90, "15")]), 3508, page_number=15)
        self.assertEqual(page.paragraphs, ["Άρθρο 15"])

    def test_language_and_fixes(self):
        self.assertEqual(ocr.language("o fato de que uma sociedade residente de um estado não".split()), "pt")
        self.assertEqual(ocr.language("informacje niejawne są przekazywane w drodze dyplomatycznej i w inny sposób "
                                      "oraz przez".split()), "pl")
        self.assertEqual(ocr.language("240 250 kod cn".split()), "?")
        self.assertEqual(ocr.fix_text("ust. | pkt 2 i art. |, w strefach | i 2; 240 | Oznaczenie"),
                         "ust. 1 pkt 2 i art. 1, w strefach 1 i 2; 240 | Oznaczenie")

    def test_markdown(self):
        doc = Document(blocks=[Block("p", "Art. 1. Tekst.", 1), Block("ocr", "Art. 2. „Odczytane", 2),
                               Block("ocr", "# nie nagłówek", 2), Block("ocr", "- nie lista", 3),
                               Block("notext", "", 4), Block("p", "Art. 3. Dalej.", 5)],
                       no_text_pages=[2, 3, 4], ocr_pages=[2, 3], ocr_engine="tesseract 5.5.0",
                       ocr_langs={2: "pol+eng", 3: "por+eng"})
        md = to_markdown(doc, META)
        self.assertIn('pages_without_text: "2-4"', md)
        self.assertIn('pages_ocr: "2-3"', md)
        self.assertIn('ocr: "tesseract 5.5.0"', md)
        self.assertIn("\n\n> [Strona 2 PDF nie ma czytelnej warstwy tekstowej. Tekst poniżej odczytał OCR (tesseract 5.5.0, "
                      "pol+eng). Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]\n\n> Art. 2. „Odczytane\n\n"
                      "> \\# nie nagłówek\n\n> [Strona 3 PDF nie ma czytelnej warstwy tekstowej. Tekst poniżej odczytał OCR "
                      "(tesseract 5.5.0, por+eng).", md)
        self.assertIn("\n\n> \\- nie lista\n\n> [Strona 4 PDF nie ma czytelnej warstwy tekstowej (np. skan", md)
        # OCR text is never a heading, and its unclosed quote does not swallow the next heading
        self.assertEqual(md.count("##### "), 2)
        self.assertIn("##### Art. 3.", md)

    def test_auto_language(self):
        pt = [(1, 1, 1, 400 + 40 * k, 95, w) for k, w in enumerate(
            "o fato de que uma sociedade residente de um estado nao seja da outra por".split() * 2)]
        el = [(1, 1, 1, 400 + 40 * k, 93, w) for k, w in enumerate("και το της του να των τα η ο με σε για".split() * 2)]
        garbage = [(1, 1, 1, 400 + 40 * k, 40, w) for k, w in enumerate("Ilapahafńc sev 8a anokaAdyei".split() * 6)]

        class Img:
            height = 3508

            def rotate(self, *a, **k):
                return self

        def run(img, lang, fmt="txt", psm=3):
            calls.append(lang)
            return tsv({"pol+eng": page_words, "por+eng": pt, "ell": el}.get(lang, garbage))

        for page_words, script, want in ((pt, "Latin", "por+eng"), (garbage, "Greek", "ell")):
            calls = []
            with mock.patch.object(ocr, "tesseract", return_value=("t", "5.5.0", frozenset({"pol", "eng", "por", "ell", "osd"}))), \
                    mock.patch.object(ocr, "render", return_value=Img()), mock.patch.object(ocr, "_run", run), \
                    mock.patch.object(ocr, "osd", return_value=(0, script)):
                read = ocr.ocr_page(mock.Mock(page_number=5))
            self.assertEqual(read.lang, want)
            self.assertTrue(ocr.usable(read))
            self.assertEqual(calls, ["pol+eng", want])
        # an explicit language is used as it is
        calls, page_words = [], pt
        with mock.patch.object(ocr, "tesseract", return_value=("t", "5.5.0", frozenset({"pol", "eng", "por"}))), \
                mock.patch.object(ocr, "render", return_value=Img()), mock.patch.object(ocr, "_run", run):
            self.assertEqual(ocr.ocr_page(mock.Mock(page_number=5), "pol+eng").lang, "pol+eng")
        self.assertEqual(calls, ["pol+eng"])

    def test_timeout(self):
        import subprocess

        def slow(*a, **k):
            raise subprocess.TimeoutExpired("tesseract", ocr.TIMEOUT)
        with mock.patch.object(ocr, "tesseract", return_value=("t", "5.5.0", frozenset({"pol", "eng"}))), \
                mock.patch.object(ocr, "render", return_value=mock.Mock(height=3508)), \
                mock.patch.object(ocr, "_run", slow), self.assertWarnsRegex(UserWarning, "took over"):
            self.assertFalse(ocr.usable(ocr.ocr_page(mock.Mock(page_number=19))))

    def test_no_ocr_fields_without_ocr(self):
        md = to_markdown(Document(blocks=[Block("notext", "", 1)], no_text_pages=[1]), META)
        self.assertNotIn("pages_ocr", md)
        self.assertNotIn("pages_images_ocr", md)
        self.assertNotIn("\nocr:", md)

    def test_image_ocr_markdown(self):
        # MP/2026/869 s.1: title in the text layer, preamble and Art. 1 as an image of text, read by OCR
        doc = Document(blocks=[Block("p", "UMOWA", 1), Block("ocr", "Rząd Rzeczypospolitej Polskiej i Rząd ...", 1),
                               Block("ocr", "Artykuł 1 DEFINICJE", 1), Block("p", "Art. 2. Dalej.", 2),
                               Block("image", "", 3)],
                       image_pages=[1, 3], image_ocr_pages=[1], ocr_engine="tesseract 5.5.0", ocr_langs={1: "pol+eng"})
        md = to_markdown(doc, META)
        self.assertIn('pages_with_images: "1, 3"', md)
        self.assertIn('pages_images_ocr: "1"', md)
        self.assertIn('ocr: "tesseract 5.5.0"', md)
        self.assertNotIn("pages_ocr", md)
        self.assertIn("UMOWA\n\n> [Na stronie 1 PDF jest obraz tekstu (skan). Tekst poniżej odczytał z obrazu OCR "
                      "(tesseract 5.5.0, pol+eng). Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]\n\n"
                      "> Rząd Rzeczypospolitej Polskiej i Rząd ...\n\n> Artykuł 1 DEFINICJE\n\n##### Art. 2.", md)
        self.assertEqual(md.count("> [Na stronie 1 "), 1)  # one note per image
        self.assertIn("> [Na stronie 3 PDF jest obraz (np. wzór, rysunek, skan). Jego treści tu nie ma", md)

    def test_text_image(self):
        # MP/2026/869 s.1 as read: running text in long lines across the image
        lines = ["Rząd Rzeczypospolitej Polskiej i Rząd Królestwa Arabii Saudyjskiej, zwane dalej",
                 "„Stronami”, pragnąc zacieśnić przyjazne stosunki między obydwoma Państwami;",
                 "biorąc pod uwagę interes Stron dotyczący zwolnienia z obowiązku posiadania wiz",
                 "dla swoich obywateli legitymujących się paszportami dyplomatycznymi, służbowymi",
                 "i specjalnymi, zgodnie z obowiązującymi przepisami prawa obydwu Państw;",
                 "uzgodniły, co następuje:"]

        def page(lines, conf=96.2, widths=None, width=1760):
            return ocr.OcrPage([" ".join(lines)], words=len(" ".join(lines).split()), confidence=conf, width=width,
                               line_widths=widths or [1700] * (len(lines) - 1) + [500],
                               line_chars=[len(l) for l in lines])
        self.assertTrue(ocr.text_image(page(lines)))
        self.assertFalse(ocr.text_image(page(lines, conf=90)))  # an unclear scan, a drawing: below IMAGE_MIN_CONF
        self.assertFalse(ocr.text_image(page(lines[:4])))  # fewer than IMAGE_MIN_LINES lines
        # the same words in short centred lines (a title, DU/2026/204 s.1): a miss rather than a false acceptance
        short = [w for l in lines for w in l.split(", ")]
        self.assertFalse(ocr.text_image(page(short, widths=[700] * len(short))))
        # the text is in long lines, but they do not span the image (a label box of a form or a chart)
        self.assertFalse(ocr.text_image(page(lines, width=4000)))
        # an ID card or a form: field labels, no function words
        form = ["Legitymacja studencka Numer albumu Kod kreskowy Imię Nazwisko PESEL Data urodzenia Ważna do"] * 6
        self.assertFalse(ocr.text_image(page(form)))
        # a chart with long labels: bars read as | and «
        chart = [l + " | ss « 20% =" for l in lines]
        self.assertFalse(ocr.text_image(page(chart)))
        # a table drawn as an image, under its caption
        self.assertFalse(ocr.text_image(page(["Tabela 2. " + lines[0]] + lines[1:])))
        self.assertFalse(ocr.text_image(page(["Rys. 5. " + lines[0]] + lines[1:])))

    def test_image_text_region(self):
        from eli2md import pdf

        def page(chars):
            return mock.Mock(width=595.0, height=842.0, page_number=1, chars=chars,
                             images=[{"x0": 70.0, "x1": 500.0, "top": 357.0, "bottom": 685.0},
                                     {"x0": 400.0, "x1": 480.0, "top": 700.0, "bottom": 780.0}])
        good = ocr.OcrPage(["Rząd Rzeczypospolitej Polskiej i Rząd ..."], words=100, confidence=96, lang="pol+eng")
        with mock.patch.object(ocr, "ocr_page", return_value=good) as read, \
                mock.patch.object(ocr, "text_image", return_value=True):
            self.assertIs(pdf._image_text(page([{"text": "U", "x0": 280, "x1": 290, "top": 231, "bottom": 241}]),
                                          "auto"), good)
            read.assert_called_once()
            self.assertEqual(read.call_args.kwargs["bbox"], (70.0, 357.0, 500.0, 685.0))  # the largest image
            # text-layer text over the image: the image is a background (a form), not read
            read.reset_mock()
            over = [{"text": "x", "x0": 100 + 5 * k, "x1": 104 + 5 * k, "top": 400, "bottom": 410} for k in range(40)]
            self.assertIsNone(pdf._image_text(page(over), "auto"))
            read.assert_not_called()
        with mock.patch.object(ocr, "ocr_page", return_value=good), mock.patch.object(ocr, "text_image", return_value=False):
            self.assertIsNone(pdf._image_text(page([]), "auto"))

    def test_region_keeps_top_line(self):
        # a line at the top of an image cut out of a page is not the gazette header
        words = [(1, 1, 1, 20, 95, "–"), (1, 1, 1, 20, 95, "2"), (1, 1, 1, 20, 95, "–"), (2, 1, 1, 900, 95, "Dalej")]
        self.assertEqual(ocr.parse_tsv(tsv(words), 3508).paragraphs, ["Dalej"])
        self.assertEqual(ocr.parse_tsv(tsv(words), 3508, band=0.0).paragraphs, ["– 2 – Dalej"])


class Scan(unittest.TestCase):
    """Pages scanned with Acrobat's invisible OCR layer (Dz.U. 1918-1999), read again by OCR."""

    def page(self, fonts, image=(0, 0, 600, 840)):
        chars = [{"fontname": f} for f in fonts]
        images = [dict(zip(("x0", "top", "x1", "bottom"), image))] if image else []
        return SimpleNamespace(chars=chars, images=images, width=600, height=840)

    def test_hidden_ocr_scan(self):
        self.assertTrue(_hidden_ocr_scan(self.page(["Helvetica"] * 500 + ["HiddenHorzOCR"] * 10)))
        self.assertFalse(_hidden_ocr_scan(self.page(["Helvetica"] * 500 + ["HiddenHorzOCR"] * 9)))
        self.assertFalse(_hidden_ocr_scan(self.page(["HiddenHorzOCR"] * 50, image=(0, 0, 600, 400))))  # half a page
        self.assertFalse(_hidden_ocr_scan(self.page(["Times-Roman"] * 50)))  # a digital page under an image

    def test_section_sign(self):
        self.assertEqual(_fix_section_sign("8 2. Rozporządzenie wchodzi w życie"), "§ 2. Rozporządzenie wchodzi w życie")
        self.assertEqual(_fix_section_sign("1) w 8 1 skreśla się pkt 3, w $ 13 w ust. 1"),
                         "1) w § 1 skreśla się pkt 3, w § 13 w ust. 1")
        self.assertEqual(_fix_section_sign("1) w 81 w ust. 1:"), "1) w § 1 w ust. 1:")
        self.assertEqual(_fix_section_sign("2) w82:"), "2) w § 2:")
        for t in ("8. Zadania gminy", "w 8 dni od dnia", "8 osób", "w 81 przypadkach"):
            self.assertEqual(_fix_section_sign(t), t)
        # a glued "8"/"5" continuing a numbered list of the page is the list's number (DU/1995/495), not "§ 0."
        countries = {77, 78, 79, 80, 81, 82}
        self.assertEqual(_fix_section_sign("80. Malezja,", countries), "80. Malezja,")
        self.assertEqual(_fix_section_sign("82. Malta,", countries), "82. Malta,")
        self.assertEqual(_fix_section_sign("50. PN-T-83020:1996 Ochronnik", {49, 50, 51}), "50. PN-T-83020:1996 Ochronnik")
        # without a chain to a number that cannot be a glued "§" it stays a paragraph, also in a run of them
        self.assertEqual(_fix_section_sign("81. 1. Ustala się kategorie", {81, 82, 83}), "§ 1. 1. Ustala się kategorie")
        self.assertEqual(_fix_section_sign("85. 1. Kuchnie", {84, 85, 86}), "§ 5. 1. Kuchnie")
        self.assertEqual(_fix_section_sign("82. Organy prowadzące", {1, 2, 82}), "§ 2. Organy prowadzące")

    def test_signature(self):
        lines = _ocr_lines(["Art. 3. Ustawa wchodzi w życie z dniem ogłoszenia. Prezydent Rzeczypospolitej Polskiej: "
                            "W. Jaruzelski", "Minister Finansów może określić, w drodze rozporządzenia: 1) wzory"],
                           1, 600, 840, None, "scan")
        self.assertEqual([l.text for l in lines], ["Art. 3. Ustawa wchodzi w życie z dniem ogłoszenia.",
                                                   "Prezydent Rzeczypospolitej Polskiej: W. Jaruzelski",
                                                   "Minister Finansów może określić, w drodze rozporządzenia: 1) wzory"])
        self.assertEqual([b.kind for b in _segment(lines)], ["scan", "signature", "scan"])

    @unittest.skipUnless(ocr.speller(), "libhunspell or hunspell-pl not installed")
    def test_fix_words(self):
        self.assertEqual(ocr.fix_words("Wrozporządzeniu zdnia 4 maja, wart. 5 dziata od dnia ogtoszenia"),
                         "W rozporządzeniu z dnia 4 maja, w art. 5 działa od dnia ogłoszenia")
        self.assertEqual(ocr.fix_words("Rozporzadzenie wchodzi w zycie z dniem 1 pazdziernika"),
                         "Rozporządzenie wchodzi w życie z dniem 1 października")
        for t in ("Bielsko", "lata", "tak", "Ustawa wchodzi w życie", "final", "Material"):
            self.assertEqual(ocr.fix_words(t), t)

    @unittest.skipUnless(ocr.speller(), "libhunspell or hunspell-pl not installed")
    def test_fix_words_old(self):
        # "ą" read for the "a" of the pre-war typeface: only for issues of 1918-1989 (later "jątek" of "ma-jątek" would
        # become "jatek", DU/1998/304)
        self.assertEqual(ocr.fix_words("z dnią 5 maja", old=True), "z dnia 5 maja")
        self.assertEqual(ocr.fix_words("z dnią 5 maja"), "z dnią 5 maja")

    def test_act_start_1918_1989(self):
        def acts(paras, position, old=True):
            return [(l.act, l.text) for l in _ocr_lines(paras, 1, 600, 840, position, "scan", old=old) if l.act]
        # the number glued to the title in ordinary case, the header read with the page's positions (DU/1921/259)
        page = ['"Ne 41. Dziennik Wstaw. Poz. 258 i 259. 603', "§ 11. Niniejsze rozporządzenie wchodzi w życie.",
                "259. Rozporządzenie Ministra Kolei Żelaznych z dnia 6 maja 1921 r. w sprawie przedłużenia terminu"]
        self.assertEqual(acts(page, 259), [(259, "259")])
        self.assertEqual(acts(page, 259, old=False), [])  # later issues as before
        # the type in capitals is enough without the header (DU/1930/111); a list item in ordinary case is not
        self.assertEqual(acts(["§ 3. Rozporządzenie wchodzi w życie.", "111. ROZPORZADZENIE RADY MINISTRÓW | z dnia 7 lutego"], 111),
                         [(111, "111")])
        self.assertEqual(acts(["Tracą moc:", "112. rozporządzenie Ministra Skarbu z dnia 1 maja 1930 r."], 111), [])
        # the end of the previous act's signature between the number and the type goes before the number (DU/1919/305)
        lines = _ocr_lines(["305.", "Ministerstwa: I, kberhavat", "ROZPORZĄDZENIE Ministra Kolei"], 1, 600, 840, 305, "scan",
                           old=True)
        self.assertEqual([l.text for l in lines], ["Ministerstwa: I, kberhavat", "305", "ROZPORZĄDZENIE Ministra Kolei"])
        # the next act's number and type read into the last paragraph of the act before it (DU/1983/45, DU/1931/12)
        self.assertEqual(acts(["§ 6. Rozporządzenie wchodzi w życie. Prezes Rady Ministrów: w z. J. Obodowski 45 c | "
                               "ROZPORZĄDZENIE RADY MINISTRÓW | z dnia 7 lutego 1983 r."], 45), [(45, "45")])
        self.assertEqual(acts(["W sprawie tej obowiązuje rozporządzenie z dnia 3 maja (Dz. U. Nr 5, poz. 45) "
                               "ROZPORZĄDZENIE RADY MINISTRÓW"], 45), [])  # a reference, not after a sentence or signature
        # the number at the end of the issue's contents (DU/1919/101), a dash between number and type (DU/1979/146)
        self.assertEqual(acts(["103. Dekret w przedmiocie kar . . . 36 —_ z —— m za maa 2 101.", "DEKRET"], 101), [(101, "101")])
        self.assertEqual(acts(["(Dz. U. Nr 5, poz. 101.", "DEKRET"], 101), [])
        self.assertEqual(acts(["146 - OŚWIADCZENIE RZĄDOWE ] 2"], 146), [(146, "146")])
        # an erratum after the act ends it (DU/1923/635)
        lines = _ocr_lines(["635.", "Rozporządzenie Ministrów Skarbu", "Minister Skarbu: H. Linde", "Sprostowanie. W Dz. U. R. P."],
                           1, 600, 840, 635, "scan", old=True)
        self.assertEqual([l.act for l in lines], [635, 0, 0, 655, 0])
        # a speck under the number and before the type (DU/1984/126)
        lines = _ocr_lines(["126", ";", "i ROZPORZĄDZENIE RADY MINISTRÓW."], 1, 600, 840, 126, "scan", old=True)
        self.assertEqual([(l.act, l.text) for l in lines], [(126, "126"), (0, "ROZPORZĄDZENIE RADY MINISTRÓW.")])

    def test_end_by_next_title(self):
        from eli2md.pdf import _by_neighbors, _title_at
        def L(t):
            return _ocr_lines([t], 1, 600, 840, None, "scan", old=True)[0]
        t428 = 'Rozporządzenie Rady Ministrów z dnia 19 marca 1928 r. o wydzieleniu z administracji państwowej przedsiębiorstwa'
        body = [L("Rozporządzenie Rady Ministrów"), L("z dnia 19 marca 1928 r."), L("§ 1. Gminę wiejską Mokrany znosi się."),
                L("Prezes Rady Ministrów: J. Piłsudski"), L("Rozporządzenie Rady Ministrów"),
                L("z dnia 19 marca 1928 r. o wydzieleniu z administracji państwowej przedsiębiorstwa „Państwowa Wytwórnia”")]
        self.assertTrue(_title_at(body, 4, t428))
        self.assertFalse(_title_at(body, 0, t428))  # same type, issuer and date, other words after it
        kept = _by_neighbors((body, [], 1, 1), 427, {428: t428})[0]
        self.assertEqual([l.text for l in kept][-1], "Prezes Rady Ministrów: J. Piłsudski")
        # an item of the issue's contents is no header (DU/1947/49)
        toc = [L("DEKRET"), L("Poz.: 49 — z dnia 28 stycznia 1947 r. o utworzeniu etatów")]
        self.assertFalse(_title_at(toc, 0, "Dekret z dnia 28 stycznia 1947 r. o utworzeniu etatów"))

    def test_annex_header(self):
        self.assertTrue(ANNEX_OCR.match("Załącznik do obwieszczenia Ministra z dnia 27 marca 1997 r. (poz. 224)"))
        self.assertTrue(ANNEX_OCR.match("ZAŁĄCZNIK Nr 2"))
        self.assertFalse(ANNEX_OCR.match("Załącznik do ustawy określa wzór wniosku."))

    def test_column_order(self):
        def line(top, text, left, right):  # words (top, bottom, text, conf, left, right) spread over left-right
            ws = text.split()
            w = (right - left) // len(ws)
            return [(top, top + 30, t, 95.0, left + k * w, left + (k + 1) * w - 10) for k, t in enumerate(ws)]
        lines = {(0, 0, 0): line(10, "TYTUŁ AKTU", 400, 600)}
        for k in range(6):  # tesseract gives the right column's block first, and joins one line across the gutter
            lines[(1, 0, k)] = line(100 + 40 * k, f"prawy{k} tekst", 520, 900)
        for k in range(6):
            lines[(2, 0, k)] = line(100 + 40 * k, f"lewy{k} tekst", 100, 480)
        lines[(3, 0, 0)] = line(340, "lewy6 tekst", 100, 480) + line(340, "prawy6 tekst", 520, 900)
        lines[(4, 0, 0)] = line(400, "Wydawca: tekst na całą szerokość strony", 100, 900)
        out = [" ".join(w[2] for w in ws) for ws in ocr._column_order(lines, 1000).values()]
        self.assertEqual(out, ["TYTUŁ AKTU"] + [f"lewy{k} tekst" for k in range(7)] + [f"prawy{k} tekst" for k in range(7)]
                         + ["Wydawca: tekst na całą szerokość strony"])
        # an act's number centred on the page over a title across the page starts a band (DU/1993/20)
        lines2 = dict(lines)
        lines2[(5, 0, 0)] = line(100 + 40 * 3 + 5, "21", 485, 515)
        out2 = [" ".join(w[2] for w in ws) for ws in ocr._column_order(lines2, 1000).values()]
        self.assertEqual(out2, ["TYTUŁ AKTU"] + [f"lewy{k} tekst" for k in range(4)] + [f"prawy{k} tekst" for k in range(4)]
                         + ["21"] + [f"lewy{k} tekst" for k in range(4, 7)] + [f"prawy{k} tekst" for k in range(4, 7)]
                         + ["Wydawca: tekst na całą szerokość strony"])
        one = {(0, 0, k): line(100 + 40 * k, "tekst w jednym łamie", 100, 900) for k in range(12)}
        self.assertIs(ocr._column_order(one, 1000), one)
        # a short first line of the colophon under the columns, within the left one, comes after the right column
        # (DU/2000/214: before, it stood between the columns and the colophon cut cut the right one off)
        lines3 = {k: v for k, v in lines.items() if k != (4, 0, 0)}
        lines3[(4, 0, 0)] = line(400, "Egzemplarze bieżące można nabywać:", 100, 450)
        lines3[(5, 0, 0)] = line(440, "— w Wydziale Wydawnictw na całą szerokość", 100, 900)
        out3 = [" ".join(w[2] for w in ws) for ws in ocr._column_order(lines3, 1000).values()]
        self.assertEqual(out3, ["TYTUŁ AKTU"] + [f"lewy{k} tekst" for k in range(7)] + [f"prawy{k} tekst" for k in range(7)]
                         + ["Egzemplarze bieżące można nabywać:", "— w Wydziale Wydawnictw na całą szerokość"])

    def test_column_order_1918_1989(self):
        def line(top, text, left, right):
            ws = text.split()
            w = (right - left) // len(ws)
            return [(top, top + 30, t, 95.0, left + k * w, left + (k + 1) * w - 10) for k, t in enumerate(ws)]
        # the end of a centred title split off by tesseract goes with the title, not to the top of the right column
        # (DU/1961/309); in later issues as before
        lines = {(0, 0, 0): line(40, "w sprawie szczepienia psów", 150, 700), (0, 0, 1): line(42, "przeciw wściekliźnie.", 720, 850)}
        for k in range(8):
            lines[(1, 0, k)] = line(100 + 40 * k, f"lewy{k} tekst", 100, 480)
            lines[(2, 0, k)] = line(100 + 40 * k, f"prawy{k} tekst", 540, 900)
        out = [" ".join(w[2] for w in ws) for ws in ocr._column_order(lines, 1000, year=1961).values()]
        self.assertEqual(out, ["w sprawie szczepienia psów przeciw wściekliźnie."] + [f"lewy{k} tekst" for k in range(8)]
                         + [f"prawy{k} tekst" for k in range(8)])
        out = [" ".join(w[2] for w in ws) for ws in ocr._column_order(lines, 1000).values()]
        self.assertEqual(out[:2], ["w sprawie szczepienia psów", "lewy0 tekst"])

    def test_quoted_annex_on_scan(self):
        # DU/2000/1315: Art. 2 gives the new annexes of the amended act; "Załącznik nr 3" is not this act's annex
        blocks = [Block("scan", "Art. 1. W ustawie …", 1), Block("scan", "Art. 2. W ustawie … załączniki otrzymują brzmienie:", 1),
                  Block("annex", "Załącznik nr 3", 2), Block("scan", "STAWKI MINIMALNE", 2),
                  Block("scan", "Art. 3. Ustawa wchodzi w życie …", 3)]
        self.assertEqual([b.kind for b in _quoted_scan_annexes([replace(b) for b in blocks])],
                         ["scan", "scan", "scan", "scan", "scan"])
        signed = blocks[:2] + [Block("scan", "Art. 3. Ustawa wchodzi w życie …", 1), Block("signature", "Prezes Rady Ministrów: J. Buzek", 1)] \
            + [Block("annex", "Załącznik nr 3", 2), Block("scan", "STAWKI MINIMALNE", 2)]
        self.assertEqual(_quoted_scan_annexes([replace(b) for b in signed])[4].kind, "annex")
        # an act set in the annex of an announcement starts at Art. 1: the annex stays
        announced = [Block("scan", "§ 1. Ogłasza się jednolity tekst ustawy …", 1), Block("annex", "Załącznik do obwieszczenia …", 2),
                     Block("scan", "USTAWA", 2), Block("scan", "Art. 1. Ustawa określa …", 2)]
        self.assertEqual(_quoted_scan_annexes([replace(b) for b in announced])[1].kind, "annex")
        # DU/1994/753: the act's own annex ("(poz. 753)") with the signature read after it stays an annex
        own = [Block("scan", "§ 1. Ustanawia się zakaz wywozu towarów wymienionych w załączniku.", 1),
               Block("annex", "Załącznik do rozporządzenia Rady Ministrów z dnia 28 grudnia 1994 r. (poz. 753)", 1),
               Block("scan", "WYKAZ TOWARÓW OBJĘTYCH ZAKAZEM WYWOZU", 1), Block("signature", "Prezes Rady Ministrów: W. Pawlak", 1)]
        self.assertEqual(_quoted_scan_annexes([replace(b) for b in own], "753")[1].kind, "annex")
        self.assertEqual(_quoted_scan_annexes([replace(b) for b in own], "75")[1].kind, "scan")
        self.assertEqual(_quoted_scan_annexes([replace(b) for b in own])[1].kind, "scan")

    def test_markdown(self):
        doc = Document(blocks=[Block("scan", "§ 1. Tekst.", 1), Block("scan", "Dalej.", 1), Block("scan", "§ 2. Koniec.", 2)],
                       no_text_pages=[1, 2], ocr_pages=[1, 2], ocr_engine="tesseract 5.5.0",
                       ocr_langs={1: "pol+eng", 2: "pol+eng"})
        md = to_markdown(doc, META)
        self.assertIn("> [Strona 1 PDF jest skanem. Tekst poniżej odczytał OCR (tesseract 5.5.0, pol+eng), a nie warstwa "
                      "tekstowa PDF. Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]\n\n##### § 1.\n\nTekst.\n\n"
                      "Dalej.\n\n> [Strona 2 PDF jest skanem.", md)
        self.assertIn("##### § 2.\n\nKoniec.", md)


@unittest.skipUnless(shutil.which("tesseract"), "tesseract not installed")
class OcrImage(unittest.TestCase):
    def test_reads_rendered_text(self):
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("L", (1600, 300), 255)
        try:
            font = ImageFont.truetype("DejaVuSerif.ttf", 48)
        except OSError:
            self.skipTest("DejaVu font not available")
        ImageDraw.Draw(img).text((50, 100), "Umowa wchodzi w życie z dniem podpisania.", font=font, fill=0)
        lang = "pol" if "pol" in ocr.tesseract()[2] else "eng"
        page = ocr.parse_tsv(ocr._run(img, lang, "tsv"), img.height)
        self.assertIn("wchodzi", " ".join(page.paragraphs))


if __name__ == "__main__":
    unittest.main()
