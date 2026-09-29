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

Pobrane pliki trafiają do `~/cache/eli` (zmienna `ELI2MD_CACHE`). Klient robi przerwę 1 s między zapytaniami.

## Format wyniku

- Front matter YAML z metadanymi z API ELI. Klucze są zgodne z legalize-pl tam, gdzie znaczą to samo
  (`title`, `identifier`, `rank`, `eli`, `display_address`, …). Do tego `source_pdf`, `converter`
  oraz `disclaimer`.
- `# Tytuł`, potem akapity w kolejności z PDF-a.
- Jednostki najwyższego rzędu jako `##### Art. N.`, a gdy w akcie nie ma artykułów, `##### § N.`
  (rozporządzenia).
- Nagłówki załączników jako `## Załącznik nr …`, podpis kursywą.
- Przypisy w składni Markdown: `[^1]` w tekście i `[^1]: …` na końcu.

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
kolejności tekstu wewnątrz tabel. Porównuje tylko ciąg słów.

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
```

## Znane ograniczenia

- Tabele są spłaszczane do akapitów (komórki wierszami), wzory do zwykłego tekstu, grafiki pomijane.
- Strony z tekstem obróconym (tabele w poziomie na stronie pionowej) czytam w obróconym układzie
  (od 0.2). Tekst w innym kierunku niż reszta strony, np. pionowe nagłówki kolumn, trafia na
  koniec strony.
- Załączniki bywają wklejonymi PDF-ami, a ich pierwotny nagłówek jest w Dzienniku Ustaw zakryty.
  Taki ukryty tekst wykrywam heurystycznie: renderuję stronę i sprawdzam, czy pod znakiem jest tusz.
  Mogą zostać pojedyncze duplikaty.
- Objaśnienia pod formularzami w załącznikach bywają brane za przypisy (niska precision przypisów).
- Tylko PDF-y z warstwą tekstową (Dz.U. je ma). Bez OCR.

## Licencja

Kod: MIT. Teksty aktów normatywnych nie podlegają prawu autorskiemu (art. 4 pkt 2 ustawy
o prawie autorskim i prawach pokrewnych).
