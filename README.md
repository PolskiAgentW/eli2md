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

Losowa próba 50 aktów z 2024 r. (seed 2024, ocenionych 49):

| część          | n  | recall (micro) | precision (micro) |
|----------------|---:|---------------:|------------------:|
| treść główna   | 49 | 0.993          | 0.985             |
| przypisy       | 41 | 0.954          | 0.880             |
| załączniki     | 24 | 0.934          | 0.819             |

**Zastrzeżenie:** na tej próbie stroiłem konwerter (to zbiór deweloperski), więc liczby są
zawyżone. Wynik na nowej próbie, uruchomionej raz i bez strojenia, dopiszę tutaj,
gdy go zmierzę. Na drugiej próbie (seed 7) wyszło recall 0.999, ale precision tylko 0.109.
Winne są akty z obróconymi stronami, np. ustawa budżetowa z tabelami w poziomie.

Odtworzenie wyników:

```sh
pip install -e '.[eval]'
python eval/fetch_sample.py 50 2024
python eval/evaluate.py eval/sample_2024_n50_s2024.json
```

## Znane ograniczenia

- Strony obrócone (tabele w poziomie) dają tekst pomieszany lub odwrócony. Do naprawy jako pierwsze.
- Tabele są spłaszczane do akapitów, wzory do zwykłego tekstu, grafiki pomijane.
- Przypisy w załącznikach bywają łączone z tekstem (niska precision przypisów).
- Tylko PDF-y z warstwą tekstową (Dz.U. je ma). Bez OCR.

## Licencja

Kod: MIT. Teksty aktów normatywnych nie podlegają prawu autorskiemu (art. 4 pkt 2 ustawy
o prawie autorskim i prawach pokrewnych).
