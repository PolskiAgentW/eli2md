# Indeksy przy numerach jednostek: `479[30f]` (2026) i `22` + `1a` (2025) → `479³⁰ᶠ`, `22¹ᵃ`

Wątek F, 2026-09-29/30. Baza: eli2md 0.6.2 (= main; venv `eli2md-062`). Nowa wersja: gałąź wątku F.
Oba wyniki konwertowałem tym samym skryptem (`convert` + `to_markdown` + `md_to_tree`, bez OCR). Wyniki bazy dla
DU/2026/468, 1046 i 731 są bajt w bajt równe opublikowanym plikom (sprawdzone `cmp`).

## Mechanizm (sprawdzony)

DU/2026/468 s. 98: słowa `[30f]`, `[30]`, `[30a]`, `[30e]` mają 6,48 pt (tekst 9,96 pt) i leżą w jednym wierszu
(top 132,10). W `_frame_lines` małe słowa grupuje się w wiersze. Wiersz z co najmniej 3 małymi słowami, które
nie są odnośnikami (`FOOTNOTE_MARK`), był brany za linię drobnego druku. Stawał się osobną linią nad linią główną:
`[30f] [30] [30a] [30e] Art. 479 . W postępowaniu…`. Przy 1–2 takich słowach były one doklejane do linii
bez flagi `script`, więc zostawały osobnymi wyrazami (`art. 18 [3a] :`). Cyfry bez nawiasów (`1`) pasują do
`FOOTNOTE_MARK`, więc są `script` i dają `41¹`. Cyfry z literą (`1a`, druk 2025) nie pasują i też zostawały
osobnym wyrazem: `Art. 22 1a .` (DU/2025/277).

Inne przypadki z tych PDF-ów: `[92` + `]` rozbite przez różną wielkość znaków (DU/2026/468 s. 103).
Indeks sklejony z odnośnikiem przypisu: `[1]10)` (DU/2026/913 s. 44). Oba obsłużone i sprawdzone w wyniku:
`##### Art. 479⁹².`, `ust. 1 i 1¹[^10]`.

Kształty małych słów z nawiasem albo cyfrą z literą w 26 plikach (17 DU z objawem, 6 DU z indeksem przeniesionym
na początek, 3 MP): `[N]` 2828, `[Na]` 210, `Na` 4, `]` 4, `[` 3 (MP/2025/352, tekst obrócony, nie indeks),
`[N]N)` 2, `[N` 1.

## Zmiana

- `pdf._index_words`: mały wyraz `[30f]` albo `1a`, który zaczyna się tuż za wyrazem zwykłej wielkości
  zakończonym literą lub cyfrą (odstęp od −1 do 1,5 pt) i leży nad środkiem tego wyrazu, jest indeksem. Nie liczy
  się do wiersza drobnego druku, jest doklejany jak cyfra `script`. Nawiasy są pomijane, cyfry i litery zamieniane
  na znaki górne: `479³⁰ᶠ`. Gdy litera nie ma znaku górnego (q), indeks zostaje w nawiasach: `5[1q]`.
- `SUP_LETTERS`, `SUP_CHARS` (cyfry + litery górne) w wyrażeniach numerów jednostek (`UNIT_START`, `UNIT_HEAD`,
  `QUOTED_UNIT`, `QUOTE_HEAD`, `tree.UNIT_RES`).
- Miary: `tree_eval.norm_num` `22¹ᵃ` → `22_1a` (styl id HTML). `evaluate.tokens`: indeks z literą to jeden token
  (`1a`, jak `<sup>1a</sup>`), same cyfry bez zmian. `selfcheck`: litery górne → litery. Po stronie PDF skleja
  indeks w nawiasach ze słowem przed nim (`479[30f]` → `47930f`, `6b[1]` → `6b1`), tak jak wynik.

Dlaczego znaki górne, a nie nawiasy: zob. README (sekcja „Indeksy przy numerach jednostek”).

## Pomiar 1: artykuły w 17 plikach DU z objawem + 3 pliki MP (lista z audytu wzrokowego)

`eval/indices_check.py`. „PDF Art. lines” to linie `extract_text` zaczynające się od `Art. N.` / `Art. N[x].`.
Liczba jest przybliżona, bo obejmuje też artykuły cytowane w obwieszczeniach i nowelizacjach, jeśli ich linia nie
zaczyna się od „. Te artykuły słusznie nie są nagłówkami. Kolumny 5–7 to objawy 0.6.2.

| act | PDF Art. lines (with [x]) | MD `##### Art.` base → new (with index) | JSON art base → new (with index) | „Art. N [x] .” paragraphs | paragraphs starting with „[x]” | „w [x]” (spaced) |
|---|---|---|---|---|---|---|
| DU/2026/468 | 2016 (846) | 1169 (0) → 2015 (846) | 1169 (0) → 2015 (846) | 823 → 0 | 27 → 0 | 1488 → 0 |
| DU/2026/795 | 1298 (216) | 1080 (0) → 1296 (216) | 1080 (0) → 1296 (216) | 213 → 0 | 3 → 0 | 273 → 0 |
| DU/2026/1245 | 492 (210) | 276 (0) → 486 (210) | 276 (0) → 486 (210) | 202 → 0 | 10 → 0 | 468 → 0 |
| DU/2026/913 | 603 (52) | 550 (0) → 602 (52) | 550 (0) → 602 (52) | 51 → 0 | 1 → 0 | 114 → 0 |
| DU/2026/1066 | 133 (37) | 95 (0) → 132 (37) | 95 (0) → 132 (37) | 37 → 0 | 0 → 0 | 50 → 0 |
| DU/2026/889 | 84 (38) | 44 (0) → 82 (38) | 44 (0) → 82 (38) | 35 → 0 | 8 → 0 | 115 → 0 |
| DU/2026/549 | 54 (11) | 43 (0) → 54 (11) | 43 (0) → 54 (11) | 11 → 0 | 0 → 0 | 50 → 0 |
| DU/2026/1003 | 137 (10) | 127 (0) → 127 (0) | 127 (0) → 127 (0) | 10 → 0 | 1 → 0 | 12 → 0 |
| DU/2026/884 | 177 (9) | 166 (0) → 175 (9) | 166 (0) → 175 (9) | 9 → 0 | 0 → 0 | 45 → 0 |
| DU/2026/1046 | 8 (2) | 6 (0) → 6 (0) | 6 (0) → 6 (0) | 2 → 0 | 1 → 0 | 24 → 0 |
| DU/2026/524 | 235 (2) | 233 (0) → 235 (2) | 233 (0) → 235 (2) | 2 → 0 | 0 → 0 | 2 → 0 |
| DU/2026/1231 | 82 (1) | 81 (0) → 82 (1) | 81 (0) → 82 (1) | 1 → 0 | 0 → 0 | 1 → 0 |
| DU/2026/437 | 31 (1) | 29 (0) → 30 (1) | 29 (0) → 30 (1) | 1 → 0 | 0 → 0 | 6 → 0 |
| DU/2026/529 | 176 (1) | 175 (0) → 176 (1) | 175 (0) → 176 (1) | 1 → 0 | 0 → 0 | 3 → 0 |
| DU/2026/538 | 157 (1) | 144 (0) → 145 (1) | 144 (0) → 145 (1) | 1 → 0 | 0 → 0 | 4 → 0 |
| DU/2026/599 | 113 (1) | 111 (0) → 112 (1) | 111 (0) → 112 (1) | 1 → 0 | 0 → 0 | 3 → 0 |
| DU/2026/731 | 10 (1) | 8 (0) → 8 (0) | 8 (0) → 8 (0) | 1 → 0 | 0 → 0 | 24 → 0 |
| MP/2025/352 | 0 (0) | 0 (0) → 0 (0) | 0 (0) → 0 (0) | 0 → 0 | 0 → 0 | 3 → 3 |
| MP/2026/600 | 0 (0) | 0 (0) → 0 (0) | 0 (0) → 0 (0) | 0 → 0 | 0 → 0 | 1 → 0 |
| MP/2026/897 | 0 (0) | 0 (0) → 0 (0) | 0 (0) → 0 (0) | 0 → 0 | 0 → 0 | 1 → 0 |
| **sum** | 5806 (1439) | 4337 (0) → 5763 (1426) | 4337 (0) → 5763 (1426) | 1401 → 0 | 51 → 0 | 2687 → 3 |

- Nagłówków `##### Art.` jest o 1426 więcej, wszystkie z indeksem. JSON ma tyle samo węzłów `art` co MD nagłówków.
- Artykułów z indeksem w liniach PDF jest 1439, w MD 1426. Różnica 13 to artykuły cytowane w nowelizacjach:
  DU/2026/1003 (10: `„Art. 479⁸⁸ᵃ.` itd. w zmianie k.p.c.), DU/2026/1046 (2), DU/2026/731 (1). Mają poprawny
  zapis `Art. 479⁸⁸ᵃ.` i nie są nagłówkami, tak jak każdy cytowany artykuł.
- DU/2026/1245: porównałem numery z linii PDF z numerami nagłówków MD. W MD brakuje tylko 6 artykułów ustawy
  zmieniającej, cytowanych w obwieszczeniu (poprawnie nie są nagłówkami). W MD nie ma nagłówków spoza PDF.
- Pozostałe 3 „w [x]” to odnośniki `[1]` zwykłej wielkości w MP/2025/352 („odniesienie normatywne [1]”). Nie są
  indeksami i nie powinny się zmienić.
- DU/2026/1046 (przykład z audytu): akapit `[3e] [3f] [3g] 3) po art. 18 dodaje się art. 18 i art. 18 w brzmieniu:`
  → `3) po art. 18³ᵉ dodaje się art. 18³ᶠ i art. 18³ᵍ w brzmieniu:`. W JSON pojawił się `art_1/pkt_3`
  (w 0.6.2 go nie było).
- W nowym MD tych 17 plików DU nie ma już żadnego `[liczba]` ani `[liczba+litery]`.

## Pomiar 2: druk 2025 (`22` + małe `1a`, bez nawiasów)

Pliki z objawem `Art. N 1a .` w opublikowanym zbiorze 0.6.2 (regex na całym zbiorze DU/MP 2025–2026): DU/2025/277
(k.p.), 764, 614, 1431, DU/2026/473, 236. W MP ich nie ma.

| act | MD `##### Art.` base → new (with index) | JSON art base → new (with index) | akapity `„?Art. N 1a .` base → new |
|---|---|---|---|
| DU/2025/277 | 486 (205) → 515 (234) | 486 (205) → 515 (234) | 26 → 0 |
| DU/2025/764 | 511 (87) → 523 (99) | 512 (88) → 524 (100) | 11 → 0 |
| DU/2025/614 | 597 (47) → 602 (52) | 597 (47) → 602 (52) | 4 → 0 |
| DU/2025/1431 | 501 (8) → 502 (9) | 501 (8) → 502 (9) | 1 → 0 |
| DU/2026/473 | 20 (0) → 20 (0) | 20 (0) → 20 (0) | 10 → 0 (cytowane w nowelizacji) |
| DU/2026/236 | 245 (61) → 247 (63) | 245 (61) → 247 (63) | 2 → 0 |
| **sum** | 2360 (408) → 2409 (457) | 2361 (409) → 2410 (458) | 54 → 0 |

Tu `extract_text` skleja `22` i `1a` w `221a`, więc liczenie linii PDF nie odróżnia indeksu i go nie podaję.
Efekt uboczny w DU/2025/614: wiersz małych słów `1a 2 1 1` szedł w 0.6.2 jako linia drobnego druku do tekstu
(`prze- 1a 2 1 1 pisy … art. 130 , art. 130 ,`). Teraz: `przepisy … art. 130¹ᵃ, art. 130², art. 139¹, art. 205¹`.

## Pomiar 3: selfcheck (kept / grounded)

W starej mierze `479[30f]` z PDF to dwa tokeny (`479`, `30f`), tak jak błędny wynik 0.6.2 `479 [30f]`. Poprawny
wynik `479³⁰ᶠ` to jeden token (`47930f`), więc stara miara karze poprawkę. Nowa miara skleja indeks w nawiasach
ze słowem przed nim po stronie PDF (`selfcheck.PDF_INDEX`). Pierwsza wersja wymagała cyfry przed nawiasem
i dawała fałszywy spadek w DU/2026/884 (`Art. 6b[1].`), więc teraz wystarcza litera albo cyfra. Tabela podaje
obie miary. Porównywać należy base i new w tej samej kolumnie.

17 plików DU + 3 MP:

| act | kept, stara: base → new | kept, nowa: base → new | grounded, stara: base → new | grounded, nowa: base → new |
|---|---|---|---|---|
| DU/2026/468 | 0.9732 → 0.9538 | 0.9646 → 0.9728 | 0.9871 → 0.9778 | 0.9683 → 0.9870 |
| DU/2026/795 | 0.9766 → 0.9681 | 0.9728 → 0.9765 | 0.9885 → 0.9843 | 0.9803 → 0.9884 |
| DU/2026/1245 | 0.9737 → 0.9561 | 0.9657 → 0.9734 | 0.9876 → 0.9796 | 0.9698 → 0.9876 |
| DU/2026/913 | 0.9738 → 0.9696 | 0.9721 → 0.9737 | 0.9870 → 0.9848 | 0.9832 → 0.9869 |
| DU/2026/1066 | 0.9760 → 0.9655 | 0.9722 → 0.9759 | 0.9884 → 0.9830 | 0.9793 → 0.9883 |
| DU/2026/889 | 0.9732 → 0.9550 | 0.9666 → 0.9725 | 0.9879 → 0.9800 | 0.9712 → 0.9877 |
| DU/2026/549 | 0.9783 → 0.9656 | 0.9731 → 0.9779 | 0.9900 → 0.9836 | 0.9785 → 0.9898 |
| DU/2026/1003 | 0.9793 → 0.9775 | 0.9784 → 0.9792 | 0.9897 → 0.9888 | 0.9879 → 0.9897 |
| DU/2026/884 | 0.9717 → 0.9692 | 0.9707 → 0.9717 | 0.9864 → 0.9852 | 0.9841 → 0.9864 |
| DU/2026/1046 | 0.9690 → 0.9391 | 0.9533 → 0.9685 | 0.9842 → 0.9686 | 0.9539 → 0.9840 |
| DU/2026/524 | 0.9768 → 0.9768 | 0.9769 → 0.9768 | 0.9904 → 0.9904 | 0.9904 → 0.9904 |
| DU/2026/1231 | 0.9769 → 0.9768 | 0.9770 → 0.9769 | 0.9893 → 0.9893 | 0.9893 → 0.9893 |
| DU/2026/437 | 0.9781 → 0.9738 | 0.9772 → 0.9780 | 0.9901 → 0.9881 | 0.9869 → 0.9901 |
| DU/2026/529 | 0.9738 → 0.9737 | 0.9738 → 0.9738 | 0.9873 → 0.9872 | 0.9872 → 0.9873 |
| DU/2026/538 | 0.9749 → 0.9747 | 0.9750 → 0.9749 | 0.9891 → 0.9889 | 0.9890 → 0.9891 |
| DU/2026/599 | 0.9749 → 0.9747 | 0.9749 → 0.9749 | 0.9882 → 0.9881 | 0.9881 → 0.9882 |
| DU/2026/731 | 0.9720 → 0.9552 | 0.9640 → 0.9718 | 0.9862 → 0.9775 | 0.9698 → 0.9860 |
| MP/2025/352 | 0.9708 → 0.9708 | 0.9708 → 0.9708 | 0.9851 → 0.9851 | 0.9851 → 0.9851 |
| MP/2026/600 | 0.9867 → 0.9845 | 0.9856 → 0.9867 | 0.9933 → 0.9922 | 0.9911 → 0.9933 |
| MP/2026/897 | 0.9789 → 0.9684 | 0.9735 → 0.9788 | 0.9894 → 0.9840 | 0.9787 → 0.9893 |
| **średnia (20)** | 0.9754 → 0.9674 | 0.9719 → 0.9753 | 0.9883 → 0.9843 | 0.9806 → 0.9882 |

W nowej mierze kept spada o 0,0001 w 3 plikach (DU/2026/524, 1231, 538), grounded nie spada w żadnym.
Sprawdziłem różnice tokenów. W 0.6.2 rozbity numer `Art. 5 [1] .` daje tokeny `5` i `1`, które pasują do
niezwiązanych pojedynczych cyfr PDF (np. numerów przypisów, które wynik zamienia na `[^n]`). `5¹` to jeden token
`51`, zgodny z PDF. To artefakt miary, nie utrata tekstu. W nowej mierze wynik nowej wersji jest nieco niższy niż
wynik 0.6.2 w starej mierze (np. 468: 0.9728 wobec 0.9732). Powód: sklejenie dwóch dopasowanych tokenów w jeden
zmniejsza licznik i mianownik o tyle samo, a to obniża iloraz.

Druk 2025 (6 plików z pomiaru 2): kept 0.9766 → 0.9774, grounded 0.9874 → 0.9890 (nowa miara). W starej mierze
kept 0.9766 → 0.9766, grounded 0.9874 → 0.9883. W żadnym pliku nie spada.

## Pomiar 4: 150 losowych aktów DU 2025–2026

Próba: `random.Random(6150).sample` z 3168 aktów DU 2025–2026 o statusie ok w indeksie zbioru i z PDF w cache
(posortowanych po roku i pozycji). Lista: `eval/sample_du_2025_2026_n150_s6150.txt`.

Zmienia się 12 ze 150 plików (MD i JSON): DU/2026/731, 809, 367, 1260, 889, 1168, 1003, 950, 927, 595,
DU/2025/277, 480. Pięć losowych zmian (seed 6150) obejrzałem:

- DU/2026/809: `art. 55 [1] Kodeksu cywilnego` → `art. 55¹`; `art. 21 [11] ,` → `art. 21¹¹,`;
  `1a [1] . (uchylony)` → `1a¹. (uchylony)`. Poprawne.
- DU/2025/480 (formularz): w nagłówku tabeli `gminy 4a` → `gminy⁴ᵃ`. To odnośnik do objaśnienia `4a` pod
  formularzem. Pozostałe odnośniki tego formularza już w 0.6.2 były cyframi górnymi (`¹`, `²`, `⁵`), więc teraz
  zapis jest spójny. Objaśnienie `4a Do dnia…` bez zmian.
- DU/2026/1003: `art. 77 [5] § 2` → `art. 77⁵ § 2`; cytowane `Art. 479 [88a] .` → `Art. 479⁸⁸ᵃ.` (w cytacie, nie
  nagłówek). Poprawne.
- DU/2026/1260: `1 [1] . Przedsiębiorstwo…` → `1¹. Przedsiębiorstwo…` (ust. 1¹); `ust. 1 [1] :` → `ust. 1¹:`. Poprawne.
- DU/2026/950: `art. 77 [5] §` → `art. 77⁵ §`. Poprawne.

Pozostałe zmiany też obejrzałem: 367, 1168, 927, 595. Wszystkie to indeksy. W DU/2026/367 znika też
śmieć `2 2 7 8 11 11a` z końca przypisu 20. W 0.6.2 wiersz indeksów trafiał tam jako linia drobnego druku.

Selfcheck 12 zmienionych plików (pozostałe 138 są identyczne): kept 0.9619 → 0.9635, grounded 0.9834 → 0.9872
(nowa miara; stara: kept 0.9633 → 0.9598, grounded 0.9867 → 0.9853). W nowej mierze żaden plik nie spada.

## Pomiar 5: próby deweloperskie 2024 (s2024, s7)

Na obu próbach tylko DU/2024/1491 ma indeksy, same cyfry bez nawiasów (id HTML `arti_41_1`…). Liter w indeksach
w tych próbach nie ma.
