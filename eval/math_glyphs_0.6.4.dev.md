# Wzory Worda (Cambria Math): podwojone litery i miara selfchecku (0.6.4.dev)

Od 0.6.3 wzory zapisane fontem Cambria Math są w wyniku widoczne (poprawka testu tuszu). W części PDF-ów
litery tych wzorów wychodzą podwojone: „kk”, „LL”, „AA pp”, „UU⁰”, „ηη ii” (DU/2026/1236 s. 10). Przyczyna
jest w PDF-ie: mapa ToUnicode przypisuje jednemu glifowi dwa jednakowe znaki (`𝑘𝑘`, font `GOZOOC+CambriaMath`).
Poppler (`pdftotext`) czyta to tak samo, to nie błąd pdfminera. W treści PDF-u jest też `/ActualText` z tym samym
podwojeniem (`FEFF D835DC58 D835DC58`, DU/2026/40), więc to cecha eksportu z Worda.

## 1. Przegląd: DU i MP 2025–2026

Skrypt `eval/math_glyphs_survey.py` dekoduje strumienie treści pdfminerem bez budowania układu (tekst znaku to
`font.to_unichr(cid)`, jak w pdfplumberze) i zapisuje każdy znak, którego tekst ma 2+ znaki, z fontem i stroną.
Wszystkie akty z obu `index.csv` z lat 2025–2026: 5440 aktów (3168 DU, 2272 MP), 63 957 stron,
174 716 074 znaki. Bez zawężania do PDF-ów z fontem „Math”, 0 błędów, 4 procesy, ok. 39 min.

**Znak = ten sam znak dwa razy** (17 055 znaków w 25 aktach):

| font | klasa | znaków | aktów | przykłady |
|------|-------|-------:|------:|-----------|
| CambriaMath | alfanumeryczne matematyczne U+1D400–U+1D7FF (też greka matematyczna `𝜂`, `𝜆`) | 16 991 | 19 (wszystkie DU) | `𝑠𝑠 𝑍𝑍 𝑜𝑜 𝑛𝑛 𝑎𝑎 𝑧𝑧 𝑖𝑖 𝑃𝑃 𝑑𝑑` |
| SegoeUISymbol | symbol (So) | 46 | 1 (MP/2025/781) | `🖸🖸` |
| Calibri | łacina | 14 | 1 (MP/2026/168) | `tt` (ligatura) |
| PalatinoLinotype-Roman | łacina | 2 | 2 (MP/2025/1013, MP/2026/943) | `tt` (ligatura) |
| Aptos Display,Italic / Lato | łacina | 1 + 1 | 2 (MP/2026/413, MP/2025/1197) | `ff` (ligatura) |

Zwykła greka (U+0370–U+03FF) podwojona: 0. Cyfry, operatory i litery łacińskie w fontach „Math” podwojone: 0
(np. `ż` we wzorze DU/2025/452 jest pojedyncze). Fonty z „Math” w nazwie ma 118 aktów (115 DU, 3 MP), zawsze
CambriaMath (156 podzbiorów fontu). 98 z nich nie ma ani jednego podwojonego znaku, więc nie każdy eksport
Cambria Math ma tę wadę.

19 aktów z podwojeniem (DU, znaków / stron): 2025/454 3641/6, 2025/459 3639/5, 2025/1743 3709/7,
2025/1744 3707/7, 2026/40 568/5, 2025/1548 458/16, 2025/452 392/7, 2026/1236 307/24, 2025/978 192/4,
2025/928 139/3, 2025/597 136/4, 2026/1012 36/3, 2025/932 22/3, 2025/441 15/1, 2026/748 12/1, 2025/919 8/1,
2026/710 6/1, 2025/1555 2/1, 2026/447 2/1.

**Inne teksty wieloznakowe** (poprawne, zostają): 2318 znaków w 78 aktach, 15 różnych. Ligatury: `fi` 1472
(72 akty; Lato, Aptos), `ti` 47, `fl` 17, `tf` 5, `fk` 4, `ffb` 1 (Calibri, Lato). Litera + znak łączący
(rozłożone polskie litery): `ś` = s + U+0301 290 znaków w 3 aktach, `ę` 182, `ż` 149, `ą` 118, `ć` 17, `ń` 9,
`ź` 3, `Ś` 2, `Ą` 2 (PalatinoLinotype-Roman, TimesNewRomanPSMT).

## 2. Poprawka w konwerterze

`eli2md/pdf.py`: `_doubled(c)` i `_single_glyphs(page)`, wywołane w `_page_lines` przed resztą (znak wodny,
test tuszu, ramki). Znak, którego tekst to ten sam znak dwa razy, dostaje jeden znak, jeśli to znak
alfanumeryczny matematyczny (U+1D400–U+1D7FF) i font ma w nazwie „Math”. Zawężenie z przeglądu: tylko taka
klasa jest podwojona w fontach „Math”, a podwojenia w fontach tekstowych to ligatury (`ff`, `tt`), które muszą
zostać. Greki nie dodawałem, bo zwykła greka nie jest nigdzie podwojona. `🖸🖸` (Segoe UI Symbol) zostaje bez
zmian (patrz niżej). Testy: `test_doubled_math_glyphs` w `tests/test_basic.py`.

DU/2026/1236 s. 10, 0.6.3 → teraz: `0,302∙kk¹ ∙kk² ∙AA pp ∙(UU⁰ −¹ dd )` → `0,302∙k¹ ∙k² ∙A p ∙(U⁰ −¹ d )`,
`ηη ii` → `η i`, `∆QQ⁰` → `∆Q⁰`. Wzór dalej jest spłaszczonym tekstem (ułamki, indeksy dolne liter).

## 3. Miara selfchecku

`eval/selfcheck.py`: znaki alfanumeryczne matematyczne są zwykłymi literami po obu stronach (NFKC, jak
`_plain_math` w konwerterze), a po stronie PDF podwojony glif liczy się raz (ta sama reguła co `_doubled`,
skopiowana, żeby kontrola działała na wyniku każdej wersji). Miara porównuje więc to, co widać. W starej mierze
`𝑘𝑘` z PDF nie pasował do niczego w wyniku, a „kk” z 0.6.3 do niczego w PDF. Wyniki dla aktów ze wzorami
Cambria Math nie są porównywalne z wcześniejszymi plikami `selfcheck_*`.

**Przed i po** (wyniki: `eval/math_glyphs_0.6.4.dev.json`). 32 akty: 19 z podwojonymi glifami z przeglądu i 27
aktów, w których grounded spadł przy 0.6.2 → 0.6.3 (14 wspólnych). 0.6.3 to opublikowane dane, „nowy” to ten
kod (konwersja do /tmp, OCR tak jak w danych: `auto` dla aktów z niepustym `ocr_pages`). Obie wersje oceniam tą
samą, nową miarą.

| akt | podwojonych glifów w PDF | kept 0.6.3 → nowy | grounded 0.6.3 → nowy |
|-----|---:|---|---|
| DU/2025/1743 | 3709 | 0.9319 → 0.9967 | 0.9348 → 0.9998 |
| DU/2025/1744 | 3707 | 0.9266 → 0.9909 | 0.9346 → 0.9994 |
| DU/2025/459 | 3639 | 0.9359 → 0.9899 | 0.9432 → 0.9977 |
| DU/2026/40 | 568 | 0.4747 → 0.5041 | 0.8553 → 0.9084 |
| DU/2025/454 | 3641 | 0.9337 → 0.9856 | 0.9445 → 0.9970 |
| DU/2025/452 | 392 | 0.9150 → 0.9305 | 0.9368 → 0.9527 |
| DU/2025/978 | 192 | 0.9335 → 0.9493 | 0.9386 → 0.9544 |
| DU/2026/1236 | 307 | 0.9313 → 0.9437 | 0.9629 → 0.9758 |
| DU/2025/928 | 139 | 0.9367 → 0.9448 | 0.9430 → 0.9512 |
| DU/2025/1548 | 458 | 0.9559 → 0.9607 | 0.9714 → 0.9763 |
| DU/2025/932 | 22 | 0.8016 → 0.8042 | 0.9773 → 0.9804 |
| DU/2025/597 | 136 | 0.9433 → 0.9442 | 0.9864 → 0.9874 |
| DU/2025/441 | 15 | 0.9500 → 0.9507 | 0.9845 → 0.9852 |
| DU/2026/748 | 12 | 0.9509 → 0.9514 | 0.9867 → 0.9872 |
| DU/2026/1012 | 36 | 0.9927 → 0.9932 | 0.9986 → 0.9992 |
| DU/2025/1555 | 2 | 0.9746 → 0.9748 | 0.9948 → 0.9950 |
| DU/2025/919 | 8 | 0.9392 → 0.9393 | 0.9865 → 0.9866 |
| DU/2026/447 | 2 | 0.9730 → 0.9731 | 0.9813 → 0.9814 |
| DU/2026/710 | 6 | 0.9738 → 0.9739 | 0.9986 → 0.9987 |

Tekst zmienił się w 19 aktach, w każdym lepszy kept i grounded. Średnia ważona tokenami: kept
0.9388 → 0.9512, grounded 0.9746 → 0.9875.
W pozostałych 13 aktach (spadek grounded w 0.6.3 miał tam inną przyczynę) wynik jest identyczny:
DU/2025/822, DU/2026/1013, DU/2026/1231, DU/2026/1242, DU/2026/393, DU/2026/490, DU/2026/511, DU/2026/520, DU/2026/522, DU/2026/524, DU/2026/526, DU/2026/639, DU/2026/848.

W 17 z 19 aktów zmiana to wyłącznie usunięte litery: każda zmieniona linia nowego wyniku jest podciągiem starej
(380 linii). Usuniętych znaków jest tyle, ile podwojonych glifów w PDF (np. DU/2025/454: 3641, DU/2025/1548: 458),
albo mniej, gdy część wzorów jest ukryta (DU/2026/40: 422 z 568, DU/2025/932: 13 z 22). W DU/2025/1743
i DU/2025/459 wynik ma też po 4 linie więcej. Statystyki strony liczone od długości tekstu liczą teraz każdy glif
raz: rozmiar pisma ważony liczbą znaków i prawa krawędź z linii mających co najmniej 40 znaków. W DU/2025/1743 s. 5
prawa krawędź to teraz 488 pt zamiast 392, a s. 4 ma 41 linii zamiast 47. Etykiety tabeli („Rentowność aktywów”,
„Rentowność kapitału własnego”) są przez to osobnymi akapitami. Słowa się nie zmieniają (kept i grounded w górę).

Uwaga: w DU/2025/454, 459, 1743 i 1744 (tabele wskaźników finansowych) mapa ToUnicode Cambria Math jest poza
podwojeniem błędna. Wiele glifów ma tę samą literę: „𝑃𝑃𝑃𝑃𝑃𝑃𝑃𝑃𝑃𝑃ℎ𝑜𝑜𝑜𝑜𝑜𝑜” (poppler czyta to tak samo), w wyniku
„PszZcℎadZ aossa zo ZoszodsżZ” zamiast „Przychody netto ze sprzedaży”. Wysoki kept (0.99) mierzy tylko zgodność
z warstwą tekstową, a ta jest tu nieczytelna.

## 4. Próby deweloperskie

DEV_EVALS

## 5. DU/2026/40 (kept 0.47)

To nie jest strona obrócona: wszystkie 6 stron ma znaki pod kątem 0°. Na s. 2–6 pod tekstem Dziennika Ustaw
(10 pt, `LUACCH+TimesNewRomanPSMT`) leży wklejony PDF z Worda (12 pt, `PDXQGZ+Times`, `PDXQGZ+CambriaMath`).
Z wklejonej strony widać tylko wzory. Reszta jej tekstu jest niewidoczna (obejrzałem render s. 3). Czy zakrywa
ją ścieżka przycinania, czy biały prostokąt, nie sprawdzałem.

Dwie przyczyny, dla których ukryta kopia trafia do wyniku i miesza się z widocznym tekstem
(„b tudentów w ii ii ne , w 1,0 dług SSSS LL …”):

1. **Zgubiony znacznik `PlacedPDF`.** pdfplumber (`PDFPageAggregatorWithMarkedContent`) nie ma stosu znaczników:
   `end_tag` ustawia `tag = None`. Wklejony PDF ma w środku zagnieżdżone `/Span <</ActualText …>> BDC … EMC`
   (wzory), więc po pierwszym wewnętrznym `EMC` reszta jego znaków ma `tag` None albo `Span`. `_drop_hidden_placed`
   uznaje je za tekst Dziennika i w ogóle ich nie testuje. Znaki wklejonego PDF (liczone ze stosem) / z tych bez
   znacznika: s. 2 5439/4009, s. 3 5225/449, s. 4 5456/1952, s. 5 4183/1450, s. 6 1872/0.
2. **Test tuszu oszukany przez cudzy tusz.** Ze znaków ze znacznikiem test zostawia: s. 2 189, s. 3 1572,
   s. 4 254, s. 5 177, s. 6 215 (w tym widoczne wzory, 341 znaków CambriaMath). Ramka ukrytej litery 12 pt
   nachodzi na tusz linii 10 pt Dziennika albo wzoru. Reguła „pod tekstem Dziennika” patrzy na środek znaku w
   ramce słowa ± 3 pt, więc nie łapie znaków między liniami i poza słowami.

**Miara.** Strona PDF zawiera całą ukrytą kopię: 6864 tokeny wobec 2192 w samym tekście Dziennika (znaki spoza
`PlacedPDF`, liczone ze stosem). Tekst Dziennika jest w wyniku prawie cały (kept względem niego 0.992). 1634 tokeny
wyniku nie występują w tekście Dziennika: to widoczne wzory i przeciek ukrytej kopii. Kept 0.47 wynika więc głównie
z miary (liczy niewidoczną kopię). Realną wadą wyniku są wymieszane akapity przy wzorach.

**Bez poprawki.** Przyczyna 1 jest jasna, ale poprawka nie jest wąska. Wymaga stosu znaczników w agregatorze
pdfplumbera (podklasa albo łatka). To zmienia, które znaki idą do testu tuszu, w każdym akcie z wklejonym PDF-em
z zagnieżdżonym znakowaniem. Przyczyny 2 i tak nie usuwa (s. 3: 1572 znaki). Potrzebny osobny pomiar na
wszystkich aktach z `PlacedPDF` i na próbach deweloperskich.

## Otwarte sprawy

- DU/2026/40 i podobne: zgubiony `PlacedPDF` po zagnieżdżonym `EMC` (pdfplumber 0.11.10) i test tuszu przy
  nakładających się warstwach (wyżej). Nie wiem, ile aktów ma zagnieżdżone znakowanie we wklejonych PDF-ach,
  nie liczyłem.
- `🖸🖸` w MP/2025/781 (Segoe UI Symbol, 46 znaków, w wyniku 37 razy „🖸🖸”): wygląda na to samo podwojenie przy
  symbolu wypunktowania. Zostawione, bo to jeden akt i inna klasa znaków.
- Rozłożone polskie litery (`s` + U+0301) w 4 aktach zostają rozłożone. Wynik nie jest w NFC. Nie sprawdzałem, czy
  to przeszkadza w wyszukiwaniu.
- DU/2025/452 s. 7 i podobne: niewidoczna kopia wzoru pod widocznym (znane ograniczenie z 0.6.3). Poprawka tylko
  skraca podwojone litery („jjjjżjjeeee” → „jjżjee”), kopii nie usuwa.
