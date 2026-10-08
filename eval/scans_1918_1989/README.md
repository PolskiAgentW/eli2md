# Skany Dziennika Ustaw 1918–1989: pomiary jakości (2026-10-08)

Akty Dziennika Ustaw z lat 1918–1989, które API ELI podaje tylko jako PDF (skany całych stron numeru), czytane
`eli2md --ocr`. Mierzę trzy rzeczy, bo PDF aktu zawiera całe strony, a więc też sąsiednie akty:

1. dokładność pierwszych 100 słów tekstu względem druku (obraz strony; błąd = słowo inne niż w druku, śmieci,
   sklejenie albo rozbicie słów, słowo z innego miejsca strony, słowo pominięte; nie błąd: sama interpunkcja,
   przeniesienie jak w druku, dawna pisownia jak w druku, żywa pagina);
2. czy tekst zaczyna się od tego aktu i czy tekst z 1. strony nie zawiera innego aktu (końcówki poprzedniej
   pozycji, spisu treści numeru, następnej pozycji);
3. czy kolejność łamów na 1. stronie jest dobra.

Próbka: 32 akty, po 4 losowe z każdej dekady 1910–1980 (`random.Random(seed).sample`, lista posortowana po roku
i pozycji), każda kolejna bez aktów poprzednich. Ocena: 4 podagenty (model językowy) po 8 aktów, wg
`ocena_instrukcja.md`, oraz moja kontrola 4 aktów w każdej próbce (werdykty zgodne w 15 z 16; różnica: DU/1923/635, gdzie po akcie
stoi sprostowanie innej pozycji; liczba błędów różni się najwyżej o 4). Wyniki per akt: `wyniki*.jsonl`.
Próg publikacji korpusu ustalony przed pomiarami: mediana ≥ 95%, ≥ 28/32 aktów ≥ 90%, 0 aktów z tekstem innego aktu
albo złą kolejnością łamów.

| próbka (seed) | kod | mediana | aktów ≥ 90% | inny akt albo złe łamy |
|---|---|---:|---:|---:|
| 1008 (`probka_1008.csv`, `wyniki_*.jsonl`) | 0.6.39 | 95,5% | 24/32 | 17/32 |
| 1009 (`probka_1009.csv`, `wyniki2_*.jsonl`) | 0.6.40 przed ostatnimi poprawkami | 97% | 27/32 | 11/32 |
| 1010 (`probka_1010.csv`, `wyniki3_*.jsonl`) | 0.6.40 | 97,5% | 25/32 | 12/32 |
| 1012 (`probka_1012.csv`, `wyniki4_*.jsonl`) | 0.6.43 | 97% | 28/32 | 6/32 |

Próg nie jest spełniony. Usterka z punktu 2 albo 3: lata 1918–1939 w 9, 3, 3 i 1 akcie z 12; lata 1940–1989 w 8, 8,
9 i 5 z 20 (kolejno próbki 1008, 1009, 1010, 1012). Opublikowany zbiór 1990–1999 mierzony tą samą metodą: 4/32
(`../scans_1990_1999/`). W próbce 1012 (0.6.43): łamy przeplatane wierszami u góry strony w 3 aktach (DU/1946/228,
1965/60, 1976/247), tekst następnego aktu w DU/1926/734, tekst poprzedniego (227) zamiast DU/1988/228, a w DU/1955/175
tylko początek aktu 176. To ostatnie to regresja 0.6.42, poprawiona w 0.6.44 (na tej, już oglądanej, próbce zmienia
się tylko ten akt; 0.6.44 nie był mierzony na nowej próbce). W `wyniki4_C.jsonl` oceniający pisze o liniach
„(1742, 2410)” na końcu tekstu: takich linii w ocenianych plikach nie ma (sprawdzone grep), to rozmiar obrazu z jego
własnego skryptu. Na werdykty to nie wpływa. Poprawki 0.6.40 zrobione na próbce 1009 (oglądanej) nie zmniejszyły odsetka usterek na nowej próbce 1010:
każda próbka pokazuje inne warianty (numer aktu zgubiony albo zniekształcony przez OCR, pierwsza strona numeru ze spisem
treści, łamy przeplatane w zaszumionych skanach, tabele).

Narzędzia: `du1918_sample.py` (losowanie próbki; odtwarza próbkę 1010), `du1918_dev.py` (konwersja listy aktów
z cache OCR), `du1918_materials.py` (materiały do oceny; od próbki 1012 obraz to pierwsza strona PDF, na której jest tekst aktu).
Uwaga: w próbkach 1008–1010 obraz był zawsze 1. stroną PDF; dla DU/1989/257 tekst zaczyna się na 3. stronie
(oceniający pobrał ją sam).
