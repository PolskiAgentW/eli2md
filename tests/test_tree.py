import json
import sys
import unittest
from pathlib import Path

from eli2md.pdf import Block, Document, to_markdown
from eli2md.tree import iter_units, md_to_tree


def md(*paras: str) -> str:
    return "\n\n".join(paras) + "\n"


def paths(nodes: list[dict]) -> list[str]:
    return [n["path"] for n in iter_units(nodes)]


class Tree(unittest.TestCase):
    def test_common_part_after_enumeration(self):
        # text after a list continues the sentence of the unit above the list; a dash there is not a tiret
        t = md_to_tree(md("##### § 1.", "1. Ogłasza się tekst jednolity, z uwzględnieniem zmian wprowadzonych:",
                          "1) ustawą z dnia 1 lutego 2024 r. (Dz. U. poz. 1),", "2) ustawą z dnia 2 marca 2024 r. (Dz. U. poz. 2)",
                          "oraz zmian wynikających z przepisów ogłoszonych przed dniem 1 kwietnia 2024 r.",
                          "– w brzmieniu określonym w załączniku.", "2. Drugi ustęp."))
        ust1 = t["body"][0]["children"][0]
        self.assertEqual([c.get("path", c["type"]) for c in ust1["children"]],
                         ["par_1/ust_1/pkt_1", "par_1/ust_1/pkt_2", "text", "text"])
        self.assertEqual(paths(t["body"]), ["par_1", "par_1/ust_1", "par_1/ust_1/pkt_1", "par_1/ust_1/pkt_2", "par_1/ust_2"])

    def test_article_range(self):
        # "##### Art. 266–280." (consolidated text): an art node of its own; the article before keeps its text
        t = md_to_tree(md("##### Art. 265.", "§ 1. Treść.", "##### Art. 266–280.", "[^52]",
                          "##### Art. 22–28a.", "(pominięte)", "[^52]: Przez art. 1 ustawy."))
        self.assertEqual(paths(t["body"]), ["art_265", "art_265/par_1", "art_266–280", "art_22–28a"])
        self.assertEqual([n["text"] for n in t["body"]][1:], ["[^52]", "(pominięte)"])
        t = md_to_tree(md("##### Art. 41a–Art. 41i.", "(uchylone)"))
        self.assertEqual(paths(t["body"]), ["art_41a–41i"])
        t = md_to_tree(md("##### Art. 106l.", "Treść.", "##### Art. 106ł.", "§ 1. Kto."))
        self.assertEqual(paths(t["body"]), ["art_106l", "art_106ł", "art_106ł/par_1"])

    def test_item_text_split_by_layout_is_not_common_part(self):
        # a boxed layout splits an item into lines; a lit that follows shows the line was the item's own text
        t = md_to_tree(md("##### § 1.", "1. Wniosek zawiera:", "3) wdrożone środki mające na celu zapobieganie",
                          "zakażeniom w stadzie, w tym:", "a) szczepienia,", "b) dezynfekcję;", "4) inne dane."))
        self.assertEqual(paths(t["body"]), ["par_1", "par_1/ust_1", "par_1/ust_1/pkt_3", "par_1/ust_1/pkt_3/lit_a",
                                            "par_1/ust_1/pkt_3/lit_b", "par_1/ust_1/pkt_4"])
        pkt3 = t["body"][0]["children"][0]["children"][0]
        self.assertEqual(pkt3["children"][0], {"type": "text", "text": "zakażeniom w stadzie, w tym:"})

    def test_chapter_heading_with_dot_ends_units(self):
        # DU/2024/853: "Rozdział 2. Tytuł" in one line; the pkt after it are not under ust. 2 of chapter 1
        t = md_to_tree(md("Rozdział 1. Dane ogólne", "1. Wybory przeprowadziły:", "1) komisja;", "2. Wybierano posłów.",
                          "Rozdział 2. Zbiorcze wyniki", "Komisja ustaliła wyniki:", "1) liczba wyborców;"))
        self.assertEqual(paths(t["body"]), ["ust_1", "ust_1/pkt_1", "ust_2", "pkt_1"])
        self.assertEqual([n.get("label") for n in t["body"] if n["type"] == "heading"], ["Rozdział 1", "Rozdział 2"])

    def test_code_headings_in_words_and_with_letters_end_units(self):
        # DU/2026/1245 (k.p.), DU/2026/468 (k.p.c.), DU/2025/24: "DZIAŁ PIĄTY", "CZĘŚĆ PIERWSZA …", "TYTUŁ IIIA …",
        # "Oddział 6[^20]" were text of the article before them
        t = md_to_tree(md("##### Art. 113¹.", "(uchylony)", "DZIAŁ PIĄTY", "Odpowiedzialność materialna pracowników",
                          "##### Art. 14.", "(uchylony)", "CZĘŚĆ PIERWSZA POSTĘPOWANIE ROZPOZNAWCZE", "KSIĘGA PIERWSZA PROCES",
                          "##### Art. 63.", "§ 1. Treść.", "TYTUŁ IIIA Państwowa Inspekcja Pracy",
                          "##### Art. 295.", "§ 2. Treść.", "DZIAŁ CZTERNASTY A", "Odpowiedzialność za szkody",
                          "##### Art. 35⁹.", "Treść.", "Oddział 6[^20]", "Postanowienia wspólne",
                          "##### Art. 1110⁴.", "§ 3. Treść.", "KSIĘGA PIERWSZA a IMMUNITET SĄDOWY",
                          "##### Art. 36.", "Część pierwsza wniosku zawiera dane."))
        self.assertEqual([(n["label"], n["text"]) for n in t["body"] if n["type"] == "heading"],
                         [("DZIAŁ PIĄTY", "Odpowiedzialność materialna pracowników"),
                          ("CZĘŚĆ PIERWSZA", "POSTĘPOWANIE ROZPOZNAWCZE"), ("KSIĘGA PIERWSZA", "PROCES"),
                          ("TYTUŁ IIIA", "Państwowa Inspekcja Pracy"), ("DZIAŁ CZTERNASTY A", "Odpowiedzialność za szkody"),
                          ("Oddział 6", "[^20] Postanowienia wspólne"), ("KSIĘGA PIERWSZA a", "IMMUNITET SĄDOWY")])
        self.assertEqual([n.get("text") for n in t["body"] if n["type"] == "art"],
                         ["(uchylony)", "(uchylony)", "", "", "Treść.", "", "Część pierwsza wniosku zawiera dane."])
        self.assertEqual(paths(t["body"]), ["art_113¹", "art_14", "art_63", "art_63/par_1", "art_295", "art_295/par_2",
                                            "art_35⁹", "art_1110⁴", "art_1110⁴/par_3", "art_36"])
        self.assertFalse(any(c["type"] == "text" for n in t["body"] for c in n.get("children", [])))

    def test_roman_sections_in_annex_end_units(self):
        # DU/2024/629: section III starts with a "1)" list, which is not under "6." of section II
        annex = ("## Załącznik nr 1", "WYKAZ STANOWISK", "I. Stanowiska w obszarze wytwarzania:", "1. realizacji procesu:",
                 "1) asystent;", "II. Stanowiska w obszarze remontów:", "6. gospodarowania nieruchomościami:",
                 "1) dyrektor;", "III. Stanowiska w obszarze warsztatów:", "1) administrator sieci", "IV. Inne", "1. Zasady")
        t = md_to_tree(md("##### § 1.", "Tekst.", *annex))
        body = t["annexes"][0]["body"]
        self.assertEqual(paths(body), ["ust_1", "ust_1/pkt_1", "ust_6", "ust_6/pkt_1", "pkt_1", "ust_1"])
        self.assertEqual([(n["label"], n["text"]) for n in body if n["type"] == "heading"],
                         [("I.", "Stanowiska w obszarze wytwarzania:"), ("II.", "Stanowiska w obszarze remontów:"), ("III.", "Stanowiska w obszarze warsztatów:"),
                          ("IV.", "Inne")])
        # "I." inside an open unit is a row of a table (DU/2024/1657), and so are the sections after it
        annex = ("## Załącznik", "1. Substancje i zawartości:", "Lp. Substancja I II", "I. METALE I METALOID", "1 arsen 25",
                 "II. ZANIECZYSZCZENIA", "1 cyjanki 5", "2. Drugi ustęp.")
        t = md_to_tree(md("##### § 1.", "Tekst.", *annex))
        body = t["annexes"][0]["body"]
        self.assertEqual(paths(body), ["ust_1", "ust_2"])
        self.assertEqual(len(body[0]["children"]), 5)
        # in the main text a roman line is left alone: here it is a row of a table replaced without quotes
        t = md_to_tree(md("##### § 1.", "W załączniku:", "a) część I otrzymuje brzmienie:", "I. Pakiet 1. Uprawy",
                          "1 bobik R UR", "b) część II otrzymuje brzmienie:"))
        self.assertEqual(paths(t["body"]), ["par_1", "par_1/lit_a", "par_1/lit_b"])
        self.assertEqual(t["body"][0]["children"][0]["children"][0]["text"], "I. Pakiet 1. Uprawy")

    def test_quote_not_closed_by_the_source(self):
        # DU/2007/162: "…sądu,”;" closes only the inner of two quotes; the next point of the amending act ends the
        # outer one. Points of a quoted amending article ("2) uchyla się art. 6a;" after "„Art. 6. … 20) …”;",
        # DU/2008/539) stay quoted.
        t = md_to_tree(md("##### Art. 1.", "W ustawie z dnia 1 lutego 2006 r. wprowadza się następujące zmiany:",
                          "1) art. 30 otrzymuje brzmienie:",
                          "„Art. 30. W ustawie z dnia 26 maja 1982 r. wprowadza się następujące zmiany:",
                          "1) w art. 68 ust. 3 otrzymuje brzmienie:", "„3. Do wniosku dołącza się informację.”;",
                          "2) w art. 72 w ust. 1 po pkt 6 dodaje się pkt 6a w brzmieniu:",
                          "„6a) złożenia oświadczenia,”;", "2) art. 31 otrzymuje brzmienie:", "„Art. 31. Tekst.”;",
                          "3) w art. 34:", "a) pkt 1 otrzymuje brzmienie:", "„1) tekst,”,", "b) uchyla się pkt 2."))
        self.assertEqual(paths(t["body"]), ["art_1", "art_1/pkt_1", "art_1/pkt_2", "art_1/pkt_3", "art_1/pkt_3/lit_a",
                                            "art_1/pkt_3/lit_b"])
        t = md_to_tree(md("##### Art. 1.", "W ustawie wprowadza się następujące zmiany:",
                          "1) art. 245 ustawy, który stanowi:", "„Art. 245. W ustawie wprowadza się następujące zmiany:",
                          "1) art. 6 otrzymuje brzmienie:", "„Art. 6. Do zadań należy:", "1) pierwsze;",
                          "2) drugie.”;", "2) uchyla się art. 6a;", "3) w art. 6b ust. 1 otrzymuje brzmienie:",
                          "„1. Tekst.”.”;", "2) art. 21 ustawy, który stanowi:", "„Art. 21. Tekst.”."))
        self.assertEqual(paths(t["body"]), ["art_1", "art_1/pkt_1", "art_1/pkt_2"])

    def test_ocr_paragraphs_are_not_units(self):
        t = md_to_tree(md("##### Art. 1.", "Tekst.", "> [Strona 2 PDF nie ma czytelnej warstwy tekstowej. Tekst poniżej odczytał OCR "
                          "(tesseract 5.5.0, pol+eng). Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]",
                          "> 1. Odczytany ustęp.", "> „Art. 5. cytat", "##### Art. 2.", "Dalej."))
        self.assertEqual(paths(t["body"]), ["art_1", "art_2"])
        self.assertEqual([c["type"] for c in t["body"][0]["children"]], ["note", "ocr", "ocr"])

    def test_text_starting_with_gt_is_not_ocr(self):
        doc = Document(blocks=[Block("p", "§ 1. Okres:", 1), Block("p", "> 90 dni ≤ 180 dni", 1), Block("p", "# 5", 1)])
        md_text = to_markdown(doc)
        self.assertIn("\n\n\\> 90 dni ≤ 180 dni\n\n\\# 5\n", md_text)
        t = md_to_tree(md_text)
        self.assertEqual([(c["type"], c["text"]) for c in t["body"][0]["children"]],
                         [("text", "> 90 dni ≤ 180 dni"), ("text", "# 5")])

    def test_index_with_letters(self):  # DU/2026/468: "Art. 479[30f]." printed, "Art. 479³⁰ᶠ." in Markdown
        t = md_to_tree(md("##### Art. 479³⁰ᶠ.", "§ 1¹ᵃ. Treść.", "1³ᵇ) pkt."))
        self.assertEqual(paths(t["body"]), ["art_479³⁰ᶠ", "art_479³⁰ᶠ/par_1¹ᵃ", "art_479³⁰ᶠ/par_1¹ᵃ/pkt_1³ᵇ"])

    def test_statute_units_and_front_matter(self):
        doc = Document(blocks=[Block("p", "USTAWA", 1), Block("p", "Art. 1. 1. Ustawa określa:", 1),
                               Block("p", "1) zasady;", 1), Block("p", "2) tryb, w tym:", 1),
                               Block("p", "a) terminy:", 1), Block("p", "– pierwszy,", 1), Block("p", "– drugi,", 1),
                               Block("p", "b) opłaty.", 1), Block("p", "2. Przepis ust. 1 stosuje się.", 1),
                               Block("p", "Art. 41¹. Ustawa wchodzi w życie po 14 dniach.", 1),
                               Block("signature", "Prezydent: A. B", 1)])
        meta = {"ELI": "DU/2025/1", "title": "Ustawa z dnia 1 stycznia 2025 r. o próbie", "type": "Ustawa", "pos": 1}
        t = md_to_tree(to_markdown(doc, meta))
        self.assertEqual(t["eli"], "DU/2025/1")
        self.assertEqual(t["title"], "Ustawa z dnia 1 stycznia 2025 r. o próbie")
        self.assertTrue(t["converter"].startswith("eli2md "))
        self.assertEqual(paths(t["body"]), [
            "art_1", "art_1/ust_1", "art_1/ust_1/pkt_1", "art_1/ust_1/pkt_2", "art_1/ust_1/pkt_2/lit_a",
            "art_1/ust_1/pkt_2/lit_a/tir_1", "art_1/ust_1/pkt_2/lit_a/tir_2", "art_1/ust_1/pkt_2/lit_b",
            "art_1/ust_2", "art_41¹"])
        art1 = t["body"][1]
        self.assertEqual((art1["type"], art1["num"], art1["text"]), ("art", "1", ""))
        self.assertEqual(art1["children"][0]["text"], "Ustawa określa:")
        self.assertEqual(t["body"][2]["text"], "Ustawa wchodzi w życie po 14 dniach.")
        self.assertEqual(t["body"][-1], {"type": "signature", "text": "Prezydent: A. B"})
        json.dumps(t)  # serialisable

    def test_amendment_quoted_units_are_text(self):
        t = md_to_tree(md(
            "##### Art. 1.",
            "W ustawie z dnia 1 lutego 2020 r. o czymś wprowadza się następujące zmiany:",
            "1) art. 5 otrzymuje brzmienie:",
            "„Art. 5.",
            "1. Nowa treść ust. 1.",
            "2. Nowa treść ust. 2:",
            "1) pierwszy,",
            "2) drugi.”;",
            "2) w art. 6 ust. 2 otrzymuje brzmienie:",
            "„2. Treść.”.",
            "##### Art. 2.",
            "Ustawa wchodzi w życie z dniem 1 stycznia 2026 r."))
        self.assertEqual(paths(t["body"]), ["art_1", "art_1/pkt_1", "art_1/pkt_2", "art_2"])
        pkt1 = t["body"][0]["children"][0]
        self.assertEqual(pkt1["text"], "art. 5 otrzymuje brzmienie:")
        self.assertEqual([c["type"] for c in pkt1["children"]], ["text"] * 5)
        self.assertTrue(all(c.get("quoted") for c in pkt1["children"]))
        self.assertEqual(pkt1["children"][0]["text"], "„Art. 5.")

    def test_quote_missing_opening_mark(self):
        # DU/2024/859: the source prints no „ before the added ust. 1a, but closes the quote
        t = md_to_tree(md("##### Art. 1.", "W ustawie … wprowadza się następujące zmiany:",
                          "1) po ust. 1 dodaje się ust. 1a i 1b w brzmieniu:",
                          "1a. Pierwszy.", "1b. Drugi.”;", "2) uchyla się ust. 3."))
        self.assertEqual(paths(t["body"]), ["art_1", "art_1/pkt_1", "art_1/pkt_2"])
        # tables replaced in an amendment carry no quotes; the next unit must still be a unit (DU/2024/1141)
        t = md_to_tree(md("##### § 1.", "W rozporządzeniu … wprowadza się następujące zmiany:",
                          "a) lp. 3 otrzymuje brzmienie:", "3 470 694 RADIODYFUZJA cywilne",
                          "b) lp. 4 otrzymuje brzmienie:", "4 694 790 STAŁA cywilne"))
        self.assertEqual(paths(t["body"]), ["par_1", "par_1/lit_a", "par_1/lit_b"])

    def test_announcement_with_consolidated_text_annex(self):
        t = md_to_tree(md(
            "OBWIESZCZENIE", "1. Ogłasza się jednolity tekst rozporządzenia.",
            "2. Tekst jednolity nie obejmuje § 2 rozporządzenia zmieniającego, który stanowi:",
            "„§ 2. Rozporządzenie wchodzi w życie z dniem 1 października 2023 r.”.",
            "*Minister: J. K*",
            "## Załącznik do obwieszczenia Ministra z dnia 9 lutego 2024 r. (Dz. U. poz. 193)",
            "ROZPORZĄDZENIE", "Rozdział 1", "Przepisy ogólne", "##### § 1.", "Rozporządzenie określa:",
            "1) zasady;", "1a)[^2] fundusz;", "1b)¹⁾ zamówień;", "##### § 2.", "[^3] 1. Treść.", "2.Druga treść bez spacji.",
            "[^2]: Dodany przez § 1.", "[^3]: W brzmieniu ustalonym przez § 1."))
        self.assertEqual(paths(t["body"]), ["ust_1", "ust_2"])
        self.assertTrue(t["body"][2]["children"][0]["quoted"])
        a = t["annexes"][0]
        self.assertTrue(a["heading"].startswith("Załącznik do obwieszczenia"))
        self.assertEqual(paths(a["body"]), ["par_1", "par_1/pkt_1", "par_1/pkt_1a", "par_1/pkt_1b", "par_2", "par_2/ust_1", "par_2/ust_2"])
        self.assertEqual(a["body"][1], {"type": "heading", "label": "Rozdział 1", "text": "Przepisy ogólne"})
        par1 = a["body"][2]
        self.assertEqual(par1["text"], "Rozporządzenie określa:")
        self.assertEqual(par1["children"][1]["text"], "[^2] fundusz;")
        self.assertEqual(a["body"][3]["text"], "[^3]")  # the marker printed before ust. 1 belongs to § 2
        self.assertEqual(t["footnotes"], {"2": "Dodany przez § 1.", "3": "W brzmieniu ustalonym przez § 1."})

    def test_footnote_paragraphs(self):
        # indented paragraphs after a footnote belong to it, not to the body (DU/2026/421)
        t = md_to_tree(md("USTAWA[^1]", "##### Art. 1.", "Treść.", "*Prezydent: A. B*",
                          "[^1]: Niniejsza ustawa:", "    1) wdraża dyrektywę;", "    2) służy stosowaniu.",
                          "[^2]: Inny przypis."))
        self.assertEqual(paths(t["body"]), ["art_1"])
        self.assertEqual(t["footnotes"], {"1": "Niniejsza ustawa:\n\n1) wdraża dyrektywę;\n\n2) służy stosowaniu.",
                                          "2": "Inny przypis."})

    def test_split_quoted_article_is_not_a_unit(self):
        # to_markdown splits "Art. 25. „1. …" into "Art. 25." + "„1. …" (not a heading)
        t = md_to_tree(md("##### Art. 1.", "Tekst jednolity nie obejmuje art. 25, który stanowi:",
                          "Art. 25.", "„1. Świadczenie przysługuje:", "1) członkom;", "2) innym.”"))
        self.assertEqual(paths(t["body"]), ["art_1"])
        self.assertTrue(all(c.get("quoted") for c in t["body"][0]["children"]))

    def test_code_style_paragraphs_under_article(self):
        t = md_to_tree(md("##### Art. 14t.", "§ 1. Treść.", "§ 2. Treść:", "1) pkt;", "##### Art. 15.", "Treść."))
        self.assertEqual(paths(t["body"]), ["art_14t", "art_14t/par_1", "art_14t/par_2", "art_14t/par_2/pkt_1", "art_15"])

    def test_form_card_rows_are_text(self):
        # DU/2024/1337: a card of a sea area is a table; rows 1-4 are glued into other paragraphs, so "5." with an
        # upper-case label is the first ust. of the §; it and everything up to the next § stay text
        card = ("## Załącznik nr 2", "##### § 1.", "Ustala się rozstrzygnięcia szczegółowe dla akwenu SWI.1.Ip określone w karcie",
                "akwenu.", "KARTA AKWENU 1. OZNACZENIE LITEROWE", "SWI.1.Ip Ip",
                "2. NUMER 18 3. OPIS 1. 54°10′40,76″ N 19°22′59,11″ E AKWENU POŁOŻENIA", "5. FUNKCJA PODSTAWOWA",
                "FUNKCJONOWANIE PORTU", "6. FUNKCJE DOPUSZCZALNE", "1) badania naukowe (N);", "2) transport (T).",
                "7. ZAKAZY LUB OGRANICZENIA W KORZYSTANIU Z POSZCZEGÓLNYCH OBSZARÓW", "a) nie ustala się.",
                "##### § 2.", "Ustala się rozstrzygnięcia szczegółowe dla akwenu SWI.2.T.", "1. Treść.", "2. Treść:", "1) pkt.")
        t = md_to_tree(md("##### § 1.", "Tekst.", *card))
        body = t["annexes"][0]["body"]
        self.assertEqual(paths(body), ["par_1", "par_2", "par_2/ust_1", "par_2/ust_2", "par_2/ust_2/pkt_1"])
        self.assertEqual(len(body[0]["children"]), 11)
        self.assertEqual(body[0]["children"][4]["text"], "5. FUNKCJA PODSTAWOWA")
        # not a form: a sentence after an acronym, and an ust. whose "1." was printed
        t = md_to_tree(md("##### § 1.", "Tekst.", "## Załącznik", "##### § 3.", "Tekst.", "2. NFZ przekazuje dane.",
                          "##### § 4.", "1. ZASADY OGÓLNE", "2. ZAKRES"))
        self.assertEqual(paths(t["annexes"][0]["body"]), ["par_3", "par_3/ust_2", "par_4", "par_4/ust_1", "par_4/ust_2"])

    def test_coordinate_rows_are_text(self):
        # DU/2024/1594, DU/2025/947: numbered points of a list of coordinates are rows of a table
        t = md_to_tree(md("##### § 17.", "1. Wyznacza się akwen ELB.01.T. Ustala się wykaz współrzędnych:",
                          "6. 54°10′43,83″ N 19°22′52,30″ E", "7. 54°10′43,79″ N 19°22′52,76″ E",
                          "2. Wyznacza się akwen ELB.02.P o współrzędnych:", "1) 52°34'21\"N 019°38'47\"E",
                          "2) 52°36'08\"N 019°39'05\"E", "3. Temperatura:", "a) 30 °C lub więcej:"))
        self.assertEqual(paths(t["body"]), ["par_17", "par_17/ust_1", "par_17/ust_2", "par_17/ust_3", "par_17/ust_3/lit_a"])
        self.assertEqual([c["text"][:2] for c in t["body"][0]["children"][1]["children"]], ["1)", "2)"])

    def test_table_rows_replaced_without_quotes(self):
        # MP/2025/1248: rows "3.", "4.", "8." of a table replaced without quotes are not ust. of § 1, and lit. e)
        # after them is not under them
        t = md_to_tree(md("##### § 1.", "W uchwale wprowadza się następujące zmiany:", "1) w § 4 wyraz „a” zastępuje się wyrazem „b”;",
                          "2) w załączniku do uchwały:", "d) w rozdziale 1:", "– w pkt 1.4:",
                          "– – w tabeli nr 1.3 Koszty realizacji Krajowego planu w latach 2020–2033:",
                          "– – – lp. 3 i 4 otrzymują brzmienie:", "3. Realizacja Krajowego planu 2.500 300 200",
                          "4. Zamknięcie KSOP RÓŻAN 10.000 - - - -", "– – – lp. 8 otrzymuje brzmienie:",
                          "8. Program naukowo-badawczy 10.000 - - - 5.000", "e) w rozdziale 2 wyraz „c” zastępuje się wyrazem „d”.",
                          "##### § 2.", "Uchwała wchodzi w życie z dniem następującym po dniu ogłoszenia."))
        self.assertEqual(paths(t["body"]), [
            "par_1", "par_1/pkt_1", "par_1/pkt_2", "par_1/pkt_2/lit_d", "par_1/pkt_2/lit_d/tir_1",
            "par_1/pkt_2/lit_d/tir_1/tir_1", "par_1/pkt_2/lit_d/tir_1/tir_1/tir_1", "par_1/pkt_2/lit_d/tir_1/tir_1/tir_2",
            "par_1/pkt_2/lit_e", "par_2"])
        # DU/2025/1847: the list of a replaced row is text too; "2)" after its "9)" continues the list of Art. 3
        t = md_to_tree(md("##### Art. 3.", "W ustawie w załączniku do ustawy w części I:", "1) po ust. 9b dodaje się ust. 9ba w brzmieniu:",
                          "9ba. Przyjęcie zgłoszenia dotyczącego budowy: 155 zł", "1) wolno stojących budynków,",
                          "2) kolumbariów", "– od którego organ nie wniósł sprzeciwu", "2) po ust. 9c dodaje się ust. 9ca w brzmieniu:",
                          "9ca. Przyjęcie zgłoszenia dotyczącego przebudowy: 155 zł", "1) wolno stojących budynków",
                          "##### Art. 4.", "Ustawa wchodzi w życie po upływie 14 dni od dnia ogłoszenia."))
        self.assertEqual(paths(t["body"]), ["art_3", "art_3/pkt_1", "art_3/pkt_2", "art_4"])
        self.assertEqual(len(t["body"][0]["children"][0]["children"]), 4)
        # DU/2025/1895 prints "§ 7." without "1.": without an announced new wording "2." stays a unit
        t = md_to_tree(md("##### § 7.", "Rozliczenia są składane w terminach:", "1) do 20. dnia każdego miesiąca;",
                          "2) do dnia 5 lutego – rozliczenie roczne.", "2. Jeżeli termin przypada na sobotę, upływa w poniedziałek."))
        self.assertEqual(paths(t["body"]), ["par_7", "par_7/pkt_1", "par_7/pkt_2", "par_7/ust_2"])

    def test_treaty_articles(self):
        # international agreements: "Artykuł N" in a paragraph of its own (title next, or in the same paragraph)
        t = md_to_tree(md("UMOWA", "Umawiające się Strony uzgodniły, co następuje:", "Artykuł 1", "Definicje",
                          "1. Określenie „inwestycja” oznacza:", "a) mienie ruchome,", "Artykuł 2 Zakres stosowania umowy",
                          "Niniejsza umowa ma zastosowanie do inwestycji.", "Artykuł IV", "Treść."))
        self.assertEqual(paths(t["body"]), ["art_1", "art_1/ust_1", "art_1/ust_1/lit_a", "art_2", "art_IV"])
        self.assertEqual([n["text"] for n in t["body"] if n["type"] == "art"], ["Definicje", "Zakres stosowania umowy", "Treść."])
        # the closing formula and the ratification after it are outside the last article
        t = md_to_tree(md("Artykuł 1", "Treść.", "Artykuł 2", "1. Umowa wchodzi w życie.", "Sporządzono w Warszawie dnia 1 maja 1995 r.",
                          "Po zaznajomieniu się z powyższą umową oświadczam, że:", "– jest przyjęta,"))
        self.assertEqual(paths(t["body"][:2]), ["art_1", "art_2", "art_2/ust_1"])
        self.assertEqual([n["type"] for n in t["body"][2:4]], ["text", "text"])
        # one such paragraph, a reference to an article ("ustęp" in lower case) or a sentence stays text
        for paras in (("Artykuł 1", "Treść."), ("Artykuł 15 ustęp 1", "Zastrzeżenie.", "Artykuł 17 ustęp 2"),
                      ("Artykuł 309 Konstytucji ma następujące brzmienie:", "Artykuł 3 Konstytucji stanowi, że.")):
            self.assertEqual(paths(md_to_tree(md(*paras))["body"]), [])
        # quoted in an amendment: depth > 0
        t = md_to_tree(md("Artykuł 5 otrzymuje brzmienie:", "„Artykuł 5", "Treść.", "Artykuł 6", "Treść”."))
        self.assertEqual(paths(t["body"]), [])


class TreeMeasure(unittest.TestCase):
    """eval/tree_eval.py on a tiny HTML reference: a correct tree scores 1, broken ones do not."""

    HTML = """<html><h1>Ustawa o próbie</h1><section id="part_1">
<div class="unit unit_arti pro-text" id="arti_1">Art. 1. W ustawie wprowadza się zmiany:
<div class="unit unit_pint pro-text" id="arti_1-pint_1">1) art. 5 otrzymuje brzmienie:
<div class="unit unit_arti pro-rplc-text" id="arti_1-pint_1-arti_5">„Art. 5. Treść.”;</div></div>
<div class="unit unit_pint pro-text" id="arti_1-pint_2">2) uchyla się art. 6.</div></div>
<div class="unit unit_arti pro-text" id="arti_41_1">Art. 41<sup>1</sup>. Wchodzi w życie.</div>
</section></html>"""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
        import tree_eval
        self.te = tree_eval

    def score(self, tree: dict) -> tuple[str, str]:
        from collections import Counter
        ref = self.te.html_units(self.HTML)
        hyp = self.te.json_units(tree)
        c = Counter()
        self.te.score_part(ref["main"], hyp["main"], c, "main")
        core = ("art", "par", "ust", "pkt", "lit")
        r = f"{self.te.summed(c, 'main', 'R', core, 'hit')}/{self.te.summed(c, 'main', 'R', core, 'n')}"
        p = f"{self.te.summed(c, 'main', 'P', core, 'hit')}/{self.te.summed(c, 'main', 'P', core, 'n')}"
        return r, p

    def test_scores(self):
        good = md("# Ustawa o próbie", "##### Art. 1.", "W ustawie wprowadza się zmiany:",
                  "1) art. 5 otrzymuje brzmienie:", "„Art. 5. Treść.”;", "2) uchyla się art. 6.",
                  "##### Art. 41¹.", "Wchodzi w życie.")
        self.assertEqual(self.score(md_to_tree(good)), ("4/4", "4/4"))  # quoted Art. 5 is no unit on either side
        # pkt 2 flattened into text of Art. 1 (same words): missed
        t = md_to_tree(good)
        art1 = t["body"][0]
        art1["children"][1] = {"type": "text", "text": "2) uchyla się art. 6."}
        self.assertEqual(self.score(t), ("3/4", "3/3"))
        # pkt 2 with a wrong number in its path: missed and false
        t = md_to_tree(good)
        t["body"][0]["children"][1]["path"] = "art_1/pkt_3"
        self.assertEqual(self.score(t), ("3/4", "3/4"))
        # the quoted Art. 5 taken for a unit of the act: a false Art. 5, and pkt 2 lands under it
        bad = good.replace("\n\n„Art. 5. Treść.”;", "\n\n##### Art. 5.\n\nTreść.")
        self.assertEqual(self.score(md_to_tree(bad)), ("3/4", "3/5"))


if __name__ == "__main__":
    unittest.main()
