# Losowa kontrola wzrokowa opublikowanych danych (eli2md 0.6.2), DU i MP 2025–2026

Data: 2026-09-29. Dane: `dziennik-ustaw-md` i `monitor-polski-md` w stanie z 2026-09-29 (wszystkie pliki
`eli2md 0.6.2`). Porównanie: strona PDF (render) obok odpowiadającego fragmentu `.md` (i `.json` dla 5+5 aktów).
To jest jeden pomiar na małej próbie, nie gwarancja jakości.

## Metoda

**Losowanie aktów.** Wiersze `index.csv` z `status == "ok"` i `year` ∈ {2025, 2026}, w kolejności pliku
(DU: 3168 wierszy, MP: 2272). `rng = random.Random(seed)`, `rng.sample(rows, n)`; seed 20260930, n = 20 dla DU;
seed 20260931, n = 15 dla MP.

**Losowanie stron.** Tym samym generatorem, po kolei dla aktów w kolejności wylosowania: akt 1-stronicowy → strona 1;
akt dłuższy → strona 1 oraz `rng.randint(2, pages)` (strona losowa różna od 1). Razem 55 stron: DU 35, MP 20.

```python
rows = [r for r in csv.DictReader(open(index)) if r["status"] == "ok" and r["year"] in ("2025", "2026")]
rng = random.Random(seed); picks = rng.sample(rows, n)
for r in picks: p = int(r["pages"]); pages = [1] if p == 1 else [1, rng.randint(2, p)]
```

**Porównanie.** Render `pdfplumber page.to_image(resolution=100)`, dla drobnego druku wycinki w 170–200 dpi.
Fragment MD odpowiadający stronie wyznaczyłem skryptem (kotwice z pierwszych i ostatnich słów warstwy tekstowej strony),
a skrypt pokazywał też różnice słów między warstwą tekstową strony a fragmentem MD (pomocniczo; decyduje render).
Sprawdzane: (1) tekst: brakujące/zbędne słowa, zniekształcenia, kolejność; (2) akapity i nagłówki; (3) przypisy;
(4) tabele; (5) strony-skany/obrazy (notka, OCR); (6) front matter (tytuł, daty, pozycja) – skryptem dla wszystkich
35 aktów i wzrokowo na s. 1; (7) JSON: dla pierwszych 5 aktów z każdej listy (kolejność losowania) ścieżki
art./§/ust./pkt/lit. węzłów z tekstem tej strony.

**Oceny.** *OK* – brak uwag. *Błąd drobny* – bez utraty ani zniekształcenia treści (formatowanie, spacje, podpis).
*BŁĄD* – zniekształcony tekst lub kolejność, zły podział na jednostki, błędna struktura JSON, utrata treści.
Błędy metadanych z API ELI liczę osobno („metadane API”): konwerter przepisuje je bez zmian.

### Próba

DU (seed 20260930): 2025/1896 [1, 5], 2025/1661 [1, 2], 2026/683 [1], 2026/1089 [1, 2], 2025/911 [1, 65],
2026/865 [1], 2025/1261 [1], 2026/721 [1], 2026/156 [1, 57], 2026/1020 [1], 2026/1046 [1, 2], 2026/738 [1, 4],
2025/1715 [1, 6], 2025/91 [1, 24], 2025/205 [1, 2], 2026/421 [1, 8], 2026/998 [1, 2], 2026/1173 [1, 2],
2025/1134 [1, 3], 2026/13 [1, 7]. JSON: 1896, 1661, 683, 1089, 911.

MP (seed 20260931): 2025/635 [1], 2025/702 [1], 2025/1248 [1, 3], 2025/337 [1], 2025/478 [1], 2025/640 [1],
2026/690 [1], 2026/724 [1], 2025/81 [1], 2025/1002 [1], 2026/686 [1, 2], 2026/166 [1, 4], 2026/374 [1, 2],
2026/869 [1, 13], 2025/1203 [1]. JSON: 635, 702, 1248, 337, 478.

Skład próby: DU – 9 rozporządzeń, 6 obwieszczeń (5 tekstów jednolitych), 3 ustawy; żaden akt DU w próbie nie ma stron
bez warstwy tekstowej. MP – 7 postanowień, 3 obwieszczenia, 3 uchwały, 1 zarządzenie, 1 umowa (skany, OCR);
10 z 15 aktów MP ma 1 stronę.

## Wyniki: Dziennik Ustaw (35 stron)

| akt | str. | wynik | kategoria | opis / dowód |
|---|---|---|---|---|
| DU/2025/1896 | 1 | OK | – | tytuł, daty, poz., przypis 1; JSON par_1/pkt_1/lit_a–f, par_2/pkt_1/lit_a–b zgodne |
| DU/2025/1896 | 5 | OK | – | § 7 ust. 3 – § 14, podpis, przypis 2; JSON zgodny |
| DU/2025/1661 | 1 | OK | – | art. 1–3, przypisy 1–2; JSON zgodny |
| DU/2025/1661 | 2 | OK | – | art. 3 ust. 3 pkt 4 – art. 7 ust. 3; JSON zgodny |
| DU/2026/683 | 1 | OK | – | JSON zgodny |
| DU/2026/1089 | 1 | metadane API | front matter | PDF „z dnia 3 lipca 2026 r.” (także w tytule), `announcement_date: "2026-08-03"` (tak samo w meta.json z API). Tekst i JSON zgodne |
| DU/2026/1089 | 2 | OK | – | § 7–13; JSON zgodny („niedłużej” – tak w PDF) |
| DU/2025/911 | 1 | OK | – | cytaty „Art. 212. …” jako `quoted`; JSON zgodny |
| DU/2025/911 | 65 | OK | – | art. 157–160 k.k.w.; „Oddział 11” → w JSON `heading` z `label`; JSON art_159/par_2/pkt_1–4 zgodny |
| DU/2026/865 | 1 | OK | – | |
| DU/2025/1261 | 1 | OK | – | przypis 1 ma w PDF 2 akapity, w MD jeden `[^1]` (tekst pełny) |
| DU/2026/721 | 1 | OK | – | |
| DU/2026/156 | 1 | OK | – | cytowane „„Art. 25. 1. …” rozbite na „„Art. 25.” i „1. …” (jak nagłówki w treści głównej; nie liczę) |
| DU/2026/156 | 57 | OK | – | |
| DU/2026/1020 | 1 | OK | – | |
| DU/2026/1046 | 1 | błąd drobny | tekst (indeks górny) | PDF drukuje indeksy w nawiasach: „w art. 18[3a]:”, „§ 4[1] w brzmieniu”; MD: „w art. 18 [3a] :”, „„§ 4 [1] . Dyskryminowanie” (spacje; słowa kompletne) |
| DU/2026/1046 | 2 | **BŁĄD** | kolejność tekstu; jednostki (JSON) | PDF: „3) po art. 18[3e] dodaje się art. 18[3f] i art. 18[3g] w brzmieniu:”; MD (l. 71): „[3e] [3f] [3g] 3) po art. 18 dodaje się art. 18 i art. 18 w brzmieniu:”. JSON: brak `art_1/pkt_3`, akapit jest węzłem `text` pod `art_1/pkt_2` |
| DU/2026/738 | 1 | błąd drobny | podpis | „Minister Rodziny, Pracy i Polityki Społecznej: A. Dziemianowicz-Bąk” (tuż nad kreską przypisów) – zwykły akapit, bez `*…*`, w JSON brak węzła `signature` |
| DU/2026/738 | 4 | OK | – | |
| DU/2025/1715 | 1 | OK | – | |
| DU/2025/1715 | 6 | OK | – | „§ 9.⁶⁾ 1.” → „##### § 9.” + „[^6] 1. …”; przypis 6 ok |
| DU/2025/91 | 1 | OK | – | |
| DU/2025/91 | 24 | OK | – | art. 28–29 (ust. 9a–9c) |
| DU/2025/205 | 1 | **BŁĄD** | tabela | tabela lp. 5–12; w lp. 9 druga linia komórki 2 wpleciona w komórkę 3. PDF: kol. 2 „Świadczenia z zakresu gruźlicy i chorób płuc”, kol. 3 „1270 Poradnia gruźlicy i chorób płuc; 1271 Poradnia gruźlicy i chorób płuc dla dzieci; …”; MD: „9 Świadczenia z zakresu gruźlicy 1270 Poradnia gruźlicy i chorób płuc; 1271 Poradnia gruźlicy i chorób płuc i chorób płuc dla dzieci; …” |
| DU/2025/205 | 2 | OK | – | |
| DU/2026/421 | 1 | **BŁĄD** | przypisy (+ JSON) | Przypis 1 w PDF: „Niniejsza ustawa: 1) wdraża … 2) służy stosowaniu …”; MD: `[^1]: Niniejsza ustawa:`, a pkt 1) i 2) to osobne, niewcięte akapity (w renderze Markdown poza przypisem). JSON: `footnotes["1"] = "Niniejsza ustawa:"`, a pkt 1–2 przypisu są na końcu `body` (po podpisie) jako fałszywe jednostki `pkt_1`, `pkt_2`. Też: w cytowanej zmianie „„¹⁾ Niniejsza ustawa:” (odnośnik zmienianej ustawy) → „„[^1] Niniejsza ustawa:” – wskazuje przypis 1 tego aktu |
| DU/2026/421 | 8 | OK | – | zagnieżdżone cytaty jako tekst |
| DU/2026/998 | 1 | OK | – | tiret „–” i „– –” |
| DU/2026/998 | 2 | OK | – | |
| DU/2026/1173 | 1 | OK | – | |
| DU/2026/1173 | 2 | OK | – | kwoty, tiret (kursywa nazw łacińskich nie jest zachowywana – nie liczę) |
| DU/2025/1134 | 1 | OK | – | |
| DU/2025/1134 | 3 | **BŁĄD** | tabela | załącznik, tabela 3-kolumnowa, lp. 3: PDF kol. 2 „Zwierzęta łowne z gatunków wrażliwych na zarażenie włośniem, inne niż dziki”, kol. 3 „filary przepony, mięśnie żwacza, …”; MD: „3 Zwierzęta łowne z gatunków wrażliwych filary przepony, na zarażenie włośniem, inne niż dziki mięśnie żwacza, mięśnie okołojęzykowe, język, mięśnie zginaczy palców” |
| DU/2026/13 | 1 | OK | – | |
| DU/2026/13 | 7 | OK | – | art. 5 pkt 14–23 |

## Wyniki: Monitor Polski (20 stron)

| akt | str. | wynik | kategoria | opis / dowód |
|---|---|---|---|---|
| MP/2025/635 | 1 | **BŁĄD** (+ metadane API) | podział; JSON | PDF: „MEDALEM ZA OFIARNOŚĆ I ODWAGĘ”, „na wniosek Wojewody Łódzkiego:”, pozycje 2–5 i „na wniosek Wojewody …” w osobnych wierszach. MD: pierwsze dwa doklejone do akapitu „Na podstawie art. 138 … odznaczeni zostają:”, a l. 35 to jeden akapit „2. Kuśmierek Mateusz Piotr, na wniosek Wojewody Opolskiego 3. Pers Tycjan Łukasz, na wniosek Wojewody Śląskiego 4. Radoń Piotr Przemysław, na wniosek Wojewody Wielkopolskiego 5. Arczewska Aleksandra Anna.”; JSON: `ust_2` zawiera pozycje 3–5. Tytuł „POSTANOWIENIE / PREZYDENTA … / z dnia 19 maja 2025 r.” sklejony w jeden akapit. Front matter: `promulgation_date: "2025-07-08"`, PDF „Warszawa, dnia 11 lipca 2025 r.” (meta.json z API: 2025-07-08). Tekst kompletny |
| MP/2025/702 | 1 | OK | – | JSON zgodny |
| MP/2025/1248 | 1 | OK | – | JSON par_1/pkt_2/lit_d/tir_2/tir_1 itd. zgodny |
| MP/2025/1248 | 3 | **BŁĄD** | JSON (+ przypis drobny) | MD zgodny z PDF. JSON: lit. e–i tej strony mają ścieżki `par_1/ust_8/lit_e` … `par_1/ust_8/lit_i` (powinno być `par_1/pkt_2/lit_e` …), bo niecytowany wiersz tabeli ze s. 2 „8. Program naukowo-badawczy 10.000 - - - 5.000 …” stał się jednostką `par_1/ust_8` (wiersze „3.” i „4.” → `ust_3`, `ust_4`). W cytacie nowego brzmienia odnośnika „„⁴⁷⁾ Art. 57c ustawy …” → „„[^47] Art. 57c …” – odnośnik bez definicji (`footnotes: {}`) |
| MP/2025/337 | 1 | OK | – | ē, ņ, š poprawnie. JSON: lista odznaczonych „1.”–„13.” jako `ust_1`–`ust_13` (to nie ustępy; umowne, nie liczę) |
| MP/2025/478 | 1 | błąd drobny | podpis | kontrasygnata „Prezes Rady Ministrów: D. Tusk” zwykłym akapitem, w JSON `text` zamiast `signature` |
| MP/2025/640 | 1 | OK | – | |
| MP/2026/690 | 1 | OK | – | lista 1–11 w osobnych akapitach |
| MP/2026/724 | 1 | OK | – | |
| MP/2025/81 | 1 | OK | – | |
| MP/2025/1002 | 1 | OK | – | |
| MP/2026/686 | 1 | OK | – | |
| MP/2026/686 | 2 | OK | – | |
| MP/2026/166 | 1 | OK | – | |
| MP/2026/166 | 4 | OK | – | wklejony załącznik (inny krój) |
| MP/2026/374 | 1 | OK | – | |
| MP/2026/374 | 2 | błąd drobny | podział | strona tytułowa wklejonego sprawozdania: ukryty tekst warstwy („doz donbiaw 27i emsazrccaz…”) poprawnie pominięty, `## Załącznik …` ok; ale tytuł „Sprawozdanie z realizacji … za lata 2022–23” sklejony w jeden akapit z „SPIS TREŚCI” z następnej strony |
| MP/2026/869 | 1 | brak treści (znany typ) | obraz | Warstwa tekstowa s. 1 ma tylko tytuł umowy; preambuła i cały Artykuł 1 „DEFINCJE” (pkt 1–2) są na tej stronie obrazem (skan). OCR nie działa, bo strona ma warstwę tekstową; w MD jest notka „> [Na stronie 1 PDF jest obraz …]” i nie ma tej treści |
| MP/2026/869 | 13 | błędy OCR (znane typy) | skan/OCR | notka OCR obecna, akapity jako `>`; tekst angielski poprawny poza: „1.” → „I.”; odręczne „Warsaw … 26th of January 2026” → „Marsa) AE on2b2..0 „A. of. pqinaity 2026”; dwie kolumny podpisów czytane wierszami: „FOR THE GOVERNMENT FOR THE GOVERNMENT OF THE REPUBLIC OF THE KINGDOM OF POLAND OF SAUDI ARABIA” |
| MP/2025/1203 | 1 | OK | – | |

## Liczby

| | DU | MP | razem |
|---|---:|---:|---:|
| stron | 35 | 20 | 55 |
| bez żadnego błędu (OK) | 28 | 14 | 42 |
| z błędem konwertera (dowolnym, bez metadanych API) | 6 | 6 | 12 |
| – w tym BŁĄD istotny (bez obrazów/OCR) | 4 | 2 | 6 |
| – w tym znane typy (obraz bez OCR, błędy OCR) | 0 | 2 | 2 |
| – w tym tylko drobne | 2 | 2 | 4 |
| tylko błąd metadanych z API | 1 | 0 (1 razem z błędem konwertera) | 1 (+1) |

Strony z błędem według kategorii (strona może mieć kilka):

| kategoria | DU | MP |
|---|---:|---:|
| tekst: słowa/kolejność (warstwa tekstowa) | 2 (1046 s. 1 drobny, s. 2) | 0 |
| podział na akapity/jednostki, nagłówki | 1 (1046 s. 2) | 2 (635, 374 s. 2 drobny) |
| podpis nierozpoznany | 1 (738) | 1 (478) |
| przypisy | 1 (421) | 1 (1248 s. 3, drobny) |
| tabele | 2 (205, 1134) | 0 |
| obrazy/skany/OCR | 0 (brak takich stron w próbie) | 2 (869 s. 1, s. 13) |
| front matter (metadane API) | 1 (1089) | 1 (635) |
| JSON (tylko 5 aktów na zbiór) | 0 z 9 stron | 2 z 6 stron (635, 1248 s. 3) + 1 drobny (478) |

- Przedziały (Clopper–Pearson 95%) dla odsetka stron z jakimkolwiek błędem konwertera: DU 6/35 = 0.17 (0.07–0.34),
  MP 6/20 = 0.30 (0.12–0.54); z istotnym błędem konwertera (bez obrazów/OCR): DU 4/35 = 0.11 (0.03–0.27),
  MP 2/20 = 0.10 (0.01–0.32). Próba jest mała, przedziały szerokie.
- Słowa z warstwy tekstowej były obecne w MD na wszystkich 54 stronach, które ją mają (zgodnie z selfcheckiem).
  Błędy dotyczą kolejności, podziału, tabel, przypisów i struktury, nie gubienia słów. Jedyna utrata treści to
  obraz na s. 1 umowy MP/2026/869.
- Tabele: w próbie tylko 2 strony z tabelą (obie DU) i na obu jest błąd przeplatania komórek.
- Przypisy: 14 stron DU z przypisami, błąd na 1 (DU/2026/421); 2 strony MP z przypisami, bez błędów, plus cytowany
  odnośnik na MP/2025/1248 s. 3 (drobny).
- Front matter: tytuł, `display_address`/`position` zgodne w 35/35 aktach; daty: 2 niezgodności, obie przepisane
  z API (meta.json).
- JSON w podzbiorach (DU 5 aktów/9 stron, MP 5 aktów/6 stron): DU bez błędów; MP 2 strony z błędną strukturą.
  Poza podzbiorami przy okazji znalazłem błędy JSON w DU/2026/1046 i DU/2026/421 (opisane wyżej).

## Nowe typy błędów (nieopisane w README zbiorów ani eli2md)

1. **Indeksy górne w nawiasach kwadratowych (2026).** Część PDF-ów z 2026 r. drukuje indeksy jako „Art. 479[30f].”,
   „art. 18[3a]”, „§ 4[1]” (sprawdzone na renderze). Konwerter (a) wstawia spacje: „art. 18 [3a] :”; (b) czasem
   przenosi indeksy na początek akapitu: DU/2026/1046 s. 2 (wyżej); (c) w tekstach jednolitych artykuł z takim numerem
   nie jest nagłówkiem ani jednostką `art` w JSON. Przykład spoza próby: DU/2026/468 (tekst jednolity k.p.c.) s. 98,
   PDF: „**Art. 479[30f].** W postępowaniu apelacyjnym przepisy art. 479[30] § 2 i art. 479[30a]–479[30e] stosuje się
   odpowiednio.”; MD: „[30f] [30] [30a] [30e] Art. 479 . W postępowaniu apelacyjnym przepisy art. 479 § 2 i art. 479 –479
   stosuje się odpowiednio.”. W JSON tego aktu jest 1169 węzłów `art`, żaden z indeksem. Skala (policzona regexami na całych zbiorach):
   106 plików DU ma wzorzec „słowo [cyfra…]” (górna granica: część to inne nawiasy, np. odnośniki w formularzach); 17 plików ma 1393 akapity zaczynające się od „Art. N [x] .” (nie nagłówki),
   m.in. DU/2026/468 (823), DU/2026/795 (tekst jednolity k.c., 213), DU/2026/1245 (tekst jednolity k.p., 202); 54
   akapity w 11 plikach mają indeksy przeniesione na początek. W MP 3 pliki z „[x]”, bez tych objawów. W 17 plikach
   część to cytowane artykuły w nowelizacjach (tam brak nagłówka jest poprawny), więc 1393 to górna granica utraconych
   nagłówków.
2. **Przypis z wyliczeniem (kilka akapitów).** Tylko pierwszy akapit trafia do `[^n]:`; dalsze nie są wcięte, a w JSON
   stają się jednostkami `pkt` na końcu treści głównej (DU/2026/421 s. 1). Skali nie liczyłem.
3. **Odnośnik przypisu w cytowanym przepisie zmienianego aktu** („„¹⁾ Niniejsza ustawa:”, „„⁴⁷⁾ Art. 57c …”) staje się
   odnośnikiem `[^n]` tego aktu: wskazuje zły przypis (DU/2026/421) albo nieistniejący (MP/2025/1248: `[^12]`, `[^13]`,
   `[^47]` bez definicji).
4. **Przeplatanie wieloliniowych komórek tabeli.** README opisuje spłaszczanie tabel „wiersz po wierszu”, ale nie to,
   że przy komórkach wieloliniowych linie różnych kolumn się przeplatają i zmieniają sens (DU/2025/205 lp. 9,
   DU/2025/1134 lp. 3). Na obu stronach z tabelą w próbie.
5. **Fałszywa jednostka z wiersza tabeli przejmuje następne jednostki.** README eli2md wspomina o fałszywych ust. z
   numerowanych wierszy tabel. Tu skutek jest większy: niecytowany wiersz „8.” z tabeli w nowelizacji (MP/2025/1248 s. 2)
   staje się `par_1/ust_8` i przejmuje prawdziwe lit. e–i ze s. 3 (złe ścieżki pięciu lit. i ich tiret).
6. **Nierozpoznany podpis** tuż nad kreską przypisów (DU/2026/738) i kontrasygnata pod podpisem Prezydenta
   (MP/2025/478): zwykły akapit, bez `signature` w JSON. Drobne.
7. **Akapit sklejony przez granicę strony** (tytuł na s. 2 + „SPIS TREŚCI” z s. 3, MP/2026/374). Drobne.
8. **Treść umowy jako obraz na stronie z warstwą tekstową.** README opisuje notkę o obrazach („wzory, rysunki, mapy”),
   ale tu obrazem jest tekst umowy (preambuła i art. 1), a OCR go nie czyta (MP/2026/869 s. 1). Ten sam wzór metadanych
   (obraz na s. 1 + OCR na dalszych stronach) ma 30 plików DU i 14 MP, wszystkie to umowy międzynarodowe. Sprawdziłem
   tylko ten jeden, więc 44 to kandydaci, a nie potwierdzone przypadki.
9. **Błędy dat w metadanych w MP.** W README DU są opisane, w README MP nie (MP/2025/635 `promulgation_date`).

Znane typy, policzone wyżej: sklejanie pozycji wyliczenia w jeden akapit (MP/2025/635; README DU: „ust./pkt/lit.
sklejone”, README MP: tylko w tabelach), błędy OCR i kolejność kolumn w OCR (MP/2026/869 s. 13), błędy dat z API
(DU/2026/1089).

## Czego ta kontrola nie mierzy

- **Mała próba.** 55 stron z 35 aktów; przedziały ufności są szerokie. Losowane są akty, nie strony, a s. 1 jest
  zawsze w próbie, więc krótkie akty i strony tytułowe są nadreprezentowane: 10 z 15 aktów MP ma 1 stronę,
  a długie załączniki, tabele i formularze są niedoreprezentowane. Odsetek błędów na stronę całego zbioru jest
  prawdopodobnie wyższy, bo błędy skupiają się w tabelach i załącznikach.
- **OCR i obrazy.** W próbie DU nie ma żadnej strony bez warstwy tekstowej, a w MP są tylko 2 strony jednej umowy.
  Jakości OCR ta kontrola nie mierzy.
- **JSON** sprawdziłem tylko dla 10 aktów (15 stron) i tylko ścieżki jednostek na danej stronie, a nie całe drzewo.
- **Cały akt.** Nie sprawdzałem kompletności całego aktu (inne strony, kolejność stron, koniec pliku) poza granicami
  obejrzanych stron.
- **Szczegóły renderu.** Render 100 dpi: drobne różnice znaków (indeksy, znaki diakrytyczne w przypisach) mogły umknąć.
  Tam, gdzie było to ważne, powiększałem wycinki do 170–200 dpi. Porównanie słów z warstwą tekstową PDF pomaga,
  ale nie wykryje błędu, który jest już w samej warstwie tekstowej.
- **Skala nowych typów** (pkt 1 i 8) jest policzona regexami na całych zbiorach, poza losową próbą. Liczby dla pkt 1
  to górna granica (część dopasowań to cytaty w nowelizacjach). Pkt 8 to tylko kandydaci wskazani przez metadane.
- **Oceny są moje.** Robił je jeden oceniający bez drugiej opinii. Granica „drobny/istotny” jest umowna
  (tabela z komentarzami wyżej pozwala ją przeliczyć).
