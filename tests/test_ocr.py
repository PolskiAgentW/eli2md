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
            self.assertEqual(ocr.check("eng"), "5.5.0")

    def test_markdown(self):
        doc = Document(blocks=[Block("p", "Art. 1. Tekst.", 1), Block("ocr", "Art. 2. „Odczytane", 2),
                               Block("ocr", "# nie nagłówek", 2), Block("ocr", "- nie lista", 3),
                               Block("notext", "", 4), Block("p", "Art. 3. Dalej.", 5)],
                       no_text_pages=[2, 3, 4], ocr_pages=[2, 3], ocr_engine="tesseract 5.5.0, pol+eng")
        md = to_markdown(doc, META)
        self.assertIn('pages_without_text: "2-4"', md)
        self.assertIn('pages_ocr: "2-3"', md)
        self.assertIn('ocr: "tesseract 5.5.0, pol+eng"', md)
        self.assertIn("\n\n> [Strona 2: tekst odczytany przez OCR (tesseract 5.5.0, pol+eng), może zawierać błędy. "
                      "Wiążący jest PDF.]\n\nArt. 2. „Odczytane\n\n\\# nie nagłówek\n\n> [Strona 3: ", md)
        self.assertIn("\n\n\\- nie lista\n\n> [Strona 4 PDF nie ma warstwy tekstowej", md)
        # OCR text is never a heading, and its unclosed quote does not swallow the next heading
        self.assertEqual(md.count("##### "), 2)
        self.assertIn("##### Art. 3.", md)

    def test_no_ocr_fields_without_ocr(self):
        md = to_markdown(Document(blocks=[Block("notext", "", 1)], no_text_pages=[1]), META)
        self.assertNotIn("pages_ocr", md)
        self.assertNotIn("\nocr:", md)


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
