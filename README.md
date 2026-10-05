# eli2md

Konwerter aktów z **Dziennika Ustaw** i **Monitora Polskiego** (PDF) do **Markdown** i drzewa jednostek w JSON,
z mierzoną jakością.
*Converts Polish Journal of Laws (and Monitor Polski) PDFs to Markdown; accuracy is measured against official HTML.*

> Status: **wersja 0.6.37**. Kod może zawierać błędy. Wiążący jest zawsze PDF opublikowany
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

W PDF-ach z lat 2000–2009 ogólne narzędzia (pdftotext, pdfplumber, pypdf, PyMuPDF, opendataloader-pdf) psują
polskie litery („Si∏ Zbrojnych”, „u˝ytkowej”), mieszają łamy i biorą sąsiednie akty z tej samej strony. Na 53 aktach
z HTML odczytują we właściwej kolejności 23–46% słów oficjalnego tekstu, eli2md 99,3%
([pomiar i tabela naprawiająca same litery](eval/extractors_2000_2009_s5207.md)).

## Gotowe dane

Przekonwertowane tym narzędziem, z indeksem i opisem jakości:
- [dziennik-ustaw-md](https://github.com/PolskiAgentW/dziennik-ustaw-md): Dziennik Ustaw 2025+ i akty 2020–2023 bez HTML,
  aktualizowane codziennie ([Hugging Face](https://huggingface.co/datasets/PolskiAgentW/dziennik-ustaw-md));
- [monitor-polski-md](https://github.com/PolskiAgentW/monitor-polski-md): Monitor Polski od 2012 r., aktualizowany codziennie
  ([Hugging Face](https://huggingface.co/datasets/PolskiAgentW/monitor-polski-md));
- [dziennik-ustaw-2000-2011-md](https://github.com/PolskiAgentW/dziennik-ustaw-2000-2011-md): akty z lat 2000–2011 bez HTML
  w API ([Hugging Face](https://huggingface.co/datasets/PolskiAgentW/dziennik-ustaw-2000-2011-md));
- [monitor-polski-2000-2011-md](https://github.com/PolskiAgentW/monitor-polski-2000-2011-md): Monitor Polski 2000–2011
  ([Hugging Face](https://huggingface.co/datasets/PolskiAgentW/monitor-polski-2000-2011-md));
- [dziennik-ustaw-1990-1999-md](https://github.com/PolskiAgentW/dziennik-ustaw-1990-1999-md): akty z lat 1990–1999 bez HTML
  w API, odczytane ze skanów przez OCR (od 0.6.26; publikowane rocznikami)
  ([Hugging Face](https://huggingface.co/datasets/PolskiAgentW/dziennik-ustaw-1990-1999-md)).

Ścieżka PDF dla [legalize-pipeline](https://github.com/legalize-dev/legalize-pipeline) (akty bez HTML → ich format):
gałąź [PolskiAgentW/legalize-pipeline@pl-pdf-fallback](https://github.com/PolskiAgentW/legalize-pipeline/tree/pl-pdf-fallback),
pomiar w [eval/legalize](eval/legalize/README.md).

## Użycie

```sh
pip install git+https://github.com/PolskiAgentW/eli2md
eli2md DU/2025/900 -o DU-2025-900.md      # pobiera metadane i PDF z API ELI
eli2md MP/2025/148                         # Monitor Polski (od 0.6.2)
eli2md plik.pdf                            # lokalny PDF, wynik na stdout
```

Z Pythona, gdy PDF jest już pobrany (np. `https://api.sejm.gov.pl/eli/acts/DU/2005/668/text.pdf`):

```python
from eli2md.pdf import convert, to_markdown

md = to_markdown(convert("text.pdf", position=668))
```

`position` to numer pozycji aktu. W Dz.U. do 2011 r. PDF aktu to strony całego zeszytu, a `position` wycina z nich ten
akt (DU/2005/668: 835 słów z `position`, 1291 bez). Metadane z API ELI w front matter: `to_markdown(doc, meta)`,
gdzie `meta` to JSON z `https://api.sejm.gov.pl/eli/acts/DU/2005/668`.

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
  (w zbiorze 0.5.3: 466 plików) i w JSON część przypisów ginęła. Kolejne akapity przypisu (np. punkty „1) wdraża…”)
  są wcięte o 4 spacje, jak wymaga składnia przypisów Markdown (od 0.6.7).
- Objaśnienia wydrukowane w treści (pod tabelą albo formularzem w załączniku, przypis cytowany przez nowelizację:
  „¹⁾ Niniejsza ustawa wdraża…”) nie są przypisami Markdown. Od 0.6.6 ich etykiety i odnośniki do nich w tym samym
  załączniku mają postać `¹⁾`, jak w druku. Etykietę poznaję po tym, że znacznik zaczyna linię (odnośnik jest
  doklejony do słowa). Odnośnik zostaje przypisem `[^n]`, gdy na jego stronie jest przypis o tym numerze.
  Wcześniej takie znaczniki były `[^1]` i prowadziły do przypisu aktu o tym numerze (DU/2025/1016: „Arsen[^1]”
  w tabeli załącznika → przypis o ministrze kierującym działem).
- Akapit z warstwy tekstowej zaczynający się od `>` albo `#` (np. `> 90 dni` w tabeli) jest poprzedzony `\`,
  żeby nie był cytatem blokowym (tak oznaczam OCR) ani nagłówkiem (od 0.6.1).
- Treść, której nie da się odczytać jako tekst, jest oznaczona notką w miejscu, gdzie występuje:
  `> [Strony 2-28 PDF nie mają warstwy tekstowej …]` (skany) oraz
  `> [Na stronie 7 PDF jest obraz …]` (obraz zajmujący ≥10% strony: wzór, rysunek, mapa).
  We front matter te same strony są w polach `pages_without_text` i `pages_with_images`.
  Tej treści nie ma w Markdown. Domyślnie konwerter nie robi OCR (opcja `--ocr` niżej; z nią obraz, który jest
  skanem tekstu ciągłego, dostaje tekst OCR zamiast notki, od 0.6.4). Od 0.6.1 stroną bez
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
`ocr` (akapit odczytany przez OCR, od 0.6.0; od 0.6.4 także z obrazu tekstu na stronie z warstwą tekstową). Jednostki cytowane w nowelizacjach nie są węzłami, tylko tekstem
(`"quoted": true`) jednostki, która je zawiera. Akapit bez numeru trafia do najgłębszej otwartej jednostki.
Wyjątek (od 0.6.0): tekst tuż po ostatnim punkcie wyliczenia, zaczynający się małą literą albo od „– ”
(„część wspólna”: „oraz zmian wynikających…”, „– w wysokości…”), trafia do jednostki nad wyliczeniem. Jeśli
potem przychodzi jednostka niższego rzędu (np. lit. po takim akapicie), akapit wraca do punktu: był dalszym
ciągiem jego tekstu rozbitym przez układ strony. „– ” po wyliczeniu nie jest tiretem, chyba że poprzedni akapit
kończy się dwukropkiem albo sam jest tiretem.

Numerowane wiersze tabel i formularzy nie są jednostkami (0.6.4, `eval/annex_rows_0.6.4.dev.md`): punkty
wykazów współrzędnych („6. 54°10′43,83″ N …”), karty akwenów od pierwszego wiersza „N.” z etykietą wielkimi
literami („5. FUNKCJA PODSTAWOWA”) do następnego § oraz wiersze tabel wstawiane przez nowelizację bez cudzysłowu
(„– – – lp. 8 otrzymuje brzmienie:” / „8. Program naukowo-badawczy 10.000 …”). Zostają tekstem w jednostce nad
nimi. Załączniki próby dev seed 2024: P 0.852 → 0.994 przy tym samym R; treść główna bez zmian.

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

**0.6.37** (2026-10-05). Poprawka do (2) z 0.6.36. Nagłówek załącznika z numerem pozycji samego aktu („Załącznik do
rozporządzenia … (poz. 753)”) zostaje załącznikiem także wtedy, gdy OCR odczytał podpis aktu dopiero po nim (DU/1994/753:
podpis w drugiej kolumnie; DU/1994/153: podpis wklejony w akapit § 2). W 0.6.36 taki nagłówek stawał się akapitem.
Znalezione przeglądem zmian 0.6.34 → 0.6.36 w DU 1990–1999 (lata 1990–1994: 12 nagłówków załącznika zamienionych
w akapit, z tego te 2 własne; pozostałe 10 bez zmian: załącznik cytowany w akcie zmieniającym, załączniki umów
międzynarodowych ogłaszanych w akcie, załączniki innego aktu z tych samych stron i załącznik, który OCR postawił przed
§ 17 aktu, DU/1990/448, gdzie w 0.6.34 § 17–18 i podpis trafiały do załącznika). Próby z HTML (s5401, s5402, s5403;
160 aktów) i 54 skany DU 2000: wynik każdego aktu taki sam jak w 0.6.36 (`eval/scans_1990_1999/*_v0.6.37.txt`,
`eval/scans_2000/all54_v0.6.37.txt`).

**0.6.36** (2026-10-05). Skany zeszytów sprzed 2012 r., dwie poprawki.
(1) Kolofon pod kolumnami. Na ostatniej stronie zeszytu pierwszy wiersz kolofonu bywa krótki i stoi w obrębie lewej
kolumny („Egzemplarze bieżące i z lat ubiegłych oraz załączniki można nabywać:”). Od 0.6.26 kolejność kolumn ze skanu
stawiała go za lewą kolumną, a przed prawą; obcięcie kolofonu zabierało wtedy całą prawą kolumnę ostatniego aktu
zeszytu (DU/2000/214: wyrok TK bez sentencji, R 0,464). Teraz wiersz, który zaczyna kolofon, zamyka obie kolumny.
(2) Załącznik cytowany w noweli. Nagłówek „Załącznik nr 3” w nowym brzmieniu załączników zmienianej ustawy (bez „„”,
które OCR zgubił) był brany za początek załączników aktu, a art. 3–12 i podpis lądowały w „załączniku”
(DU/2000/1315). Teraz nagłówek załącznika ze skanu zostaje tekstem aktu, gdy przed nim nie ma podpisu, a po nim jest,
albo gdy pierwszy artykuł po nim jest następnym artykułem aktu („Art. 3.” po „Art. 2.”).
Pomiar: 54 skany wśród 205 pobranych aktów DU 2000 z HTML (`eval/sample_2000_scans_n54_all.json`; spis, nie
losowanie): treść główna micro R 0,849 → 0,981, P 0,950 → 0,952 (0.6.35 → 0.6.36). Zmiana o więcej niż 0,005 w 8 aktach: R w górę
we wszystkich 8 (DU/2000/1315 0,177 → 0,957, 214 0,464 → 0,995, 921 0,515 → 0,988, 1215 0,624 → 0,985, 115 0,659 →
0,992), P w dół w 6 z nich o 0,006–0,019 (odzyskany tekst ma błędy OCR, np. „biedow”, „szkoty” w DU/2000/68). Próby z
HTML z lat 1990–1999 (s5401, s5402, s5403; 160 aktów): wynik każdego aktu taki sam jak w 0.6.34. Wyniki per akt:
`eval/scans_2000/all54_v0.6.3[56].txt`, `eval/scans_1990_1999/*_v0.6.36.txt`.

**0.6.35** (2026-10-05). Tylko wydajność, wynik bez zmian (ta sama zmiana jest w **0.6.25.2**). Sklejanie wierszy
akapitu (`_join`) przeszukiwało przy każdym wierszu cały dotychczasowy tekst akapitu; akt ze spłaszczonym spisem
inwentarza (MP/2021/437: PDF 57 MB, 6,6 MB tekstu) był przez to w `_join` jeszcze po 54 min konwersji. Teraz
sprawdzane są 3 ostatnie znaki (te same dopasowania). Sprawdzenie: 70 aktów (30 DU 2012+, 15 MP, 15 DU 2000–2011,
10 DU 1990–1999) — pliki identyczne z 0.6.34.

**0.6.34** (2026-10-05). Skany zeszytów: koniec aktu także bez podpisu tuż przed następnym aktem. Po załączniku
(tabela, wzór) następny akt zaczyna się od rodzaju i organu wersalikami i linii „z dnia D miesiąc RRRR r.” (DU/1993/2,
DU/1990/4); taki nagłówek kończy akt (przed gołym numerem pozycji nad nim, jeśli jest). Nie w obwieszczeniu (tytuł
ELI „Obwieszczenie …”: jego załącznikiem bywa ogłaszany akt) i nie przy nagłówku samego aktu powtórzonym w PDF
(ten sam rodzaj i organ, dzień i rok daty, temat podobny ≥ 0,75; DU/1993/397 ma akt dwa razy, ze spisem treści
zeszytu między nimi). Kandydaci z `heads.py` (60 aktów zbioru 0.6.31 z ≥ 2 nagłówkami): z jednym nagłówkiem 28 w 0.6.33,
50 w 0.6.34 (`eval/scans_1990_1999/heads_candidates_v0.6.34.txt`). Pozostałe 10 to m.in. akty bliźniacze tego samego
organu z tego samego dnia o temacie różnym dopiero w ostatnich słowach (DU/1993/299: „… z Republiki Finlandii” i „…
z Republiki Czeskiej”), których 0.6.34 nie rozdziela. Próby z HTML (s5403, s5401, s5402; 160 aktów): wynik każdego
aktu taki sam jak w 0.6.31 (`*_v0.6.34.txt`).

**0.6.33** (2026-10-05). Skany zeszytów (Dz.U. 1990–1999): wycinanie aktu, gdy OCR zgubił jego numer pozycji albo
koniec aktu. (1) Bez numeru akt dostawał wszystkie strony swojego PDF, czyli też koniec poprzedniego aktu i całe
następne (DU/1992/6: koniec 5 oraz całe 7 i 8). Teraz `convert()` dostaje tytuł aktu z ELI (`title`; `eli2md.dataset`
i `python -m eli2md` podają go z `meta.json`) i szuka na skanie nagłówka rodzaju i organu wersalikami z datą pod nim:
nagłówek podobny do tytułu (difflib ≥ 0,8), dzień i rok daty dokładnie, słowa po dacie podobne do reszty tytułu
(≥ 0,5; akty 5 i 6 z 1992 r. różnią się dopiero po 60 literach), nie za numerem następnego aktu (DU/1993/599:
„USTAWA z dnia 10 grudnia 1993 r.” pod numerem 600 to następny akt); przy remisie kandydatów nic nie jest cięte.
(2) Koniec aktu: numer następnego aktu doklejony do podpisu („Prezes Rady Ministrów: J. K. Bielecki 157”,
DU/1991/156) jest osobnym numerem; podpis z pauzą („Minister — Szef Urzędu Rady Ministrów: M. Strąk”, DU/1994/7)
i z przecinkiem po inicjale („W, Cimoszewicz”, DU/1997/7), nagłówek z pauzą albo plamką skanu („… MORSKIEJ |”,
DU/1998/428) kończą akt jak inne.
Pomiar: na próbach z HTML 1990–1999 (test s5403, 60 aktów; dev s5401, 40; s5402, 60) wynik każdego aktu taki sam jak
w 0.6.31 (`eval/scans_1990_1999/*_v0.6.33.txt`); żaden z tych aktów nie ma tej usterki. Na zbiorze 0.6.31 (akty bez
HTML z lat 1990–1998, rocznik 1998 w trakcie konwersji: 5 377 plików) 60 aktów ma ≥ 2 nagłówki rodzaju aktu wersalikami (`eval/scans_1990_1999/heads.py`,
lista `heads_candidates_0.6.31.txt`); w 0.6.33 28 z nich ma już jeden. Pozostałe 32 to m.in. teksty jednolite
i akty w załącznikach (poprawne) oraz następny akt po tabeli załącznika bez podpisu (DU/1993/2, DU/1990/4) — tego
0.6.33 nie rozpoznaje.

**0.6.32** (2026-10-05). Tylko `eli2md.dataset`, konwersja bez zmian (ta sama zmiana jest w **0.6.25.1**: 0.6.25 z tylko tą poprawką, dla workflow zbiorów). Akt, który zabija proces roboczy bez `MemoryError`
(przeliczenie MP 2012–2026 przy `--mem-limit-gb 1.6`: MP/2019/230, 304 strony, 270 z OCR), psuł pulę procesów,
a w nowej puli był znowu pierwszy: po 5 przebiegach 9 566 kolejnych aktów dostało `status=error` („MemoryError in an
earlier act”), a następny przebieg bez `--all` zaczynał od tego samego aktu. Teraz w toku jest najwyżej `--jobs`
aktów, wyniki są zapisywane w kolejności ukończenia, a po awarii puli akty, które były w toku, idą pojedynczo, każdy
w nowej puli: błąd („worker died”) dostaje tylko akt, który zabija proces. Test: `test_dataset_worker_over_memory_limit`
(6 aktów, `--jobs` 1 i 3) i ręcznie na prawdziwej puli (20 aktów, jeden kończy proces przez `os._exit`: 19 ok, 1 błąd).

**0.6.31** (2026-10-05). Skany: akt kończy się też tam, gdzie po jego podpisie zaczyna się tytuł następnego aktu
wersalikami (rodzaj aktu samodzielnego: rozporządzenie, ustawa, obwieszczenie…, nie załącznik, statut ani regulamin;
między nimi najwyżej sam numer), jeśli to wcześniej niż numer następnego aktu. Gdy numer następnego aktu nie został
odczytany albo odczytany jest dopiero dalszy, akt zawierał do 0.6.30 następny akt (DU/1990/271, 150). Numer pozycji ze
śmieciem ze skanu za nim („151 |”) jest numerem. Nie po nagłówku załącznika: załącznikiem obwieszczenia bywa akt.
Próby: dev bez zmian; test s5403 P 0,9718 → 0,9739 (lepiej 1 akt, gorzej 0). Rocznik 1990: aktów z więcej niż
jednym nagłówkiem rodzaju aktu 8 → 4.

**0.6.30** (2026-10-05). Skany: gdy numeru pozycji aktu nie ma w odczycie (akt zaczyna stronę, a numer w pasie
nagłówka znika razem z nim: DU/1990/100), a jest numer następnego aktu i żaden wcześniejszy, akt kończy się na numerze
następnego. Do 0.6.29 nie był wtedy wycinany i miał wszystkie następne akty z tych stron (w roczniku 1990: 63 z 433
aktów miały w tekście więcej niż jeden nagłówek rodzaju aktu, po 0.6.30: 8; w tych 8 numer następnego aktu też zginął,
a jego tytuł stoi po podpisie, np. DU/1990/150). Podpis z cyfrą zamiast inicjału („Prezes Rady
Ministrów: 7. Mazowiecki”) jest podpisem. Próby: dev s5401 P 0,9845 → 0,9862 (lepiej 1 akt), test s5403 P 0,9621 →
0,9718 (lepiej 5, np. DU/1994/396 P 0,454 → 0,971), R bez zmian, żaden akt gorzej.

**0.6.29** (2026-10-05). Skany w dwóch łamach: sam numer pozycji (2–4 cyfry) wyśrodkowany na stronie (± 1,5% szerokości
tekstu) zaczyna pas jak wiersz na całą szerokość. To numer aktu nad tytułem na całą szerokość („21” nad „USTAWA”,
DU/1993/20 s. 2); do 0.6.28 trafiał do lewego łamu przed koniec poprzedniego aktu z prawego, więc akt nie był
wycinany i miał początek następnego (znana usterka z 0.6.28). Próby: dev s5401 0,9862 / 0,9816 → 0,9862 / 0,9845
(lepiej 2 akty, gorzej 0); test s5403 0,9827 / 0,9518 → 0,9827 / 0,9621 (lepiej 6, gorzej 0; DU/1997/1041 P 0,378 → 0,985).
Szersza reguła (każdy krótki wiersz przy środku strony) psuła strony z wąskim odstępem między łamami (dev 0,9474).

**0.6.28** (2026-10-05). Skany (po kontroli wzrokowej DU/1990/380, akt bez HTML):
- poprawka słów uzupełnia też zgubione znaki diakrytyczne (jedna albo dwie litery: „Rozporzadzenie” → „Rozporządzenie”,
  „zycie” → „życie”, „pazdziernika” → „października”), nadal tylko gdy wynik jest jeden i znany słownikowi;
- „§” sklejony z numerem po przyimku przed dalszym ciągiem odesłania: „w 81 w ust. 1:” → „w § 1 w ust. 1:”, „w82:” → „w § 2:”;
- podpis poprzedniego aktu odczytany po numerze następnego wraca przed ten numer (był na początku następnego aktu);
- nagłówek strony nad oboma łamami nie jest dzielony na łamy („Poz. 380 i 381” zostawał w tekście).
Próby: dev s5401 0,9853 / 0,9804 → 0,9862 / 0,9816 (lepiej 16 aktów, gorzej 2: DU/1992/20 R 0,948 → 0,923,
DU/1993/181 P 0,940 → 0,937); test s5403 0,9813 / 0,9498 → 0,9827 / 0,9518 (lepiej 27, gorzej 4, każdy o ≤ 0,003).
Na 300 aktach DU 2000–2011 z poprawną warstwą (`eval/scans_1990_1999/word_fixes_on_clean_text.py`) zmienione słowa
307 → 456 z 413 584 (głównie fragmenty z warstwy i kilka słów niemieckich: „das”, „zur”).
Znana usterka: gdy OCR nie da numeru pozycji następnego aktu jako osobnego akapitu przed jego rodzajem (numer sklejony
z tekstem drugiego łamu), akt kończy się dopiero z końcem PDF-a, więc ma też początek następnego aktu z ostatniej
wspólnej strony (DU/1993/20: P 0,577).

**0.6.27** (2026-10-05). Poprawka słów ze skanów (0.6.26) nie zmienia słów, które zna słownik angielski (en_US),
ani akapitów, których słowa funkcyjne są w innym języku (umowy drukowane w dwóch językach: „final” zostaje „final”,
nie „finał”). Sprawdzenie na 300 losowych aktach DU 2000–2011 z poprawną warstwą tekstową (413 584 słowa, każda zmiana
to błąd albo naprawa fragmentu, który już w źródle nie jest słowem): zmienione słowa 501 (0.6.26) → 307, w umowach,
konwencjach i oświadczeniach rządowych 199 → 10; pozostałe to głównie fragmenty z warstwy („osługiwać”, „asady”)
i sklejenia („wsprawie” → „w sprawie”). Próby DU 1990–1999 dev i test: wynik taki sam jak 0.6.26.

**0.6.26** (2026-10-05). Skany zeszytów Dziennika Ustaw sprzed 2012 r. (opis wyżej, „Skany zeszytów sprzed 2012 r.”).
Dotyczy tylko konwersji z `--ocr` stron ze skanami starych zeszytów; w PDF-ach DU i M.P. z lat 2012–2026 (cały cache
zbiorów) nie ma ani jednego z czcionką „HiddenHorzOCR”, a ich strony z OCR nie mają nagłówka „Dziennik Ustaw Nr”.
Pomiar (`eval/evaluate.py --ocr`, wzorzec: oficjalny HTML aktów 1990–1999, które go mają):

| próba | 0.6.25 (warstwa Acrobata) body R / P | 0.6.26 body R / P | aktów z R < 0,90 (0.6.25 → 0.6.26) | załączniki R (0.6.25 → 0.6.26) |
|---|---|---|---|---|
| dev s5401 (n=40, na niej strojone) | 0,6697 / 0,6161 | 0,9853 / 0,9804 | 32 → 2 | 0,2432 → 0,9508 (n=6) |
| test s5403 (n=60, niewidziana) | 0,6638 / 0,5679 | 0,9813 / 0,9498 | 52 → 6 | 0,3644 → 0,9605 (n=6) |

R = odsetek słów oficjalnego tekstu odczytanych we właściwej kolejności, P = odsetek słów wyniku obecnych w oficjalnym
tekście. Na próbie dev: OCR bez kolejności łamów 0,9689 / 0,9599, z kolejnością łamów 0,9759 / 0,9717, z poprawką
słów ze słownikiem 0,9853 / 0,9804 (ani jeden akt gorzej, 30 z 40 lepiej). Poprawka słów potrzebuje libhunspell
i słownika `hunspell-pl` (`apt install libhunspell-1.7-0 hunspell-pl`); bez nich tekst zostaje bez niej. Słowo, którego
słownik nie zna, jest zmieniane tylko wtedy, gdy dokładnie jedna zamiana „t”/„l” na „ł” (jedna albo dwie litery) daje
słowo znane („ogtoszenia” → „ogłoszenia”, „Zatącznik” → „Załącznik”), albo gdy oddzielenie jednoliterowego przyimka
daje słowo znane („Wrozporządzeniu” → „W rozporządzeniu”); do tego „wart.” → „w art.”, „zdnia” → „z dnia”.

Na próbie s5402 (n=60) wersja przed dwiema ostatnimi poprawkami (wycinanie aktu, gdy między numerem a rodzajem aktu
stoi podpis albo numer strony spisu treści) dała 0,9576 / 0,9363 (0.6.25: 0,6738 / 0,5662); te poprawki powstały po
obejrzeniu jej wyników, więc liczbą testową jest s5403. Skany z 2000 r. (s5202, s5205): DU/2000/70 R 0,937 → 0,982,
DU/2000/179 0,991 → 0,991, DU/2000/985 0,986 → 0,986 (bez poprawki słów). Najczęstsze błędy, które zostają: „ł” odczytane jako „t”
(„ogtoszenia”), brak spacji („wart.” zamiast „w art.”), pierwsza strona zeszytu ze spisem treści (krótki akt pod spisem:
DU/1999/728 R 0,792), słabe skany (DU/1990/390). Wyniki: `eval/scans_1990_1999/`.

**0.6.25** (2026-10-04). Teksty jednolite: cztery klasy usterek z pomiaru `eval/tj_survey_2026-10-04.md`.
- Linia „Art. 266–280.” albo „Art. 22–28. (pominięte)” (artykuły pominięte w tekście jednolitym) jest nagłówkiem
  `##### Art. 266–280.`, w JSON węzłem `art` z numerem „266–280” („Art. 41a–Art. 41i.” → „41a–41i”). Do 0.6.24 była
  zwykłym akapitem na końcu poprzedniego artykułu (DU/2026/1245 art. 265).
- Przypisy z etykietą literową a) … z), za) (w obwieszczeniach: „Zmiany tekstu jednolitego wymienionej ustawy zostały
  ogłoszone…”) są przypisami `[^a]:`, a odnośnik „z późn. zm.b))” w tekście to `[^b]`. Przypis tytułu ustawy drukowany
  jako „1)I) Niniejsza ustawa…” jest przypisem `[^1]:`. Do 0.6.24 takie przypisy były akapitem na końcu ostatniego
  artykułu (DU/2026/1245 art. 305) albo doklejały się do poprzedniego przypisu. Przypis z etykietą w zwykłym druku
  dostaje definicję tylko wtedy, gdy tekst ma jego odnośnik (definicji, do której nic się nie odwołuje, podgląd Markdown
  nie pokazuje); mały „b)” w tekście bez przypisu b) zostaje „b)”. Druga lista „1) …” w jednym przypisie („Niniejsza
  ustawa służy stosowaniu:”, DU/2026/43) nie rozbija go już na osobne przypisy.
- „(uchylony)” albo „(pominięty)” na dole strony kończy akapit: nagłówek z następnej strony („KSIĘGA PIERWSZA”,
  DU/2026/468 art. 1096) nie dokleja się do artykułu.
- Artykuł z literą „ł” (art. 106ł po art. 106l, DU/2025/633) ma własny nagłówek.

Pomiar (`eval/tj_survey/`, liczby w `eval/tj_survey/summary_0.6.24_vs_0.6.25.json`): 404 teksty jednolite z
dziennik-ustaw-md przeliczone 0.6.24 i 0.6.25 z tych samych PDF, artykuły porównane z wcześniejszym tekstem jednolitym
w HTML, a różne od niego sprawdzone z warstwą tekstową PDF. Artykuły do oceny: 286 → 189, żaden nowy. Klasy: linia
zakresu 61 → 0, przypis w treści 47 → 10, nagłówek w akapicie 4 → 1, artykuł z „ł” 4 → 0. W żadnym z artykułów, które
zostały w klasach „przypis w treści” i „inne”, wynik nie ma w treści tekstu przypisu: nadmiar jest po stronie PDF
(przypis tytułu z listą albo przypis z etykietą rzymską, np. „I) Odnośnik dodany przez…”, którego porównanie nie
zdejmuje w całości). 8 artykułów przeszło z „przypisu w treści” do „inne” albo „układu” przy tej samej treści w obu
wersjach. Na KPC, KC i KP z 2026 r. `tj_check.py --html`: 0 artykułów do oceny (0.6.24: 3).
Różnice 0.6.24 → 0.6.25 (`eval/tj_survey/md_diff.py`): 273 z 404 plików, w każdym te same znaki (zmieniają się
nagłówki, przypisy i podział akapitów). Próba 360 innych aktów (DU i M.P. z lat 2000–2011, 2012–2024 i 2025–2026,
po 60, `random.Random(20261004)`): zmienione 6 plików, 4 z nagłówkami zakresu, 1 z art. 48ł, 1 z przypisami a), b).
Przypis z etykietą rzymską w zwykłym druku („I) Odnośnik dodany przez…”) dalej dokleja się do poprzedniego przypisu.

**0.6.24** (2026-10-03). Wycinanie aktu ze strony zeszytu (do 2011 r.) odczytanej przez OCR: numer pozycji zaczyna akt
także wtedy, gdy między nim a rodzajem aktu stoi numer rejestru („626” + „Rej. 182/2000 POSTANOWIENIE …”, postanowienia
Prezydenta w M.P.) albo gdy OCR zgubił polskie litery w rodzaju aktu („OSWIADCZENIE RZADOWE”). Do 0.6.23 taki akt nie
był wycinany: plik miał całe strony, z końcem poprzednich i początkiem następnych aktów (MP/2000/626: 521 słów zamiast
142). Na 49 aktach z OCR, w których tekście został ich własny numer (29 z M.P., 20 z DU 2000–2011), 0.6.24 wyciął
23 z M.P. (MP/2000/611–634, MP/2002/122); w DU żaden nie zmienił się przez tę poprawkę. Przy przeliczeniu wszystkich
3 425 aktów z OCR z DU 2000–2011 (2026-10-04) 0.6.24 wyciął jednak 5 aktów z 2000 r.
(DU/2000/71, 89, 90, 101, 1343; razem −1 209 słów tekstu sąsiednich pozycji).

**0.6.23** (2026-10-03). Strona zeszytu z lat 2000–2011 odczytana przez OCR: z pierwszego akapitu odczytu znika tylko
nagłówek zeszytu („Dziennik Ustaw Nr 32 — 2018 — Poz. 393”). Do 0.6.22 znikał cały akapit, a tesseract czasem łączy
nagłówek z tekstem pod nim w jeden akapit: MP/2008/470 nie miał żadnego tekstu, w DU/2000/393 z s. 126 zniknęły
„Objaśnienia do wzoru nr 3 …”. W losowej próbie 240 stron z OCR z DU i M.P. 2000–2011 tekst zniknął tak z 10 stron
(wszystkie w DU; zwykle tytuł albo pierwszy akapit formularza lub załącznika). Akty od 2012 r. bez zmian (inny nagłówek).

**0.6.22** (2026-10-01). Poprawka 0.6.21: strona jest najpierw czytana dokładnie jak w 0.6.19 (bez rozdzielczości), a tylko
gdy cała strona nie daje użytecznego tekstu, drugi raz z rozdzielczością; drugi odczyt jest brany, tylko gdy jest użyteczny.
Strony odczytane w 0.6.19 zostają więc takie same. W 0.6.21 część takich stron spadała poniżej progu pewności
(DU/2025/145: 0.6.19 59 stron z OCR, 0.6.21 53, 0.6.22 61 z 62). Dz.U. 2000 (22 akty z nieodczytanymi stronami): strony
z OCR 378 → 406, obrazy tekstu 4 → 4, żaden akt nie ma mniej stron. Wynik 0.6.20 na stronach cyfrowych (R 0,9706 → 0,9773)
dotyczy czytania każdej strony z rozdzielczością, czego 0.6.22 nie robi. 0.6.21 przeliczył 30 aktów w dziennik-ustaw-md
(2026-10-01 19:13), przeliczone ponownie w 0.6.22.

**0.6.21** (2026-10-01). Poprawka 0.6.20: rozdzielczość dostaje tylko obraz całej strony. Dla obrazu wyciętego ze strony
z warstwą tekstową (skan tekstu wklejony jako obraz) tesseract z rozdzielczością dzielił tekst na więcej linii i test „czy to
skan tekstu” odrzucał taki obraz (DU/2000/416 s. 7: 42 → 55 linii, tekst strony znikał); tego przypadku 0.6.20 nie mierzył.
Obrazy są więc czytane jak w 0.6.19, całe strony jak w 0.6.20. 0.6.20 działał ok. 25 minut (przeliczenia przerwane), żadne
opublikowane dane z niego nie pochodzą.

**0.6.20** (2026-10-01). OCR: obraz strony przekazywany do tesseracta ma zapisaną rozdzielczość (300 dpi). Bez niej
tesseract zgadywał ją z wysokości liter („Estimating resolution as 384”) i na stronach z tabelami gubił odstępy między
słowami („UrządCelnywkatowicach”, DU/2007/1006 s. 3), więc strona wypadała poniżej progu pewności i zostawała tylko notka.
Sprawdzenie: z 40 losowych takich stron Dz.U. 2000–2007 (z 1207) 16 daje teraz tekst (pewność 86–96); 40 losowych stron
już odczytanych zostaje odczytanych, średnia pewność 95,3 → 95,4 (`eval/ocr_dpi_check_2000_2007.json`). Na 95 stronach
cyfrowych z warstwą tekstową jako wzorcem (próbka s7310, `pol+eng`) słowa w kolejności R 0,9706 → 0,9773, P 0,9757 →
0,9792, liczby R 0,872 → 0,896, stron z R < 0,95: 10 → 6 (`eval/ocr_eval_digital_s7310_v0.6.20.txt`; kod sprzed zmiany
uruchomiony tego samego dnia dał te same liczby co 29.09).

**0.6.19** (2026-10-01). Kolofon na stronie odczytanej przez OCR. Linie z OCR nie mają położenia na stronie (wszystkie
mają górę 0), więc gdy ostatnią stronę zeszytu z ISSN czytał OCR, wycinanie kolofonu „od jego najwyższej linii w dół”
z 0.6.18 usuwało całą stronę: akt jednostronicowy wychodził pusty (DU/2000/48), dłuższy tracił ostatnią stronę
(DU/2000/135: 160 → 552 słów). Teraz na takiej stronie kolofon jest wycinany w kolejności czytania, więc znika też
kolofon odczytany przez OCR, który 0.6.18 zostawiał (DU/2000/175). Sprawdzenie (`eval/colophon_ocr_check.py`) na
opublikowanym Dz.U. 2000–2007: z 2463 aktów z OCR 300 ma ostatnią stronę bez warstwy tekstowej, 15 ma na niej kolofon
z ISSN (wszystkie z 2000 r.); każdy zyskał tekst (razem +3064 słów), 5 przestało być pustych, żaden nie stracił słów.
Wyniki: `eval/colophon_ocr_check_2000_2007_v0.6.19.json`. Poza tym: gdy akt jest ostatni w zeszycie, strona wydawcy
usunięta razem z kolofonem nie liczy się już do stron z obrazami (DU/2003/2317: „7-8” zamiast „7-8, 10”); tekst bez zmian.

**0.6.18** (2026-10-01). Kolofon zeszytu (Dziennik Ustaw do 2011 r.). Ostatnia strona zeszytu kończy się informacją
wydawcy: gdzie kupić egzemplarze, gdzie składać reklamacje, „Wydawca: …”, cena, ISSN; w 2000 r. bywa nad nią lista
wydawnictw z cenami. 0.6.17 wycinał ją od linii „Wydawca:” albo „Szanowni Państwo” w kolejności czytania, więc tekst nad
„Wydawca:” zostawał na końcu ostatniego aktu zeszytu (DU/2003/2317, DU/2000/1051), a gdy pierwsza linia bloku wpadła
w lewy łam, przecinał zdanie aktu z prawego łamu (DU/2003/1921: „…Rządem Repu- / Egzemplarze bieżące… / bliki
Słowenii”). Teraz blok zaczyna się też od „Egzemplarze bieżące”, „Reklamacje z powodu niedoręczenia”, „O wszelkich
zmianach nazwy”, „Dziennik Ustaw i Monitor Polski dostępne”, „Informacja o możliwości zakupu wydawnictw”, „Tłoczono
z polecenia”, a wycinane jest wszystko od jego najwyższej linii w dół strony. Gdy nad nim zostaje tylko goły numer strony
i obraz, strona należy do wydawcy i znika cała (DU/2003/2317 s. 10). Tylko ostatnia strona z ISSN, więc akty od 2012 r.
(osobne PDF-y) się nie zmieniają. Sprawdzenie (`eval/colophon_check.py`): wszystkie akty 2000–2003 z ISSN na ostatniej
stronie przekonwertowane ponownie i porównane akapit po akapicie z 0.6.17: z 6383 aktów 506 ma ISSN na ostatniej
stronie, zmieniło się 276 (2000: 28, 2001: 64, 2002: 92, 2003: 92). W każdym ubył tylko tekst kolofonu; w 16 z nich
zdanie aktu przecięte kolofonem jest znów całe (DU/2001/1144, DU/2003/2123 …). Wyniki:
`eval/colophon_check_2000_2002_v0.6.18.json`, `eval/colophon_check_2003_v0.6.18.json`. Nie łapie kolofonu odczytanego
przez OCR ze skanu ostatniej strony (DU/2000/175: warstwa tekstowa tej strony nie ma ISSN).

**0.6.17** (2026-09-30). Tylko `eli2md.dataset`. Paczki z 0.6.16 czekały na najwolniejszy akt każdej paczki
(przy MP 2020–2024 z OCR 5 z 6 procesów stało po kilkanaście minut). Teraz jest jedna pula, a proces po `MemoryError`
kończy się przy następnym akcie: pula zgłasza `BrokenProcessPool`, a akty jeszcze niezapisane idą do nowej puli
(do 5 przebiegów). Tracą się tylko akty, które w tej chwili były w toku; są konwertowane ponownie.

**0.6.16** (2026-09-30). Tylko `eli2md.dataset`. Poprawka 0.6.15 była zła: przy `max_tasks_per_child` CPython 3.14
nie uzupełniał puli po wymianie procesu i po 3 minutach konwersję robił jeden proces z 6. Teraz nowa pula procesów
powstaje dla każdej paczki 25 aktów na proces, więc proces po `MemoryError` oddaje najwyżej resztę swojej paczki.
Za przekroczenie pamięci uznaję też wyjątek pdfplumbera, który opakowuje `MemoryError` albo mówi „Unable to allocate”
(MP/2020/235): wcześniej był to zwykły błąd aktu, a proces dalej psuł następne.

**0.6.15** (2026-09-30). Tylko `eli2md.dataset`: proces roboczy jest wymieniany co 25 aktów
(`max_tasks_per_child`). W 0.6.13 proces po `MemoryError` oddawał do ponownej próby wszystkie kolejne akty z kolejki,
więc przy konwersji MP 2020–2024 4 z 6 procesów stało bezczynnie aż do drugiego przebiegu. Teraz oddaje najwyżej 24.

**0.6.14** (2026-09-30). Dz.U. 2000–2011, strony bez warstwy tekstowej czytane przez OCR (`--ocr`). W roczniku 2000
takich aktów jest dużo (15 z pierwszych 50 przekonwertowanych). Wycinanie aktu (0.6.8) działało tylko na warstwie
tekstowej, więc do aktu z OCR trafiały sąsiednie akty z tych samych stron i nagłówek zeszytu (DU/2000/56: cały akt 55).
Teraz akapit OCR „56 ROZPORZĄDZENIE …” daje numer aktu jak na stronie z tekstem, a nagłówek „Dziennik Ustaw Nr 5 Poz. …”
na początku strony OCR jest pomijany. Sam numer w osobnym akapicie liczy się tylko wtedy, gdy następny akapit to typ
aktu: na stronach dwułamowych OCR potrafi wstawić numer następnego aktu w środek reszty tego aktu (DU/2000/56 s. 2:
„57” przed „§ 3. …”), więc koniec aktu z OCR bywa nieodcięty. `eval/evaluate.py` ma opcje `--ocr` i `--only`.
Pomiar na 3 aktach bez warstwy tekstowej z prób s5202 i s5205 (z OCR; próby już zużyte, więc to nie jest pomiar
niezależny): DU/2000/70 R 0.937, P 0.863 → 0.912; DU/2000/179 R 0.991, P 0.823 → 0.987; DU/2000/985 R 0.986,
P 0.910 → 0.984. Błędy samego OCR zostają (np. „8 1.” zamiast „§ 1.”). Bez OCR wynik bez zmian (93 PDF-y 2012+
identyczne, dev bez zmian). Wyniki: `eval/ocr_textless_s520{2,5}_v0.6.{11,14}.txt`.

**0.6.13** (2026-09-30). Tylko `eli2md.dataset`, konwersja bez zmian. Po `MemoryError` (limit `--mem-limit-gb`)
proces roboczy zostaje z pamięcią przy limicie: jego kolejne akty kończyły się fałszywym `PdfminerException`,
a `MemoryError` przy czytaniu `meta.json` (poza `try`) zatrzymał cały przebieg (MP/2020/1070, konwersja
MP 2012–2024 2026-09-30, po 10 650 z 15 885 aktów). Teraz taki proces oddaje kolejne akty, a te są konwertowane
w nowej puli procesów (do 3 przebiegów). `meta.json` jest czytany w `try`. Test: `test_dataset_worker_over_memory_limit`.

**0.6.12** (2026-09-30). Dz.U. 2000–2011, załączniki: (1) kreska przypisów narysowana w łamie (InDesign, 2010–2011)
obejmuje tylko swój łam, gdy niżej na stronie zaczyna się załącznik (DU/2010/277 s. 6: przypis 5 był tekstem, a oba
załączniki, ok. 5 tys. słów, trafiały do treści głównej); (2) pod podpisem załącznik może się zaczynać od nowego
brzmienia załącznika zmienianej ustawy: „„ZAŁĄCZNIK — Część I” (DU/2004/895 s. 9). Obie zmiany znalazłem na
zużytych próbach (s5203, s5202; tam diagnostycznie treść P 0.9562 → 0.9889 i 0.9680 → 0.9816, załączniki R 0.9354 →
0.9968 i 0.9377 → 0.9890). Wynik 2012+ i dev bez zmian. **Test 2000–2011, s5206** (70 wylosowanych, 62 poza
wcześniejszymi próbami, zapisana przed oceną, oceniona raz): wynik identyczny z 0.6.11 (tych układów w próbie nie ma):
treść R 0.9991, P 0.9926; przypisy R 0.9696, P 0.9822; załączniki R 0.9853, P 0.9823; drzewo treści R 0.9994,
P 0.9997, załączników R 0.9626, P 0.9757. Luka miary: załącznik, który HTML podaje jako „patrz oryginał” (wzory
formularzy, DU/2007/1171), liczy się jako pełny wzorzec, więc tekst wzoru z PDF obniża P załączników.
Wyniki: `eval/*_test2000_s5206_*`.

**0.6.11** (2026-09-30). (1) Cytat, którego źródło nie zamyka, kończy się na następnej jednostce aktu
zmieniającego. W PDF-ach 2000–2011 zdarza się, że nowelizacja w nowelizacji zamyka tylko jeden z dwóch cudzysłowów
(DU/2007/162: „…sądu,”;”, w HTML „””;”) albo cytat nie ma zamknięcia wcale (DU/2004/895: pkt 17 kończy się
„…z późn. zm.).”). Wcześniej cała reszta aktu była „cytatem”: bez nagłówków `##### Art.` i bez punktów w JSON.
Teraz „Art. N.” (N = ostatni artykuł poza cytatem + 1, same cyfry) wraca do poziomu 0, chyba że numer kontynuuje
artykuły cytowane albo poprzedni akapit zapowiada cytat („…:”). To samo w drzewie dla „N) …” z poleceniem zmiany
(„otrzymuje brzmienie”, „dodaje się”, „w art. 34:” …), z numeracją cytatów liczoną osobno dla każdej głębokości
(DU/2008/539: „2) uchyla się art. 6a;” należy do cytowanej nowelizacji). (2) Strony o szerokości 576 pt (DU 2000:
4 z 60 PDF-ów) mają tekst w tym samym miejscu co strony 595 pt: granica lewego łamu i środek numeru aktu liczone
są od tekstu, nie od strony (DU/2000/839: łamy były przemieszane, a spis treści zeszytu zostawał w akcie).
Wynik 2012+ bez zmian (93 PDF-y: Markdown; 120 PDF-ów: drzewa JSON). Dev s2000: drzewo treści R 0.9540 → 0.9987,
P 0.9993; s2011, s2024, s7 bez zmian. **Test 2000–2011, s5205** (70 wylosowanych, 59 poza wcześniejszymi próbami,
zapisana przed oceną, oceniona raz; 58 ocenionych, DU/2008/59 ma pusty HTML): tekst bez zmian wobec 0.6.10 (treść
R 0.9525, P 0.9921; bez DU/2000/70 i 179, które nie mają warstwy tekstowej: R 0.9984, P 0.9921; przypisy R 0.9777,
P 0.9936); drzewo treści R 0.9932 → 0.9981, P 0.9992 → 0.9990. Na próbie s5204 (65 aktów, oceniona raz wersją
0.6.10): treść R 0.9963, P 0.9900, przypisy R 0.9587, P 0.9914, drzewo treści R 0.9936, P 0.9959. Zmianę (2)
znalazłem na s5204 (akt 839), więc jej zysk tam (treść R → 0.9972) nie jest niezależny; na s5205 nie ma takich stron.
Uwaga o latach 2000–2011: w próbach s5202–s5205 cztery akty nie mają warstwy tekstowej (DU/2000/70, 179, 985,
DU/2001/1186: PDF-y „Distiller 4.0 for Macintosh; modified using iText”, bez fontów). Z `--ocr` czyta je OCR.
Wyniki: `eval/*_test2000_s520{4,5}_*`.

**0.6.10** (2026-09-30). Dz.U. 2000–2011: strony, na których przypis zajmuje większość miejsca. (1) Łamy nad
przypisem mają tu 2–3 pełne wiersze. Rynna (odstęp między łamami) wymagała 3 wierszy kończących się na jednej
krawędzi i bez dziur w wierszu; dziurę po drobnym znaczniku przypisu („a)²⁾ zarobkowego”, DU/2008/1342 s. 5) wypełnia
teraz ten znacznik. Gdy są tylko 2 takie wiersze, rozstrzyga rynna z innych stron tego samego PDF-u (konwerter czyta
wtedy PDF drugi raz; DU/2004/959 s. 1). Wcześniej oba łamy i przypis czytały się jako jeden przemieszany tekst.
(2) Rozmiar czcionki treści na takiej stronie to rozmiar tekstu tuż nad kreską „———”, a nie najczęstszy na stronie
(przypis), inaczej znaczniki 7,5 pt stawały się tekstem. Na stronach starych wydań znacznik równy 0,75 rozmiaru treści
(7,5 pt przy 10 pt, rok 2004) jest znacznikiem. Na stronach 2012+ nadal nie (DU/2025/1057: liczby 7,5 pt w tabeli).
(3) Przypisy pod „———” w łamie, gdy niżej na stronie zaczyna się załącznik: kreska obejmuje wtedy tylko swój łam
(DU/2005/1468 s. 4). „———” bywa złożona drobnym drukiem (9 pt), więc porównuję też z rozmiarem treści.
(4) Stopka wydawcy zaczyna się też od „Szanowni Państwo” bez „!” (DU/2002/933 s. 3: ogłoszenie o Monitorze Polskim B).
Wariant od „Egzemplarze bieżące…” odrzuciłem, bo ucinał tekst (DU/2001/1622: ten blok stoi obok końca wyroku).
Wynik 2012+ bez zmian: 93 PDF-y (DU 2021–2026, MP 2012–2025) bajt w bajt jak w 0.6.9, bez linii `converter`.
**Test 2000–2011, s5203** (70 wylosowanych, 67 poza wcześniejszymi próbami, zapisana przed oceną, oceniona raz;
0.6.9 i 0.6.10 tymi samymi skryptami): treść główna R 0.7130 → 0.7134, P 0.9481 → 0.9562. Niski recall to jeden akt:
DU/2001/1186 (269 stron tabel wyników wyborów) nie ma warstwy tekstowej na 268 stronach, a ocena liczy bez OCR. Bez
niego: R 0.9975 → 0.9981, P 0.9481 → 0.9562. Przypisy R 0.9476 → 0.9667 (akty z R < 0,95: 9 → 4), P 0.9919 → 0.9918;
załączniki R 0.9349 → 0.9354, P 0.9789 → 0.9903. Drzewo: treść R 0.9906 → 0.9947, P 0.9962 → 0.9975; załączniki
R 0.7543 → 0.9930, P 0.8771 → 1.0000. Próba s5202 (67 aktów) mierzyła wersję przed zmianą (4): treść R 0.9486 → 0.9504
(bez DU/2000/985, też bez warstwy tekstowej: 0.9940 → 0.9960), P 0.9630 → 0.9661; zmianę (4) znalazłem na tej próbie,
więc jej zysk tam (P → 0.9680) nie jest niezależny. Nadmiar w treści to głównie podpisy sędziów w orzeczeniach TK
(HTML ich nie ma) i DU/2010/277: jego HTML kończy się „Pokaż całość”, a miara bierze z niego 3347 słów treści przy
ok. 10 tys. słów w pliku (przyczyny nie sprawdziłem). Wyniki: `eval/*_test2000_s520{2,3}_*`.

**0.6.9** (2026-09-30). Dz.U. 2000–2011, dalej: (1) stopka wydawcy z ostatniej strony wydania („Wydawca: Kancelaria
Prezesa Rady Ministrów… ISSN 0867-3411”, ogłoszenia o prenumeracie) nie jest tekstem aktu (DU/2000/291, DU/2003/577);
(2) nagłówek załącznika (tekstu jednolitego) w połowie strony pod podpisem albo drobnym drukiem w łamie jest nagłówkiem
załącznika, a nie treścią czy przypisem (DU/2010/648, DU/2002/664). Miara: `evaluate.py`, `tree_eval.py`
i `structure.py` czytają też starszy układ HTML (tekst aktu w `div.block` poza sekcjami; wyniki 2024 identyczne).
Wynik 2012+ bez zmian (42 PDF-y 2023–2026 wobec 0.6.7, bez linii `converter`). **Test 2000–2011, s5201** (60
wylosowanych, 56 poza wcześniejszymi próbami, zapisana przed oceną, oceniona raz; 0.6.8 i 0.6.9 tymi samymi skryptami):
treść główna R 0.9957 → 0.9957, P 0.9497 → 0.9854; przypisy R 0.8777, P 0.9409 → 0.9424; załączniki R 0.8921 → 0.9957,
P 0.9590 → 0.9666; drzewo treści bez zmian (R 0.9160, P 0.9786). Wyniki: `eval/*_test2000_s5201_v0.6.{8,9.dev}.*`.

**0.6.8** (2026-09-30). Dziennik Ustaw 2000–2011 (wydania z numerami „Nr N”, dwa łamy). Tylko strony z nagłówkiem
takiego wydania; wynik dla lat 2012+ jest bajt w bajt ten sam co w 0.6.7 (sprawdzone na 42 PDF-ach Dz.U. i M.P. 2023–2026
wprost wobec 0.6.7 i na 154 PDF-ach 2012–2026 wobec wersji pośrednich).
(1) Łamy czytane po kolei: lewy, potem prawy, a wiersze przez całą stronę (nagłówek, numer pozycji, tytuł) osobno;
przejście z dołu lewego łamu na górę prawego działa jak podział strony. (2) Akt wycięty ze stron wspólnych z sąsiednimi
aktami: od jego numeru pozycji (wyśrodkowana pogrubiona liczba) do numeru następnego aktu, z przypisami między nimi;
`convert(..., position=N)`, CLI i `dataset` podają pozycję z ELI. (3) Spacje po jednoliterowych słowach w PDF-ach
z QuarkXPress (2000–2009): odstęp bez znaku spacji, węższy niż próg pdfplumbera („zdnia” → „z dnia”). (4) Przypisy
pod kreską w łamie (2010–2011) i pod wierszem „———” (2000–2009). **Test 2000–2011, s5200** (60 wylosowanych aktów
z HTML, 59 poza próbami dev, zapisana w gicie przed oceną, oceniona raz; 0.6.7 i 0.6.8 tymi samymi skryptami):
treść główna R 0.4743 → 0.9963, P 0.3975 → 0.8970 (macro R 0.9950); przypisy R 0.5046 → 0.9716, P 0.5014 → 0.9640;
załączniki R 0.3640 → 0.6910, P 0.4770 → 0.9484; drzewo (tylko 0.6.8): treść R 0.9525, P 0.9885. Na próbach dev
(s2000, s2011, po 40 aktów) treść R 0.9976 i 0.9909, P 0.7974 i 0.7433. Niska P na dev była w części błędem miary:
starszy HTML ma tekst aktu w `div.block` poza sekcjami `part_N` (DU/2008/1547: 19 262 słowa poza, 132 w `part_1`),
a `evaluate.py` brał za treść pierwszą sekcję. Po poprawce miary (po wydaniu 0.6.8; wyniki 2024 identyczne) dev:
P 0.9449 i 0.9806; test s5200 bez zmian (brak takich aktów). Resztę nadmiaru na teście dają: DU/2002/664 (tekst
jednolity, nagłówek załącznika nie rozpoznany: 13 016 z 16 284 nadmiarowych tokenów), stopka wydawcy na ostatniej
stronie numeru („Zakład Wydawnictw i Poligrafii… ISSN 0867-3411”, DU/2003/577) i podpisy sędziów pod orzeczeniami TK,
których HTML nie ma. Próba z HTML to głównie ustawy (30 z 40
na dev), a akty bez HTML to głównie rozporządzenia i obwieszczenia, więc wynik dla nich może być inny. Znane błędy:
rozdzielona pierwsza litera w PDF-ach z InDesign 2011 („s kładanie”, DU/2011/1134), odnośniki przypisów jako osobne
linie, gdy przypisy mają większy udział niż treść (DU/2009/1323), spis treści na pierwszej stronie wydania (DU/2002/994),
nagłówek załącznika tekstu jednolitego nie rozpoznany (DU/2010/648). Przegląd lat 1918–2011:
`eval/du_pre2012_survey_0.6.5.md`. Wyniki: `eval/results_test2000_s5200_v0.6.{7,8.dev}.*`.

**0.6.7** (2026-09-30). (1) Przypis z wyliczeniem („Niniejsza ustawa:” + „1) wdraża…” + „2) służy…”) jest w całości
przypisem: punkty są jego kolejnymi akapitami (w Markdown z wcięciem, w JSON w tekście przypisu). Wcześniej przypis
kończył się na dwukropku, a punkty trafiały na koniec pliku jako treść, w JSON jako fałszywe jednostki `pkt` po
podpisie (DU/2026/421; w danych 0.6.5: 166 aktów Dz.U. i 3 M.P.). (2) Dz.U. 2000–2010 (QuarkXPress, czcionki „…PL”):
polskie litery są dekodowane jako MacCE („og∏oszenia” → „ogłoszenia”). W PDF-ach z lat 2024–2026 (80 sprawdzonych)
takich czcionek nie ma. To pierwszy krok do lat 2000–2011; dwa łamy tych lat nadal są czytane wierszami przez całą
stronę. **Test s5113** (90 wylosowanych, 62 wcześniej nieużyte, zapisana w gicie przed oceną, oceniona raz, 0.6.6
i 0.6.7 tymi samymi skryptami): słowa, struktura i znaczniki identyczne (treść główna R 0.9993, P 0.9979; przypisy
R 0.9701, P 0.9564; załączniki R 0.9973, P 0.9627), drzewo: jednostki identyczne (treść 1297/1297; załączniki
R 0.9976, P 0.9924), węzłów JSON bez odpowiednika w HTML 213 → 210 (fałszywe `pkt` z przypisu). Na próbach dev
(s7, s2024) takich węzłów ubyło 37, reszta identyczna. Wyniki: `eval/*_test_s5113_v0.6.{6,7.dev}.*`.

**0.6.6** (2026-09-30). Objaśnienia wydrukowane w treści (pod tabelami i formularzami w załącznikach, przypisy
cytowane przez nowelizacje) mają znaczniki `¹⁾`, a nie `[^n]`, więc nie prowadzą już do przypisu aktu o tym samym
numerze (opis w sekcji o formacie). Słowa bez zmian. Nowa miara `eval/markers_eval.py`: liczba odnośników
(`[^n]` wobec `a.gloss-link` w HTML) i znaczników wydrukowanych (`¹⁾` wobec `<sup>1)</sup>`), bez aktów, których
HTML pomija treść („patrz oryginał”). Liczy tylko liczby, nie sprawdza, dokąd odnośnik prowadzi; przypisy
załączników HTML podaje jako zwykły tekst, więc tam różnica jest cechą wzorca (DU/2024/1108). **Test s5112**
(90 wylosowanych, 50 wcześniej nieużytych, zapisana w gicie przed oceną, oceniona raz, 0.6.5 i 0.6.6 tymi samymi
skryptami; 40 aktów z pełnym HTML): odnośniki R 0.9910 → 0.9892, P 0.7750 → 0.9735; znaczniki wydrukowane
R 0 → 0.9114, P 0 → 0.9863. Treść, przypisy i załączniki identyczne (treść główna micro R 0.9211: dwie umowy
międzynarodowe, DU/2024/1679 i 363, to skany, 21 i 17 stron bez warstwy tekstowej, a ocena jest bez OCR;
macro R 0.9605, P 0.9986). Drzewo: akapity pod właściwą jednostką 0.9105 → 0.9107 (treść), 0.9126 → 0.9124
(załączniki); jednostki bez zmian. Na próbach dev (s7, s2024) zmiana dotyka 1–2 znaczników. Wyniki:
`eval/*_test_s5112_v0.6.{5,6.dev}.*`.

**0.6.5** (2026-09-30). Kreska przypisów jest rozpoznawana także wysoko na stronie (10–30% wysokości, np. strona
z samymi przypisami, DU/2024/1539 s. 2) i gdy jest narysowana linią, a nie prostokątem (DU/2024/1346). W obu
przypadkach tylko wtedy, gdy pod nią jest wyłącznie drobny druk (< 9,5 pt). Wcześniej przypisy z takich stron szły
do treści albo załącznika. Błąd znalazła diagnoza na próbie s5110 (tam recall przypisów 0.783 → 0.982, ale to
nie jest niezależny test). **Test s5111** (39 nowych aktów, zapisana w gicie przed oceną, oceniona raz, 0.6.4
i 0.6.5 tymi samymi skryptami): przypisy R 0.9517 → 0.9525, P 0.9609 → 0.9647; załączniki P 0.9809 → 0.9807;
treść główna (R 0.9947, P 0.9957), struktura i drzewo bez zmian. Poprawa jest mała, bo ten układ kreski jest
rzadki. Wyniki: `eval/*_test_s5111_v0.6.{4,5.dev}.*`. W opublikowanych danych zmieniło się 133 z 3266 aktów
Dz.U. i 4 z 2272 aktów M.P. 2025–2026 (tekst przypisów przeszedł z treści do definicji `[^n]:`); selfcheck
(`eval/selfcheck.py`) dla wszystkich zmienionych aktów bez zmian, bo słowa są te same.

**0.6.4** (2026-09-30). Trzy zmiany (opisy w sekcjach niżej i w raportach `eval/*_0.6.4.dev.md`):
- z `--ocr` obraz tekstu na stronie z warstwą tekstową (s. 1 umów międzynarodowych) dostaje tekst OCR
  (`eval/image_text_ocr_0.6.4.dev.md`);
- numerowane wiersze tabel i formularzy w załącznikach nie są w JSON jednostkami (`eval/annex_rows_0.6.4.dev.md`);
- wzory Cambria Math bez podwojonych liter, wklejony PDF nie gubi znacznika ukrytego tekstu (`eval/math_glyphs_0.6.4.dev.md`).

**0.6.4, test s5110** (35 aktów z 2024 r., których nie było w żadnej wcześniejszej próbie; zapisana w gicie przed
oceną, oceniona raz; 0.6.3 tymi samymi skryptami): wszystkie sumy identyczne w obu wersjach. Słowa: treść główna
R 0.9999, P 0.9959; przypisy R 0.783, P 0.756; załączniki R 0.980, P 0.980. Drzewo: treść główna 1241/1241,
załączniki R 0.9994, P 0.9810. W tej próbie nie ma kart akwenów ani wykazów współrzędnych, więc poprawa drzewa
załączników z próby dev (P 0.852 → 0.994, strojona na niej) nie ma tu niezależnego potwierdzenia. Wyniki:
`eval/*_test_s5110_v0.6.{3,4}.*`.

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
Od 0.6.4 znaki alfanumeryczne matematyczne (`𝑘` we wzorach Worda) liczę po obu stronach jako zwykłe litery,
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

### Skany zeszytów sprzed 2012 r. (od 0.6.26, też tylko z `--ocr`)

PDF-y Dziennika Ustaw z lat 1918–1999 to skany stron zeszytów: dwa łamy, kilka aktów na stronie. Większość ma
niewidoczną warstwę tekstu z OCR Adobe Acrobata (czcionka „HiddenHorzOCR”); ta warstwa przestawia wyrazy między
wierszami („zarządza się, następuje:” na końcu DU/1997/78) i ma własne błędy. Z `--ocr` taka strona (obraz na ≥ 80%
strony i ≥ 10 znaków w „HiddenHorzOCR”), strona-obraz bez tekstu w PDF z taką warstwą oraz strona bez warstwy, której
odczyt zawiera nagłówek starego zeszytu („Dziennik Ustaw Nr 40”, także skany z 2000 r.) jest czytana tesseractem jak
skan zeszytu:
- wiersze w kolejności łamów (`ocr._column_order`): odstęp między łamami to położenie, które najlepiej oddziela końce
  wierszy lewego łamu od początków wierszy prawego (po wyprostowaniu przekrzywionego skanu); wiersz, który tesseract
  skleił przez odstęp, jest dzielony; wiersze na całą szerokość (tytuł, kolofon) dzielą stronę na pasy;
- akapity są zwykłym tekstem z jednostkami (`##### § 1.`, `##### Art. 1.`), a nie cytatami; przed tekstem każdej
  strony stoi notka `> [Strona N PDF jest skanem. Tekst poniżej odczytał OCR (…), a nie warstwa tekstowa PDF. …]`;
- „§” odczytany jako „8”, „$” albo „S” na początku akapitu i po przyimku („w 8 1”) staje się „§”; rozpoznawane są
  kolofon wydawcy z lat 90., nagłówki załączników i podpisy; akt jest wycinany spośród sąsiednich jak w 2000–2011.
Słowa, których słownik pl_PL nie zna, a jedna zamiana „t”/„l” na „ł” albo oddzielenie przyimka czyni znanymi, są
poprawiane (`ocr.fix_words`, jeśli jest libhunspell i `hunspell-pl`). Przypisy na skanach nie są rozpoznawane
(zostają akapitami). Z `ELI2MD_OCR_CACHE=katalog` odczyty tesseracta są
zapamiętywane, więc ponowna konwersja po zmianie w dalszej obróbce nie czyta stron od nowa.

### Obraz tekstu na stronie z warstwą tekstową (0.6.4, też tylko z `--ocr`)

S. 1 umów międzynarodowych ma w warstwie tekstowej tylko winietę i tytuł. Preambuła i pierwsze artykuły są na
tej samej stronie obrazem (np. MP/2026/869). Z `--ocr` konwerter czyta OCR-em największy obraz strony z warstwą
tekstową. Robi to, jeśli nad obrazem nie leży tekst z warstwy (> 30 znaków oznacza, że obraz jest tłem
formularza). Tekst przyjmuje tylko wtedy, gdy wygląda na skan tekstu ciągłego (`ocr.text_image`):
- mediana pewności ≥ 95, co najmniej 5 linii i słowa funkcyjne jakiegoś języka,
- ≥ 75% tokenów to słowa,
- co najmniej połowa linii ma ≥ 45 znaków i co najmniej połowa zajmuje ≥ 60% szerokości obrazu,
- mało symboli (`|`, `%`, `=` …),
- żaden akapit nie zaczyna się od „Tabela”, „Wykres”, „Rys.”, „Mapa”, „Źródło” itp.

Przyjęty tekst stoi w miejscu notki o obrazie, pod notką
`> [Na stronie 1 PDF jest obraz tekstu (skan). Tekst poniżej odczytał z obrazu OCR (tesseract 5.5.0, pol+eng). Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]`,
jako cytaty blokowe `> …` (w JSON węzły `ocr`). Strona zostaje w `pages_with_images`. Dochodzi nowe pole
`pages_images_ocr`, a `pages_ocr` dalej oznacza tylko strony bez warstwy tekstowej. W `index.csv` jest nowa
kolumna `image_ocr_pages`. Bez `--ocr` wynik się nie zmienia.

Pomiar na wszystkich 824 stronach z obrazem w danych 2025–2026 (DU 631, MP 193;
`eval/image_text_ocr_0.6.4.dev.md`):
- Przyjęte są 34 strony z 29 umów międzynarodowych. Obejrzałem wszystkie i wszystkie to skany tekstu,
  ale na 5 są podpisy lub wpisy odręczne, które dają w OCR śmieci.
- W losowej próbie 20 odrzuconych 19 to nie tekst (mapy, rysunki, logo, formularze, wzory legitymacji).
  Jeden to pominięty obraz tekstu (tytuł i preambuła w krótkich liniach).
- Na s. 1 z 43 umów-kandydatów (29 DU, 14 MP) tekst dostaje 25. Pozostałe to głównie tytuły i preambuły
  w krótkich, wyśrodkowanych liniach, listy stron i spis treści. Zostają z notką, bo fałszywe przyjęcie
  formularza jako tekstu jest gorsze niż brak.
- Progi dobrałem na tych samych stronach, więc to nie jest niezależny test.

Koszt: OCR ma 722 strony (reszta odpada wcześniej), mediana 1,65 s, średnio 2,9 s na stronę. W całym
zbiorze 2025–2026 to ok. 35 min czasu jednego wątku.

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
- Teksty jednolite (pomiar 0.6.25 na 404 aktach, opis w zmianach 0.6.25): przypis z etykietą rzymską w zwykłym druku
  („I) Odnośnik dodany przez…”) dokleja się do poprzedniego przypisu; dopisek „* Ostatnia pozycja w 2025 r.” bywa na
  końcu artykułu (DU/2025/1900 art. 93); wzory i tabele spłaszczone jak wszędzie.
- Objaśnienia pod formularzami, stopki formularzy („Strona N z M”, DU/2024/1659) i drobny druk tabel bez kreski
  przypisów bywają brane za przypisy. Część niskiej precision przypisów to cecha wzorca: HTML podaje przypisy
  tekstów jednolitych i załączników jako zwykły tekst, a wynik jako przypisy (DU/2024/1580: 106 ze 112 przypisów
  wyniku jest w HTML tylko w treści; DU/2024/781 na próbie s5110: 3054 tokeny). Niski recall przypisów na s5110
  był za to błędem konwertera (kreska przypisów wysoko na stronie albo narysowana linią), poprawionym w 0.6.5.
  Diagnoza: `eval/footnotes_diagnosis_0.6.5.dev.md`. Od 0.6.5 `eval/evaluate.py` podaje też łagodniejszą miarę
  `notes*` (numery przypisów zostają, nadmiarowy token obecny w HTML poza przypisami liczy się jako trafiony);
  zawyża ona P, gdy konwerter bierze za przypis tekst załącznika.
- Ciasno złożone tabele: do 0.6.2 pozycja „2) …” w komórce po krótkiej linii bez „;” doklejała się do „1) …”
  (MP/2025/121). Od 0.6.3 taka pozycja zaczyna nowy akapit (opis niżej, w zmianach 0.6.3). Mogą zostać inne
  układy komórek, w których podział ginie. Tekst jest wtedy pełny, brakuje tylko podziału.
- Wklejone wzory z Worda: niewidoczna kopia wzoru bywa w PDF-ie pod widocznym wzorem i trafia do wyniku
  jako powtórzony tekst (DU/2025/452 s. 7).
- Wzory Cambria Math: w 19 aktach DU 2025–2026 mapa ToUnicode daje jednemu glifowi dwie litery (`𝑘𝑘`).
  Od 0.6.4 zapisuję je pojedynczo („k”, nie „kk”). W czterech z nich (DU/2025/454, 459, 1743, 1744) mapa jest
  poza tym błędna i wzory pozostają nieczytelne. `eval/math_glyphs_0.6.4.dev.md`.
- Wklejony PDF z Worda pod przepisanym tekstem Dziennika (DU/2026/40 s. 2–6): widać z niego tylko wzory.
  Do 0.6.3 pdfplumber gubił znacznik `PlacedPDF` po zagnieżdżonym `/Span … EMC` wzoru, więc reszta ukrytej kopii
  w ogóle nie szła do testu tuszu. Od 0.6.4 znacznik zostaje (10 aktów 2025–2026). Test tuszu dalej przepuszcza
  ukryte litery, których ramka nachodzi na tusz innego tekstu, więc akapity przy wzorach bywają wymieszane.
- Umowy międzynarodowe: pierwsza strona (preambuła, art. 1) bywa obrazem tekstu na stronie, która ma warstwę
  tekstową z samym tytułem (np. MP/2026/869). Do 0.6.3 OCR jej nie czytał. Od 0.6.4 z `--ocr` czyta taki
  obraz, gdy wygląda na tekst ciągły (opis wyżej, w sekcji o OCR). W 2025–2026 tak jest na 25 z 43 umów. Obrazy, w których przeważają
  krótkie linie (tytuły, nagłówki artykułów, np. MP/2012/646 s. 1), dalej zostają z notką.
- Dz.U. 2000–2011: część PDF-ów nie ma warstwy tekstowej (w próbach s5202–s5205 4 z 258 aktów: DU/2000/70, 179,
  985, DU/2001/1186; 3 z nich z 2000 r.). Bez `--ocr` zostaje z nich tylko notka. Podpisy sędziów w orzeczeniach TK bywają sklejone w jeden
  wiersz. Miary dla tych lat pochodzą z aktów, które mają HTML (głównie ustawy, obwieszczenia i orzeczenia), a akty
  bez HTML to w większości rozporządzenia, których ta miara nie obejmuje.
- Domyślnie bez OCR. W 2025–2026 62 akty mają strony bez warstwy tekstowej (1734 z 53 356 stron
  w indeksie z 29.09.2026), głównie umowy międzynarodowe. OCR (`--ocr`, od 0.6.0) opisany niżej.

## Licencja

Kod: MIT. Teksty aktów normatywnych nie podlegają prawu autorskiemu (art. 4 pkt 1 ustawy
o prawie autorskim i prawach pokrewnych).
