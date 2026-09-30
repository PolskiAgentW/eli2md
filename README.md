# eli2md

Konwerter aktów z **Dziennika Ustaw** i **Monitora Polskiego** (PDF) do **Markdown** i drzewa jednostek w JSON,
z mierzoną jakością.
*Converts Polish Journal of Laws (and Monitor Polski) PDFs to Markdown; accuracy is measured against official HTML.*

> Status: **wersja 0.6.3**. Kod może zawierać błędy. Wiążący jest zawsze PDF opublikowany
> w Dzienniku Ustaw albo w Monitorze Polskim.

## Po co

API ELI Sejmu (`api.sejm.gov.pl/eli`) udostępniało teksty aktów także w HTML. Od 2025 r.
dla Dziennika Ustaw jest już tylko PDF (stan sprawdzony 2026-09-29):

| rok  | aktów | z `textHTML` |
|------|------:|-------------:|
| 2024 | 1984  | 1984         |
| 2025 | 1900  | 0            |
| 2026 | 1255  | 0            |

Narzędzia budujące na tekście HTML (np. [legalize-pl](https://github.com/legalize-dev/legalize-pl))
nie obejmują więc aktów od 2025 r. eli2md ma tę lukę wypełnić: z PDF-a robi tekst,
w którym artykuły, ustępy i punkty są w osobnych akapitach, a przypisy są przypisami.

## Użycie

```sh
pip install git+https://github.com/PolskiAgentW/eli2md
eli2md DU/2025/900 -o DU-2025-900.md      # pobiera metadane i PDF z API ELI
eli2md MP/2025/148                         # Monitor Polski (od 0.6.2)
eli2md plik.pdf                            # lokalny PDF, wynik na stdout
```

Cały rocznik (nowe i zmienione akty; indeks w `index.csv`):

```sh
python -m eli2md.dataset --root dane/ --years 2025 2026 --jobs 4
python -m eli2md.dataset --publisher MP --root dane-mp/ --years 2025 2026 --jobs 4   # Monitor Polski (od 0.6.2)
```

Dla Dziennika Ustaw zbiór obejmuje akty bez tekstu HTML w API (od 2025 r. wszystkie, wcześniej luki);
w Monitorze Polskim HTML-a nie ma dla żadnego aktu (sprawdzone dla lat 2012–2026), więc obejmuje wszystkie.

Pobrane pliki trafiają do `~/cache/eli` (zmienna `ELI2MD_CACHE`). Klient robi przerwę 1 s między zapytaniami.
Każdy proces konwersji ma limit pamięci 3 GB (`--mem-limit-gb`). Akt, który go przekroczy, dostaje w indeksie
`status=error` i nie przerywa reszty.

## Format wyniku

- Front matter YAML z metadanymi z API ELI. Klucze są zgodne z legalize-pl tam, gdzie znaczą to samo
  (`title`, `identifier`, `rank`, `eli`, `display_address`, …). Do tego `source_pdf`, `converter`
  oraz `disclaimer`.
- `# Tytuł`, potem akapity w kolejności z PDF-a.
- Jednostki najwyższego rzędu jako `##### Art. N.`, a gdy w akcie nie ma artykułów, `##### § N.`
  (rozporządzenia). Jednostki cytowane (nowelizacje, „przepisy nieobjęte tekstem jednolitym”)
  nie są nagłówkami. Ich numer jest osobnym akapitem: `„Art. 21.`, potem `1. Treść…` (od 0.5.0).
- Ust., pkt i lit. zaczynają nowy akapit (`1.`, `1)`, `a)`). Jawne drzewo jednostek jest w JSON (niżej, od 0.5.3).
- Cyfry w indeksie górnym i dolnym jako znaki Unicode: `Art. 41¹.`, `m²`, `P₂O₅` (od 0.5.0;
  wcześniej błędnie jako odnośniki do przypisów `[^1]`).
- Indeks numeru jednostki z literą też w całości jako znaki górne, litery jako litery modyfikujące Unicode:
  `Art. 22¹ᵃ.`, `Art. 479³⁰ᶠ.`, tak samo `num` i `path` w JSON (`"479³⁰ᶠ"`, `art_479³⁰ᶠ`) (od 0.6.3, szczegóły niżej).

#### Indeksy przy numerach jednostek (od 0.6.3)

PDF-y drukują indeks (`Art. 479³⁰ᶠ`) małym, podniesionym pismem, ale w dwóch zapisach. Do 2025 r. (i w części
PDF-ów z 2026 r., np. DU/2026/236) bez nawiasów: `22` + małe `1` albo `1a` (DU/2025/277). W części PDF-ów
z 2026 r. w nawiasach kwadratowych, także same cyfry: `479[30f]`, `§ 4[1]` (DU/2026/468, 795, 1245, 1046).
Oba zapisy dają ten sam wynik: cały indeks jako znaki górne, bez nawiasów (`479³⁰ᶠ`, `§ 4¹`). Nawiasy to tylko
zapis drukarski, więc ten sam artykuł ma w wyniku ten sam numer niezależnie od rocznika druku. Zapisu cyframi
górnymi (`41¹`, od 0.5.0; w zbiorze DU 2025–2026 z 0.6.2 było 848 takich nagłówków) nie zmieniałem. Zapis
z nawiasami dla wszystkich indeksów dałby dwa zapisy tego samego artykułu w danych z różnych lat. Litery
modyfikujące (`ᵃ` U+1D43, `ᶠ` U+1DA0, …) mają rozkład zgodności na zwykłe litery: po normalizacji NFKC
`479³⁰ᶠ` to `47930f` (tak jak `41¹` to `411`). Litera q nie ma znaku górnego w Unicode. Indeks z taką literą
zostaje w zapisie z nawiasami: `5[1q]` (w sprawdzonych PDF-ach go nie było).

Za indeks uznaję mały wyraz w nawiasach (`[30f]`) albo cyfry z literą (`1a`), który zaczyna się tuż za wyrazem
zwykłej wielkości zakończonym literą lub cyfrą (odstęp < 1,5 pt) i jest podniesiony nad jego środek. Mały
wyraz `[2]` z dala od poprzedniego wyrazu zostaje bez zmian. Do 0.6.2 indeks z literą był osobnym wyrazem
(`Art. 22 1a .`). Indeks w nawiasach też był osobnym wyrazem (`art. 18 [3a] :`). Gdy w jednej linii były
co najmniej trzy indeksy, linia indeksów trafiała przed linię główną: `[30f] [30] [30a] [30e] Art. 479 . W
postępowaniu…`. Artykuły z takim numerem nie były nagłówkami ani węzłami `art`. Skalę i pomiar opisuje
`eval/indices_2026_v0.6.3.dev.md`.
- Nagłówki załączników jako `## Załącznik nr …`, podpis kursywą.
- Przypisy w składni Markdown: `[^1]` w tekście i `[^1]: …` na końcu. Numeracja przypisów zaczyna się od nowa
  w załącznikach i formularzach; od 0.6.1 kolejny przypis o tym samym numerze ma etykietę `[^1_2]`, `[^1_3]`…,
  a odnośnik wskazuje przypis z tej samej strony (albo najbliższej dalszej). Wcześniej etykiety się powtarzały
  (w zbiorze 0.5.3: 466 plików) i w JSON część przypisów ginęła.
- Akapit z warstwy tekstowej zaczynający się od `>` albo `#` (np. `> 90 dni` w tabeli) jest poprzedzony `\`,
  żeby nie był cytatem blokowym (tak oznaczam OCR) ani nagłówkiem (od 0.6.1).
- Treść, której nie da się odczytać jako tekst, jest oznaczona notką w miejscu, gdzie występuje:
  `> [Strony 2-28 PDF nie mają warstwy tekstowej …]` (skany) oraz
  `> [Na stronie 7 PDF jest obraz …]` (obraz zajmujący ≥10% strony: wzór, rysunek, mapa).
  We front matter te same strony są w polach `pages_without_text` i `pages_with_images`.
  Tej treści nie ma w Markdown. Domyślnie konwerter nie robi OCR (opcja `--ocr` niżej). Od 0.6.1 stroną bez
  czytelnej warstwy tekstowej jest też strona, na której ponad 10% znaków nie ma kodu Unicode (pdfminer daje wtedy
  `(cid:N)`; formularze, np. DU/2025/161). Wcześniej te znaki trafiały do wyniku (w zbiorze 0.5.3: 27 plików).

### JSON: drzewo jednostek (od 0.5.3)

`eli2md DU/2025/900 --json` (albo `--format json`) oraz `python -m eli2md.dataset … --json` (plik `.json`
obok `.md`) dają drzewo jednostek zbudowane z Markdown (`eli2md/tree.py`; da się je odtworzyć
z opublikowanych plików `.md`):

```json
{"eli": "DU/2025/1", "title": "…", "converter": "eli2md …", "source_pdf": "…",
 "body": [{"type": "art", "num": "1", "path": "art_1", "text": "…",
           "children": [{"type": "pkt", "num": "1", "path": "art_1/pkt_1", "text": "art. 5 otrzymuje brzmienie:",
                         "children": [{"type": "text", "text": "„Art. 5. …”;", "quoted": true}]}]}],
 "annexes": [{"heading": "Załącznik nr 1 …", "body": […]}],
 "footnotes": {"1": "…"}}
```

Typy: `art`, `par` (§), `ust`, `pkt`, `lit`, `tir` oraz `text`, `heading` (rozdział, dział…), `signature`, `note`,
`ocr` (akapit odczytany przez OCR, od 0.6.0). Jednostki cytowane w nowelizacjach nie są węzłami, tylko tekstem
(`"quoted": true`) jednostki, która je zawiera. Akapit bez numeru trafia do najgłębszej otwartej jednostki.
Wyjątek (od 0.6.0): tekst tuż po ostatnim punkcie wyliczenia, zaczynający się małą literą albo od „– ”
(„część wspólna”: „oraz zmian wynikających…”, „– w wysokości…”), trafia do jednostki nad wyliczeniem. Jeśli
potem przychodzi jednostka niższego rzędu (np. lit. po takim akapicie), akapit wraca do punktu: był dalszym
ciągiem jego tekstu rozbitym przez układ strony. „– ” po wyliczeniu nie jest tiretem, chyba że poprzedni akapit
kończy się dwukropkiem albo sam jest tiretem.

`eval/tree_eval.py` porównuje ścieżki (`art_5/ust_2/pkt_3`) z identyfikatorami jednostek w HTML 2024 (bez
jednostek cytowanych) w tym samym miejscu tekstu. **R**: odsetek jednostek HTML, dla których w JSON jest węzeł
o tej samej ścieżce zaczynający się w tym samym słowie; **P**: odwrotnie. Od 0.6.0 miara sprawdza też
**przypięcie**: czy akapit bez numeru wisi pod tą jednostką, do której należy w HTML, i jaki odsetek słów
jest we właściwej jednostce (tirety pomijam po obu stronach, bo HTML ich nie oznacza).

| art, §, ust., pkt, lit.  | **test s5105 (38)**, 0.6.0 | test s5104 (46), 0.5.3 | dev seed 2024 (49)     | dev seed 7 (50)        |
|--------------------------|----------------------------|------------------------|------------------------|------------------------|
| treść główna             | **1.000 / 1.000** (774)    | 1.000 / 1.000 (1256)   | 1.000 / 1.000 (942)    | 0.992 / 0.996 (1830)   |
| załączniki               | **0.991 / 0.992** (3459)   | 0.998 / 0.994 (7217)   | 0.993 / 0.852 (4825)   | 1.000 / 0.994 (11946)  |

Przypięcie na teście s5105, 0.5.3 → 0.6.0 (jednostki bez zmian): akapity bez numeru we właściwej jednostce
w treści głównej 0.995 → **1.000** (385), w załącznikach 0.876 → **0.969** (195); słowa we właściwej jednostce
0.9905 → **1.000** i 0.985 → **0.991**. s5105 zapisana w gicie przed oceną, oceniona raz, obie wersje tą samą miarą.

Próba odłożona s5104 zapisana w gicie przed oceną, oceniona raz. Na próbach deweloperskich stroiłem, więc
tamte liczby są zawyżone. Niska precision załączników w seed 2024 to głównie DU/2024/1337 (karty akwenów:
numerowane wiersze tabel, których HTML nie oznacza jako jednostek). W teście najsłabsze są lit. w załącznikach
(R 0.978, P 0.937). Tiret HTML nie oznacza, więc nie są mierzone. Nagłówków rozdziałów miara nie sprawdza.
**0.6.1, test s5106** (45 aktów, ocena jednorazowa; 0.6.0 i 0.6.1 dają tu identyczne słowa, strukturę i drzewo):
treść główna 2517/2517 jednostek, przypięcie akapitów 1916/1916; załączniki R 0.976, P 0.974. Większość błędów
w załącznikach to trzy teksty jednolite. W DU/2024/54 (113 błędów) PDF ma „Art. 3. Ilekroć w ustawie jest mowa o:
1) …” bez numeru ustępu, a HTML i tak tworzy `ust_1`, więc ścieżki `art_3/pkt_1` i `art_3/ust_1/pkt_1` się różnią
(sprawdzone w PDF). DU/2024/1366 (90: HTML zagnieżdża ust. 1a w ust. 1) i DU/2024/456 (237) nie sprawdzałem.
Zdublowane etykiety przypisów na s5106: 9 w 0.6.0 → 0; tekst „(cid:N)”: 1 → 0. Escapowanie `>`/`#` dodałem po teście.

**0.6.2, test s5108** (41 aktów, zapisana w gicie przed oceną, oceniona raz, 0.6.1 i 0.6.2 tą samą miarą):
treść główna bez zmian, 1455/1455 jednostek i przypięcie 761/761 w obu wersjach; załączniki R 0.995 → 0.995,
P 0.920 → **0.937** (fałszywe ust.: 269 → 199; z 236 fałszywych jednostek 225 to numerowane wiersze tabeli
współrzędnych w DU/2024/1594), przypięcie akapitów 0.837 → **0.961**,
słów 0.954 → 0.957. Co zmieniło się w 0.6.2 (znalezione na teście s5107, potem sprawdzone na próbach deweloperskich
i zużytych testach):
- „Rozdział 2. Tytuł” w jednej linii (z kropką po numerze) nie był nagłówkiem, więc pkt z rozdziału 2 wisiały
  pod ust. 2 z rozdziału 1 (DU/2024/853). Na s5107 pkt w treści głównej R 0.974 → 0.997;
- sekcje załącznika „I.”, „II.”, „III.” … (w JSON węzły `heading` z etykietą „III.”) zamykają jednostki poprzedniej
  sekcji. Wcześniej lista „1) …” z sekcji III wisiała pod „6.” z sekcji II (DU/2024/629, 456). Tylko w załącznikach
  i tylko jako ciąg od „I.” zaczęty poza jednostką: „I. METALE” w tabeli wewnątrz „1.” (DU/2024/1657) to wiersz tabeli,
  a w treści głównej takie linie to zwykle wiersze tabel zmienianych przez nowelizację. Na s5107 pkt w załącznikach
  R 0.834 → 1.000, na s5106 0.953 → 0.982.

Wyniki per akt: `eval/tree_test_s5108_v0.6.*.txt`, `eval/tree_test_s5106_v0.6.1.txt`, `eval/tree_test_s5105_v0.6.0.txt`, `eval/tree_test_s5104_v0.5.3.txt`, `eval/tree_dev_s*.txt`.

**0.6.3** (2026-09-30). Zmiany znalezione przy kontroli danych 2025–2026, bez wzorca HTML:
- indeksy przy numerach jednostek jako znaki górne, także w nawiasach i z literą (`Art. 479³⁰ᶠ.`, opis wyżej).
  W danych DU 2012–2026 nagłówków art./§ 91 151 → 92 626; k.p.c. (DU/2026/468) 1169 → 2015 nagłówków artykułów;
- test tuszu (ukryty tekst pod wklejonymi załącznikami) sprawdza sam glif, a nie ramkę pdfminera. Fonty z błędnym
  `/Descent` (Cambria) dawały ramkę sięgającą 16–27 pt pod glif, więc widoczne litery uchodziły za ukryte:
  MP/2025/1128 z odsetkiem słów 0.72 („elekt omobinos ci”) → 0.997. Skutek uboczny: widać teraz wzory Worda
  zapisane tym fontem (DU/2026/1236). Litery we wzorach bywają podwojone („kk”), bo w PDF-ie jeden glif ma w mapie
  ToUnicode dwa znaki (`𝑘𝑘`). W DU/2025/452 s. 7 do wyniku trafia też niewidoczna kopia wzoru;
- na stronach obróconych znaki zdublowane usuwam tylko wtedy, gdy to ten sam glif w tym samym miejscu (≤ 0,3 pt).
  Deduplikacja pdfplumbera zlewała też różne litery drobnego druku (MP/2025/541, obrócona tabela: 0.976 → 0.991);
- w ciasnych tabelach pozycja „2)”/„b)” po krótkiej linii bez interpunkcji zaczyna nowy akapit (MP/2025/121:
  229 → 535 akapitów);
- Monitor Polski 2012: pomijam ukośny znak wodny „www.rcl.gov.pl” i winietę „Pozycja N”.

Zmiana w danych (wszystkie akty od nowa, 0.6.2 → 0.6.3): tekst zmienił się w 352 z 3266 plików DU i 37 z 2272
MP (w pozostałych tylko pole `converter`). Na tych plikach selfcheck (niżej; ta sama, nowa miara dla obu wersji):
odsetek słów PDF w wyniku lepszy w 154 DU i 12 MP, gorszy w 14 DU (najwięcej o 0.0002). Odsetek słów wyniku
obecnych w PDF gorszy w 27 DU. W obejrzanych (DU/2026/1236, DU/2026/40) to wzory Cambria Math, które wcześniej
ginęły: miara porównuje kursywę matematyczną z PDF (`𝑘`) ze zwykłą literą w wyniku i liczy ją jako obcą.

**0.6.3, test s5109** (37 aktów; 0.6.3 oceniona raz przed wydaniem, 0.6.2 potem tymi samymi skryptami):
słowa bez zmian (treść główna R 0.9997, P 0.9807; przypisy R 0.900, P 0.925; załączniki R 0.9977, P 0.9536),
drzewo w treści głównej 656/656 w obu wersjach, w załącznikach R 0.9986, P 0.9964 w obu. Przypięcie akapitów
w załącznikach 181/208 → 182/209, podziały w załącznikach P 0.9975 → 0.9973 (jeden fałszywy podział więcej,
DU/2024/1018). Zmiany 0.6.3 dotyczą układów, których w aktach z 2024 r. prawie nie ma, więc ta próba ich
nie mierzy. Wyniki: `eval/*_test_s5109_v0.6.3.dev.*`, `eval/*_test_s5109_v0.6.2.txt`, porównanie selfchecku
`eval/selfcheck_changed_0.6.2_vs_0.6.3.json`.

## Jakość: jak mierzę i co wyszło

Akty z 2024 r. mają zarówno PDF, jak i oficjalny HTML. Konwertuję PDF i porównuję słowa
z tekstem HTML (`eval/evaluate.py`: tokeny słów bez rozróżniania wielkości liter, dopasowanie difflib).

- **recall** to odsetek słów oficjalnego tekstu odzyskanych we właściwej kolejności,
- **precision** to odsetek słów wyniku, które są w oficjalnym tekście.

Treść główna, przypisy i załączniki są liczone osobno. Pomijam akty, dla których HTML jest
pustym placeholderem, oraz załączniki, które HTML podaje tylko jako link do PDF-a.

**Test (próba odłożona):** 50 losowych aktów z 2024 r. (seed 99) minus 3, które były już w próbach
deweloperskich, czyli 47. Zbiór zapisałem w gicie przed oceną (`eval/test_2024_s99.json`).
Ocena jednorazowa, wersja 0.2.0, bez strojenia pod ten zbiór:

| część          | n  | recall | precision |
|----------------|---:|-------:|----------:|
| treść główna   | 47 | 0.9999 | 0.9995    |
| przypisy       | 41 | 0.968  | 0.883     |
| załączniki     | 18 | 0.997  | 0.962     |

Wynik jest lepszy niż na próbach deweloperskich poniżej. W tej próbie trafiło się mniej
dużych tabel. Traktuj to jako jeden pomiar, nie jako gwarancję.

**Czego ta miara nie sprawdza:** podziału na akapity, nagłówków (`##### Art.`), tabel ani
kolejności tekstu wewnątrz tabel. Porównuje tylko ciąg słów. Strukturę mierzy osobno
`eval/structure.py` (niżej).

Próby deweloperskie (na nich stroiłem, więc liczby są zawyżone), wersja 0.2:

| część          | seed 2024 (n, R, P)       | seed 7 (n, R, P)       |
|----------------|---------------------------|------------------------|
| treść główna   | 49, 0.993, 0.984          | 50, 0.999, 0.998       |
| przypisy       | 41, 0.954, 0.879          | 45, 0.971, 0.745       |
| załączniki     | 24, 0.934, 0.826          | 29, 0.996, 0.829       |

Między wersjami 0.1 a 0.2 precision treści głównej na próbie seed 7 wzrosła z 0.109 do 0.998.
To efekt obsługi obróconych stron (np. ustawa budżetowa DU/2024/122). Wyniki per akt: `eval/results_*.txt`.

Odtworzenie wyników:

```sh
pip install -e '.[eval]'
python eval/fetch_sample.py 50 99                 # pobiera PDF + HTML do ~/cache/eli
python eval/evaluate.py eval/test_2024_s99.json
python eval/fetch_sample.py 50 5102 && python eval/structure.py eval/test_2024_s5102.json
```

### Struktura: nagłówki i akapity (od 0.5.0)

HTML aktów z 2024 r. oznacza każdą jednostkę redakcyjną (`id` z `arti`, `para` (§), `pass` (ust.),
`pint` (pkt), `lett` (lit.), `chpt` …). `eval/structure.py` wyrównuje słowa HTML i Markdown
(jak wyżej) i sprawdza:

- **nagłówki R**: odsetek artykułów (w aktach bez artykułów: §) najwyższego rzędu, które w Markdown
  są nagłówkiem `#####` w tym samym miejscu; **nagłówki P**: odsetek nagłówków `#####`, które
  stoją na początku takiej jednostki (fałszywy nagłówek to np. cytowany artykuł nowelizacji);
- **ust./pkt/lit. R**: odsetek jednostek danego rodzaju, od których zaczyna się akapit;
- **podziały P**: odsetek początków akapitów, które w HTML są początkiem bloku (jednostki,
  akapitu, komórki tabeli). Podziały w tytule aktu liczę osobno;
- **podziały R** (od 0.6.2): odsetek początków bloków HTML poza tabelami, w których zaczyna się akapit.
  Pomijam komórki tabel (tabele są spłaszczone wiersz po wierszu) i początek tekstu jednostki tuż po jej numerze
  (HTML trzyma numer „1)” i tekst w osobnych blokach). Bez tej miary zlewanie akapitów poprawiało wynik P.

Wersje 0.5.x powstały po tym pomiarze. Znalazł on błędy, których miara słów nie widziała:
cyfry w indeksie górnym (`Art. 41¹`, `m²`) zamieniane na odnośniki do przypisów oraz cytowane
artykuły nowelizacji oznaczane jako nagłówki. Próby deweloperskie (seed 2024 i 7) posłużyły do
poprawek. Każdą próbę odłożoną zapisałem w gicie przed oceną i oceniłem jeden raz. Każdy test
wykazał błąd, który poprawiłem w kolejnej wersji, więc następną wersję mierzyłem już na nowej próbie:

| treść główna / załączniki                    | test s20260929 (47)<br>0.4.0 → 0.5.0 | test s5101 (44)<br>0.4.0 → 0.5.1 | test s5102 (42)<br>0.4.0 → **0.5.2** |
|----------------------------------------------|---------------------|-------------------|-------------------|
| nagłówki R, treść główna                     | 1.000 → 1.000       | 1.000 → 1.000     | 1.000 → 1.000     |
| nagłówki P, treść główna                     | 0.821 → 1.000       | 0.710 → 0.791     | 0.918 → **1.000** |
| nagłówki R, załączniki (teksty jednolite)    | 0.901 → 1.000       | 1.000 → 1.000     | 0.999 → **0.984** |
| ust. R, treść główna                         | 0.975 → 0.997       | 0.951 → 1.000     | 0.929 → **0.997** |
| cytowane § R, treść główna                   | 0.987 → 0.789       | 1.000 → 1.000     | 1.000 → 1.000     |
| podziały P, treść główna                     | 1.000 → 1.000       | 0.999 → 1.000     | 1.000 → 1.000     |
| słowa R, treść główna                        | 0.9959 → 0.9960     | 0.9987 → 0.9995   | 0.9967 → 0.9984   |
| słowa P, treść główna                        | 0.9996 → 0.9996     | 0.9987 → 0.9983   | 0.9989 → 0.9969   |

Co wyszło w testach i co z tym zrobiłem:
- s20260929: cytowane § w kodeksach („Art. 14t. § 1. …”, DU/2024/1685) przestały zaczynać akapit.
  Poprawione w 0.5.1.
- s5101: 29 fałszywych nagłówków. „”” jako znak sekund we współrzędnych (16°41’56,70”) zamykał cytat
  (DU/2024/303), a „Art. 30. „1. …” (cytat zaczyna się po numerze) był nagłówkiem (DU/2024/1288).
  Poprawione w 0.5.2. Wynik 0.5.2 na próbach s20260929 i s5101 to 1.000 dla nagłówków, ale te próby
  nie są już dla tych poprawek niezależne.
- s5102 (0.5.2): **regresja** nagłówków w załącznikach, 14 z 880.
  W DU/2024/610 w samym oficjalnym tekście brakuje cudzysłowu zamykającego („zwany dalej „kodem
  świadczenia;”), więc konwerter uznaje resztę załącznika za cytat i nie robi tam nagłówków.
  Śledzenie cudzysłowów ma tę wadę: jeden niedomknięty cudzysłów w źródle wyłączał nagłówki do końca
  załącznika. W 0.5.3 cudzysłów otwarty w środku zdania i niedomknięty kończy się z akapitem
  (DU/2024/610: 3/16 → 16/16; sprawdzone po fakcie na tej samej próbie, więc to nie jest niezależny wynik).
- Słowa P spada, bo HTML pisze wzory chemiczne zwykłym tekstem („P2O5”, jeden token), a wynik ma
  „P₂O₅” (cztery tokeny). Wcześniej wynik miał tu „P[^2]O[^5]”.
- Pozostałe miary (pkt, lit., podziały w załącznikach) się nie zmieniły. Najsłabsze są lit. w załącznikach
  (0.916 w s5101) i podziały w tabelach (P 0.87–0.97 w próbach deweloperskich; każda linia komórki
  tabeli jest osobnym akapitem).


**0.5.3.** Próba s5103 (41 aktów) nie zawierała przypadku z DU/2024/610 i dała dla 0.5.2 i kandydata
0.5.3 identyczne wyniki. Pokazała za to trzy nowe błędy: ust. R w treści głównej 0.936 (147/157),
pkt 0.967, lit. 0.959, a słowa R w DU/2024/876 tylko 0.790:
- niektóre rozporządzenia składane są z odstępem między jednostkami 2 pt zamiast 6 pt (DU/2024/1134, 591).
  Próg 0.45 × rozmiar czcionki go nie widział, więc ust./pkt/lit. sklejały się w jeden akapit. W zbiorze
  2025–2026 taki wzorzec („…: a) …; b) …” w jednym akapicie) miało 347 z 3168 plików. Teraz jednostka zaczyna
  akapit także wtedy, gdy odstęp jest o >1,2 pt większy od zwykłego na tej stronie albo gdy poprzednia
  linia kończy się przed prawym marginesem;
- obramowanie tabeli o szerokości kreski nad przypisami (~144 pt) było brane za tę kreskę, więc dół
  tabeli trafiał do przypisów (DU/2024/876). Teraz kreska musi być wolnostojąca;
- wyraz złożony przeniesiony na dywizie („rolno-” / „-środowiskowy”) dawał „rolno- -środowiskowy”
  (w danych 0.5.2: 421 plików). Miara słów tego nie widzi (dzieli na dywizach).

Po poprawkach nowa próba s5104 (46 aktów), ocena jednorazowa:

| s5104, 0.5.2 → 0.5.3              |                   |
|-----------------------------------|-------------------|
| nagłówki R / P, treść główna      | 0.980 → 0.980 / 1.000 → 1.000 |
| nagłówki R, załączniki            | 0.999 → 0.999     |
| ust. / pkt / lit. R, treść główna | 1.000 / 1.000 / 1.000 (bez zmian) |
| podziały P, treść główna          | 0.9995 → 0.9995   |
| słowa R / P, treść główna         | 0.9977 → 0.9984 / 0.9844 → 0.9837 |
| przypisy P                        | 0.741 → 0.865     |
| załączniki R (średnia po aktach)  | 0.917 → 0.975     |

s5104 ma mało aktów składanych „na ciasno”, więc główna poprawka jest tu prawie niewidoczna; na próbach
deweloperskich pkt R 0.995 → 1.000, lit. R 0.992 → 1.000, przypisy P 0.879 → 0.911 i 0.745 → 0.853.
Test pokazał jeszcze jeden błąd, obecny też w 0.5.2: w DU/2024/553 akapit załącznika „Art. 42 ust. 1
ustawy określa…” sprawiał, że cały akt dostawał nagłówki `##### Art.`, więc § w treści głównej ich nie
miały (nagłówki R 0/3). Poprawione w 0.5.3 po teście: jednostka nagłówka jest wybierana osobno dla treści
głównej i każdego załącznika. Na próbach deweloperskich nic to nie zmienia, a w DU/2024/553 daje 3/3,
ale s5104 nie jest już dla tej poprawki niezależna. Kolejna wersja dostanie nową próbę.

Wyniki per akt: `eval/structure_test_*.txt`, `eval/structure_dev_*.txt`, `eval/results_test_*.txt`.
Po zmianie tokenizacji w 0.5.0 (`41¹` → `41 1`, jak w HTML) liczby słów różnią się od starszych
plików w czwartym miejscu po przecinku.

**0.6.2: interlinia.** Niektóre akty są składane z odstępem między liniami akapitu większym niż 0,45 rozmiaru
czcionki (DU/2024/853: 7 pt przy 12 pt; załączniki DU/2024/440, 1337, 1442), a stały próg robił z każdej linii osobny
akapit (podziały P w załączniku 440: 0.35). Teraz próg jest liczony dla każdej strony: dolny kwartyl odstępu przed
liniami zaczynającymi się małą literą (kontynuacje akapitu) + 0,1 rozmiaru, co najmniej 0,45. Na stronach z takim
podniesionym progiem „1)”, „a)”, „Art.”, „§” na początku linii zaczynają jednostkę, „1.” i „– ” tylko po końcu zdania,
a linia kończąca się przed prawym marginesem kończy akapit (bez tego w 440 nagłówki sekcji zlewały się z tekstem;
wykryła to dopiero miara R, poprawione przed testem). Mediana zamiast kwartyla psuła uchwałę SN DU/2024/1883 (kolejne
klauzule „po rozpoznaniu…”, „z udziałem…” zaczynają się małą literą).

| podziały (s5108: 0.6.1 → 0.6.2, pozostałe: 0.6.2.dev0 → 0.6.2) | P | R |
|---|---|---|
| **test s5108**, załączniki (41 aktów, ocena jednorazowa) | 0.953 → **0.989** | 0.997 → 0.997 |
| test s5108, treść główna | 0.999 → 0.999 | 0.999 → 0.999 |
| test s5107 (zużyty), treść główna | 0.878 → 0.936 | 0.999 → 0.999 |
| dev seed 2024, załączniki | 0.870 → 0.972 | 0.985 → 0.985 |
| dev seed 7, załączniki | 0.969 → 0.999 | 0.9938 → 0.9933 |

Na próbach zużytych i deweloperskich (s5107 i s2024, s7 też) porównuję 0.6.2.dev0 (0.6.1 + zmiana dla stron „cid”,
te same słowa i struktura) z 0.6.2. Słowa (evaluate.py) nie zmieniły się w żadnej próbie. ust./pkt/lit. R bez zmian.
Koszt: w DU/2024/440 7 z 264 prawdziwych podziałów zginęło (za to 533 fałszywe mniej), a przypięcie słów
w załącznikach s7 spadło 0.980 → 0.976 (ten sam akt: tabela pod pkt 2 trafia do ust. 1).

Wyniki per akt: `eval/structure_test_s5108_v0.6.*.txt`, `eval/structure_dev_s*_v0.6.2.txt`.

### Kontrola bez wzorca: akty 2025–2026

Dla aktów z 2025 r. i później nie ma oficjalnego HTML, więc nie ma wzorca. `eval/selfcheck.py`
porównuje słowa z Markdown ze słowami z warstwy tekstowej PDF (bez winiety i nagłówków stron).
Sprawdza tylko, czy tekst nie ginie. Poprawności kolejności i struktury nie sprawdza. Wynik dla
wszystkich 3155 aktów (2026-09-29):

| wersja | kept: mediana, <0.95, <0.8 | grounded: mediana, <0.95 |
|--------|----------------------------|--------------------------|
| 0.4.0  | 0.975, 225, 24             | 0.989, 41                |
| 0.5.2  | 0.9755, 220, 23            | 0.9894, 40               |
| 0.5.3  | 0.9755, 220, 23 (3168 aktów) | 0.9894, 40             |

kept to odsetek słów PDF obecnych w wyniku, grounded to odsetek słów wyniku obecnych w PDF.
Od 0.5.2 indeksy (`41¹`) liczę jako cyfry doklejone do słowa, bo tak czyta je `extract_words`
(„411”). Bez tego grounded spadał w aktach z wieloma indeksami, choć wynik był poprawniejszy.
Od 0.6.3 tak samo indeks z literą (`22¹ᵃ` → „221a”). Indeks w nawiasach z PDF-ów z 2026 r. (`479[30f]`) sklejam
po stronie PDF ze słowem przed nim („47930f”), bo wynik ma go bez nawiasów (`479³⁰ᶠ`). Bez tego poprawiony
wynik wypadał gorzej (średni kept w 20 aktach z takimi indeksami: 0.9754 → 0.9674 w starej mierze,
0.9719 → 0.9753 w nowej; `eval/indices_2026_v0.6.3.dev.md`).
Od 0.6.4.dev znaki alfanumeryczne matematyczne (`𝑘` we wzorach Worda) liczę po obu stronach jako zwykłe litery,
a podwojony glif Cambria Math (`𝑘𝑘`) po stronie PDF jako jedną literę. Miara porównuje więc to, co widać
(`eval/math_glyphs_0.6.4.dev.md`).

Obejrzałem tylko najgorszy przypadek, DU/2025/243. To wzór formularza z kilkoma nakładającymi się
warstwami tekstu, a wynik jest tam częściowo pomieszany. Pozostałych nie przeglądałem.
Strony bez warstwy tekstowej (skany) są dla tej kontroli niewidoczne. Wynik je tylko oznacza.

## OCR stron bez warstwy tekstowej (od 0.6.0, opcja `--ocr`)

```sh
sudo apt install tesseract-ocr tesseract-ocr-pol      # wymagane; opcjonalnie np. -por -fra -ell
eli2md DU/2025/1604 --ocr -o DU-2025-1604.md           # język dobierany dla każdej strony (auto)
eli2md DU/2025/1604 --ocr pol+eng                      # jeden zestaw języków dla wszystkich stron
python -m eli2md.dataset --root dane/ --ocr            # zbiór: nowe akty i akty ze skanami jeszcze bez OCR
```

Domyślnie wyłączone. Strona bez warstwy tekstowej jest renderowana w 300 dpi i czytana przez
tesseract (`eli2md/ocr.py`). W Markdown przed jej tekstem stoi notka
`> [Strona 5 PDF nie ma warstwy tekstowej. Tekst poniżej odczytał OCR (tesseract 5.5.0, pol+eng). Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]`,
a każdy akapit OCR jest cytatem blokowym (`> tekst`), żeby nie mylił się z tekstem z warstwy PDF
(w JSON to węzły `ocr`, nigdy jednostki). We front matter są pola `pages_ocr` i `ocr`.
`pages_without_text` zostaje (opisuje PDF).
Strona, z której OCR daje mniej niż 20 słów albo medianę pewności słów poniżej 80
(mapy, nuty, podpisy), dostaje tylko dawną notkę. Tekst OCR nigdy nie jest nagłówkiem `#####`.

Tryb `auto`: najpierw `pol+eng`. Jeśli wynik jest nieczytelny, orientacja strony wg OSD
(formularze drukowane w poziomie, np. DU/2025/15) i ewentualnie pismo (grecki → `ell`).
Jeśli słowa funkcyjne wskazują inny język (pt, fr, de, es, sv, it) i są jego dane, strona jest
czytana jeszcze raz w tym języku. Bez tych danych zostaje wynik `pol+eng` bez części znaków
diakrytycznych (não → nao).

**Jak mierzę (bez ręcznego wzorca).** Strony *z* warstwą tekstową renderuję w 300 dpi, robię OCR
i porównuję słowa z warstwą tekstową tej strony (`eval/ocr_eval.py digital`, tokeny i difflib jak
w `evaluate.py`). Próba: 95 stron z aktów 2025–2026 (seed 7310; jedna losowa strona z losowego aktu,
55 z umów międzynarodowych i oświadczeń rządowych, 40 z innych aktów). Wyrenderowana strona cyfrowa
jest czystsza niż skan, więc to **górna granica** jakości na skanach. Wynik `pol+eng` z `fix_text`
(tak działa `--ocr`):

| strony                     | n  | recall (mediana / micro) | precision (mediana / micro) | recall liczb (micro) |
|----------------------------|---:|--------------------------|-----------------------------|---------------------:|
| wszystkie                  | 95 | 0.984 / 0.972            | 0.989 / 0.976               | 0.881                |
| tekst po polsku            | 79 | 0.989 / 0.982            | 0.993 / 0.986               | 0.908                |
| tabele, listy (język „?”)  | 14 | 0.963 / 0.830            | 0.967 / 0.836               | 0.613                |

Liczby to tokeny z cyfrą. Część strat nie jest błędem OCR: tabele i kolumny OCR czyta w innej
kolejności (recall bez kolejności: 0.978 wszystkie, 0.987 po polsku), a w warstwie tekstowej
odnośniki przypisów są doklejone do słów („wsi1”), których OCR nie odtwarza. Najczęstszy błąd
liczb to samotne „1” czytane jako „|”; `fix_text` poprawia je po słowach jak „ust.”, „art.”,
„Ustęp” (recall liczb na stronach po polsku 0.897 → 0.908). `pol` i `pol+eng` dają prawie to samo,
`eng` na polskich stronach ma recall 0.72. Wyniki: `eval/ocr_eval_digital_s7310.txt`.

Na prawdziwych skanach nie mam wzorca. Kontrola wzrokowa czterech stron polskich i angielskich
(`eval/ocr_eval_visual_check.txt`, to nie pomiar): 0–3 błędy w treści na ok. 110–230 słów
(np. „się” → „sie”, „II” → „H”, „1” → „|”); odnośniki przypisów w indeksie górnym są zniekształcone,
podpisy dają śmieci. Strony portugalskie i francuskie czytane `pol+eng` tracą diakrytyki, grecka
to śmieci. Z danymi `por` i `fra` sprawdzone fragmenty nie miały różnic; z `ell` grecki tekst ma
medianę pewności 92.7 (nie sprawdzałem go litera po literze).

**Co jest na 1734 stronach bez tekstu** (`eval/ocr_eval_scans_poleng.txt`, OCR `pol+eng` wszystkich
stron). Każda to obraz całej strony razem z nagłówkiem Dziennika Ustaw. Mediana pewności słów
jest ≥ 90 na 1600 stronach (na stronach cyfrowych z próby wyżej: 92 z 95 stron ≥ 95, mediana 96.4).
Kryteria z `--ocr` przyjmuje 1618 stron. Język wg słów funkcyjnych: polski 907, angielski 347,
portugalski 43, francuski 37, szwedzki 11, hiszpański 2, bez rozpoznanego języka 271 (tabele, listy,
legendy map). Odrzuconych 115, m.in. mapy (np. DU/2025/57, 348), obrócone formularze, nuty, prawie
puste strony i 9 stron umowy z Grecją (DU/2026/968, wersja grecka; z `auto` i danymi `ell` 8 z nich
ma tekst). Jedna strona (DU/2026/14 s. 19, formularz na tle gilosza) zajęła tesseractowi ponad
10 minut, dlatego limit to 120 s na stronę. Tekstu tych skanów nie znalazłem w warstwie tekstowej
innych aktów 2025–2026 (sprawdzone DU/2025/29, 360, 370: 0 z 36 losowych fragmentów po 8 słów).

**Koszt.** Ok. 2.1 s CPU tesseracta na stronę (1 wątek, i5-1335U, 40 losowych stron) plus 0.2 s
renderowania; 1734 strony to ok. 66 min jednego wątku. `auto` czyta część stron drugi raz
(inny język, obrót). Nowe akty: średnio 83 strony bez tekstu na miesiąc (od 1 do 306).

## Znane ograniczenia

- Tabele są spłaszczane do akapitów (komórki wierszami), wzory do zwykłego tekstu. Grafik i skanów
  nie ma w wyniku (od 0.4.0 miejsce jest oznaczone notką).
- Wzory formularzy z kilkoma warstwami tekstu bywają pomieszane (np. DU/2025/243).
- Strony z tekstem obróconym (tabele w poziomie na stronie pionowej) czytam w obróconym układzie
  (od 0.2). Tekst w innym kierunku niż reszta strony, np. pionowe nagłówki kolumn, trafia na
  koniec strony.
- Załączniki bywają wklejonymi PDF-ami, a ich pierwotny nagłówek jest w Dzienniku Ustaw zakryty.
  Taki ukryty tekst wykrywam heurystycznie: renderuję stronę i sprawdzam, czy pod znakiem jest tusz.
  Mogą zostać pojedyncze duplikaty.
- Objaśnienia pod formularzami w załącznikach bywają brane za przypisy. Niska precision przypisów to jednak
  w dużej części cecha wzorca: w obwieszczeniach z tekstem jednolitym HTML podaje przypisy tego tekstu jako zwykły
  tekst załącznika, a wynik jako przypisy (DU/2024/1580: 106 ze 112 przypisów wyniku jest w HTML tylko w treści,
  DU/2024/1442: 11 z 12). Wtedy spada też recall załącznika.
- Ciasno złożone tabele: do 0.6.2 pozycja „2) …” w komórce po krótkiej linii bez „;” doklejała się do „1) …”
  (MP/2025/121). Od 0.6.3 taka pozycja zaczyna nowy akapit (opis niżej, w zmianach 0.6.3). Mogą zostać inne
  układy komórek, w których podział ginie. Tekst jest wtedy pełny, brakuje tylko podziału.
- Wklejone wzory z Worda: niewidoczna kopia wzoru bywa w PDF-ie pod widocznym wzorem i trafia do wyniku
  jako powtórzony tekst (DU/2025/452 s. 7).
- Wzory Cambria Math: w 19 aktach DU 2025–2026 mapa ToUnicode daje jednemu glifowi dwie litery (`𝑘𝑘`).
  Od 0.6.4.dev zapisuję je pojedynczo („k”, nie „kk”). W czterech z nich (DU/2025/454, 459, 1743, 1744) mapa jest
  poza tym błędna i wzory pozostają nieczytelne. `eval/math_glyphs_0.6.4.dev.md`.
- Wklejony PDF z Worda pod przepisanym tekstem Dziennika (DU/2026/40 s. 2–6): widać z niego tylko wzory.
  Do 0.6.3 pdfplumber gubił znacznik `PlacedPDF` po zagnieżdżonym `/Span … EMC` wzoru, więc reszta ukrytej kopii
  w ogóle nie szła do testu tuszu. Od 0.6.4.dev znacznik zostaje (10 aktów 2025–2026). Test tuszu dalej przepuszcza
  ukryte litery, których ramka nachodzi na tusz innego tekstu, więc akapity przy wzorach bywają wymieszane.
- Umowy międzynarodowe: pierwsza strona (preambuła, art. 1) bywa obrazem tekstu na stronie, która ma warstwę
  tekstową z samym tytułem. Taka strona nie jest „bez tekstu”, więc OCR jej nie czyta i w wyniku brakuje treści
  (np. MP/2026/869).
- Domyślnie bez OCR. W 2025–2026 62 akty mają strony bez warstwy tekstowej (1734 z 53 356 stron
  w indeksie z 29.09.2026), głównie umowy międzynarodowe. OCR (`--ocr`, od 0.6.0) opisany niżej.

## Licencja

Kod: MIT. Teksty aktów normatywnych nie podlegają prawu autorskiemu (art. 4 pkt 1 ustawy
o prawie autorskim i prawach pokrewnych).
