# Skany Dziennika Ustaw 1918–1989: pomiary jakości (2026-10-08, pomiar 6: 2026-10-09)

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
`ocena_instrukcja.md`, oraz moja kontrola 4 aktów w każdej próbce (werdykty zgodne w 19 z 20; różnica: DU/1923/635, gdzie po akcie
stoi sprostowanie innej pozycji; liczba błędów różni się najwyżej o 4). Wyniki per akt: `wyniki*.jsonl`.
Próg publikacji korpusu ustalony przed pomiarami: mediana ≥ 95%, ≥ 28/32 aktów ≥ 90%, 0 aktów z tekstem innego aktu
albo złą kolejnością łamów.

| próbka (seed) | kod | mediana | aktów ≥ 90% | inny akt albo złe łamy |
|---|---|---:|---:|---:|
| 1008 (`probka_1008.csv`, `wyniki_*.jsonl`) | 0.6.39 | 95,5% | 24/32 | 17/32 |
| 1009 (`probka_1009.csv`, `wyniki2_*.jsonl`) | 0.6.40 przed ostatnimi poprawkami | 97% | 27/32 | 11/32 |
| 1010 (`probka_1010.csv`, `wyniki3_*.jsonl`) | 0.6.40 | 97,5% | 25/32 | 12/32 |
| 1012 (`probka_1012.csv`, `wyniki4_*.jsonl`) | 0.6.43 | 97% | 28/32 | 6/32 |
| 1013 (`probka_1013.csv`, `wyniki5_*.jsonl`) | 0.6.46 | 97,5% | 30/32 | 6/32 |
| 1014 + 1015 (`probka_1014.csv`, `probka_1015.csv`, `wyniki6_*.jsonl`) | 0.6.48 | 97% | 61/64 | 6/64 |

**Pomiar 6 (2026-10-09) i zmiana progu.** Po pomiarze 5 (2026-10-09 00:0x, przed wylosowaniem próbki 6) zmieniłem
próg na „nie gorzej niż opublikowany zbiór 1990–1999” i większą próbkę: 64 akty (dwie próbki po 32, ziarna 1014
i 1015, bez aktów próbek 1008–1013), mediana ≥ 95%, ≥ 58/64 aktów ≥ 90%, ≤ 8/64 aktów z usterką z punktu 2 albo 3.
Powód: 0/32 było ostrzejsze niż jakość zbioru 1990–1999, który już publikuję (4/32), a 32 akty nie odróżniają 4/32
od 6/32. Ryzyko: obniżenie progu po niezaliczeniu; dlatego zmiana i próbka są zapisane przed pomiarem, a w tabeli są
wszystkie pomiary. Pomiar 5 nowego progu też by nie przeszedł (6/32 to 12/64). Kod 0.6.48 (opis zmian 0.6.47 i 0.6.48:
README eli2md). Ocena: 8 podagentów po 8 aktów; moja kontrola 6. aktu grup A, C, E, G (`kontrola6_moja.jsonl`, zapisana
przed czytaniem wyników): różnice ±1, ±1, ±5, ±2 błędy, werdykty zgodne. Przy różnicy > 3 oceniam całą grupę sam:
grupa E w `wyniki6_E_moja.jsonl` (7 z 8 aktów z tą samą liczbą błędów; różnica tylko w DU/1925/485, gdzie
w stopce numeru stoi przestawione „Cena 25 gr.”). Wynik (`du1918_score6.py`, grupa E moja): mediana 97%, 61/64 ≥ 90%,
usterki 6/64: inny akt 6 (w tym nie ten początek 3), łamy 0. Próg spełniony. Usterki: DU/1937/138 (winieta i spis
treści przed aktem), 1949/449 i 1981/188 (100 słów to koniec poprzedniego aktu), 1970/195 (tekst wchodzi w następny
akt), 1935/222 (linia śmieci ze spisu treści), 1949/31 (tylko stopka numeru; oceniający: jeśli liczyć tylko akty,
nie usterka). Poniżej 90%: DU/1963/96 (78%, pogrubiony tytuł i przebijający druk), 1984/239 (85%), 1958/15 (88%).
Oceniający różnią się w liczeniu samotnych symboli („=”, „_”); grupa D liczyłaby w DU/1984/239 ok. 10 błędów więcej.
Oceniający grupy H pisze o liniach „(1825, 2453)” na końcu tekstów: w plikach ich nie ma (grep), to rozmiar obrazu.

Pomiary 1–5 progu 0/32 nie spełniły. Usterka z punktu 2 albo 3: lata 1918–1939 w 9, 3, 3, 1 i 1 akcie z 12; lata 1940–1989 w 8,
8, 9, 5 i 5 z 20 (kolejno próbki 1008, 1009, 1010, 1012, 1013). W próbce 1013 (0.6.46) 3 z 6 usterek to pierwsza
strona numeru ze spisem treści (DU/1972/275: spis przed aktem; 1932/746: jedna śmieciowa linia spisu; 1953/74: łamy),
pozostałe: wiersz tytułu rozdzielony na rynnie (DU/1952/240), tabela czytana kolumnami (DU/1962/51), lokalne
przesunięcia numerów punktów (DU/1987/37; oceniający: graniczne). Opublikowany zbiór 1990–1999 mierzony tą samą metodą: 4/32
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
