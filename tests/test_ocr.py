import shutil
import unittest
from unittest import mock

from eli2md import ocr
from eli2md.pdf import Block, Document, to_markdown

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
