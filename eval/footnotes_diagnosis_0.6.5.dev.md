# Dlaczego wyniki przypisów są niskie (0.6.4 → 0.6.5.dev)

Pytanie: jaka część luki R/P przypisów (s5110: R 0.783, P 0.756; s5109: R 0.900, P 0.925) to realny błąd
konwertera widoczny w PDF, a jaka to właściwość referencji HTML albo miary.

## Metoda

`eval/footnotes_diag.py SAMPLE --out F.json` robi to samo wyrównanie co `evaluate.py` (tokeny przypisów
HTML `.gloss-section` vs `doc.footnotes`) i dla każdego aktu liczy:
- `label_miss`: pojedynczy numer przypisu po stronie HTML („1)”), bez odpowiednika u nas — `tokens()` usuwa
  nasze znaczniki `[^1]`, więc numer przypisu nigdy się nie zgadza;
- pozostałe braki (R) i ile z nich jest w naszej treści głównej/załącznikach (difflib);
- nadmiar (P) i ile z niego jest w HTML poza przypisami (treść + wszystkie załączniki, także tylko-link).
Duże przypadki sprawdziłem w PDF (pdfplumber: prostokąty/linie reguły, rozmiary czcionek) i na PNG
strony (Read). Dane: 0.6.4, próbki s5110, s5109 (skonsumowane, tylko diagnoza) i dev s2024, s7.
Liczby dla s5109 z 0.6.4 są takie same jak w wynikach 0.6.3.dev (R 0.9001, P 0.9251).

## Odpowiedź w skrócie

- **Recall: luka to głównie realny błąd konwertera.** Na s5110 2597 z 2818 brakujących tokenów (92%)
  to przypisy, które konwerter wstawił do tekstu załącznika albo treści głównej, bo nie rozpoznał kreski
  przypisów (3 akty). Reszta (221, 8%) to numery przypisów (artefakt miary). Na s5109: 512 z 708 (72%)
  to ten sam błąd (DU/2024/1018, 1659: kreska narysowana linią), 196 (28%) numery.
- **Precision: na s5110 cała luka to artefakt referencji.** 3217 z 3269 nadmiarowych tokenów HTML ma
  w tekście załącznika (przypisy pod tabelami załączników, DU/2024/781: 3054), 52 to przypis formularza
  w załączniku, który HTML daje tylko jako link. Na s5109 i próbkach dev jest inaczej: większość nadmiaru
  nie występuje w HTML poza przypisami (s5109: 485 z 517, s2024: 619 z 1071, s7: 1485 z 2150). W
  przejrzanych aktach to mieszanka: realne błędy (stopki „Strona N z 13” w DU/2024/1659: 373 tokeny;
  tabele/pola formularzy drobnym drukiem na dole strony), objaśnienia pod wzorami, przypisy tekstu
  jednolitego nieznalezione w HTML i przypisy, których HTML nie ma (te trzy ostatnie niesprawdzone w PDF).
- Twierdzenie z README („niska precyzja przypisów to w dużej mierze właściwość referencji”) jest
  prawdziwe dla s5110, ale **nie dla recall** i tylko częściowo dla dev/s5109.
- Naprawiłem błąd kreski przypisów (pdf.py, 1 test). s5110 (diagnostycznie, próbka skonsumowana): przypisy
  R 0.7826 → 0.9820, P 0.7563 → 0.7957, treść P 0.9959 → 0.9995, załączniki P 0.9796 → 0.9881.
  Łagodna miara `notes*` na s5110 po poprawce: R 0.9998, P 0.9969.

## Tabela przyczyn (0.6.4)

Tokeny; R = brak tokenu przypisu HTML w naszych przypisach, P = nasz token przypisu nieobecny
w przypisach HTML.

### s5110 (n=32 aktów z przypisami w HTML; ref 12963, hyp 13414, dopasowane 10145)

| przyczyna | R (brak) | P (nadmiar) | akty | sprawdzone w PDF |
|---|---:|---:|---|---|
| (c) przypisy w tekście załącznika/treści: kreska przypisów nierozpoznana (wysoko na stronie z samymi przypisami) | 1917 | 0 | DU/2024/1505 (1123, s. 4: kreska na 14% wysokości), DU/2024/1539 (794, s. 2: 25%) | tak (PNG s. 4 i s. 2) |
| (c) j.w., kreska narysowana jako `line`, nie `rect`; przypisy jako akapit „[^1] Minister Zdrowia…” w treści głównej (treść P 0.772) | 680 | 0 | DU/2024/1346 (s. 1) | tak (pdfplumber) |
| (e) numer przypisu („1)” w HTML, `[^1]` usuwany z naszych) | 221 | 0 | wszystkie 32 | — (miara) |
| (a) przypisy załącznika pod kreską w PDF, w HTML jako tekst załącznika | 0 | 3217 | DU/2024/781 (3054), DU/2024/1505 (162), DU/2024/526 (1) | 781 tak (PNG s. 10: 9 przypisów pod kreską pod tabelą); 1505 nie |
| (a') przypis formularza w załączniku, który HTML daje tylko jako link do PDF | 0 | 52 | DU/2024/1581 | tak (pdfplumber: przypisy 1)–3) pod kreską na s. 2–3 wzoru; HTML: 2 załączniki, oba link-only) |
| razem | 2818 | 3269 | | |

Realny błąd konwertera: R 2597/2818 (92% luki R), P 0/3269. Łącznie 2597 z 6087 niedopasowanych
tokenów (43%).

### s5109 (n=27; ref 7089, hyp 6898, dopasowane 6381)

| przyczyna | R | P | akty |
|---|---:|---:|---|
| (c) kreska jako `line`, przypisy w treści (0 przypisów na wyjściu) | 430 | 0 | DU/2024/1018 |
| (c) j.w. (kreska s. 2 to `line`): prawdziwy przypis („Niniejsze rozporządzenie było poprzedzone…”) w treści | 82 | 0 | DU/2024/1659 |
| (f) stopki stron formularzy „Strona 2 z 13 … Ministerstwo Sprawiedliwości Strona 16” jako przypis | 0 | 373 | DU/2024/1659 |
| (e) numery przypisów | 196 | 0 | wszystkie |
| (d) tekst załącznika drobnym drukiem jako przypis („folia zawiera elementy graficzne…”, opis wzoru); HTML: 2 z 3 załączników link-only | 0 | 57 | DU/2024/398 |
| (f) nieustalone: ciągi liczb „22 22 29 30 31…” jako przypisy | 0 | 84 | DU/2024/1751 (18 tokenów jest w HTML poza przypisami) |
| (a) w HTML poza przypisami | 0 | 3 | DU/2024/573 |
| razem | 708 | 517 | |

(DU/2024/164: 24 nadmiarowe tokeny, ale HTML nie ma przypisów, więc akt nie wchodzi do wyniku przypisów.)
Realny błąd konwertera: R 512/708 (72%), P ≥ 373/517 (72%; 57 i 84 prawdopodobnie też, niesprawdzone w PDF).

### Dev (0.6.4): s2024 n=41, s7 n=45

| | s2024 | s7 |
|---|---:|---:|
| ref / hyp / dopasowane | 11420 / 11964 / 10893 | 12832 / 14609 / 12459 |
| R brak: numery (e) | 297 | 363 |
| R brak: pozostałe (w naszej treści/załącznikach) | 230 (182) | 10 (2) |
| P nadmiar | 1071 | 2150 |
| P nadmiar znaleziony w HTML poza przypisami | 452 | 665 |

Akty z największym nadmiarem i co widać w niedopasowanym tekście (sprawdzone tylko tekstowo, bez PDF):
- przypisy tekstu jednolitego („w brzmieniu ustalonym przez § 1 pkt 2 rozporządzenia, o którym mowa
  w odnośniku 3”) — wzorzec (a) z README; część jest w HTML poza przypisami, część nie znaleziona:
  s7 DU/2024/1040 (116, znalezione 27), 870 (124/28), 453 (122/68), 1334 (146/146), 1108 (108/108);
  s2024 DU/2024/1777 (133/133), 1442 (88/88), 1703 (50/41);
- objaśnienia pod wzorami/formularzami (d): s2024 DU/2024/1973 (708, „Objaśnienia: Wzory zawierają…”),
  s7 DU/2024/273 („miejscowość, data, własnoręczny podpis… właściwe podkreślić”), 458 (pola formularza);
- tabela drobnym drukiem na dole strony jako przypis (realny błąd, reguła zapasowa bez kreski):
  s2024 DU/2024/1337 (236, współrzędne; HTML bez przypisów), 840 (25, „średnio bezpieczna…”);
- przypis, którego HTML nie ma w ogóle (nieznalezione; niesprawdzone w PDF): s7 DU/2024/77
  („Niniejsze rozporządzenie dokonuje… wdrożenia dyrektywy Komisji 2006/17/WE”, 68/7),
  DU/2024/193 („Minister Spraw Wewnętrznych i Administracji kieruje działem…”, 41/8).

Uwaga: „znalezione w HTML poza przypisami” nie rozróżnia (a) od (d): tekst formularza, który
konwerter błędnie wziął za przypis, też jest w HTML w załączniku (DU/2024/1337: 210 z 236).

## Poprawka w pdf.py (0.6.5.dev)

Kreska przypisów (`_frame_lines`): dotąd tylko `page.rects` i tylko poniżej 30% wysokości strony.
Teraz kandydatami są też `page.lines` (DU/2024/1346, 1018, 1659), a kreska w górnych 10–30% strony
albo narysowana linią liczy się tylko, gdy wszystko pod nią jest drukiem przypisu (< 9.5 pt).
Kreska-prostokąt poniżej 30% działa jak dotąd. Test: `test_footnote_rule_high_or_drawn_as_line`.

Skutek na poszczególnych aktach (footnotes_diag, po poprawce): DU/2024/1346 brak 680 → 0,
DU/2024/1018 430 → 0, DU/2024/1539 794 → 0, DU/2024/1505 1123 → 0 (zostają tylko numery).

Dev po poprawce vs 0.6.4 (evaluate): zmieniły się tylko 3 akty s2024, wszystkie na plus:
- DU/2024/1973: treść P 0.959 → 0.999, przypisy R 0.374 → 0.983, P 0.057 → 0.136;
- DU/2024/1542: przypisy R 0.719 → 0.780, P 0.901 → 0.969;
- DU/2024/1777: przypisy P 0.528 → 0.631, załącznik R 0.965 → 0.978.
- TOTAL s2024: treść P 0.9830 → 0.9849; przypisy R 0.9539 → 0.9622, P 0.9105 → 0.9158;
  załączniki R 0.9349 → 0.9352, P 0.8247 → 0.8248.
- s7: zmienił się tylko DU/2024/1334: przypisy P 0.505 → 0.598, załącznik R 0.991 → 0.994; TOTAL przypisy
  P 0.8528 → 0.8555, załączniki R 0.9965 → 0.9966 (reszta bez zmian).
s5110 (skonsumowana, tylko diagnoza) po poprawce vs 0.6.4: zmieniły się 3 akty — DU/2024/1539 przypisy
R 0.782 → 0.989; DU/2024/1505 R 0.551 → 0.989, P 0.896 → 0.940; DU/2024/1346 treść P 0.772 → 1.000,
przypisy R 0.000 → 0.996. TOTAL: treść P 0.9959 → 0.9995, przypisy R 0.7826 → 0.9820, P 0.7563 → 0.7957,
załączniki R 0.9801 bez zmian, P 0.9796 → 0.9881.

s5109 (skonsumowana, tylko diagnoza) po poprawce vs 0.6.3.dev: zmieniły się 2 akty — DU/2024/1018 treść
P 0.321 → 1.000, przypisy R 0.000 → 0.991; DU/2024/1659 treść P 0.818 → 1.000, przypisy R 0.079 → 0.989,
P 0.018 → 0.188 (stopki „Strona N z 13” nadal jako przypis). TOTAL: treść P 0.9807 → 0.9990, przypisy
R 0.9001 → 0.9716, P 0.9251 → 0.9293, załączniki bez zmian.

structure s7: bez zmian; structure s2024: jedyna różnica „annex break unaligned 1440 → 1437”
(P/R bez zmian). tree_eval s2024: main attach unaligned 63 → 62; annex attach 3101/3351 → 3102/3352
akapitów, 140299/147024 → 140345/147070 słów (wskaźniki 0.9254 i 0.9543 bez zmian); reszta bez zmian.
tree_eval s7: jedyna różnica annex attach 3707/4043 → 3708/4044 akapitów, 277438/284420 → 277484/284466
słów (wskaźniki bez zmian). Testy jednostkowe: 62/62 OK.

## Łagodniejsza miara (evaluate.py, linia `TOTAL notes*`)

Istniejące liczby bez zmian; dodatkowa linia: nasze numery przypisów (`[^3]` → „3”) zostają w tekście,
a nasz nadmiarowy token przypisu znaleziony w HTML poza przypisami (treść, wszystkie załączniki) liczy się
jako trafiony dla P. R liczony tylko z numerami (brakujący przypis HTML, który mamy w treści, nadal jest
błędem — to był realny błąd w 1346/1505/1539).

| próbka | wersja | notes R | notes P | notes* R | notes* P |
|---|---|---:|---:|---:|---:|
| s5110 | 0.6.4 | 0.7826 | 0.7563 | ≈0.7997 | ≈0.9862 |
| s5110 | 0.6.5.dev | 0.9820 | 0.7957 | 0.9998 | 0.9969 |
| s5109 | 0.6.4 | 0.9001 | 0.9251 | ≈0.9278 | ≈0.9315 |
| s5109 | 0.6.5.dev | 0.9716 | 0.9293 | 1.0000 | 0.9352 |
| s2024 | 0.6.4 | 0.9539 | 0.9105 | ≈0.9799 | ≈0.9442 |
| s7 | 0.6.4 | 0.9709 | 0.8528 | ≈0.9992 | ≈0.8972 |

≈ = wyliczone z footnotes_diag (dopasowane + numery; nadmiar znaleziony w HTML; hyp + liczba przypisów),
a nie przez `evaluate.py`; różnica względem `notes*` może wynikać z innego wyrównania.
Ograniczenie: `notes*` P zawyża wynik, gdy konwerter bierze za przypis tekst, który w HTML jest w
załączniku (tabela/formularz, np. DU/2024/1337) — tego miara nie odróżni od przypisu załącznika (781).

## Czego nie zrobiłem / co zostaje

- Nie sprawdziłem w PDF: DU/2024/1505 (nadmiar 162), 398, 1751, 1659 (poza typem kreski), ani aktów dev
  z listy wyżej.
- Realne błędy do dalszej pracy (nie naprawiałem):
  1. stopki formularzy „Strona N z M” (DU/2024/1659) jako przypis — pomijać wiersz pasujący do
     `^Strona \d+ z \d+$` pod kreską/na dole strony;
  2. reguła zapasowa bez kreski (`size < body_size - 0.5 and top > 0.6 * ph`) bierze tabele i pola
     formularzy drukiem drobnym za przypisy (DU/2024/1337, 840, 458, 273, 164, 398); przypis bez kreski
     powinien zaczynać się znacznikiem `[^N]`;
  3. objaśnienia pod wzorami (DU/2024/1973) — decyzja, czy to przypisy, czy tekst załącznika.
- README („Znane ograniczenia”) warto poprawić: niski recall przypisów s5110 był błędem konwertera.
