import unittest

from eli2md.eli import parse_eli
from eli2md.pdf import (MASTHEAD_END, OLD_HEADER, UNIT_START, Block, Document, Line, _char_angle, _dedupe, _doubled,
                        _group_notes, _drop_watermark, _frame_lines, _free, _glyph_box, _join, _plain_math, _segment,
                        _single_glyphs, _to_frame, _watermark, page_ranges, to_markdown)

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

    def test_dedupe(self):
        # a char drawn twice goes; distinct letters of small print stay, also where same letters of
        # neighbouring lines chain them within 1pt (pdfplumber's dedupe_chars dropped them, MP/2025/541),
        # and so does overlapping text of another size (MP/2025/1142)
        def ch(t, x0, top, size=3.9):
            return {"text": t, "fontname": "F", "size": size, "x0": x0, "x1": x0 + 1.7, "top": top, "bottom": top + size}
        chars = [ch("e", 10.0, 100.0), ch("e", 10.1, 100.0), ch("i", 20.0, 100.0), ch("i", 20.9, 100.0),
                 ch("e", 12.9, 100.0), ch("e", 12.2, 100.8), ch("e", 11.5, 100.0), ch("a", 10.0, 100.0),
                 ch("e", 10.2, 100.2, 4.2)]
        self.assertEqual([(c["text"], c["x0"]) for c in _dedupe(chars)],
                         [("e", 10.0), ("i", 20.0), ("i", 20.9), ("e", 12.9), ("e", 12.2), ("e", 11.5), ("a", 10.0),
                          ("e", 10.2)])

    def test_doubled_math_glyphs(self):
        # Word's Cambria Math maps one glyph to its character twice: 𝑘 reads "𝑘𝑘", 𝜂 "𝜂𝜂" (DU/2026/1236 p. 10)
        def ch(t, font="GOZOOC+CambriaMath"):
            return {"text": t, "fontname": font}
        for t in ("𝑘𝑘", "𝐿𝐿", "𝜂𝜂", "𝜆𝜆"):
            self.assertTrue(_doubled(ch(t)), t)
        # ligatures stay ("ff", "tt" are two letters), as do two different chars, one char, other chars (never seen
        # doubled in a math font) and other fonts
        for c in (ch("ff", "ABCD+TimesNewRomanPSMT"), ch("tt", "ABCD+Calibri"), ch("ff"), ch("fi"), ch("𝑘𝑙"),
                  ch("𝑘"), ch("=="), ch("11"), ch("λλ"), ch("𝑘𝑘", "ABCD+TimesNewRomanPS-ItalicMT")):
            self.assertFalse(_doubled(c), c)

        class Page:
            chars = [ch("𝑘𝑘"), ch("1"), ch("ff", "ABCD+Times")]
        _single_glyphs(Page)
        self.assertEqual([c["text"] for c in Page.chars], ["𝑘", "1", "ff"])
        self.assertEqual(_plain_math("0,302∙𝑘1∙𝐴𝑝"), "0,302∙k1∙Ap")

    def test_placed_tag_survives_nested_marked_content(self):
        # a formula "/Span <</ActualText …>> BDC … EMC" inside "/PlacedPDF BDC" (DU/2026/40): pdfplumber reset the
        # tag to None at the inner EMC, so the rest of the placed page skipped the ink test
        from pdfminer.pdfinterp import PDFResourceManager
        from pdfminer.psparser import LIT
        import pdfplumber.page
        from eli2md.pdf import _PlacedTags
        self.assertIs(pdfplumber.page.PDFPageAggregatorWithMarkedContent, _PlacedTags)
        d = _PlacedTags(PDFResourceManager(), pageno=1)
        d.begin_tag(LIT("PlacedPDF"))
        d.begin_tag(LIT("Span"), {"ActualText": "𝑘𝑘"})
        self.assertEqual(d.cur_tag, "PlacedPDF")
        d.end_tag()
        self.assertEqual(d.cur_tag, "PlacedPDF")
        d.end_tag()
        self.assertIsNone(d.cur_tag)
        d.begin_tag(LIT("P"), {"MCID": 3})  # outside a placed PDF: as in pdfplumber
        d.begin_tag(LIT("Span"))
        self.assertEqual(d.cur_tag, "Span")
        d.end_tag()
        self.assertIsNone(d.cur_tag)

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

    def test_small_indices(self):
        # 2026 prints: indices in brackets, several in one line (DU/2026/468 p. 98); 2025 prints: "22" + small "1a"
        def w(text, x0, top=100.0, size=10.0, x1=None):
            return {"text": text, "x0": x0, "x1": x1 or x0 + 5 * len(text), "top": top, "bottom": top + size,
                    "size": size}
        words = [w("Art.", 50), w("479", 72), w("[30f]", 87, 98, 6.5, 100), w(".", 100),
                 w("art.", 110), w("479", 132), w("[30a]", 147, 98, 6.5, 160), w("–479", 160, x1=180),
                 w("[30e]", 180, 98, 6.5, 193), w("i", 200), w("479", 210),
                 w("[92", 225, 98, 6.5, 233), w("]", 233, 98, 7, 235),  # split by size (DU/2026/468 p. 103)
                 w("ust.", 240), w("1", 262), w("[1]10)", 267, 98, 6.5, 285),  # index + marker (DU/2026/913 p. 44)
                 w("art.", 290), w("22", 312), w("1a", 322, 98, 6.5, 328), w(",", 328)]
        body, _ = _frame_lines(words, 600, 800, [], 1)
        self.assertEqual([l.text for l in body], ["Art. 479³⁰ᶠ. art. 479³⁰ᵃ–479³⁰ᵉ i 479⁹² ust. 1¹[^10] art. 22¹ᵃ,"])
        # a small "[2]" away from the word before it is not an index: kept as printed
        body, _ = _frame_lines([w("Pole", 50), w("x", 100), w("[2]", 150, 98, 6.5)], 600, 800, [], 1)
        self.assertEqual([l.text for l in body], ["Pole x [2]"])
        body, _ = _frame_lines([w("Art.", 50), w("5", 72), w("[1q]", 77, 98, 6.5), w(".", 97)], 600, 800, [], 1)
        self.assertEqual([l.text for l in body], ["Art. 5[1q]."])  # no superscript q: as printed
        md = to_markdown(Document(blocks=[Block("p", "Art. 479³⁰ᶠ. Treść.", 1)]))
        self.assertTrue(md.startswith("##### Art. 479³⁰ᶠ.\n\nTreść."))
        self.assertTrue(UNIT_START.match("5¹ᵃ) treść"))

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

    def test_footnote_rule_high_or_drawn_as_line(self):
        def w(text, x0, top, size):
            return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top, "bottom": top + size, "size": size}

        def rule(top, line=False):
            r = {"x0": 51.0, "x1": 195.6, "top": top, "bottom": top + 0.5, "width": 144.6, "height": 0.5}
            return {**r, "line": True} if line else r
        # a page of footnotes only: the rule at 25% of the page, 9pt below (DU/2024/1539 p. 2)
        page = [w("USTAWA", 250, 100, 11), w("o", 250, 130, 10), w("transporcie", 260, 130, 10),
                w("1)", 51, 216, 6), w("Niniejsza", 64, 216, 9), w("ustawa", 114, 216, 9)]
        page += [w("dyrektywy", 60, 228 + 12 * k, 9) for k in range(40)]
        body, notes = _frame_lines(page, 595, 842, [rule(209)], 1)
        self.assertEqual([l.text for l in body], ["USTAWA", "o transporcie"])
        self.assertTrue(notes[0].text.startswith("[^1] Niniejsza"))
        # the rule drawn as a line (DU/2024/1346 p. 1)
        body, notes = _frame_lines(page, 595, 842, [rule(209, line=True)], 1)
        self.assertEqual(len(body), 2)
        # a high rule or a line with body type below it is not the footnote rule
        page2 = page + [w("Art.", 51, 760, 10), w("1.", 75, 760, 10)]
        for r in (rule(209), rule(209, line=True), rule(600, line=True)):
            body, notes = _frame_lines(page2, 595, 842, [r], 1)
            self.assertEqual(notes, [], r)

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

    def test_segment_points_in_tight_table_cell(self):
        # MP/2025/121: points in a table cell set with the usual line gap and no ";": "2)" after a short line
        # starts a point; "2." after a short line without a sentence end, and "2)" after a full line, do not
        def line(top, x0, x1, text):
            return Line(1, top, top + 9, x0, 9.0, text, x1=x1, right=301, lead=1.5)
        body = [line(100, 58, 217, "1. W zakresie koncesji na przewóz lotniczy:"),
                line(110.5, 66, 431, "1) przyznanie uprawnień do wykonywania regularnego 9553"),
                line(121, 85, 301, "przewozu z wykorzystaniem statków powietrznych bez"),
                line(131.5, 85, 157, "miejsc pasażerskich"),
                line(142, 66, 431, "2) przyznanie uprawnień do wykonywania regularnego 6372"),
                line(152.5, 85, 199, "określonych w pkt"),
                line(163, 85, 301, "2. kwartał – dalszy ciąg zdania w tej samej komórce tabeli i"),
                line(173.5, 85, 301, "3) dalszy ciąg po pełnej linii")]
        self.assertEqual([b.text[:6] for b in _segment(body)], ["1. W z", "1) prz", "2) prz"])

    def test_segment_one_line_points_with_value_cell(self):
        # MP/2025/121: one-line points whose row also holds the fee cell, so no line is short; "2)" right
        # below "1)" at the same x0 starts a point, a label that does not follow ("4)" after "2)") does not
        def line(top, x0, x1, text):
            return Line(1, top, top + 9, x0, 9.0, text, x1=x1, right=301, lead=1.5)
        body = [line(100, 58, 250, "5. Wydanie licencji mechanika lotniczego w zakresie:"),
                line(110.5, 66, 429, "1) B1.1, B1.3, B2, C 483"),
                line(121, 66, 429, "2) B1.2, B1.4 326"),
                line(131.5, 66, 429, "4) pozostałych kategorii lub podkategorii 164")]
        self.assertEqual([b.text[:5] for b in _segment(body)], ["5. Wy", "1) B1", "2) B1"])

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

    def test_notes_printed_in_the_text(self):
        # explanations under an annex table are labelled at the start of a line; their markers are not links to
        # the act's footnotes (DU/2025/1016), nor are markers of footnotes quoted by an amendment
        doc = Document(blocks=[Block("p", "USTAWA[^1] o paszach", 1), Block("p", "„[^1] Niniejsza ustawa wdraża.", 1),
                               Block("annex", "Załącznik nr 1[^2]", 2), Block("p", "1 Arsen[^1] pasza 2[^3]", 3),
                               Block("p", "[^1] Maksymalne zawartości. [^3] Obejmuje.", 3),
                               Block("p", "Wzór[^2] i formularz[^7].", 4)],
                       footnotes=["[^1] Minister kieruje działem.", "[^2] W brzmieniu ustalonym."], footnote_pages=[1, 2])
        md = to_markdown(doc)
        self.assertIn("USTAWA[^1] o paszach", md)
        self.assertIn("„¹⁾ Niniejsza ustawa wdraża.", md)
        self.assertIn("## Załącznik nr 1[^2]", md)
        self.assertIn("1 Arsen¹⁾ pasza 2³⁾", md)
        self.assertIn("¹⁾ Maksymalne zawartości. ³⁾ Obejmuje.", md)
        self.assertIn("Wzór[^2] i formularz[^7].", md)  # 2 is a footnote, not a label; 7: its footnote may be lost
        self.assertIn("[^1]: Minister kieruje działem.", md)
        # a number labelled in the annex, but also a footnote printed on this page: the footnote
        doc.blocks.append(Block("p", "Tabela[^1].", 5))
        doc.footnotes.append("[^1] Przypis strony 5.")
        doc.footnote_pages.append(5)
        md = to_markdown(doc)
        self.assertIn("Tabela[^1_2].", md)
        self.assertIn("1 Arsen¹⁾ pasza", md)

    def test_footnote_with_points(self):
        # "Niniejsza ustawa:" + "1) wdraża…" + "2) służy…" is one footnote (DU/2026/421); "3) …" after "[^2]" and a
        # plain "N)" footnote without an introducing colon start footnotes
        lines = ["[^1] Niniejsza ustawa:", "1) wdraża dyrektywę", "2019/884;", "2) służy stosowaniu.",
                 "[^2] Zmiany ogłoszono.", "3) Ustawa ogłoszona", "w dniu 5 maja."]
        texts, pages = _group_notes([Line(2, 0, 0, 0, 9.0, t) for t in lines])
        self.assertEqual(texts, ["[^1] Niniejsza ustawa:\n\n1) wdraża dyrektywę 2019/884;\n\n2) służy stosowaniu.",
                                 "[^2] Zmiany ogłoszono.", "3) Ustawa ogłoszona w dniu 5 maja."])
        self.assertEqual(pages, [2, 2, 2])
        md = to_markdown(Document(blocks=[Block("p", "USTAWA[^1]", 1)], footnotes=texts[:1], footnote_pages=[1]))
        self.assertIn("[^1]: Niniejsza ustawa:\n\n    1) wdraża dyrektywę 2019/884;\n\n    2) służy stosowaniu.\n", md)

    def test_masthead_end(self):
        for line in ("Poz. 5", "Poz. 1021", "Pozycja 19", ") Poz. 1024*", "Poz. 1024*)"):  # MP/2012/19, MP/2012/1024
            self.assertTrue(MASTHEAD_END.match(line), line)
        for line in ("poz. 5", "Poz. 5 i 6", "Pozycja nr 3 tabeli", "Monitor Polski – 2 – Poz. 5"):
            self.assertFalse(MASTHEAD_END.match(line), line)

    def test_watermark(self):
        # the invisible "www.rcl.gov.pl" over MP 2012 pages: Artifact chars written at ~55 degrees (MP/2012/988)
        wm = {"object_type": "char", "text": "w", "tag": "Artifact", "matrix": (3.09, 4.42, -4.42, 3.09, 94.4, 54.1)}
        self.assertTrue(_watermark(wm))
        self.assertFalse(_watermark({**wm, "tag": None}))  # diagonal text that is not an artifact stays
        self.assertFalse(_watermark({**wm, "matrix": (48.0, 0.0, 0.0, 48.0, 0, 0)}))  # Word masthead, an Artifact
        self.assertFalse(_watermark({**wm, "matrix": (0.0, 10.0, -10.0, 0.0, 0, 0)}))  # rotated table

        class Page:
            def __init__(self, objs):
                self.objs = objs

            @property
            def chars(self):
                return [o for o in self.objs if o["object_type"] == "char"]

            def filter(self, keep):
                return Page([o for o in self.objs if keep(o)])

        text = {"object_type": "char", "text": "a", "tag": None, "matrix": (10.0, 0.0, 0.0, 10.0, 0, 0)}
        rect = {"object_type": "rect"}
        page = Page([text, wm, rect])
        self.assertEqual(_drop_watermark(page).objs, [text, rect])
        clean = Page([text, rect])
        self.assertIs(_drop_watermark(clean), clean)

    @staticmethod
    def _row(text, x0, x1, top, size=10.0):
        """Words of a printed line set from x0 to x1 (justified: equal gaps, the last word ends at x1)."""
        ws = text.split()
        n = sum(5 * len(t) for t in ws)
        gap = (x1 - x0 - n) / (len(ws) - 1) if len(ws) > 1 else 0.0
        assert len(ws) == 1 or x1 - x0 > 300 or 1 < gap < size, (text, gap)  # a line of a column: word spaces
        out, x = [], x0
        for t in ws:
            out.append({"text": t, "x0": x, "x1": x + 5 * len(t), "top": top, "bottom": top + size, "size": size})
            x += 5 * len(t) + gap
        return out

    def _two_column_page(self, header):
        # DU/2005/1255 p. 1: header, act number and title across the page, the text in two columns (38-292 and
        # 303.3-557.4, rows of both columns on one baseline), then the next act
        r = self._row
        page = r(header, 38, 557, 52) + r("1255", 283, 313, 78) + r("USTAWA", 273, 322, 103)
        page += r("o ratyfikacji Umowy z Anguillą", 225, 370, 125)
        left = ["Art. 1. Wyraża się zgodę na dokonanie Prezy-", "denta ratyfikacji Umowy z Anguillą, podpisanej",
                "w Warszawie dnia 17 grudnia 2004 r. oraz w dniu"]
        right = ["Art. 2. Ustawa wchodzi w życie po 14 dniach", "od dnia ogłoszenia."]
        for k, t in enumerate(left):
            page += r(t, 38, 292, 150 + 11 * k)
        page += r("21 stycznia 2005 r.", 38, 127, 183)
        page += r(right[0], 320, 557.4, 150) + r(right[1], 303.3, 394.3, 161)
        page += r("Prezydent: A. Kwaśniewski", 436.4, 557.4, 183)
        page += r("1256", 283, 313, 230) + r("USTAWA", 273, 322, 255)
        for k in range(3):
            page += r("Art. 1. Treść lewej łamanej kolumny tekstu aż", 38, 292, 280 + 11 * k)
            page += r("Treść prawej łamanej kolumny tekstu, wiersz tu", 303.3, 557.4, 280 + 11 * k)
        return page

    def test_two_columns(self):
        body, _ = _frame_lines(self._two_column_page("Dziennik Ustaw Nr 150 — 9307 — Poz. 1255 i 1256"), 595, 842, [], 1)
        self.assertEqual([l.text[:12] for l in body],
                         ["Dziennik Ust", "1255", "USTAWA", "o ratyfikacj", "Art. 1. Wyra", "denta ratyfi",
                          "w Warszawie ", "21 stycznia ", "Art. 2. Usta", "od dnia ogło", "Prezydent: A",
                          "1256", "USTAWA"] + ["Art. 1. Treś"] * 3 + ["Treść prawej"] * 3)
        self.assertEqual([(l.band, l.col) for l in body][3:9], [(7, 0), (8, 1), (8, 1), (8, 1), (8, 1), (8, 2)])
        self.assertEqual({l.right for l in body if l.col == 1}, {292})  # each column has its own right edge
        blocks = _segment(body)
        self.assertEqual([b.text for b in blocks][4:7],
                         ["Art. 1. Wyraża się zgodę na dokonanie Prezydenta ratyfikacji Umowy z Anguillą, podpisanej "
                          "w Warszawie dnia 17 grudnia 2004 r. oraz w dniu 21 stycznia 2005 r.",
                          "Art. 2. Ustawa wchodzi w życie po 14 dniach od dnia ogłoszenia.", "Prezydent: A. Kwaśniewski"])
        self.assertEqual(blocks[6].kind, "signature")

    def test_two_columns_only_in_old_issues(self):
        # the same layout without an issue number in the header (a page of 2012 on) is read across as before
        body, _ = _frame_lines(self._two_column_page("Dziennik Ustaw – 2 – Poz. 1255"), 595, 842, [], 1)
        self.assertIn("Art. 1. Wyraża się zgodę na dokonanie Prezy- Art. 2. Ustawa", [l.text[:59] for l in body])
        self.assertEqual({(l.band, l.col) for l in body}, {(0, 0)})
        self.assertTrue(OLD_HEADER.match("Dziennik Ustaw Nr 150 — 9307 — Poz. 1255, 1256 i 1257"))
        self.assertTrue(OLD_HEADER.match("Monitor Polski Nr 5 — 101 — Poz. 30"))
        self.assertFalse(OLD_HEADER.match("Dziennik Ustaw – 2 – Poz. 1255"))
        # a table of an old issue: cells far apart are not a column of text, the rows are read across
        r = self._row
        page = r("Dziennik Ustaw Nr 150 — 9307 — Poz. 1255", 38, 557, 52)
        for k in range(6):
            page += r("1.", 38, 48, 100 + 11 * k) + r("Minister", 120, 160, 100 + 11 * k)
            page += r("Finansów", 252, 292, 100 + 11 * k) + r("100 zł", 303.3, 331.3, 100 + 11 * k)
            page += r("Treść", 450, 475, 100 + 11 * k) + r("komórki", 522.4, 557.4, 100 + 11 * k)
        body, _ = _frame_lines(page, 595, 842, [], 1)
        self.assertEqual(body[1].text, "1. Minister Finansów 100 zł Treść komórki")
        self.assertEqual({l.col for l in body}, {0})

    def test_two_column_footnotes(self):
        # InDesign (DU/2011/1170 p. 2): a 70 pt line at the right column's edge, footnotes (8.5 pt) under it in that
        # column while the left column goes on; Quark (DU/2009/1323 p. 1): a row "———————" in the left column and
        # footnotes across the page
        r = self._row
        text = r("Dziennik Ustaw Nr 197", 51, 150, 49) + r("— 11235 —", 270, 324, 49) + r("Poz. 1170", 500, 544, 49)
        for k in range(6):
            text += r("treść lewej kolumny tego aktu, wiersz numer dany", 51, 291.6, 80 + 11 * k, 9.5)
        for k in range(3):
            text += r("treść prawej kolumny tego aktu, wiersz numer dany", 303.7, 544.3, 80 + 11 * k, 9.5)
        note = r("1) Zmiany tej ustawy zostały ogłoszone w Dz. U.", 303.7, 544.3, 125, 8.5)
        note += r("z 2010 r. Nr 57, poz. 352.", 311.7, 420, 134, 8.5)
        rule = {"x0": 303.7, "x1": 374.2, "top": 118.0, "bottom": 118.0, "width": 70.5, "height": 0.0, "line": True}
        body, notes = _frame_lines(text + note, 595, 842, [rule], 1)
        self.assertEqual([l.text[:6] for l in notes], ["1) Zmi", "z 2010"])
        self.assertEqual([l.col for l in body].count(1), 6)
        self.assertEqual(len(body), 10)
        body, notes = _frame_lines(text + note, 595, 842, [], 1)  # without the rule the footnote stays in the text
        self.assertEqual(notes, [])
        page = text + r("———————", 51, 118, 150, 9.5)
        page += r("1) Niniejsza ustawa zmienia ustawy: ustawę z dnia 31 stycznia 1980 r. o godle, barwach", 51, 544, 162, 8.5)
        body, notes = _frame_lines(page, 595, 842, [], 1)
        self.assertEqual([l.text[:6] for l in notes], ["1) Nin"])
        self.assertNotIn("———————", [l.text for l in body])

    def test_segment_column_break(self):
        # from the bottom of the left column to the top of the right one: as at a page break, a new block only
        # at a unit or after a sentence end, not by the (negative) gap
        def line(top, col, text, x0=38.0, x1=292.0):
            return Line(1, top, top + 10, x0, 10.0, text, x1=x1, right=x1, lead=1.0, band=2, col=col)
        body = [line(100, 1, "Art. 1. Wyraża się zgodę na dokonanie przez Prezy-"),
                line(111, 1, "denta ratyfikacji umowy."), line(100, 2, "w dniu 5 maja.", 303.3, 557.4)]
        self.assertEqual([b.text for b in _segment(body)],
                         ["Art. 1. Wyraża się zgodę na dokonanie przez Prezydenta ratyfikacji umowy.", "w dniu 5 maja."])
        body[1].text = "denta ratyfikacji umowy podpisanej"
        self.assertEqual(len(_segment(body)), 1)


if __name__ == "__main__":
    unittest.main()
