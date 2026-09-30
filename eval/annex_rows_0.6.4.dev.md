# Wiersze tabel i formularzy jako ust./pkt w drzewie JSON (0.6.4.dev, zadanie R)

Stan: kod w `eli2md/tree.py` (`_Builder.table_row`, `_next`, stałe `COORD`, `FORM_LABEL`), testy
w `tests/test_tree.py` (`test_form_card_rows_are_text`, `test_coordinate_rows_are_text`,
`test_table_rows_replaced_without_quotes`). `pdf.py` bez zmian. Wersja pakietu bez zmian (0.6.3).

## Problem

Markdown nie ma znaczników tabel: `pdf.py` spłaszcza tabele do akapitów, więc wiersz „5. FUNKCJA PODSTAWOWA”
albo „6. 54°10′43,83″ N 19°22′52,30″ E” wygląda jak ustęp. Drzewo robiło z takich wierszy `ust`/`pkt`,
a kolejne akapity i jednostki wieszało pod nimi. Znane przypadki: DU/2024/1337 (karty akwenów, próba dev
s2024), DU/2024/1594 (współrzędne i karty), MP/2025/1248 (wiersz tabeli jako `ust_8`, pod nim lit. e–i).

## Reguła

Akapit, który parsuje się jako jednostka, zostaje tekstem (węzeł `text` w najgłębszej otwartej jednostce), gdy:

1. **Punkt wykazu współrzędnych**: tekst po numerze zaczyna się od stopni i minut (`COORD`:
   „6. 54°10′43,83″ N …”, DU/2024/1594; „2) 52°36'08"N 019°39'05"E”, DU/2025/947). „a) 30 °C lub więcej:”
   zostaje jednostką (po stopniach nie ma minut). Dotyczy „N.” i „N)”.
2. **Wiersz formularza (karta akwenu)**: „N.” z etykietą wielkimi literami (`FORM_LABEL`: słowo ≥ 3 wielkich
   liter, po nim drugie takie słowo albo liczba, nie zdanie), który byłby pierwszym ust. swojego rodzica,
   a jego numer nie jest „1”. W kartach wiersze 1–4 są sklejone z innymi akapitami („KARTA AKWENU
   1. OZNACZENIE LITEROWE” / „2. NUMER 18 3. OPIS 1. 54°…”), więc pierwszy rozpoznany wiersz ma numer 2–5.
   Taki wiersz otwiera tabelę: wszystko do następnej jednostki rzędu rodzica (następny `##### §`/`Art.`),
   nagłówka albo załącznika jest tekstem, także listy „1) badania naukowe (N);” w komórkach. Oficjalny HTML
   DU/2024/1337 nie oznacza żadnego wiersza ani punktu kart jako jednostki, a § kart tak.
   „2. BGK przyznaje …” (skrót + zdanie) i „1. ZASADY OGÓLNE” (numer 1) zostają jednostkami.
3. **Wiersz tabeli zmienianej bez cudzysłowu (nowelizacje)**: „N.” pod jednostką, która ma już pkt/lit./tirety,
   a nie ma ust., tuż po jednostce kończącej się „brzmienie:”/„brzmieniu:” („– – – lp. 3 i 4 otrzymują
   brzmienie:” / „3. Realizacja Krajowego planu … 2.500 300 …”, MP/2025/1248). Kolejne jednostki są wierszami
   albo listami tej samej tabeli, dopóki któraś nie kontynuuje listy aktu (numer zaraz po ostatnim rodzeństwie
   tego typu: „2)” po „1)”, „27a.” po „27.”, „e)” po „d)”; każdy tiret po tirecie), i to nie listy samej tabeli
   (DU/2025/1847: „9ba. …: 155 zł” / „1) …” … „9) …” / „2) po ust. 9c dodaje się …” — „2)” idzie za „1)” aktu,
   a nie za „9)” tabeli). Bez zapowiedzi brzmienia ust. zostaje: DU/2025/1895 drukuje „§ 7.” bez „1.”, potem
   „1)”–„3)” i „2. Jeżeli termin …” (sprawdzone w PDF) — `par_7/ust_2` jak w 0.6.3.

Reguły działają w treści głównej i w załącznikach. W próbkach dev zadziałała tylko reguła 2 (DU/2024/1337);
w danych 2025–2026 reguły 1–2 zmieniają tylko załączniki, reguła 3 tylko treść główną nowelizacji. Odrzucone: reguła 3 dla każdej jednostki (nie tylko ust.), która po zapowiedzi brzmienia nie kontynuuje listy.
Próby dev bez zmian, ale w danych 2025–2026 dochodzi 19 aktów DU, a wśród zmian są prawdziwe jednostki
zamienione w tekst (DU/2025/159 `art_1/pkt_10/lit_e`–`lit_h`, DU/2026/947 `par_1/pkt_4`–`pkt_6`, DU/2025/1052
`par_1/pkt_2`, lit. r–x w DU/2025/1238), więc wróciłem do wersji tylko dla ust. Czego nie próbowałem: kolumny „Lp.” jako sygnału (w obu próbkach dev jest jeden akapit
jednostki po nagłówku z „Lp.”, DU/2024/1973, i nie jest błędem), restartu numeracji („1.” po „7.” bez
nagłówka), wierszy z samymi liczbami bez stopni.

## Próby deweloperskie (`eval/tree_eval.py`, HTML 2024)

Najpierw odtworzyłem wzorce: `tree_eval.py` na obu próbkach daje wyniki identyczne z
`eval/tree_dev_s2024_v0.6.3.dev.txt` i `eval/tree_dev_s7_v0.6.3.dev.txt` (`diff` pusty). Po zmianie:
`eval/tree_dev_s2024_v0.6.4.dev_R.txt`, `eval/tree_dev_s7_v0.6.4.dev_R.txt`.

**Treść główna**: drzewa identyczne w obu próbkach (porównanie JSON 0.6.3 vs nowy na Markdown wszystkich
99 aktów z obu próbek: zmienia się tylko JSON DU/2024/1337 i tylko w załączniku). Wyniki bez zmian:
s2024 R/P 1.0000 (942/942), s7 R 0.9923 (1816/1830), P 0.9962 (1816/1823).

**Załączniki, seed 2024** (49 aktów), 0.6.3 → nowa reguła:

| typ   | R                               | P                                    | fałszywe (none/path) |
|-------|---------------------------------|--------------------------------------|----------------------|
| razem | 0.9936 (4794/4825) → bez zmian   | 0.8521 (4794/5626) → **0.9936** (4794/4825) | 806/26 → 5/26 |
| art   | 1.0000 (480/480) → bez zmian     | 1.0000 → 1.0000                      | 0/0                  |
| par   | 1.0000 (145/145) → bez zmian     | 1.0000 → 1.0000                      | 0/0                  |
| ust   | 0.9994 (1624/1625) → bez zmian   | 0.8908 (1624/1823) → **0.9994** (1624/1625) | 199/0 → 1/0   |
| pkt   | 0.9936 (2172/2186) → bez zmian   | 0.7802 (2172/2784) → **0.9941** (2172/2185) | 600/12 → 1/12 |
| lit   | 0.9589 (373/389) → bez zmian     | 0.9467 (373/394) → **0.9564** (373/390)     | 7/14 → 3/14   |

Przypięcie w załącznikach s2024: akapity bez numeru we właściwej jednostce 0.8247 (2103/2550) → **0.9254**
(3101/3351), słowa 0.8699 → **0.9543** (140299/147024). DU/2024/1337: załączniki P 0.2147 (219/1020) →
**1.0000** (219/219), R 1.0000 (219/219) bez zmian; zniknęło dokładnie 801 fałszywych węzłów (198 ust.
wierszy kart, 599 pkt i 4 lit. z komórek).

**Załączniki, seed 7** (50 aktów): wynik identyczny co do znaku z 0.6.3 (R 1.0000, P 0.9927, 11946/12034).
Pozostałe fałszywe jednostki tam to nie wiersze, które reguła rozpoznaje (niżej).

**DU/2024/1594** (zużyty test, oglądany tylko ten akt, Markdown z konwersji 0.6.3): załączniki R 125/140 bez
zmian, P 125/350 → **125/137**; fałszywe (none+path) 225 → 12. Z pozostałych 12: 11 to § załącznika nr 2
(kart), których HTML 1594 w ogóle nie oznacza jako jednostek (w 1337 oznacza) i które difflib dopasowuje do
„§ 17 ust. N” załącznika nr 1; 1 pkt nie sprawdzałem.

## Dane opublikowane 2025–2026 (DU + MP)

Metoda: kopie wszystkich `.md` z `dziennik-ustaw-md` i `monitor-polski-md` za 2025 i 2026 (5440 plików: DU 3168,
MP 2272) w `/tmp`, drzewo zbudowane `tree.py` 0.6.3 (z gita) i nowym. Kontrola: 0.6.3 odtwarza opublikowane
`.json` we wszystkich 5440 plikach (body, annexes, footnotes identyczne).

- Zmienia się JSON **29 aktów**: DU 28 (2025: 22, 2026: 6), MP 1 (MP/2025/1248).
- **Załączniki**: 7 aktów, wszystkie DU 2025: sześć planów z kartami akwenów (DU/2025/145, 675, 57, 1121, 54,
  1061) i wykaz stref z współrzędnymi DU/2025/947. Węzłów jednostek mniej o **8100** (np. DU/2025/145:
  4879 → 314; DU/2025/947: 401 → 106, 295 punktów „N) 52°…”). Każda zmiana to jednostka → tekst.
- **Treść główna**: 22 akty (21 DU + MP/2025/1248), wszystkie to nowelizacje, które wstawiają wiersze tabel
  bez cudzysłowu (taryfy opłat, wykazy świadczeń, zestawy danych), w DU/2026/1162 ustęp „1. Prawo jazdy …”
  po „6) w § 16 ust. 1 otrzymuje brzmienie:” bez „„”. Węzłów jednostek w DU mniej o 156 netto
  (184 jednostki → tekst, 28 nowych tiretów, 253 jednostki ze zmienioną ścieżką — to prawdziwe pkt/lit./tirety
  aktu, które wisiały pod fałszywym ust. wiersza, np. `par_1/ust_1a/lit_c` → `par_1/pkt_3/lit_c`, DU/2025/1238);
  w MP/2025/1248 +1 (3 ust. → tekst, 4 nowe tirety, 15 zmienionych ścieżek).

**Próba zmienionych węzłów** (`random.Random(20260930)`, warstwowa, bo 94% zmian to karty: 20 z załączników
i 20 z treści głównej; każdy obejrzany w Markdown w kontekście sąsiednich akapitów, DU/2025/1847 i 1162
także całe fragmenty):

| część | poprawne | błędne (nowy błąd) | bez poprawy (błędne przed i po) |
|-------|----------|--------------------|---------------------------------|
| załączniki (20) | 20 | 0 | 0 |
| treść główna (20) | 19 | 0 | 1 |

- Załączniki: 20/20 to wiersze kart akwenów i punkty/litery w ich komórkach (DU/2025/145 ×10, 57 ×5, 54, 675 ×2,
  1061, 1121). „Poprawne” znaczy: zgodne z konwencją HTML sprawdzoną na DU/2024/1337 (dla 2025 nie ma HTML).
- Treść główna: 19 poprawnych, np. `art_1/ust_50/lit_d` → `art_1/pkt_29/lit_d` (DU/2025/179, lit. d
  kontynuuje lit. c), `art_3/ust_9ba/pkt_7` → tekst (punkt wiersza 9ba taryfy, DU/2025/1847), nowy tiret
  „– w pkt 1.5:” w MP/2025/1248. Bez poprawy 1: DU/2025/852 `par_1/ust_1/pkt_6` → `par_1/pkt_6` (punkt z komórki
  tabeli efektów kształcenia; był pod fałszywym ust., teraz jest wprost pod § 1 — nadal fałszywy).

Poza próbą obejrzałem pierwsze (do 14) zmiany każdego z 22 aktów z treścią główną: w 20 wszystkie obejrzane
zmiany są poprawne.
DU/2025/852 częściowo (5 fałszywych jednostek mniej, ale tabela ma dwie kolumny list „1) zasady
bezpieczeństwa 1) określa …” / „2) historia i wiedza …”, więc „2)” z tabeli kontynuuje „1)” aktu, tryb tabeli
się kończy i dalej jest jak w 0.6.3; prawdziwe pkt 2–3 § 1 zostają pod fałszywym `ust_3`, jak w 0.6.3).
DU/2025/1582 częściowo: wiersze ust. poprawione, ale „10) rak jajnika …” po „lit. c) … dodaje się pkt 10 i 11
w brzmieniu:” to nadal `par_1/pkt_10` (reguła 3 zaczyna się tylko od ust.; w 0.6.3 był `par_1/ust_6a/pkt_10`).

## Co zostaje

- **DU/2024/813 (s7)**: schematy sprawozdań finansowych w załącznikach („1. Bilans z podziałem na:” / „1) Aktywa”
  / „A. Aktywa trwałe” / „I. …” / „1. utworzone zgodnie z umową …” / „a) …”), ok. 72 fałszywe ust./pkt/lit.
  i ponad 150 tiretów z formularzy („– kod pocztowy”, „– ulica”; tiretów miara nie liczy). HTML nie oznacza tam
  nic, nawet „1. Bilans”. W Markdown to zwykłe listy; odróżnia je tylko to, że są w komórkach tabeli.
- **DU/2024/440 (s7)**: grupy wierszy tabeli kosztów „1. Badania laboratoryjne” … „8. Koszt pobrania próbek”
  (8 ust.) i objaśnienia kolumn „a) Region …”–„d) …” (4 lit.). Sygnał w Markdown: restart numeracji po
  „7. Szczegółowa analiza kosztów” i akapity z samymi liczbami obok — zbyt słaby, żeby go użyć bez straty
  prawdziwych ust. (restart „1.” po nagłówku bez numeru jest w załącznikach częsty).
- Listy wewnątrz tabel zmienianych bez cudzysłowu, gdy numer z tabeli przypadkiem kontynuuje listę aktu
  (DU/2025/852), i punkty dodawane bez cudzysłowu po lit./tirecie (DU/2025/1582).
- Karty, w których pierwszy rozpoznany wiersz ma numer 1 (nie widziałem w danych), i wykazy współrzędnych
  z numerem bez kropki („5 54°10′40,50″ N …”) — te drugie i tak nie są jednostkami.

**Sygnał z `pdf.py`, który by to rozwiązał**: przynależność linii do komórki tabeli z obramowaniem. `pdf.py` ma
już `page.rects` w `_frame_lines` (używa ich tylko do kreski przypisów). Potrzebne: (1) w `_frame_lines`
znaleźć siatkę tabeli (poziome i pionowe odcinki `rects`/`lines`, które się przecinają) i oznaczyć linie
leżące w jej komórkach (`Line.cell`); (2) przenieść znacznik na `Block` w `_segment` (akapit zaczęty
w komórce); (3) zapisać go w Markdown, bo drzewo buduje się z samego Markdown — np. prefiks albo komentarz
HTML przy akapicie z komórki, co zmienia format publikowanych plików; (4) w `tree.py` akapit z komórki nigdy
nie jest jednostką. Szacunek (niesprawdzony): 60–120 linii w `pdf.py`, kilka w `to_markdown` i `tree.py`,
regeneracja całych danych i ponowna ocena słów/struktury, bo zmienia się Markdown. Nie ruszałem `pdf.py`
(równolegle pracują nad nim inne wątki). Tabele bez ramek (część kart, DU/2024/440?) tego sygnału nie dadzą —
nie sprawdzałem, ile ich jest.
