# Monitor Polski 2012–2024 na eli2md 0.6.2: przegląd jakości (2026-09-29)

Pytanie: czy eli2md 0.6.2 poprawnie konwertuje starsze roczniki Monitora Polskiego (2012–2024),
które pobiera usługa `eli2md-mp-backfill`? Wszystkie liczby poniżej pochodzą z komend uruchomionych
2026-09-29 (skrypty robocze w `/tmp/threadD/`, nie w repozytorium).

## Dostępność PDF

- Listy API `https://api.sejm.gov.pl/eli/acts/MP/<rok>` 2012–2024: 15 885 aktów; **wszystkie** mają
  `textPDF: true` i `textHTML: false` (0 aktów bez PDF, 0 z HTML).
- Cache usługi, rok 2012: 1024 z 1024 aktów kompletnych (`text.pdf` zaczyna się od `%PDF-`, `meta.json`,
  pliki starsze niż 5 min). `texts` w `meta.json`: 1009 × (I, O); 12 × dodatkowy plik T (`…L.pdf`, `…TK.pdf`);
  1 × T + U; 2 akty wieloczęściowe: MP/2012/252 (3 części O) i MP/2012/475 (5 części O).
  Dla nich `…/text/O/M20120252-1.pdf` i `…-3.pdf` zwracają ten sam plik co `text.pdf` (11 318 386 B, 240 stron,
  nagłówki stron ciągłe do „Monitor Polski – 240 – Poz. 252”); MP/2012/475: `-5.pdf` = `text.pdf`
  (10 624 927 B, 134 strony). `text.pdf` jest więc całym aktem.
- Próba 2013–2024 (48 aktów, niżej): 48 z 48 pobranych, wszystkie `texts` = (I, O).

## Próba

- 30 aktów MP 2012 losowo z 1024 (seed 20260929) + po 4 akty z każdego roku 2013–2024 losowo z listy API
  (ten sam generator, dalej w sekwencji) = 78 aktów. Typy: postanowienia 26, obwieszczenia 18, uchwały 16,
  komunikaty 7, zarządzenia 6, umowy międzynarodowe 4, oświadczenie rządowe 1 (typy z `meta.json`).
- Konwersja: eli2md 0.6.2 (`/home/ai/venvs/eli2md-062`), `--ocr auto` (tak jak usługa), 3 procesy.
- Selfcheck: `eval/selfcheck.py` `check()` per akt (słowa PDF vs słowa MD, bez wzorca).
- Kontrola wzrokowa (strona PDF w 100 dpi obok MD), 14 aktów: MP/2012/19 s.1, 2012/596 s.2, 2012/302 s.2,
  2012/988 s.1, 2012/646 s.1 i 5 (umowa, skany), 2013/155 s.2, 2015/781 s.2, 2017/813 s.1 (umowa),
  2018/959 s.6 (umowa, koreański skan), 2019/1021 s.2, 2020/876 s.2, 2022/452 s.1, 2024/803 s.1 (porozumienie),
  2024/1075 s.3.
- Dodatkowo: skan s.1 wszystkich 1024 aktów 2012 i 379 pobranych aktów 2013 (znak wodny, wiersz końca winiety);
  ostatnia pozycja każdego roku 2012–2024 (13 aktów, winieta z przypisem „*)”).
- Dane per akt (typ, strony, OCR, kept/grounded obu wersji) i lista 200 aktów MP 2025:
  `eval/mp_old_years_survey_0.6.2.json`.

## Wyniki selfchecku 0.6.2 (selfcheck z 0.6.2, bez zmian)

| grupa | n | micro kept | micro grounded | mediana kept | kept < 0.95 | grounded < 0.95 |
|---|---:|---:|---:|---:|---:|---:|
| 2012 | 30 | 0.9818 | 0.9842 | 0.984 | 2 | 1 |
| 2013–2024 | 48 | 0.9845 | 0.9946 | 0.992 | 1 | 0 |
| razem | 78 | 0.9837 | 0.9912 | 0.987 | 3 | 1 |

0 błędów konwersji. Dla porównania MP 2025–26 na 0.6.2 (README zbioru): mediana kept 0.985.
Najniższe kept: MP/2012/988 0.924, 2012/995 0.946 — litery znaku wodnego (problem 1); 2017/1195 0.948
i większość pozostałych — „brakujące” słowa to połówki słów przenoszonych w PDF („miro-sławie”), które MD
poprawnie skleja (ograniczenie miary, nie błąd). MP/2019/1021 (0.951): brakuje ukrytej kopii nagłówka wklejonego załącznika
(„(poz. ....)”), pomijanej celowo — fałszywy alarm, jak w MP 2025.

## Problemy (akt, strona, co źle, jak często)

### 1. Niewidoczny ukośny znak wodny „www.rcl.gov.pl” w MP 2012 — POPRAWIONE w tej gałęzi

PDF-y MP 2012 mają w warstwie tekstowej niewidoczny (na renderze go nie ma) napis `www.rcl.gov.pl`:
14 znaków Helvetica, oznaczonych jako `Artifact`, pisanych pod kątem ~55° przez całą stronę (MP/2012/988 s.1:
macierz (3.09, 4.42, −4.42, 3.09), „rozmiar” 98–151 pt). 0.6.2 bierze te litery za tekst:

- pojedyncze litery w akapitach i tabelach: „g o UCHWAŁA”, „Gmina Wilków l 5 – – 15 822 030 c 8 …”
  (MP/2012/302 s.2), „… prowadzącą do l niego polityczną kampanię nienawiści. c Wydarzenie …” (2012/995);
- nagłówek strony nierozpoznany i wklejony w tekst: „12. Reliszko Janusz, l Monitor Polski – 2 – Poz. 596 p za
  zasługi …” (2012/596 s.2; też 2012/638 ×3, 2012/302, 2012/941);
- zepsute przenoszenie: „współprac cownik”, „różnor rodna” (2012/988), „Regiol nalnego” (2012/302);
- sklejone akapity: „za osiągnięcia dla rozwoju kultury . 20. Niewieczerzał Jacek Krzysztof, v na wniosek
  Wojewody Mazowieckiego:” — w PDF to trzy akapity (2012/596 s.2);
- **skany bez OCR**: na stronie-skanie jedynym tekstem są litery znaku wodnego i nagłówek strony, więc 0.6.2
  uznaje ją za stronę z tekstem i obrazem i nie uruchamia OCR. MP/2012/103 (umowa z Wietnamem, 9 stron) na 0.6.2
  z `--ocr`: 0 stron OCR, 9 notek „[Na stronie N PDF jest obraz …]” i wiersze „. v g o . l c r . w w w l Monitor
  Polski – 3 – Poz. 103 p” — z umowy zostaje tylko tytuł. Po poprawce: s.2–9 czytane przez OCR (8 stron),
  s.1 z notką (problem 3). Takich stron (tekst = tylko znak wodny + nagłówek) w 2012: **161 w 14 aktach**
  (12 umów międzynarodowych, 1 protokół, 1 porozumienie; sprawdzone wszystkie strony 476 aktów ze znakiem).

Częstość: znak wodny na s.1 w **476 z 1024** aktów MP 2012 (46%; poz. 1–1023, cały rok; skan s.1 wszystkich
aktów), w próbie 12 z 30 aktów 2012; w 2013: 4 z 379 aktów już pobranych przez usługę (poz. 1–379, skan s.1),
tylko poz. 1–4 — znak wodny znika na początku 2013 r.; w próbie 2013–2024: 0 z 48 (sprawdzone wszystkie strony).

Poprawka: `pdf._watermark` / `_drop_watermark` usuwa przed czytaniem strony znaki `Artifact` pisane ukośnie
(10°–80° od osi). Tekst aktu nie bywa ukośny; nagłówki i winiety z Worda (też `Artifact`, 2020+) są poziome
i zostają. `eval/selfcheck.py` usuwa te same znaki po stronie PDF (inaczej karałby wynik za brak liter
znaku wodnego).

### 2. Winieta „Pozycja N” (MP 2012 poz. 1–130) i „Poz. N*)” — POPRAWIONE w tej gałęzi

Na s.1 aktów MP 2012 poz. 1–130 winieta kończy się wierszem „Pozycja 19”, nie „Poz. 19”. 0.6.2 nie
znajduje końca winiety i zostawia w treści „MONITOR POLSKI DZIENNIK URZĘDOWY RZECZYPOSPOLITEJ POLSKIEJ”,
„Warszawa, dnia 17 stycznia 2012 r.”, „Pozycja 19” (MP/2012/19, 2012/114). Częstość: 130 z 1024 aktów 2012
(skan s.1), w próbie 2 z 30. Ponadto MP/2012/1024 (ostatnia pozycja roku, przypis „*) Ostatnia pozycja
w 2012 r.”): wiersz winiety czytany jako „) Poz. 1024*” — winieta w treści. Ostatnie pozycje wszystkich
lat 2012–2024 (13 aktów, pobrane osobno): 0.6.2 zostawia winietę w treści w 4 z 13 (MP/2012/1024, 2013/1041,
2014/1226, 2021/1206), wersja z poprawką w 0 z 13 (MP/2025/1317 z przypisem „*)” 0.6.2 już obsługuje).

Poprawka: `MASTHEAD_END` = `^[*)\s]*Poz(?:\.|ycja)\s*\d+[*)\s]*$`; selfcheck wycina winietę też do „Pozycja N”.

### 3. Umowy międzynarodowe: treść s.1 to skan na stronie z tekstem — NIE poprawione

S.1 umowy ma warstwę tekstową tylko dla winiety i tytułu, a preambułę i pierwsze artykuły jako obraz (skan).
0.6.2 wstawia wtedy tylko notkę „[Na stronie 1 PDF jest obraz … Jego treści tu nie ma]”; OCR (`--ocr`) czyta
tylko strony bez żadnego tekstu. Brakuje więc preambuły i pierwszych artykułów (obejrzane: MP/2012/646 s.1 —
preambuła, art. 1–2; 2017/813 s.1 — preambuła, art. 1–3; 2024/803 s.1 — preambuła, art. 1; tego tekstu nie ma
w MD). Częstość: 4 z 4 umów w próbie (2012/646, 2017/813, 2018/959, 2024/803);
w opublikowanym MP 2025–26 14 z 14 umów ma tę notkę na s.1. W listach API 2012–2024: 294 umowy
międzynarodowe. Pozostałe strony umów to skany bez tekstu: OCR działa (pol, eng, spa); strony serbskie
(cyrylica, 2012/646 s.4–6) i koreańskie (2018/959 s.6–13) zostają z notką (brak danych tesseract) —
zgodnie z założeniami 0.6.x.

### 4. Drobne

- Kapitaliki w warstwie tekstowej 2012: „Sejmu RzeczypoSpolitej polSkiej”, „Oświadczenie rządOwe”, „Rokiem
  juliana tuwima” (na renderze wersaliki) — 4 z 30 aktów 2012 (2012/988, 995, 1010, 384), tylko nagłówki;
  0 z 48 w 2013–2024. Tak jest w samym PDF (sprawdzone na znakach MP/2012/988); nie poprawiane.
- Linia przypisów narysowana podkreślnikami: „… w Białej Podlaskiej; _______________________” (MP/2013/155 s.1),
  1 z 78.
- Tabele spłaszczone wiersz po wierszu, wieloliniowe komórki jako osobne akapity („TELEFON KOMÓRKOWY”
  oddzielone od swojego wiersza, 2024/1075 s.3), dwa wiersze sklejone na granicy stron („41 … 42 …”) —
  jak w MP 2025 (znane ograniczenie).
- Granica strony po pozycji listy kończącej się przecinkiem skleja dwa akapity: „12. Reliszko Janusz, za
  zasługi w działalności na rzecz ochrony przeciwpożarowej:” (2012/596 s.1/2; także po poprawce) — ogólna
  heurystyka, nie specyfika starych roczników; częstość nie mierzona.

### Bez problemów

- Front matter: 78 z 78 zgodne z `meta.json` (title, rank = typ, eli, announcement_date, promulgation_date,
  entry_into_force, display_address, position, status_pl) i nagłówek `# tytuł`. `entry_into_force` brak
  w 39 `meta.json` (postanowienia itp.), więc brak też w front matter.
- Winieta i nagłówki stron 2013–2024: w 48 aktach próby żadnego niewyciętego nagłówka ani winiety (winieta
  wycięta w 48 z 48, 4 wiersze do „Poz. N”).
- § / Art. jako `#####`: poprawne w obejrzanych (2015/781: 10 × § z ust./pkt/lit./tiret, 2022/452: § 1–2
  i Art. 1–4 aneksu w załączniku, 2019/1021: § 1–3).
- Obwieszczenia z długimi listami (obejrzane 2013/155, 2020/876): pozycje jako osobne akapity.
- Ukryte kopie nagłówków wklejonych załączników (2019/1021 „(poz. ....)”) pomijane jak w 2025.

## Poprawka: pomiar base (0.6.2) vs new (ta gałąź)

Próba 78 aktów, selfcheck z tej gałęzi (bez znaku wodnego, winieta do „Pozycja N”) dla obu wersji:

| wersja | micro kept | micro grounded | mediana grounded | kept < 0.95 | grounded < 0.95 |
|---|---:|---:|---:|---:|---:|
| 0.6.2 | 0.9849 | 0.9880 | 0.996 | 1 | 9 |
| ta gałąź | 0.9847 | 0.9942 | 1.000 | 1 | 0 |

Zmieniło się 14 z 78 plików MD (12 ze znakiem wodnym + 2 „Pozycja”), 64 identyczne (bez wiersza
`converter`). Spadek kept o 0.0002 to artefakt miary: nowa wersja poprawnie skleja przeniesienia
(„współpracownik”, „różnorodna”, „społecznych”, „wysokości”), a selfcheck liczy po stronie PDF połówki słów;
0.6.2 miało je rozdzielone przez literę znaku wodnego („współprac cownik”), więc „trafiało” w połówkę.
Selfcheckiem z 0.6.2 (który liczy litery znaku wodnego jako słowa PDF): 0.6.2 kept 0.9837 / grounded 0.9912,
ta gałąź 0.9792 / 0.9930 — spadek kept to litery znaku wodnego i winieta „Pozycja”, których nowa wersja
celowo nie przepisuje.

**200 losowych aktów MP 2025** (seed 20260930, z 1317 w cache; `--ocr auto`, jak zbiór): 200 z 200 plików MD
identycznych w obu wersjach. Selfcheck (z tej gałęzi) dla obu: micro kept 0.9972, grounded 0.9990, mediana kept
0.983, grounded 0.993, kept < 0.95: 7, grounded < 0.95: 1 — i dla wszystkich 200 aktów te same wartości co
w opublikowanym `eval/selfcheck_mp_2025_2026_v0.6.2.json` (selfcheck z 0.6.2); selfcheck z 0.6.2 na wynikach
tej gałęzi też daje micro kept 0.9972, grounded 0.9990, kept < 0.95: 7 — zmiana selfchecku nie rusza wyników
2025. Nic się nie pogorszyło.

Testy: `python -m unittest discover -s tests` — 46 testów, OK (2 nowe: `test_masthead_end`, `test_watermark`).
Wersja w `__init__.py` pozostaje 0.6.2 (nie podbijałem; przed użyciem w usłudze trzeba nadać nową).

## Rekomendacja

- **2012: nie publikować z 0.6.2.** 476 z 1024 aktów (46%) ma w tekście litery znaku wodnego (sklejone akapity,
  nierozpoznane nagłówki stron, zepsute przeniesienia), w 14 z nich 161 stron-skanów w ogóle nie trafia do OCR;
  131 aktów (13%) ma winietę w treści. Przekonwertować 2012 wersją z tej gałęzi (np. jako 0.6.3).
- **2013–2024: można publikować na 0.6.2** z tymi samymi znanymi ograniczeniami co MP 2025 (s.1 umów
  międzynarodowych bez treści, tabele spłaszczone). W próbie 48 aktów nie znalazłem problemów swoistych dla tych
  roczników; selfcheck 2013–2024 (micro kept 0.9845, grounded 0.9946) jest na poziomie MP 2025. Wyjątki, które
  ta gałąź też poprawia: znak wodny w MP/2013/1–4 i winieta w ostatnich pozycjach 2013, 2014, 2021.
  Ograniczenie próby: problem obecny w 5% aktów 2013–2024 zostałby przeoczony z prawdopodobieństwem ok. 9%
  (0.95^48), obecny w 2% — ok. 38% (0.98^48).
- Najprościej: całość 2012–2024 z wersją z tej gałęzi (dla 2013–2024 wynik jest identyczny z 0.6.2 poza
  aktami ze znakiem wodnym / winietą z „*)”; na 200 aktach 2025 — 0 różnic).
- Usługa `eli2md-mp-backfill` najpierw pobiera wszystkie 15 885 aktów, dopiero potem konwertuje
  (`dataset.main`), więc do tej pory nie przekonwertowała nic (o 23:15 w `/home/ai/data/mp-backfill` 0 plików
  `.md`). Nie podmieniać pakietu w jej venv w trakcie (proces główny ma załadowane 0.6.2 i zapisze
  `converter: eli2md 0.6.2`, a workery mogłyby zaimportować nowy kod — nie sprawdzałem). Albo zrestartować
  ją z nową wersją (pobrane pliki zostają w cache), albo po jej zakończeniu przekonwertować 2012 ponownie
  (`--all --years 2012`; bez `--all` akty z niezmienionym `changeDate` nie są konwertowane ponownie).
- Warto przed publikacją (osobna zmiana): OCR obrazu na stronach z warstwą tekstową, gdy obraz to skan tekstu
  (s.1 umów: 294 umowy w 2012–2024 wg list API, 14 w opublikowanym MP 2025–26). Wymaga decyzji, jak oznaczać
  stronę częściowo z OCR (notka, `pages_ocr`, selfcheck pomija dziś całe strony OCR).

## Nie sprawdzone

- Pełne roczniki 2013–2024 (tylko 48 losowych + 13 ostatnich pozycji + s.1 379 aktów 2013).
- Struktura jednostek (art./§/ust./pkt, drzewo JSON) — brak wzorca; tylko kontrola wzrokowa kilku aktów.
- Jakość OCR na starych skanach (tylko przejrzana w MP/2012/646; błędy typu „wzajeranego”, „łub”).
- Długie akty starszych roczników (> 33 stron w próbie nie było; MP/2012/252 ma 240 stron) — czas i pamięć
  konwersji w usłudze.
- Czy w latach 2013–2024 są inne ukośne/niewidoczne warstwy tekstu niż `www.rcl.gov.pl`.
