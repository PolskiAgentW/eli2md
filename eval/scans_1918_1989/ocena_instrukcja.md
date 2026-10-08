# Instrukcja oceny (pomiar 2, próbka 1009) — dla podagentów; ta sama dla każdej grupy

You evaluate OCR text of acts of the Polish Journal of Laws (Dziennik Ustaw) 1918–1989 against the printed page.
For each act directory given to you (under /home/ai/data/du1918_probka2/<DU-YYYY-POS>/):
- `strona-1.png`: image of page 1 of the act's PDF (200 dpi). The page may hold several acts (positions); the act
  evaluated is the one with position POS (the number printed above its title, e.g. "259." or "126").
- `tekst_100_numerowany.txt`: the first 100 tokens (split on spaces) of the converter's text, numbered.
- `tekst_md.md`: the full converter output (front matter, then text; "> [...]" lines are notes, not text).

Do, for each act:
1. Read the image (Read tool on the PNG; zoom by cropping with Python/PIL into /tmp if needed, never write elsewhere).
2. Compare the 100 tokens with the print, in order. An error = a token different from the print: a different
   letter/digit, garbage not in the print, two words glued or one word split, a word from another place of the page
   inserted; a word of the print skipped = 1 error. NOT an error: punctuation-only differences, a hyphenated
   line-break split ("gospo- darstwie") as in print, old spelling as in print, page number / running header that is
   in the print. Count errors against what is actually printed at that place (even if the tokens are another act's text).
3. accuracy = 1 − errors / tokens (min 0); tokens = number of tokens in the file (100, or fewer for short acts).
4. this_act: do the tokens start with THIS act (its title/heading; the number itself may be missing — not an error)?
5. other_act_text: does the text from page 1 (whole page-1 part of tekst_md.md, not only 100 tokens) contain text
   of ANOTHER act (e.g. the end of the previous position, the issue's table of contents, the next act)?
6. columns_ok: is the reading order of page 1 right (whole page-1 part of tekst_md.md vs image): columns not
   interleaved, title lines not moved, lines not shuffled? Minor single-word displacement → note it, judge honestly.

Output: one JSON line per act appended to the results file given to you, fields:
{"eli", "tokens", "errors", "accuracy", "error_list": [[got, print], ...], "this_act": bool, "other_act_text": bool,
 "other_act_note", "columns_ok": bool, "columns_note", "uncertain": "what you were unsure about"}
Do not change any other file. Do not look at other groups' results.
