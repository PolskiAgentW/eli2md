# Consolidated texts of ustawy 2025–2026 in dziennik-ustaw-md vs the PDF text layer (2026-10-16)

`TJ_DATA=<clone of dziennik-ustaw-md> python eval/tj_pdf_layer.py tj_2025_2026.txt eval/tj_pdf_layer_2025_2026.jsonl`
(per act: `eval/tj_pdf_layer_2025_2026.jsonl`).

Acts: all 491 notices of a consolidated text of an ustawa (type Obwieszczenie, „jednolitego tekstu ustawy” in the
title, status ok) of 2025 (267) and 2026 (224) in `index.csv` of dziennik-ustaw-md at 9b37756be (2026-10-16 05:01Z),
as published there (converted by eli2md 0.6.53: 420, 0.6.56: 57, 0.6.57: 11, 0.6.25.2: 3). PDFs: the ELI API,
sha256 491/491 equal to `pdf_sha256` in `index.csv`. Reference: `pdftotext` (poppler) of the same PDF.
Measures and their limits: docstring of `eval/tj_pdf_layer.py`. Every act flagged (C or P < 0.98, or other article
numbers) was checked by hand against the PDF: 31 acts.

| | Acts |
|---|---:|
| other article numbers in the PDF than in `annexes[0]` (script; `missing` or `extra` not empty) | 7 |
| of them by hand: an „Art. N.” of the PDF that is not an `art` node in `annexes[0]` | 1 (DU/2025/960) |
| text missing from the JSON | 0 |
| word coverage C, median | 0.995 |
| C < 0.98 (all: layer artifacts, below) | 23 |
| the act has its own annexes, in `annexes[1]` … | 84 |

- DU/2025/960: „Art. 480–524. (pominięte)” is in the text of the heading „Rozdział 1 Zmiany w przepisach” (a heading
  set tight to its title and to the article; in the whole of dziennik-ustaw-md 7 acts). Fixed in 0.6.58 (`_segment`);
  the published file changes when the act is converted again.
- Low C or other article numbers, all from the PDF text layer, not from the conversion: the masthead and the spaced
  title („O B W IE S Z CZ E N I E”, heavy in short acts), letter-spaced words („b u d o wn ict wo”; the JSON has
  „budownictwo”), footnote markers glued to words („inwalidzkiej1”), superscripts on a line of their own („Art. 101 .”
  + „[1]”), „Art. 41a–Art. 41i.”, the note of eli2md for a drawing (DU/2025/816, 299).
- Tables and formulas are weaker: lines of neighbouring cells are interleaved, so a word is cut by the next cell
  („jednocześ- 129 zł za każdą strefę geograficzną nie o ponowne …”, fee tables in the annexes of DU/2025/1431;
  „administracyjno- 8.2. … -biurowe” in DU/2025/163, 278, DU/2026/554, 592; a formula legend in DU/2026/68). Acts with
  such cut words: 10 (DU/2025/1431, 901, 163, 278, 1154, DU/2026/1, 554, 592, 563, 68), all but DU/2026/68 in the
  annexes of the ustawa.
- Not seen by these measures: a word replaced by another of the same act, order inside a paragraph.
