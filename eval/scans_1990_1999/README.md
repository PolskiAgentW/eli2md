# Skany Dz.U. 1990–1999: pomiar 0.6.25 a 0.6.26 (2026-10-05)

`eval/evaluate.py --ocr` na aktach 1990–1999, które w API ELI mają oficjalny HTML (wzorzec). Próby:
`sample_1990-1999_n40_s5401_dev.json` (dev, na niej strojone), `sample_1990-1999_n60_s5402_heldout.json` (obejrzana
po dwóch poprawkach wycinania aktu, więc nie jest już testem), `sample_1990-1999_n60_s5403_heldout.json` (test,
pobrana i zacommitowana przed oceną, niestrojona). Pliki:
- `dev_s5401_v0.6.25.txt`, `test_s5403_v0.6.25.txt`, `s5402_v0.6.25.txt`: 0.6.25 (warstwa tekstowa Acrobata);
- `dev_s5401_ocr_without_columns.txt`: OCR stron bez kolejności łamów;
- `dev_s5401_columns_without_word_fixes.txt`, `test_s5403_without_word_fixes.txt`, `s5402_before_last_fixes.txt`:
  etapy pośrednie;
- `dev_s5401_v0.6.26.txt`, `test_s5403_v0.6.26.txt`: wersja wydana (micro R/P, akty od najgorszego);
- `scans_2000_s5202_s5205.txt`: trzy skany z 2000 r., 0.6.25 i wersja przed poprawką słów.
Wyniki w README eli2md, wpis 0.6.26.
