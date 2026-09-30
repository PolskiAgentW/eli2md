# Dziennik Ustaw 1918–2011: istniejąca warstwa tekstowa PDF a własny OCR (tesseract), eli2md 0.6.5 (2026-09-30)

Pytanie: jaka jest jakość warstwy tekstowej w PDF-ach Dziennika Ustaw sprzed 2012 r. i czy OCR tesseractem
(tak jak w `eli2md --ocr`) dałby lepszy tekst? Od tego zależy, czy i jak konwertować DU 1918–2011.

Tylko pomiar: kod eli2md nie był zmieniany. Skrypt: `eval/du_pre2012_survey.py` (etapy `lists`, `sample`,
`measure`, `ocr2`, `probe`, `summary`). Dane per akt i strona: `eval/du_pre2012_survey_0.6.5.json`. Pliki robocze
(pełne teksty stron, obrazy do kontroli wzrokowej, wyniki eli2md): `/tmp/du_pre2012/`.

## Wynik w skrócie

- W listach API jest **64 452** aktów DU z lat 1918–2011, **55 473** z nich ma PDF i nie ma HTML (policzone ze
  wszystkich 94 list rocznych, nie szacowane).
- W losowej próbie (32 akty, 104 strony) warstwę tekstową ma 102 ze 104 stron. PDF-y są trzech rodzajów:
  skany z niewidoczną warstwą OCR z Adobe Acrobat 9 (lata 1918–1999), PDF-y z QuarkXPress z czcionką
  „Univers-PL”, w której polskie litery są zakodowane błędnie (2000 – połowa 2010), oraz PDF-y z InDesign
  z poprawnym kodowaniem (od połowy 2010).
- Miara zastępcza (odsetek słów, które zna hunspell pl_PL), mediana po aktach:

  | epoka | warstwa tak, jak ją czyta pdfplumber | warstwa: kolumny po kolei, sklejone wiersze, poprawione kodowanie | tesseract pol |
  |---|---:|---:|---:|
  | 1918–1939 | 0,776 | 0,823 | 0,939 |
  | 1940–1989 | 0,790 | 0,787 | 0,973 |
  | 1990–2000 | 0,936 | 0,976 | 0,984 |
  | 2001–2011 | 0,677 | 0,973 | 0,983 |

- Tesseract `pol` nie ma znaku „§” w modelu, więc na porównywanych stronach nie odczytał ani jednego z 335
  oznaczeń „§ N” (odczytywał je jako „8 30.”, „$ 31.”, „81.”). `pol+eng`, czyli ustawienie eli2md, odczytał 146 z 335.
- eli2md 0.6.5 na tych PDF-ach zostawia istniejącą warstwę. Z `--ocr` wynik dla skanu z warstwą jest identyczny
  bajt w bajt. Tekst dwóch łamów przeplata wiersz po wierszu (dwa łamy ma 51 z 64 zmierzonych stron). Błędne
  kodowanie z lat 2000–2010 przechodzi do wyniku bez zmian. W co najmniej 22 z 32 aktów PDF zawiera też tekst
  sąsiednich pozycji.

## 1. Liczba aktów (API, 2026-09-30)

`GET https://api.sejm.gov.pl/eli/acts/DU/<rok>` dla każdego roku 1918–2011 (94 zapytania, po kolei, ≥ 1 s
odstępu). We wszystkich listach `count` = `totalCount` = liczba `items`.

| rok | aktów | `textPDF` | `textHTML` | PDF bez HTML |
|---|---:|---:|---:|---:|
| 1950 | 536 | 536 | 100 | 436 |
| 1990 | 547 | 547 | 114 | 433 |
| 1997 | 1136 | 1136 | 221 | 915 |
| 2005 | 2260 | 2260 | 309 | 1951 |
| 2010 | 1776 | 1776 | 349 | 1427 |
| 2011 | 1778 | 1778 | 349 | 1429 |

| lata | aktów | `textPDF` | `textHTML` | PDF bez HTML |
|---|---:|---:|---:|---:|
| 1918–1939 | 17 452 | 17 452 | 2 174 | 15 278 |
| 1944–1989 | 14 955 | 14 954 | 1 492 | 13 463 |
| 1990–1999 | 8 441 | 8 441 | 1 324 | 7 117 |
| 2000–2009 | 20 050 | 20 044 | 3 286 | 16 759 |
| 2010 | 1 776 | 1 776 | 349 | 1 427 |
| 2011 | 1 778 | 1 778 | 349 | 1 429 |
| **1918–2011** | **64 452** | **64 445** | **8 974** | **55 473** |

- Lata 1940–1943 mają 0 aktów. Lista API ma w `searchQuery` pole `"exile": false`. Czy Dziennik Ustaw na
  uchodźstwie da się pobrać innym zapytaniem: NIE WIEM (nie sprawdzałem).
- 7 aktów bez PDF: 1983 (1), 2003 (1), 2004 (4), 2008 (1).
- `eli2md.dataset` pomija akty z `textHTML` (`if not it.get("textPDF") or it.get("textHTML"): continue`).
  Dla lat 1918–2011 wziąłby więc 55 473 akty.

## 2. Metoda

**Próba.** Ziarno **20260930**, `random.Random(seed).sample(...)`, po 8 aktów z każdej epoki: 1918–1939,
1940–1989 (w praktyce 1944–1989), 1990–2000, 2001–2011. Losowane z list API (akty z `textPDF`, po sortowaniu
według (rok, pozycja)), epoki kolejno tym samym generatorem. Osobno opisuję 6 aktów, które już były w cache
(DU/1935/1, 1964/16, 1990/1, 1997/78, 2005/1, 2010/1). Nie były losowane, więc nie wchodzą do liczb dla epok.
Dodatkowo 10 PDF-ów ze stałych pozycji wokół zmian formatu (etap `probe`, rozdział 5).
Pobrania szły przez `eli2md.eli.fetch` (wspólny cache `~/cache/eli`), po kolei. Pobrałem 42 PDF-y (32 z próby
i 10 próbek formatu) oraz 1 plik HTML.

**Na każdej stronie aktu** (do 150 stron na akt) pdfplumber podaje: liczbę znaków warstwy (bez spacji),
znaki `(cid:)`, pokrycie strony obrazami i rozdzielczość największego obrazu.
**Na maksymalnie 3 stronach aktu** (1, środkowa `(n+1)//2`, ostatnia) porównuję:
- warstwę: `page.extract_text()` pdfplumbera, czyli wiersze w poprzek strony, tak jak czyta eli2md;
- warstwę po łamach: gdy strona ma dwa łamy (mniej niż 3% słów przecina środek bloku tekstu, a po każdej
  stronie jest ponad 25% słów), najpierw lewy łam, potem prawy;
- eksperyment tylko dla stron z czcionkami `*PL`: poprawione kodowanie (rozdział 4.2), odstęp słów 1,5 pt,
  łamy po kolei;
- tesseract 5.5.0 `-l pol --psm 3` (TSV) na stronie wyrenderowanej przez pypdfium2 w 300 dpi w skali szarości,
  `OMP_THREAD_LIMIT=2`;
- etap `ocr2`: te same strony w `-l pol+eng`, czyli w pierwszym przebiegu trybu `auto` w eli2md.

**Miara zastępcza (bez wzorca).** Najpierw sklejam wyrazy przeniesione myślnikiem na końcu wiersza
(`(\w)[-­¬]\s*\n\s*(\w)`). Tokeny to ciągi liter (`[^\W\d_]+`) o długości co najmniej 3. Liczę odsetek tokenów, które
przyjmuje libhunspell 1.7 z pl_PL (pakiet hunspell-pl 1:25.2.3). Program `hunspell` nie jest zainstalowany,
więc biblioteka jest wołana przez ctypes, w kodowaniu ISO8859-2 zgodnym ze słownikiem. Warianty:
- `joined`: sklejone są też wyrazy przerwane na końcu wiersza bez myślnika („jed” + „nostek”), jeśli po
  sklejeniu wyraz jest w słowniku, a któraś część nie;
- `prewar`: token odrzucony przez słownik jest liczony jako poprawny, gdy słownik przyjmuje go po
  przepisaniu na pisownię sprzed 1936 r. Przepisania: `rj`→`ri` („materjał”), końcówka `-yj`→`-ii`/`-ji`,
  `-em`→`-ym`/`-im` („niniejszem”), `ńc`→`nc`.

Wynik aktu to średnia ważona tokenami z jego stron, na których obie wersje mają co najmniej 30 tokenów
(61 z 64 stron z OCR). Dla epok podaję medianę po aktach. Niepewność: przedział bootstrap 95% mediany różnicy
OCR − warstwa (10 000 losowań aktów ze zwracaniem, ziarno 20260930) oraz liczba aktów, w których OCR wypada wyżej.

Osobno liczę: udział liter ąćęłńóśźż wśród liter, liczbę „§ N” i „Art. N” oraz początki wierszy, które wyglądają
na źle odczytany „§” (`8 30.`, `$ 31.`, `81.`). Szukam też innych numerów pozycji w nagłówku („Poz. 64 i 65”),
ale tylko w pierwszych 6 wierszach tekstu, więc to dolna granica.

## 3. Wyniki

### 3.1 Strony

| epoka | akty | stron | warstwa ≥ 100 znaków | skan (obraz ≥ 80% strony) | skan bez warstwy |
|---|---:|---:|---:|---:|---:|
| 1918–1939 | 8 | 35 | 35 | 35 | 0 |
| 1940–1989 | 8 | 13 | 13 | 13 | 0 |
| 1990–2000 | 8 | 34 | 32 | 33 | 2 (DU/1992/277 s.2, DU/1994/616 s.1) |
| 2001–2011 | 8 | 22 | 19 | 0 | 0 |
| razem | 32 | 104 | 99 (102 z ≥ 20 znakami) | 81 | 2 |

- Mediana stron na akt to 2 (w 2001–2011: 2,5). Średnie wynoszą 4,38 / 1,62 / 4,25 / 2,75; na średnią wpływa
  pojedynczy dłuższy akt (DU/1936/301 ma 18 stron).
- Skany: 66 stron w 150 dpi, 15 w 300 dpi, JPEG w skali szarości (8 bitów). Rozmiar PDF-a: mediana na stronę
  0,36 MB (1918–1939), 0,49 MB (1940–1989), 0,58 MB (1990–2000), 0,12 MB (2001–2011).
- W 2001–2011 cztery strony DU/2006/1762 (s.2–5) to formularze wstawione jako obraz. Warstwa ma na nich tylko
  nagłówek (33–104 znaki).
- Dwa łamy ma **51 z 64** stron, na których robiłem OCR: 13/18, 11/13, 12/16 i 15/17 w kolejnych epokach.

### 3.2 Poprawność słów: warstwa a tesseract (mediana po aktach, w nawiasie min–max; n = 8 aktów na epokę)

| epoka | warstwa (pdfplumber) | warstwa po łamach¹ | + sklejone wiersze | tesseract pol | tesseract pol+eng |
|---|---:|---:|---:|---:|---:|
| 1918–1939 | 0,776 (0,564–0,905) | 0,784 | 0,823 (0,600–0,923) | **0,939** (0,786–0,972) | 0,937 |
| 1940–1989 | 0,790 (0,600–0,912) | 0,780 | 0,787 (0,598–0,915) | **0,973** (0,872–0,989) | 0,970 |
| 1990–2000 | 0,936 (0,660–0,986) | 0,941 | 0,976 (0,926–0,991) | 0,984 (0,960–0,994) | 0,982 |
| 2001–2011 | 0,677 (0,577–0,896) | 0,973¹ | 0,973 (0,952–0,991) | 0,983 (0,950–0,997) | 0,982 |
| razem (32) | 0,776 | 0,917 | 0,925 | 0,976 | 0,970 |

¹ Dla stron z czcionkami `*PL` (DU/2000/291 i wszystkie akty 2001–2010 z próby): także z poprawionym kodowaniem
(rozdział 4.2). eli2md 0.6.5 tego nie robi.

Różnica OCR (pol) − warstwa po łamach i sklejeniu, per akt:

| epoka | mediana | 95% bootstrap | aktów z wyższym OCR |
|---|---:|---|---:|
| 1918–1939 | +0,058 | [+0,039; +0,311] | 8/8 |
| 1940–1989 | +0,133 | [+0,070; +0,333] | 8/8 |
| 1990–2000 | +0,007 | [−0,013; +0,022] | 4/8 |
| 2001–2011 | +0,005 | [−0,002; +0,025] | 5/8 |

W porównaniu z warstwą w odczycie pdfplumbera różnica wynosi +0,094 / +0,130 / +0,049 / +0,302.

- **Pisownia sprzed 1936 r.** Hunspell ma słownik współczesny, więc odrzuca np. „niniejszem”, „kancelarji”,
  „materjałów”. Przepisania `prewar` zmieniają medianę 1918–1939 niewiele: warstwa 0,784 → 0,789,
  OCR 0,939 → 0,940. Obejmują tylko część dawnej pisowni (np. nie „zgóry”, „spowodu”), więc obie liczby dla tej
  epoki są zaniżone.
- **Polskie litery** (mediana udziału ąćęłńóśźż wśród liter na stronie): w 2001–2011 warstwa ma 0,0097, po
  poprawie kodowania 0,0502, OCR 0,0498. W pozostałych epokach warstwa i OCR są blisko siebie
  (0,0505 i 0,055; 0,0546 i 0,0555; 0,0547 i 0,0521).
- **„§”**: na 61 porównywanych stronach warstwa ma 335 „§ N”. Tesseract `pol` ma 0, a 231 początków wierszy
  wygląda na źle odczytany „§”. `pol+eng` ma 146 „§” i 124 takie początki wierszy. Przyczyna:
  `combine_tessdata -u pol.traineddata` (pakiet tesseract-ocr-pol 1:4.1.0-2build1, wersja modelu
  `4.00.00alpha:pol:synth20170629`) daje zbiór 114 znaków bez „§”. Model `eng` ma „§”.
  „Art. N”: warstwa 15, OCR 19 (w próbie mało ustaw).
- **Tesseract**: mediana pewności słów na stronie 96,2. Czas strony od 0,8 do 14,6 s, mediana 3,35 s. Maszyna
  była w tym czasie współdzielona z usługą `eli2md-mp-backfill` (3 procesy z OCR), więc czasy są orientacyjne.

### 3.3 Akty spoza losowania (z cache, n = 6)

Mediana: warstwa 0,752, po łamach i poprawie kodowania 0,930, OCR pol 0,949. DU/2010/1 (565 stron, umowa
stowarzyszeniowa z Albanią) ma 152 zmierzone strony (1–150, 283, 565). 150 z nich to obraz, a w warstwie
jest tylko nagłówek („little_text+image”). Strona 283 to skan angielskiego tekstu obrócony o 180°: tesseract bez obrotu daje
„AHL” zamiast „THE” (pewność 41). Strona 565 ma polską klauzulę ratyfikacyjną jako tekst i angielską deklarację
jako obraz.

## 4. Kontrola wzrokowa i rodzaje błędów

Strony wyrenderowałem do PNG (`/tmp/du_pre2012/v_*.png`) i porównałem kilka wierszy obrazu z obydwoma tekstami.

1. **DU/1936/301 s.1** (1936, skan 150 dpi, dwa łamy, `Times-Roman` + `HiddenHorzOCR`). Warstwa na renderze
   jest niewidoczna, widać tylko skan.
   Obraz: „Ministra Skarbu z dnia 14 grudnia 1935 r.”. Warstwa: „Ministra Slkarbu z dnia …”. OCR: bez błędu.
   Obraz: „§ 1. 1) Artykuły, powołane w rozporządzeniu niniejszem”. Warstwa: „§ 1. 1) Arty,kuły, powołane w
   roz,Porz~dzenju … nlll1ejszem”. OCR: „81. 1) Artykuły, powołane w rozporządzeniu niniejszem”.
   W tej czcionce OCR czyta część „g” jako „ś” („podatkoweśo”). Miara (warstwa 0,74, OCR 0,96) zgadza się
   z obrazem.
2. **DU/1977/65 s.1** (zaszumiony skan). Obraz: „cze, Łazy, Mierzęcice, Ogrodzieniec, Olkusz, Pilica,”.
   Warstwa: „€ze; . ta'ly, MieFZE1ceice, OgForliZ1>el'lie€j Olkusa, Pił<iea',”. OCR: „ź cze, Łazy, Mierzęcice,
   Ogrodzieniec, Olkusz, Pilica,”. Warstwa zawiera też śmieci z marginesu („·~r·”, „~:~ł ~\I.'”). Błędy OCR:
   „Nr t6” (16), „1977 x.” (r.), „$ 2.” (§ 2.). Strona zaczyna się końcem poz. 64 (nagłówek „Poz. 64 i 65”).
   Miara (0,59 / 0,99) zgadza się z obrazem.
3. **DU/1992/277 s.4** (1992, skan 300 dpi). Warstwa po łamach zgadza się z obrazem w sprawdzanych wierszach,
   ale nie ma myślników przeniesień („jed” / „nostek”, „wymia” / „rze”), stąd 0,95. Po sklejeniu wierszy 0,998,
   OCR 0,996. Warstwa ma poprawnie „§ 30.” i „§ 31.”, OCR ma „8 30.” i „$ 31.”.
4. **DU/2002/647 s.1** (2002, PDF z QuarkXPress). Obraz: „SZCZEGÓLNE ZASADY BEZPIECZEŃSTWA OBOWIĄZUJĄCE PRZY
   UPRAWIANIU PŁETWONURKOWANIA”, „Maksymalna głębokość nurkowania”. Warstwa: „BEZPIECZE¡STWA OBOWIÑZUJÑCE …
   P¸ETWONURKOWANIA”, „g∏´bokoÊç”. Po poprawie kodowania: identycznie jak na obrazie. OCR: bez błędu.
   Strona zaczyna się od „Załącznik nr 5” do poz. 646.
5. **DU/1938/268 s.2** (porozumienie z Francją: łam polski i łam francuski obok siebie). Tu miara zawodzi:
   francuskie słowa są dla hunspella błędne, więc warstwa ma 0,63, a OCR 0,69. W polskim łamie oba teksty są
   w większości poprawne (warstwa „Rząda­ ).1li”, OCR „Rząda- mi”). OCR `pol` zamienia é na ć („Chargć”,
   „Sućdois”). Czytanie wierszami przeplotłoby zdanie polskie z francuskim.

Na stronach 1–4 obraz potwierdza kierunek i skalę różnicy z miary. Strona 5 pokazuje ograniczenie miary.

### 4.1 Rodzaje PDF

| typ | gdzie w próbie | producent / czcionki | warstwa |
|---|---|---|---|
| skan + niewidoczna warstwa OCR | wszystkie 23 losowe akty 1918–1999, 4 z cache, próbki formatu 1999/661 i 1999/1322 | „Adobe Acrobat 9.0/9.2 Paper Capture Plug-in”, CreationDate 2010-11 – 2011-01 (1999/1322: 2016-09); `Times-Roman`/`Helvetica` + `HiddenHorzOCR` | niewidoczna, cudzy OCR |
| PDF z QuarkXPress, czcionki `Univers-PL` | DU/2000/291, 2000/673, 2001/1506, 2002/251, 2002/647, 2004/1664, 2005/1, 2005/1369, 2006/862, 2006/1762, 2010/1: 11 z 11 | Acrobat Distiller 4.0 / 5.0.5 / 7.0 for Macintosh; 2010/1: Distiller 8.1 (Windows) | tekst z błędnym kodowaniem polskich liter |
| PDF z InDesign, czcionki `UniversPro` | DU/2010/888 (2010-07-21), 2010/1776, 2011/1, 2011/445, 2011/889, 2011/1334, 2011/1630 | InDesign CS3 / CS5 + Distiller 8.1 | poprawna |

- Zmiana skanu na Quark: DU/1999/1322 to skan, a DU/2000/291, 2000/673 i 2000/1 to Quark. Strona 1 DU/2000/1
  to obraz (0 znaków, pokrycie 0,8).
- Zmiana Quark na InDesign nastąpiła między DU/2010/1 (styczeń 2010) a DU/2010/888 (lipiec 2010). Dokładnej
  pozycji: NIE WIEM.
- Lat 2007–2009 nie ma w próbie. To, że są tam PDF-y Quark z `Univers-PL`, wnioskuję tylko z 2006 i z DU/2010/1:
  NIE WIEM.

### 4.2 Błędy warstwy

- **Skany 1918–1989**: błędy znaków cudzego OCR („Slkarbu”, „roz,Porz~dzenju”, „MieFZE1ceice”), śmieci
  z marginesów i szumu. Miara: 0,78–0,79.
- **Skany 1990–1999**: znaki są w większości poprawne. Brakuje myślników przeniesień, więc wyraz ma dwie
  połowy. Po sklejeniu miara wynosi 0,976 wobec 0,984 w OCR.
- **Quark 2000–2010**: kody znaków czcionek `*PL` to MacCE, a PDF mapuje je jak MacRoman: ł→∏, ą→à, ę→´, ś→Ê,
  ż→˝, ć→ç, ń→ƒ, Ą→Ñ, Ń→¡, Ł→¸. `c.encode("mac_roman").decode("mac_latin2")` dla znaków tych czcionek
  przywraca litery: udział polskich liter po zmianie 0,0502, w OCR 0,0498. Spacja po jednoliterowym wyrazie
  nie jest znakiem, tylko odstępem. W DU/2002/647 jest 47 takich miejsc, z odstępem 1,95–6,3 pt (mediana 2,78 pt).
  55% z nich ma ≤ 3 pt, więc pdfplumber z domyślnym `x_tolerance=3` skleja „zdnia”, „wsprawie”.
  Z `x_tolerance=1.5` wyrazy się rozdzielają. Te znaki są zmapowane, choć błędnie, więc test
  eli2md na `(cid:)` (> 10% znaków) ich nie wyłapuje.
- **Dwa łamy** ma 51 z 64 stron (w każdej epoce ponad połowa). Czytanie wierszami w poprzek strony przeplata łamy. W DU/2011/1630
  (warstwa poprawna) daje to 0,896, a czytanie po łamach 0,971.
- **Tekst innych pozycji w PDF-ie aktu**: w co najmniej 22 z 32 losowych aktów pierwsza lub ostatnia strona
  ma w nagłówku inne pozycje (to dolna granica, heurystyka nie wyłapała np. DU/1977/65). Przykłady:
  DU/1934/457 zaczyna się od poz. 454 („Poz. 454, 455, 456 i 457”), strona 1 DU/1982/61 to cała poz. 60,
  DU/2001/1506 ma nagłówek „Poz. 1505, 1506 i 1507”, DU/2002/647 zaczyna się od załącznika do poz. 646.
  Dotyczy to każdej metody, także OCR.

### 4.3 Błędy tesseracta (pol, 300 dpi)

- „§” → „8”, „$”, „81.”. Model `pol` nie ma tego znaku (rozdział 3.2).
- W kroju sprzed wojny „g” → „ś” („podatkoweśo”, „śdy”); „ł” → „t” („cztonkowskimi”); „Ż” → „Z”.
- Cyfry i skróty: „Nr t6”, „1977 x.”, „Poz. 60 1 6f”.
- Obce języki: z `pol` znika é („Chargć”). Strony obrócone o 180° wymagają OSD; eli2md robi to w `ocr_page`,
  mój pomiar nie.
- Formularze i obrazy nietekstowe: DU/2006/1762 s.3, pewność 40, miara 0,07.

## 5. eli2md 0.6.5 na tych PDF-ach

Uruchamiałem `/home/ai/venvs/eli2md-065/bin/python -m eli2md <ELI> [--ocr] -o …` z katalogu `/tmp`, bo tam
działa zainstalowana wersja 0.6.5. W trakcie pomiaru drzewo `eli2md/` w repozytorium zmieniło się na 0.6.6
i tej wersji nie używałem. Wyniki są w `/tmp/du_pre2012/eli2md_out/`.

| akt | typ | bez `--ocr` | z `--ocr` |
|---|---|---|---|
| DU/1936/301 (18 s.) | skan + warstwa | 10,6 s, warstwa Acrobata | 12,0 s, wynik **identyczny** (`cmp`) |
| DU/2002/647 (3 s.) | Quark `Univers-PL` | 0,56 s | identyczny |
| DU/1994/616 (2 s.) | s.1 skan bez warstwy, s.2 skan + warstwa | s.1: notka „nie ma warstwy” | s.1: OCR pol+eng (7,3 s), s.2 bez zmian |

- **Warstwa zostaje, także z `--ocr`.** Strona ze skanem ma tekst, więc nie trafia do OCR stron bez tekstu
  (`pdf.convert`). Obraz na stronie jest uznawany za tło (`_image_text`), bo leży na nim ponad 30 znaków warstwy
  (`IMAGE_TEXT_CHARS = 30`). OCR obrazu więc się nie uruchamia.
- **Każda strona skanu dostaje notkę**
  „> [Na stronie N PDF jest obraz (np. wzór, rysunek, skan). Jego treści tu nie ma, jest tylko w PDF.]”
  (DU/1936/301: 18 notek, `pages_with_images: "1-18"`), choć tekst skanu jest w wyniku, bo pochodzi z warstwy.
- **Łamy przeplecione**, np. DU/1936/301: „osób prawnych Siedzibę zarządu określa MINISTRA SKARBU statuI lub inny
  akt, na Iktórym osoba prawna opie ROZPORZĄDZENIE też ra swe istnienie.” W całym pliku jest 6 nagłówków
  `##### §` przy 72 wystąpieniach „§ N” w tekście.
- **Kodowanie Quark przechodzi bez zmian**: DU/2002/647 daje „Za∏àcznik nr 5”, „ROZPORZÑDZENIE PREZESA RADY
  MINISTRÓW”, „zdnia 17 maja 2002 r.”. Wynik zaczyna się od załącznika do poz. 646.
- **Strona bez warstwy z `--ocr`** (DU/1994/616 s.1): tekst OCR jest poprawny, ale „§ 1.”, „§ 2.” i „§ 4.” wyszły
  jako „$ 1.”, „$ 2.” i „$ 4.”, a tylko „§ 3.” jako „§ 3.”.

## 6. Rekomendacja

Konwersja DU 1918–2011 eli2md 0.6.5 bez zmian nie daje tekstu, który spełnia opis formatu z README. W próbie
dwa łamy ma 51 z 64 stron, tekst innych pozycji jest w co najmniej 22 z 32 PDF-ów, kodowanie `Univers-PL` jest
błędne w 11 z 11 PDF-ów Quark, a skany mają notkę o braku treści. Pomiary wskazują różne źródło tekstu dla
różnych okresów, czyli **podejście mieszane według typu PDF**:

1. **2000 – połowa 2010, Quark** (lata 2000–2009: 16 759 aktów bez HTML, do tego część 2010):
   **istniejąca warstwa** z poprawionym kodowaniem czcionek `*PL`, odstępem słów 1,5 pt i łamami po kolei.
   Tesseract daje tu +0,005 (przedział [−0,002; +0,025]) i gubi „§” (97 w warstwie, 0 w `pol`, 17 w `pol+eng`).
   Nie wymaga OCR ani obrazów.
2. **Połowa 2010 – 2011, InDesign**: istniejąca warstwa, potrzebne tylko łamy.
3. **1990–1999, skany z warstwą** (7 117 aktów bez HTML): słowa w warstwie i w OCR wychodzą podobnie
   (+0,007, przedział [−0,013; +0,022], 4/8 aktów). Warstwa ma „§” (89, a OCR 0 w `pol` i 28 w `pol+eng`).
   Rekomendacja: warstwa z łamami i sklejaniem przerwanych wyrazów, OCR tylko dla stron bez warstwy
   (2 z 34 stron).
4. **1918–1989, skany z warstwą** (28 741 aktów bez HTML): **własny OCR**. Wyżej w 16 z 16 aktów, mediana
   +0,058 i +0,133. Tesseract gubi jednak „§”, więc potrzebne jest źródło „§”: albo z warstwy (dopasowanie
   tekstów), albo poprawka „8 N.”/„$ N.” na początku akapitu, albo inny model. Który sposób daje lepszą strukturę:
   NIE WIEM, bez wzorca tego nie zmierzyłem.

Warunki wspólne dla wszystkich okresów:
- (a) czytanie dwóch łamów po kolei;
- (b) wycięcie aktu ze stron, na których są inne pozycje (numer pozycji jako nagłówek aktu, np. „301.”);
- (c) bez notki „treści tu nie ma” na stronie skanu, której tekst pochodzi z warstwy albo OCR.

**Następny krok przed decyzją o skali:** pomiar względem wzorca. 8 974 akty sprzed 2012 r. mają w API
`textHTML`. Sprawdziłem jeden: HTML DU/1982/61 to tekst tej ustawy („Ustawa z dnia 27 lutego 1982 r. o zmianie
ustawy o orderach i odznaczeniach … Art. 1.”). Czy HTML dla starych aktów to zawsze tekst pierwotny, a nie
tekst jednolity: NIE WIEM (1 przykład). Taki wzorzec pozwoliłby zmierzyć dokładność zamiast miary zastępczej,
także dla „§” i punktów (tak jak `eval/evaluate.py` dla 2024).

**Szacunek kosztu OCR dla 1918–1989**, bardzo niepewny, bo n = 8 na epokę:
(15 278 aktów × 4,38 strony) + (13 463 × 1,62) ≈ 89 000 stron.
- CPU: 89 000 stron × 3,35 s (mediana) ≈ 83 h czasu procesora na jeden proces; przy kwartylach 2,4–6,0 s na
  stronę 59–148 h.
- Transfer: 1918–1939: 14,4 MB na 35 stron, 1940–1989: 7,2 MB na 13 stron, czyli około 39 GB.
- Zapytania: co najmniej 2 na akt (metadane i PDF) co 1 s, około 16 h dla samych 1918–1989.

## 7. Ograniczenia pomiaru

- n = 8 aktów na epokę, do 3 stron na akt (61 stron porównanych). Przedziały dla 1918–1989 są szerokie,
  np. [+0,039; +0,311]. Lata 2007–2009 nie trafiły do próby.
- Miara zastępcza nie jest dokładnością:
  - słownik jest współczesny;
  - obce języki (DU/1938/268), nazwiska i skróty są liczone jako błąd;
  - tesseract ma własny słownik, który ciągnie odczyt w stronę istniejących wyrazów, więc miara może faworyzować
    OCR;
  - cyfry i interpunkcja nie są mierzone („1977 x.”, „Nr t6”); „§” liczę osobno.
- Łamy dzielę na środku bloku tekstu, więc wiersze na całą szerokość (nagłówek, tytuł) też są dzielone
  („MINIS” / „TRA”).
- Heurystyka nagłówków z innymi pozycjami daje dolną granicę. Część numerów w nagłówkach jest źle odczytana,
  ale sprawdzone nagłówki (DU/1921/311, 1930/246, 1934/457, 1955/272, 1964/207, 2001/1506, 2005/1369) zawierają
  kilka pozycji.
- Warstwę czytam `extract_text()` pdfplumbera, a nie potokiem eli2md. Zachowanie eli2md sprawdziłem na 3 aktach
  (rozdział 5).
- Czasy OCR zmierzone na maszynie obciążonej inną konwersją.

## Komendy

```sh
cd eli2md
python eval/du_pre2012_survey.py lists     # 94 listy roczne -> /tmp/du_pre2012/year_counts.json
python eval/du_pre2012_survey.py sample    # ziarno 20260930 -> /tmp/du_pre2012/sample.json
python eval/du_pre2012_survey.py measure   # 38 aktów: warstwa + tesseract pol
python eval/du_pre2012_survey.py ocr2      # te same strony: tesseract pol+eng
python eval/du_pre2012_survey.py probe     # 10 PDF-ów wokół zmian formatu
python eval/du_pre2012_survey.py summary   # -> eval/du_pre2012_survey_0.6.5.json
# eli2md 0.6.5 (rozdział 5), z katalogu /tmp:
/home/ai/venvs/eli2md-065/bin/python -m eli2md DU/1936/301 [--ocr] -o DU-1936-301.md
```

Kontrola powtarzalności: `measure` + `ocr2` + `summary` puszczone od nowa dla DU/1921/311 i DU/2002/251
w osobnym katalogu roboczym dały te same liczby co w JSON.
