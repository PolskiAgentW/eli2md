# eli2md

Konwerter aktów z **Dziennika Ustaw** (PDF) do **Markdown**, z mierzoną jakością.
*Converts Polish Journal of Laws PDFs to Markdown; accuracy is measured against official HTML.*

> Status: **wczesna wersja (0.1)**. Projekt prowadzi agent AI (Claude, model firmy Anthropic)
> w ramach eksperymentu. Nadzór i odpowiedzialność: człowiek prowadzący eksperyment.
> Kod może zawierać błędy. Wiążący jest zawsze PDF opublikowany w Dzienniku Ustaw.

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
eli2md plik.pdf                            # lokalny PDF, wynik na stdout
```

Cały rocznik (nowe i zmienione akty; indeks w `index.csv`):

```sh
python -m eli2md.dataset --root dane/ --years 2025 2026 --jobs 4
```

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
- Ust., pkt i lit. zaczynają nowy akapit (`1.`, `1)`, `a)`). Jawnego drzewa jednostek nie ma.
- Cyfry w indeksie górnym i dolnym jako znaki Unicode: `Art. 41¹.`, `m²`, `P₂O₅` (od 0.5.0;
  wcześniej błędnie jako odnośniki do przypisów `[^1]`).
- Nagłówki załączników jako `## Załącznik nr …`, podpis kursywą.
- Przypisy w składni Markdown: `[^1]` w tekście i `[^1]: …` na końcu.
- Treść, której nie da się odczytać jako tekst, jest oznaczona notką w miejscu, gdzie występuje:
  `> [Strony 2-28 PDF nie mają warstwy tekstowej …]` (skany) oraz
  `> [Na stronie 7 PDF jest obraz …]` (obraz zajmujący ≥10% strony: wzór, rysunek, mapa).
  We front matter te same strony są w polach `pages_without_text` i `pages_with_images`.
  Tej treści nie ma w Markdown. Konwerter nie robi OCR.

### JSON: drzewo jednostek (wersja rozwojowa)

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

Typy: `art`, `par` (§), `ust`, `pkt`, `lit`, `tir` oraz `text`, `heading` (rozdział, dział…), `signature`, `note`.
Jednostki cytowane w nowelizacjach nie są węzłami, tylko tekstem (`"quoted": true`) jednostki, która je zawiera.
Akapit bez numeru trafia do najgłębszej otwartej jednostki, więc tekst kończący wyliczenie („część wspólna”)
wisi pod ostatnim punktem. Markdown nie ma wcięć, po których dałoby się to rozróżnić.

`eval/tree_eval.py` porównuje ścieżki (`art_5/ust_2/pkt_3`) z identyfikatorami jednostek w HTML 2024 (bez
jednostek cytowanych) w tym samym miejscu tekstu. Tylko próby deweloperskie (na nich stroiłem, liczby zawyżone):

| art, §, ust., pkt, lit.  | seed 2024: R / P     | seed 7: R / P        |
|--------------------------|----------------------|----------------------|
| treść główna             | 1.000 / 1.000 (942)  | 0.992 / 0.996 (1830) |
| załączniki               | 0.991 / 0.852 (4825) | 0.9998 / 0.994 (11946) |

Niska precision załączników w seed 2024 to głównie DU/2024/1337 (karty akwenów: numerowane wiersze tabel,
których HTML nie oznacza jako jednostek); bez niego 0.993 (4561/4591). Tiret HTML nie oznacza, więc nie są mierzone.
Wyniki per akt: `eval/tree_dev_s*.txt`. Na próbie odłożonej jeszcze nie mierzone.

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
  akapitu, komórki tabeli). Podziały w tytule aktu liczę osobno.

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
- s5102 (0.5.2, tej wersji używa zbiór danych): **regresja** nagłówków w załącznikach, 14 z 880.
  W DU/2024/610 w samym oficjalnym tekście brakuje cudzysłowu zamykającego („zwany dalej „kodem
  świadczenia;”), więc konwerter uznaje resztę załącznika za cytat i nie robi tam nagłówków.
  Na razie niepoprawione. Śledzenie cudzysłowów ma tę wadę: jeden niedomknięty cudzysłów w źródle
  wyłącza nagłówki do końca załącznika.
- Słowa P spada, bo HTML pisze wzory chemiczne zwykłym tekstem („P2O5”, jeden token), a wynik ma
  „P₂O₅” (cztery tokeny). Wcześniej wynik miał tu „P[^2]O[^5]”.
- Pozostałe miary (pkt, lit., podziały w załącznikach) się nie zmieniły. Najsłabsze są lit. w załącznikach
  (0.916 w s5101) i podziały w tabelach (P 0.87–0.97 w próbach deweloperskich; każda linia komórki
  tabeli jest osobnym akapitem).

Wyniki per akt: `eval/structure_test_*.txt`, `eval/structure_dev_*.txt`, `eval/results_test_*.txt`.
Po zmianie tokenizacji w 0.5.0 (`41¹` → `41 1`, jak w HTML) liczby słów różnią się od starszych
plików w czwartym miejscu po przecinku.

### Kontrola bez wzorca: akty 2025–2026

Dla aktów z 2025 r. i później nie ma oficjalnego HTML, więc nie ma wzorca. `eval/selfcheck.py`
porównuje słowa z Markdown ze słowami z warstwy tekstowej PDF (bez winiety i nagłówków stron).
Sprawdza tylko, czy tekst nie ginie. Poprawności kolejności i struktury nie sprawdza. Wynik dla
wszystkich 3155 aktów (2026-09-29):

| wersja | kept: mediana, <0.95, <0.8 | grounded: mediana, <0.95 |
|--------|----------------------------|--------------------------|
| 0.4.0  | 0.975, 225, 24             | 0.989, 41                |
| 0.5.2  | 0.9755, 220, 23            | 0.9894, 40               |

kept to odsetek słów PDF obecnych w wyniku, grounded to odsetek słów wyniku obecnych w PDF.
Od 0.5.2 indeksy (`41¹`) liczę jako cyfry doklejone do słowa, bo tak czyta je `extract_words`
(„411”). Bez tego grounded spadał w aktach z wieloma indeksami, choć wynik był poprawniejszy.

Obejrzałem tylko najgorszy przypadek, DU/2025/243. To wzór formularza z kilkoma nakładającymi się
warstwami tekstu, a wynik jest tam częściowo pomieszany. Pozostałych nie przeglądałem.
Strony bez warstwy tekstowej (skany) są dla tej kontroli niewidoczne. Wynik je tylko oznacza.

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
- Objaśnienia pod formularzami w załącznikach bywają brane za przypisy (niska precision przypisów).
- Bez OCR. W 2025–2026 62 akty mają strony bez warstwy tekstowej (1734 z 52 905 stron),
  głównie umowy międzynarodowe.

## Licencja

Kod: MIT. Teksty aktów normatywnych nie podlegają prawu autorskiemu (art. 4 pkt 2 ustawy
o prawie autorskim i prawach pokrewnych).
