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
        lines = _ocr_lines(["1", "Rozporządzenie Ministra Sprawiedliwości", "Art. 33.",
                            "Sprostowanie powinno być wydrukowane w języku polskim."], 1, 600, 840, 1, "scan", old=True)
        self.assertEqual([l.act for l in lines], [1, 0, 0, 0])  # a sentence of the press law (DU/1928/1)
        # a speck under the number and before the type (DU/1984/126)
        lines = _ocr_lines(["126", ";", "i ROZPORZĄDZENIE RADY MINISTRÓW."], 1, 600, 840, 126, "scan", old=True)
        self.assertEqual([(l.act, l.text) for l in lines], [(126, "126"), (0, "ROZPORZĄDZENIE RADY MINISTRÓW.")])
        # the contents of an issue after the war, in capitals and with dashes: the act's bare number under it is the
        # act's though OCR misread the type under it (DU/1947/422); a number and a dash before the type (DU/1935/405)
        page = ["RZECZYPOSPOLITEJ POLSKIEJ", "Warszawa, dnia 6 listopada 1947 r.",
                "TREŚĆ: ROZPORZĄDZENIE PREZESA RADY MINISTRÓW Poz.: 422 — z dnia 28 października 1947 r. o statystyce",
                "RGZPGRZĄDZENIA: 423 — Ministra Administracji Publicznej z dnia 14 października 1947 r.", "422",
                "RO7PORZĄDZENIE PREZESA RADY MINISTRÓW", "z dnia 28 października 1947 r."]
        self.assertEqual(acts(page, 422), [(422, "422")])
        self.assertEqual(acts(page[3:], 422), [])  # without the contents: a bare number before no type
        self.assertEqual(acts(["405. - ROZPORZĄDZENIE RADY MINISTRÓW z dnia 21 sierpnia 1935 r."], 405), [(405, "405")])
        page = ["POLSKIEJ RZECZYPOSPOLITEJ LUDOWEJ", "TREŚĆ: Poz.:", "240 — Konwencja Nr 105 o zniesieniu pracy przymusowej",
                "244 — z dnia 27 czerwca 1959 r. w sprawie", "KONWENCJA Nr 105"]  # an item of the contents (DU/1959/240)
        self.assertEqual(acts(page, 240), [])
        # a bare number of the contents before a paragraph of text is no act's number: the next act's, read by OCR in
        # the middle of this one (DU/1922/116: "117" before "§ 2. Wykonanie …")
        page = ["RZECZYPOSPOLITEJ POLSKIEJ.", "# Treść: 116. Rozporządzenie Rady Ministrów z dnia 26 stycznia 1922 r. o włączeniu",
                "117. Oświadczenie rządowe w przedmiocie konwencji polsko-gdańskiej", "116. i . \"\" .",
                "Rozporządzenie Rady Ministrów z dnia 26 stycznia 1922 r.", "§ 1. Gminę Miastków wyłącza się z powiatu.",
                "117", "§ 2. Wykonanie niniejszego rozporządzenia powierza się Ministrowi Spraw Wewnętrznych."]
        self.assertNotIn(117, [a for a, _ in acts(page, 116)])
        page = ["RZECZYPOSPOLITEJ POLSKIEJ,", "Treść: 952. Zarządzenie Prezydenta Rzeczypospolitej z dnia 20 listopada 1924 r.",
                "953. Rozporządzenie Prezydenta Rzeczypospolitej z dnia 3 grudnia 1924 r.", "952",
                "asa Zarządzenie Prezydenta kzeczypospolitej z dnia 20 listopada 1924 roku"]  # DU/1924/952: specks, type
        self.assertEqual(acts(page, 952), [(952, "952")])
        page = ["POLSKIEJ RZECZYPOSPOLITEJ LUDOWEJ", "TREŚĆ: Poz.:", "2 — z dnia 15 stycznia 1985 r. zmieniające rozporządzenie",
                "pracownik zachowuje prawo do wynagrodzenia.”", "§ 2. Rozporządzenie wchodzi w życie z dniem ogłoszenia."]
        self.assertEqual(acts(page, 2), [])  # "§ 2." is no act's number (DU/1985/2)
        page[-1] = "2. Rozporządzenie wchodzi w życie z dniem ogłoszenia."  # nor "2." when OCR lost the "§" (DU/1967/5)
        self.assertEqual(acts(page, 2), [])
        # the number and "Przekład." before the type in ordinary case, the position in contents with dashes (DU/1926/301)
        page = ["RZECZYPOSPOLITEJ POLSKIEJ.", "TREŚĆ: OŚWIADCZENIE RZĄDOWE: Poz.: 300—z dnia 20 marca 1926r. w sprawie",
                "UMOWA:", "Poz.: 301—miedzy Rzadem Rzeczypospolitej Polskiej a Rządem Rzeszy Niemieckiej",
                "300. Oświadczenie rządowe z dnia 20 marca 1926 r. w sprawie ratyfikacji Umowy",
                "301. Przekład. Umowa między Rządem Rzeczypospolitej Polskiej a Rządem Rzeszy Niemieckiej"]
        lines = _ocr_lines(page, 1, 600, 840, 301, "scan", old=True)
        self.assertEqual([(l.act, l.text[:18]) for l in lines if l.act or l.text.startswith("Przekład")],
                         [(301, "301"), (0, "Przekład. Umowa mi")])

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
        # nor one with the position after the type, or after "Poz.:" with no space after the dash: the next item of
        # the contents on an issue's first page ended the act at the masthead (DU/1952/276, DU/1927/863 in 0.6.46)
        t277 = "Oświadczenie rządowe z dnia 9 września 1952 r. o wejściu w życie umowy między Rządem Rzeczypospolitej Polskiej"
        first = [L("POLSKIEJ RZECZYPOSPOLITEJ LUDOWEJ"), L("Warszawa, dnia 30 września 1952 r."),
                 L("UMOWA MIEDZYNARODOWA. 276 — Umowa miedzy Rządem Rzeczypospolitej Polskiej a Rządem Niemieckiej Republiki"),
                 L("OŚWIADCZENIE RZĄDOWE 277 — z dnia 9 września 1952 r. o wejściu w życie umowy między Rządem "
                   "Rzeczypospolitej Polskiej a Rządem Niemieckiej Republiki"), L("276"), L("UMOWA"), L("Tekst umowy.")]
        self.assertFalse(_title_at(first, 3, t277))
        self.assertEqual(_by_neighbors((first, [], 1, 1), 276, {277: t277})[0], first)
        t864 = "Zarządzenie Prezydenta Rzeczypospolitej z dnia 4 listopada 1927 r. o wywłaszczeniu nieruchomości w Będzinie"
        toc = [L("ZARZĄDZENIE PREZYDENTA RZECZYPOSPOLITEJ"), L("Poz.: 864—z dnia 4 listopada 1927 r. o wywłaszczeniu "
                                                              "nieruchomości w Będzinie")]
        self.assertFalse(_title_at(toc, 0, t864))
        from eli2md.pdf import CONTENTS_TYPED_ITEM
        self.assertIsNone(CONTENTS_TYPED_ITEM.match("146 - OŚWIADCZENIE RZĄDOWE"))  # the act's own number before its type
        self.assertIsNone(CONTENTS_TYPED_ITEM.match("ROZPORZĄDZENIE RADY MINISTRÓW: 3 —"))  # specks (DU/1986/27)
        # a header that reads as well as the act's own title is the act's (DU/1926/314 and 315, alike in issuer, date
        # and the words after it). A header under a bare number of the act or the one before it may still be the next
        # act's: OCR misreads its number ("603" for 605, DU/1924/604; "325" for 326, DU/1927/325)
        t314 = ("Rozporządzenie Ministra Pracy i Opieki Społecznej z dnia 21 maja 1926 r. zmieniające niektóre przepisy "
                "rozporządzenia o ubezpieczeniu")
        body = [L("§ 2. Tekst."), L("Tekst"), L("Rozporządzenie Ministra Pracy i Opieki Społecznej"), L("z dnia 21 maja 1926 r."),
                L("zmieniające niektóre przepisy rozporządzenia o ubezpieczeniu")]
        self.assertEqual(_by_neighbors((body, [], 1, 1), 314, {315: t314 + " pracowników"}, t314)[0], body)
        self.assertEqual(len(_by_neighbors((body, [], 1, 1), 314, {315: t314 + " pracowników"})[0]), 2)  # no title
        # a short own title does not win on its length alone (DU/1983/221 and 222)
        t221 = "Rozporządzenie Ministra Handlu Wewnętrznego i Usług z dnia 9 sierpnia 1983 r. w sprawie rejestracji cechów."
        t222 = t221.replace("cechów.", "statutów izb rzemieślniczych.")
        body = [L("§ 5. Rozporządzenie wchodzi w życie z dniem ogłoszenia."), L("Minister Handlu: E. Szymański"),
                L("ROZPORZĄDZENIE MINISTRA HANDLU WEWNĘTRZNEGO I USŁUG z dnia 9 sierpnia 1983 r. w sprawie rejestracji "
                  "statutów izb a"), L("Na podstawie art. 34 ust. 5 ustawy zarządza się, co następuje:")]
        self.assertEqual(len(_by_neighbors((body, [], 1, 1), 221, {222: t222}, t221)[0]), 2)
        # nor a long own title on letters of the header that match by chance (DU/1928/19 and 20)
        t19 = "Rozporządzenie Prezydenta Rzeczypospolitej z dnia 23 grudnia 1927 r. o zmianie dekretu o rejestrze handlowym."
        t20 = "Rozporządzenie Prezydenta Rzeczypospolitej z dnia 23 grudnia 1927 r. o zapobieganiu upadłości."
        body = [L("Art. 3. Rozporządzenie niniejsze wchodzi w życie z dniem ogłoszenia."),
                L("Minister Poczt i Telegrafów: Bogusław Miedziński"), L("Rozporządzenie Prezydenta Rzeczypospolitej"),
                L("z dnia 23 grudnia 1927 r."), L("o zapobieganiu upadłości."),
                L("Na podstawie art. 44 ust. 6 Konstytucji i ustawy z dnia 2 sierpnia 1926 r. o upoważnieniu Prezydenta "
                  "Rzeczypospolitej do wydawania rozporządzeń z mocą ustawy (Dz. U. R. P. Ne 78, poz. 443) postanawiam "
                  "co następuje:"), L("Rozdział I.")]
        self.assertEqual(len(_by_neighbors((body, [], 1, 1), 19, {20: t20}, t19)[0]), 2)

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

    def test_column_order_gutter_specks_1923_1989(self):
        # 1923-1989: a speck of the scan in the gutter hid the gap of a line tesseract joined over it ("Prezy- ~ 1929",
        # DU/1935/396), or stood before the first word of a right column's line, past the ends of the left column's
        # lines but farther left than tol ("—w” Zarządzie" at 1303, g 1324, DU/1930/217); either line went over the
        # page and cut it into bands, so the header of the act in the right column came before the left column's text
        def line(top, text, left, right):
            ws = text.split()
            w = (right - left) // len(ws)
            return [(top, top + 30, t, 95.0, left + k * w, left + (k + 1) * w - 10) for k, t in enumerate(ws)]
        def page(left_end, right_start, odd):
            lines = {}
            for k in range(8):
                lines[(1, 0, k)] = line(100 + 40 * k, f"lewy{k} tekst", 290, left_end + 10)
                lines[(2, 0, k)] = line(100 + 40 * k, f"prawy{k} tekst", right_start, 2470)
            lines.update(odd)
            return lines
        joined = page(1359, 1409, {(1, 0, 3): line(220, "lewy3 Prezy-", 290, 1369) + [(220, 250, "~", 90.0, 1389, 1393)]
                                   + line(220, "prawy3 1929", 1409, 2470)})
        del joined[(2, 0, 3)]
        out = [" ".join(w[2] for w in ws) for ws in ocr._column_order(joined, 2607, year=1935).values()]
        self.assertEqual(out, [f"lewy{k} tekst" if k != 3 else "lewy3 Prezy-" for k in range(8)]
                         + [f"prawy{k} tekst" if k != 3 else "prawy3 1929" for k in range(8)])
        out = [" ".join(w[2] for w in ws) for ws in ocr._column_order(joined, 2607).values()]  # later issues as before
        self.assertIn("lewy3 Prezy- ~ prawy3 1929", out)
        speck = page(1297, 1345, {(2, 0, 5): [(300, 330, "—w”", 90.0, 1303, 1340)] + line(300, "prawy5 tekst", 1345, 2470)})
        out = [" ".join(w[2] for w in ws) for ws in ocr._column_order(speck, 2544, year=1930).values()]
        self.assertEqual(out, [f"lewy{k} tekst" for k in range(8)]
                         + [f"prawy{k} tekst" if k != 5 else "—w” prawy5 tekst" for k in range(8)])

    def test_join_rows_gutter_hint(self):
        # the lower quartile of the gaps in rows is far too wide when the right column holds a table or short lines
        # (DU/1965/60 p. 1: 472 px for a gutter of 52-63 px): the first row of text under a title, 60 px apart, was
        # joined as the title's end; with the gutter as _column_order sees it, it stays two lines
        def ws(top, text, left, right):
            t = text.split()
            w = (right - left) // len(t)
            return [(top, top + 30, x, 95.0, left + k * w, left + (k + 1) * w - 10, None) for k, x in enumerate(t)]
        items = [(100, 0, ws(100, "dnia 5 lipca 1930 r.", 700, 1600))]
        items += [(160, 1, ws(160, "Podaje się niniejszym do wiadomości, że", 250, 1400)),
                  (160, 2, ws(160, "Brytyjskiemu dokument przystąpienia do", 1460, 2400))]
        for k in range(8):  # rows of a table in the right column, far from the left column's short lines
            items += [(220 + 50 * k, 1, ws(220 + 50 * k, f"wiersz{k}", 250, 700)), (220 + 50 * k, 2, ws(220 + 50 * k, f"1{k}.00", 2200, 2400))]
        joined = [it for it in ocr._join_rows(list(items)) if it[1] == 0 and it[0] == 100 or it[0] == 160]
        self.assertEqual(len(joined), 2)  # the title and one row: the row went with the title
        kept = [it for it in ocr._join_rows(list(items), 63) if it[0] in (100, 160)]
        self.assertEqual(sorted(it[1] for it in kept), [0, 1, 2])

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
