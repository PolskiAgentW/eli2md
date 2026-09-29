import unittest

from eli2md.eli import parse_eli
from eli2md.pdf import Block, Document, _char_angle, _to_frame, page_ranges, to_markdown

META = {"ELI": "DU/2025/1", "title": "Ustawa z dnia 1 stycznia 2025 r. o próbie", "type": "Ustawa",
        "pos": 1, "publisher": "DU", "keywords": ["a", "b"]}


class Basic(unittest.TestCase):
    def test_parse_eli(self):
        self.assertEqual(parse_eli("DU/2025/900"), ("DU", 2025, 900))
        self.assertEqual(parse_eli("https://api.sejm.gov.pl/eli/acts/DU/2024/1/"), ("DU", 2024, 1))
        with self.assertRaises(ValueError):
            parse_eli("2025/900")

    def test_markdown_articles(self):
        doc = Document(blocks=[Block("p", "USTAWA", 1), Block("p", "Art. 1. Tekst[^1] artykułu.", 1),
                               Block("p", "§ 2. To nie nagłówek, bo są artykuły.", 1),
                               Block("signature", "Prezydent: A. B", 1), Block("annex", "Załącznik nr 1", 2)],
                       footnotes=["[^1] Przypis."])
        md = to_markdown(doc, META)
        self.assertTrue(md.startswith("---\ntitle: \"Ustawa z dnia 1 stycznia 2025 r. o próbie\"\n"))
        self.assertIn('identifier: "DU-2025-1"', md)
        self.assertIn('keywords: "a, b"', md)
        self.assertIn("\n\n##### Art. 1.\n\nTekst[^1] artykułu.\n\n", md)
        self.assertIn("\n\n§ 2. To nie nagłówek", md)
        self.assertIn("\n\n*Prezydent: A. B*\n\n## Załącznik nr 1\n\n[^1]: Przypis.\n", md)

    def test_markdown_paragraph_units(self):
        doc = Document(blocks=[Block("p", "§ 1. Rozporządzenie określa zasady.", 1)])
        self.assertEqual(to_markdown(doc), "##### § 1.\n\nRozporządzenie określa zasady.\n")

    def test_rotated_frame(self):
        # text rotated 90 degrees counter-clockwise on a portrait page (595x842), as in DU/2024/144
        c = {"matrix": (0.0, 10.0, -10.0, 0.0, 0, 0), "x0": 94.6, "x1": 104.6, "top": 747.5, "bottom": 757.0}
        self.assertEqual(_char_angle(c), 90)
        self.assertEqual(_char_angle({"matrix": (8.0, 0.0, 0.0, 8.0, 0, 0)}), 0)
        self.assertEqual(_char_angle({"matrix": (-7.8, 0.0, 0.0, -7.8, 0, 0)}), 180)
        f = _to_frame(c, 90, 595, 842)
        self.assertAlmostEqual(f["x0"], 842 - 757.0)
        self.assertAlmostEqual(f["top"], 94.6)
        self.assertEqual(f["size"], 10.0)
        self.assertTrue(f["upright"])
        # a later char in the same line (further up the page) must come later in the frame
        self.assertGreater(_to_frame({**c, "top": 737.5, "bottom": 747.0}, 90, 595, 842)["x0"], f["x0"])

    def test_dataset_index_roundtrip(self):
        import tempfile
        from pathlib import Path
        from eli2md.dataset import load_index, save_index
        with tempfile.TemporaryDirectory() as d:
            rows = {"DU/2025/10": {"eli": "DU/2025/10", "year": "2025", "pos": "10", "title": "A, \"b\"", "status": "ok"},
                    "DU/2025/9": {"eli": "DU/2025/9", "year": "2025", "pos": "9", "title": "c", "status": "error"}}
            save_index(Path(d), rows)
            back = load_index(Path(d))
            self.assertEqual(list(back), ["DU/2025/9", "DU/2025/10"])  # numeric order
            self.assertEqual(back["DU/2025/10"]["title"], 'A, "b"')


    def test_no_text_pages(self):
        self.assertEqual(page_ranges([2, 3, 4, 7]), "2-4, 7")
        self.assertEqual(page_ranges([]), "")
        doc = Document(blocks=[Block("p", "Tekst.", 1), Block("notext", "", 2), Block("notext", "", 3),
                               Block("p", "Dalej.", 4), Block("notext", "", 6)], no_text_pages=[2, 3, 6])
        md = to_markdown(doc, META)
        self.assertIn('pages_without_text: "2-3, 6"', md)
        self.assertIn("> [Strony 2-3 PDF nie mają warstwy tekstowej", md)
        self.assertIn("> [Strona 6 PDF nie ma warstwy tekstowej", md)
        self.assertEqual(md.count("> ["), 2)

    def test_image_note(self):
        doc = Document(blocks=[Block("p", "Wzór", 3), Block("image", "", 3), Block("p", "Opis.", 3)],
                       image_pages=[3])
        md = to_markdown(doc, META)
        self.assertIn('pages_with_images: "3"', md)
        self.assertIn("Wzór\n\n> [Na stronie 3 PDF jest obraz", md)


if __name__ == "__main__":
    unittest.main()
