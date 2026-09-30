# OCR obrazu tekstu na stronie z warstwą tekstową (0.6.4.dev)

Data: 2026-09-30. Kod: `pdf._image_text`, `pdf._largest_image_box`, `ocr.text_image`, `ocr.ocr_page(..., bbox=)`.
Wersja w kodzie nadal 0.6.3 (bez podbicia).

## Problem

S. 1 umów międzynarodowych ma warstwę tekstową tylko z winietą i tytułem, a preambuła i pierwsze artykuły są
obrazem (skanem) na tej samej stronie. Strona ma tekst, więc `--ocr` jej nie czytał. Dostawała tylko notkę
„[Na stronie 1 PDF jest obraz …]”, a w wyniku brakowało preambuły i art. 1 (np. MP/2026/869 s. 1).

## Co zmienia kod

Tylko z `--ocr` (`convert(path, ocr=...)`). Dla strony z warstwą tekstową i dużym obrazem
(ten sam warunek co dotąd, `_large_image`):

1. Bierze największy obraz strony (ramka przycięta do strony).
2. Jeśli nad obrazem leży więcej niż 30 znaków warstwy tekstowej (`IMAGE_TEXT_CHARS`), obraz jest tłem
   (formularz z polami w warstwie tekstowej, np. DU/2026/872 s. 39), więc nie ma OCR i zostaje notka.
3. W przeciwnym razie robi OCR tylko tego obszaru (render 300 dpi, tryb `auto` jak dla stron bez tekstu;
   w wycinku nie szuka nagłówka Dziennika, `band=0`).
4. Tekst przyjmuje tylko wtedy, gdy wygląda na skan tekstu ciągłego (`ocr.text_image`). Muszą być spełnione
   wszystkie warunki:
   - `usable()` (≥ 20 słów, mediana pewności ≥ 80) i mediana pewności ≥ 95,
   - co najmniej 5 linii,
   - rozpoznany język wg słów funkcyjnych (`language()` ≠ „?”, czyli ≥ 5 słów funkcyjnych i ≥ 10% tokenów),
   - ≥ 75% tokenów to słowa (litery z samogłoską albo jednoliterowe a, i, o, u, w, z),
   - ≥ 50% linii ma ≥ 45 znaków **i** ≥ 50% linii zajmuje ≥ 60% szerokości obrazu,
   - symboli `| = % « » < > @ # …` najwyżej 0,05 na słowo (linie tabel, wykresy, kratki formularzy),
   - żaden akapit nie zaczyna się od podpisu rysunku lub tabeli („Tabela”, „Wykres”, „Rys.”, „Mapa”,
     „Schemat”, „Legenda”, „Źródło”).
5. Przyjęty tekst zastępuje notkę o obrazie w tym samym miejscu strony. Stoi pod notką
   `> [Na stronie N PDF jest obraz tekstu (skan). Tekst poniżej odczytał z obrazu OCR (tesseract 5.5.0, pol+eng). Może zawierać błędy i pomija grafikę. Wiążący jest PDF.]`,
   a każdy akapit jest cytatem blokowym `> …`, jak inne teksty OCR. W JSON są to węzły `ocr`.

Front matter: strona zostaje w `pages_with_images` (bo PDF ma tam obraz). Nowe pole `pages_images_ocr`
podaje strony, których obraz przeczytał OCR. `pages_ocr` bez zmian, dalej tylko strony bez warstwy
tekstowej. Pole `ocr` (silnik) jest też wtedy, gdy są tylko strony z `pages_images_ocr`.
Nie użyłem `pages_ocr`, bo `eval/selfcheck.py` pomija takie strony po stronie PDF. Strona z obrazem tekstu ma
jednak zwykłą warstwę tekstową (tytuł), którą trzeba porównywać.
`index.csv`: nowa kolumna `image_ocr_pages` (liczba; pusta bez `--ocr`). `dataset --ocr` konwertuje ponownie
akty z `image_pages > 0` i pustym `image_ocr_pages`, czyli też wszystkie akty z obrazami przekonwertowane
przed tą zmianą.

Bez OCR kod nie woła niczego nowego. Wynik jest bajtowo taki sam (pkt 4).

## 1. Wszystkie strony z obrazem w opublikowanych danych 2025–2026

Źródło: `pages_with_images` z front matter opublikowanych plików 0.6.3 (DU i MP, lata 2025–2026). Mamy
824 strony w 227 aktach (DU 631, MP 193). Dla każdej zapisałem odczyt OCR i decyzję reguły.
Decyzję liczy funkcja z pakietu (`ocr.text_image`) na zapisanych odczytach. Decyzje, cechy i czasy każdej
strony są w `image_text_ocr_0.6.4.dev.json`.

| | DU | MP | razem |
|---|---:|---:|---:|
| przyjęte (tekst OCR zamiast notki) | 23 | 11 | **34** |
| odrzucone: warstwa tekstowa nad obrazem (bez OCR) | 80 | 22 | 102 |
| odrzucone: `usable()` = nie (< 20 słów lub pewność < 80) | 377 | 90 | 467 |
| odrzucone: reguła `text_image` | 151 | 70 | 221 |
| razem | 631 | 193 | 824 |

34 przyjęte strony pochodzą z 29 aktów. Wszystkie to umowy międzynarodowe: 25 to s. 1, a 9 to dalsze strony
umów z obrazem tekstu angielskiego lub francuskiego obok warstwy tekstowej (np. DU/2026/286 s. 50 czytana
`fra+eng`, DU/2025/1604 s. 78). Razem 5334 słowa OCR.

**Czas OCR** (render + tesseract + ewentualne drugie odczyty `auto`, 1 wątek tesseracta na proces, 4 procesy
na współdzielonym CPU pod obciążeniem innych zadań): 722 strony z OCR (102 odpadły wcześniej bez OCR),
suma 2069 s, średnio 2,87 s, mediana 1,65 s, 90. percentyl 6,5 s, maksimum 68 s (DU/2025/717 s. 2)
i 58 s (DU/2025/113 s. 9). Na zegarze: 552 s dla 4 procesów. Z `--ocr` każda strona z dużym obrazem
kosztuje teraz jeden odczyt OCR więcej. W całym zbiorze 2025–2026 to ok. 35 min czasu jednego wątku.

Uwaga: progi reguły dobrałem na tych samych 824 stronach. Pomiary z pkt 1–3 nie są więc niezależnym testem.
Na innych latach (MP 2012–2024) reguła nie była sprawdzana.

## 2. Precyzja: obejrzane wycinki

Wycinki największego obrazu wyrenderowałem do PNG (70 dpi, `page.crop(box).to_image`) i obejrzałem.
Przyjętych jest tylko 34, więc obejrzałem **wszystkie 34** zamiast próby 30. Odrzucone: losowa próba 20 z 790
(`random.Random(2026).sample`, po wcześniejszym wylosowaniu 30 z przyjętych tym samym generatorem).

| | skan tekstu: tak | skan tekstu: nie |
|---|---:|---:|
| przyjęte (34, wszystkie) | **34** | **0** |
| odrzucone (próba 20) | 1 | 19 |

- Przyjęte: 34/34 to skany tekstu. Na 5 z nich oprócz tekstu są podpisy lub wpisy odręczne. OCR daje z nich
  śmieci w tekście, np. DU/2025/1604 s. 78 „this <Q. day of spó pa 2022”, DU/2026/286 s. 50
  „à VAR4Oy (E, ce 7 6” jour de an vier 202 à”, MP/2025/442 s. 1 „„... 3 =”. Pozostałe z tej piątki to
  DU/2026/204 s. 40 i MP/2025/348 s. 1 (odręczne nazwiska w tekście).
- Odrzucone, skan tekstu (pominięty): DU/2026/818 s. 1 (tytuł i preambuła umowy w krótkich, wyśrodkowanych
  liniach).
- Odrzucone, nie tekst: znaki drogowe (DU/2025/100 s. 135), mapy (DU/2025/1075 s. 2, MP/2026/343 s. 19),
  rysunek techniczny (DU/2025/1323 s. 18), wzory legitymacji i dokumentów (DU/2025/1326 s. 6, DU/2025/687 s. 2),
  logo i emblematy (DU/2025/1758 s. 2, DU/2025/1768 s. 3), rysunki przedmiotów, mundurów i pojazdów
  (DU/2025/26 s. 7, DU/2026/131 s. 8, DU/2026/501 s. 18), wzór oznakowania (DU/2025/295 s. 4),
  tablica drogowa (DU/2026/132 s. 13), formularze (DU/2026/537 s. 8; DU/2026/872 s. 39 z warstwą tekstową nad
  obrazem), ilustracje (MP/2025/1276 s. 43 i 70), prawie pusty wycinek z logo (MP/2025/1072 s. 28).
  Przypadek graniczny: DU/2026/922 s. 5, wzór dokumentu na tle gilosza z kilkoma akapitami drobnego tekstu.
  Liczę go jako „nie” (to wzór dokumentu).

Wycinki i arkusze: `/tmp/imgocr/acc`, `/tmp/imgocr/rej`, `/tmp/imgocr/sheet_*.png`. Nie są w repo.

## 3. Recall na umowach-kandydatach

Kandydaci to akty 2025–2026 z s. 1 w `pages_with_images` i niepustym `pages_ocr`. Jest ich 43, same umowy
międzynarodowe: DU 29, MP 14. Audyt (`visual_audit_2025_2026_v0.6.2.md`, pkt 8) podawał 30 DU + 14 MP.
W indeksie 2025–2026 znajduję 29 DU. Rozbieżności nie wyjaśniałem.

| | kandydaci | s. 1 przyjęta |
|---|---:|---:|
| DU | 29 | 14 |
| MP | 14 | 11 |
| razem | 43 | **25** |

Obejrzałem też wszystkie 18 pominiętych obrazów s. 1. 16 z nich to obrazy tekstu:
- tytuł i preambuła w krótkich, wyśrodkowanych liniach: DU/2025/1538, DU/2025/360, DU/2025/457, DU/2026/204,
  DU/2026/286, DU/2026/684, DU/2026/818, DU/2026/1015, DU/2026/995, MP/2025/773, MP/2025/865,
- lista państw-stron: DU/2025/29,
- krótka poprawka: DU/2025/600,
- spis treści z kropkami: MP/2025/259 (pewność 91,8),
- obraz wychodzi poza stronę, a nad nim jest warstwa tekstowa z klauzulą ratyfikacyjną: DU/2025/370,
  DU/2025/380 (odrzucone przed OCR).

Dwa pozostałe to okładki z dużym tytułem na zielonym tle (DU/2025/722, DU/2026/365: „Lista substancji i metod
zabronionych”).

Najczęstszy powód pominięcia to zbyt mało długich linii. Luźniejsze progi (≥ 30% linii ≥ 45 znaków,
≥ 40% linii ≥ 60% szerokości) dałyby na tych danych 6 stron więcej: 4 kandydatów (DU/2025/1538, 360, 457,
DU/2026/286), DU/2025/360 s. 4 (tekst angielski) i DU/2026/1027 s. 14. Tej ostatniej nie oglądałem, ale jej
tekst OCR („numer prawa wykonywania zawodu diagnosty laboratoryjnego …”) wygląda na wzór dokumentu.
Zostawiłem ostrzejsze progi.

**MP/2026/869 s. 1**, pełna konwersja `python -m eli2md MP/2026/869 --ocr` (62 s dla całego aktu, 13 stron,
w tym 8 stron bez tekstu). Początek odzyskanego tekstu:

```
> [Na stronie 1 PDF jest obraz tekstu (skan). Tekst poniżej odczytał z obrazu OCR (tesseract 5.5.0, pol+eng). …]
> Rząd Rzeczypospolitej Polskiej i Rząd Królestwa Arabii Saudyjskiej, zwane dalej „Stronami”,
> pragnąc zacieśnić przyjazne stosunki między obydwoma Państwami;
> biorąc pod uwagę interes Stron dotyczący zwolnienia z obowiązku posiadania wiz dla swoich obywateli
  legitymujących się paszportami dyplomatycznymi, służbowymi i specjalnymi, zgodnie z obowiązującymi przepisami
  prawa obydwu Państw;
> uzgodniły, co następuje:
> Artykuł 1 DEFINCJE
> Do celów niniejszej Umowy:
> 1) wyrażenia „obywatele jednej Strony”, „obywatele drugiej Strony”, „obywatele każdej ze Stron” …
```

W PDF (obejrzany wycinek, `/tmp/imgocr/acc/MP-2026-869_p1.png`) jest ten sam tekst, a nagłówek artykułu brzmi
„Artykuł 1 / DEFINICJE”. W tym fragmencie jedyny widoczny błąd OCR to „DEFINCJE”. Porównałem wzrokowo
ok. 300 znaków, nie cały tekst. Front matter: `pages_with_images: "1"`, `pages_images_ocr: "1"`,
`pages_ocr: "2-5, 10-13"`. Reszta pliku jest identyczna z opublikowanym 0.6.3 (`diff`: jedyna zmiana to
notka s. 1 zamieniona na notkę OCR i 8 akapitów).

## 4. Bez OCR wynik się nie zmienia

Porównałem Markdown bez OCR (`to_markdown(convert(pdf), meta)`) z nowego kodu i z kodu sprzed zmiany (HEAD
d30b9ef, eksport `git archive`):
- 227 aktów 2025–2026 z obrazami i 40 losowych innych aktów 2025–2026 (seed 64, do 60 stron): 267 z 267
  plików identycznych bajt w bajt;
- 100 aktów z próbek dev (`sample_2024_n50_s2024.json`, `sample_2024_n50_s7.json`, bez front matter, bo nie
  mają `meta.json`): 100 ze 100 identycznych;
- z tych 267 aktów 193 opublikowano bez `pages_ocr` (bez tekstu OCR). Ich nowy Markdown jest identyczny
  z opublikowanymi plikami 0.6.3. Pozostałych 74 nie porównywałem z opublikowanymi, bo te mają tekst OCR
  stron bez warstwy tekstowej.

Ewaluacje dev (bez OCR), nowy kod:
- `evaluate.py`: wynik identyczny z `results_dev_s2024_v0.6.3.dev_F.txt` i `results_dev_s7_v0.6.3.dev_F.txt`
  (wszystkie wiersze po usunięciu czasów). s2024: body micro R=0.9939 P=0.9830; s7: body micro R=0.9991
  P=0.9983.
- `structure.py` i `tree_eval.py`: wynik identyczny z tymi samymi skryptami uruchomionymi na kodzie sprzed
  zmiany (oba próbki, wszystkie wiersze). Od plików `*_v0.6.3.dev_F.txt` oba kody różnią się w 3–4 wierszach
  (DU/2024/440, 813, 840, załączniki). Pliki `_F` powstały na gałęzi wątku F przed scaleniem pozostałych
  wątków, więc różnica jest wcześniejsza niż ta zmiana. Nie badałem jej.
- Testy jednostkowe: 56, wszystkie przechodzą (`python -m unittest discover -s tests`).

## 5. selfcheck

Wybrałem wariant „z Markdown usuwam tylko tekst OCR tej strony”. Strona z obrazem tekstu **nie** jest pomijana:
jej warstwa tekstowa (winieta, tytuł) jest porównywana jak dotąd. `md_body` już wcześniej usuwał wszystkie
linie `> …` i notki `> [Na stronie …]`, więc zmieniły się tylko opisy w `eval/selfcheck.py`. `ocr_pages()`
czyta dalej tylko `pages_ocr`, a nie `pages_images_ocr`. Sprawdzenie na MP/2026/869: opublikowany 0.6.3 i nowy
wynik z `--ocr` dają to samo (`pdf_tokens=29, md_tokens=29, kept=1.000, grounded=1.000`, pominięte strony
2–5 i 10–13).

## Znane błędy i ograniczenia

- Recall na s. 1 umów to 25/43. Tytuły i preambuły w krótkich, wyśrodkowanych liniach, listy stron i spisy
  treści zostają z notką.
- OCR czyta tylko największy obraz strony. Inne obrazy tej strony nie są czytane i nie dostają osobnej notki
  (tak było już w 0.6.3). 311 z 824 stron ma więcej niż jeden obraz, ale nie sprawdzałem, ile z nich to duże
  obrazy tekstu.
- Podpisy i wpisy odręczne na przyjętych stronach dają śmieci w tekście OCR (5 z 34 stron).
- Progi są dobrane na tych samych danych, na których je mierzę. Na MP 2012–2024 (ok. 294 umowy) reguła nie była
  sprawdzana.
- Obraz wychodzący poza stronę z warstwą tekstową nad sobą (DU/2025/370, 380) jest odrzucany przed OCR.
