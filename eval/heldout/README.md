# Próby held-out (2026-10-05): 0.6.7 a 0.6.25 na tekście (słowa)

Po co: dane DU/MP 2012+ na GitHubie i HF były do 2026-10-04 w większości z eli2md 0.6.7 (DU 3199 z 3287 aktów,
MP 12 667 z 18 165). Przed przeliczeniem wersją 0.6.25 sprawdzenie, czy nowsza wersja nie psuje tekstu na aktach,
na których konwerter nie był strojony.

Próby (`eval/heldout_sample.py`, losowanie bez aktów z żadnej wcześniejszej próby `eval/sample_*.json`,
plik próby zacommitowany przed oceną): `sample_2024_n70_s5114_heldout.json` (70 aktów DU 2024 z PDF i HTML),
`sample_2012-2023_n60_s5115_heldout.json` (60 aktów DU 2012–2023). Ocena: `eval/evaluate.py --ocr` z tego
repo (ta sama miara dla obu wersji; dla 0.6.7 bez argumentu `position`, którego ta wersja nie ma).

| próba | wersja | body R | body P | P na pełnych wzorcach | przypisy R | załączniki R |
|---|---|---:|---:|---:|---:|---:|
| 2024 s5114 (n=70) | 0.6.7 | 0,9990 | 0,9518 | 0,9987 | 0,9683 | 0,9974 |
| 2024 s5114 (n=70) | 0.6.25 | 0,9990 | 0,9518 | 0,9987 | 0,9683 | 0,9974 |
| 2012–2023 s5115 (n=60) | 0.6.7 | 0,9969 | 0,6920 | 0,6920 | 0,9516 | 0,8260 |
| 2012–2023 s5115 (n=60) | 0.6.25 | 0,9969 | 0,6920 | 0,6920 | 0,9515 | 0,8260 |

Wynik: na słowach obie wersje są takie same (akt po akcie; jedyna różnica: DU/2014/121 hyp 66 012 → 66 010
słów). Zmiany 0.6.8–0.6.25 dotyczą struktury Markdown (teksty jednolite, przypisy, nagłówki), stron z OCR i lat
2000–2011, czego ta miara nie widzi. Niskie P na s5115 to jeden akt (DU/2014/121, tekst jednolity: 66 010 słów wobec 7 780 w części głównej HTML,
w obu wersjach; przyczyny nie sprawdzałem).
Pliki: `s5114_v0.6.7.txt` itd. (wyjście evaluate.py).
