import unittest

from eli2md.eli import parse_eli
from eli2md.pdf import (UNIT_START, Block, Document, Line, _char_angle, _frame_lines, _free, _glyph_box, _join, _segment,
                        _to_frame, page_ranges, to_markdown)

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

    def test_glyph_box(self):
        # Cambria declares /Descent -2464: pdfminer's box of "r" (baseline 584.47 from the top, 10.82 pt) lies
        # 16-27 pt below the glyph; the ink test looked at the next line (MP/2025/1128, page 21)
        H, s, f = 841.89, 10.8192, 257.42
        y0 = f - 2.464 * s
        c = {"matrix": (s, 0.0, 0.0, s, 185.01, f), "x0": 185.01, "x1": 189.49, "y0": y0, "y1": y0 + s,
             "top": H - y0 - s, "bottom": H - y0}
        x0, top, x1, bottom = _glyph_box(c)
        self.assertEqual((x0, x1), (185.01, 189.49))
        self.assertAlmostEqual(bottom, H - f + 0.3 * s)
        self.assertAlmostEqual(bottom - top, s)
        # a usual descent (Times: -307/1000) is kept
        y0 = f - 0.307 * s
        times = {**c, "y0": y0, "y1": y0 + s, "top": H - y0 - s, "bottom": H - y0}
        self.assertEqual(_glyph_box(times), (185.01, H - y0 - s, 189.49, H - y0))
        # rotated 90 degrees (up is towards -x): the box is moved left, onto the glyph
        rot = {"matrix": (0.0, s, -s, 0.0, 100.0, 400.0), "x0": 100.0 + 1.464 * s, "x1": 100.0 + 2.464 * s,
               "y0": 400.0, "y1": 405.0, "top": H - 405.0, "bottom": H - 400.0}
        x0, top, x1, bottom = _glyph_box(rot)
        self.assertAlmostEqual(x0, 100.0 - 0.7 * s)
        self.assertAlmostEqual(x1, 100.0 + 0.3 * s)
        self.assertEqual((top, bottom), (H - 405.0, H - 400.0))

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
        self.assertIn("> [Strony 2-3 PDF nie mają czytelnej warstwy tekstowej", md)
        self.assertIn("> [Strona 6 PDF nie ma czytelnej warstwy tekstowej", md)
        self.assertEqual(md.count("> ["), 2)

    def test_image_note(self):
        doc = Document(blocks=[Block("p", "Wzór", 3), Block("image", "", 3), Block("p", "Opis.", 3)],
                       image_pages=[3])
        md = to_markdown(doc, META)
        self.assertIn('pages_with_images: "3"', md)
        self.assertIn("Wzór\n\n> [Na stronie 3 PDF jest obraz", md)


    def test_small_digits(self):
        # 10pt body on a baseline at 110; 6pt digits: raised = superscript, lowered = subscript
        def w(text, x0, top=100.0, size=10.0):
            return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top, "bottom": top + size, "size": size}
        words = [w("Art.", 50), w("41", 72), w("1", 82, 98, 6), w(".", 85.5),
                 w("Pole", 100), w("m", 125), w("2", 131, 98, 6), w("i", 140),
                 w("P", 150), w("2", 156, 106, 6), w("O", 160), w("5", 166, 106, 6),
                 w("ustawy", 180), w("3)", 211, 98, 6), w(",", 221)]
        body, _ = _frame_lines(words, 600, 800, [], 1)
        self.assertEqual([l.text for l in body], ["Art. 41¹. Pole m² i P₂O₅ ustawy[^3],"])
        md = to_markdown(Document(blocks=[Block("p", "Art. 41¹. Treść.", 1)]))
        self.assertTrue(md.startswith("##### Art. 41¹.\n\nTreść."))

    def test_quoted_units_are_not_headings(self):
        doc = Document(blocks=[Block("p", "Art. 1. W ustawie wprowadza się zmiany:", 1),
                               Block("p", "1) art. 29 i art. 30 otrzymują brzmienie:", 1),
                               Block("p", "„Art. 29. Treść.", 1), Block("p", "Art. 30. 1. Treść ust. 1.", 1),
                               Block("p", "2. Treść ust. 2.", 1), Block("p", "Art. 31. § 1. Treść § 1.”;", 1),
                               Block("p", "Art. 2. Ustawa wchodzi w życie.", 1)])
        md = to_markdown(doc)
        self.assertEqual(md.count("##### "), 2)
        self.assertIn("##### Art. 2.", md)
        self.assertIn("„Art. 29. Treść.\n\nArt. 30.\n\n1. Treść ust. 1.", md)
        self.assertIn("\n\nArt. 31.\n\n§ 1. Treść § 1.”;\n\n##### Art. 2.", md)

    def test_unit_start(self):
        for t in ["Art. 41¹. Treść", "§ 2. Treść", "2. Treść", "5²) treść", "b) treść", "aa) treść", "– treść"]:
            self.assertTrue(UNIT_START.match(t), t)
        for t in ["treść b) dalej", "1998 r. poz. 1", "(1, 3) x"]:
            self.assertFalse(UNIT_START.match(t), t)

    def test_quote_edge_cases(self):
        # seconds sign in coordinates does not close a quote; "Art. 30. „1." quotes only its ust. 1
        doc = Document(blocks=[Block("p", "„Art. 5. Granica biegnie południkiem 16°41’56,70” długości.", 1),
                               Block("p", "Art. 6. Nadal w cytacie.”", 1),
                               Block("p", "Art. 30. „1. Cytowany ustęp.”", 1),
                               Block("p", "Art. 7. Nagłówek.", 1)])
        md = to_markdown(doc)
        self.assertEqual(md.count("##### "), 1)
        self.assertIn("##### Art. 7.", md)
        self.assertIn("\n\nArt. 30.\n\n„1. Cytowany ustęp.”\n\n", md)

    def test_unclosed_quote_mid_sentence(self):
        # the source forgot a closing quote inside a sentence: later headings must survive
        doc = Document(blocks=[Block("p", "Art. 1. Zwany dalej „kodem świadczenia;", 1),
                               Block("p", "Art. 2. Tekst.", 1),
                               Block("p", "Art. 3. Zmiany: „Art. 9. Cytat.", 1)])
        md = to_markdown(doc)
        self.assertIn("##### Art. 2.", md)

    def test_join_repeated_hyphen(self):
        # a compound broken at its hyphen repeats the hyphen on the next line; a plain break adds one
        self.assertEqual(_join("gospodarstwa rolno-", "-środowiskowe"), "gospodarstwa rolno-środowiskowe")
        self.assertEqual(_join("metylo-17-", "-metylomorfinan"), "metylo-17-metylomorfinan")
        self.assertEqual(_join("wyna-", "grodzenie"), "wynagrodzenie")
        self.assertEqual(_join("wartość -", "- 5"), "wartość - - 5")

    def test_footnote_rule_stands_alone(self):
        rule = {"x0": 51.0, "x1": 195.1, "top": 764.3, "bottom": 764.8}
        border = {"x0": 81.0, "x1": 236.4, "top": 563.3, "bottom": 563.8}
        next_cell = {"x0": 236.9, "x1": 373.0, "top": 563.3, "bottom": 563.8}
        self.assertTrue(_free(rule, [rule, border, next_cell]))
        self.assertFalse(_free(border, [rule, border, next_cell]))

    def test_segment_small_gap_units(self):
        # line pitch 12 pt (gap 2), units 14 pt (gap 4): below the 0.45 * size threshold, above the usual gap
        def line(top, x0, x1, text):
            return Line(1, top, top + 10, x0, 10.0, text, x1=x1, right=544, lead=2.0)
        body = [line(100, 51, 544, "1) w § 2 ust. 1–3 otrzymują brzmienie:"),  # full line: no break by length
                line(114, 96, 544, "„1. Przewodniczącemu przysługuje miesięczne wynagrodzenie w wysokości"),
                line(126, 72, 253, "9500 zł."),
                line(140, 96, 544, "2. Członkom przysługuje wynagrodzenie w wysokości 625 zł, a pozostałym"),
                line(152, 72, 544, "2. kwartał – tekst, który jest dalszym ciągiem zdania z odstępem 2 pt.")]
        self.assertEqual([b.text[:6] for b in _segment(body)], ["1) w §", "„1. Pr", "2. Czł"])

    def test_segment_wide_line_spacing(self):
        # DU/2024/853: lines of a paragraph 7 pt apart at 12 pt (over 0.45 * size), paragraphs 17 pt apart;
        # the threshold follows the usual gap before continuation lines on that page, and only on that page
        def line(page, top, x0, text):
            return Line(page, top, top + 12, x0, 12.0, text, x1=500)
        p1 = ["Na podstawie protokołów wyników głosowania z wszystkich okręgów, Państwowa", "Komisja Wyborcza ustaliła:",
              "1) liczba wyborców uprawnionych wyniosła 29 098 155;", "2) karty do głosowania wydano 11 827 313 wyborcom,",
              "w tym:", "a) 12 735 kart wydano na podstawie przedstawionego", "pełnomocnictwa,", "b) 147 414 wyborców głosowało",
              "na podstawie zaświadczenia;", "3) pakiety wyborcze wysłano", "łącznie 4 277 wyborcom;", "4) liczba kart",
              "wydanych w lokalach", "oraz w głosowaniu korespondencyjnym;"]
        gaps = [7, 17, 17, 7, 17, 7, 17, 7, 17, 7, 17, 7, 7]
        body, top = [line(1, 100, 56, p1[0])], 100.0
        for g, t in zip(gaps, p1[1:]):
            top += 12 + g
            body.append(line(1, top, 56, t))
        # page 2 has the usual spacing (2 pt): a 7 pt gap still starts a paragraph there
        body += [line(2, 100, 56, "Tekst na drugiej stronie, który"), line(2, 114, 56, "ciągnie się dalej"),
                 line(2, 128, 56, "i jeszcze dalej"), line(2, 142, 56, "oraz dalej"), line(2, 156, 56, "a także dalej"),
                 line(2, 170, 56, "i do końca."), line(2, 189, 56, "Nowy akapit po odstępie 7 pt.")]
        self.assertEqual([b.text[:12] for b in _segment(body)],
                         ["Na podstawie", "1) liczba wy", "2) karty do ", "a) 12 735 ka", "b) 147 414 w", "3) pakiety w",
                          "4) liczba ka", "Tekst na dru", "Nowy akapit "])

    def test_segment_wide_spacing_units_without_extra_gap(self):
        # DU/2024/1442: lines 8.6 pt apart at 12 pt and units no further apart; "1)"/"a)" start a unit anyway,
        # "1." only after a sentence end ("2. kwartał" after "w" continues the sentence)
        texts = ["Wymagania:", "1) certyfikat wydany przez akredytowaną", "instytucję w analogicznym", "zakresie;",
                 "2) deklarację zgodności UE,", "w tym:", "a) wynik w teście co najmniej 85 punktów lub", "b) inny wynik",
                 "osiągnięty w teście;", "3) wydajność osiągana w", "2. kwartał – dalszy ciąg zdania", "i jeszcze dalej;",
                 "4. Czwarty ustęp."]
        body = [Line(1, 100 + i * 20.6, 112 + i * 20.6, 56, 12.0, t, x1=524, right=524) for i, t in enumerate(texts)]
        self.assertEqual([b.text[:8] for b in _segment(body)],
                         ["Wymagani", "1) certy", "2) dekla", "a) wynik", "b) inny ", "3) wydaj", "4. Czwar"])

    def test_heading_unit_per_part(self):
        # "Art. 42 ust. 1 ustawy…" in an annex must not turn off the § headings of the main text
        doc = Document(blocks=[Block("p", "§ 1. Treść.", 1), Block("p", "§ 2. Treść.", 1),
                               Block("annex", "Załącznik nr 1", 2), Block("p", "Art. 42 ust. 1 ustawy określa, że…", 2),
                               Block("annex", "Załącznik nr 2", 3), Block("p", "Art. 1. Tekst jednolity.", 3),
                               Block("p", "§ 1. Paragraf w artykule.", 3)])
        md = to_markdown(doc)
        self.assertIn("##### § 1.\n\nTreść.", md)
        self.assertIn("##### Art. 1.", md)
        self.assertNotIn("##### Art. 42", md)
        self.assertNotIn("##### § 1.\n\nParagraf", md)

    def test_footnote_numbering_restarts(self):
        # the annex numbers its footnotes from 1 again: labels must stay unique and markers find their footnote
        doc = Document(blocks=[Block("p", "§ 1. Tekst[^1].", 1), Block("annex", "Załącznik nr 1", 2),
                               Block("p", "Wzór[^1] i dalej[^2].", 2), Block("p", "Formularz[^1].", 3)],
                       footnotes=["[^1] Przypis aktu.", "[^1] Niepotrzebne skreślić.", "[^2] Objaśnienie.",
                                  "[^1] Na stronie 3."], footnote_pages=[1, 2, 2, 3])
        md = to_markdown(doc)
        self.assertIn("Tekst[^1].", md)
        self.assertIn("Wzór[^1_2] i dalej[^2].", md)
        self.assertIn("Formularz[^1_3].", md)
        for d in ("[^1]: Przypis aktu.", "[^1_2]: Niepotrzebne skreślić.", "[^2]: Objaśnienie.", "[^1_3]: Na stronie 3."):
            self.assertIn(d, md)


if __name__ == "__main__":
    unittest.main()
