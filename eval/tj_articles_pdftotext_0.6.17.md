# Articles of consolidated texts: `pdftotext -layout` vs eli2md (2026-10-01)

`python eval/tj_articles_pdftotext.py --out eval/tj_articles_pdftotext_0.6.17.json` (pdftotext 26.01.0, eli2md 0.6.17)

A common way to read one article from the PDF of a consolidated text is
`pdftotext -layout text.pdf - | grep -n "Art. 503\."`. This is the same measurement as
[tj_articles_0.6.17.md](tj_articles_0.6.17.md) (the same 12 consolidated texts, reference = top-level articles in the
ELI HTML, words compared case-folded without punctuation), with the text from `pdftotext -layout` instead of eli2md.

Baseline article: from a line that starts with `Art. N.` (after "Załącznik do obwieszczenia") to the next such line or
a heading line (DZIAŁ, Rozdział, ...). Two variants:

- **raw**: the pdftotext output as is;
- **clean**: page headers ("Dziennik Ustaw –12– Poz. 1061") and lines with only a footnote marker removed, words
  hyphenated at the end of a line joined. Footnote texts stay: in the PDF text nothing marks them as footnotes.

"Flat" compares again after joining adjacent number tokens on both sides ("22 1" = "221"), i.e. it does not count
the lost superscripts.

| | Same words | Same words, flat |
|---|---:|---:|
| pdftotext raw | 1868 / 5929 (31.5%) | 2456 (41.4%) |
| pdftotext clean | 3536 / 5929 (59.6%) | 5184 (87.4%) |
| eli2md 0.6.17 | 5903 / 5929 (99.6%) | 5903 (99.6%) |

Per act (same words, clean / eli2md): KC 1034 / 1294 of 1296, KP 206 / 508 of 512, KSH 529 / 937 of 941,
KPC 988 / 2003 of 2010, KK 285 / 453 of 456, PrAut 104 / 175 of 175, u.r.p. 75 / 149 of 150, u.ś.u.d.e. 15 / 29 of 31,
u.z.n.k. 38 / 44 of 44, u.p.k. 66 / 74 of 74, UODO 106 / 130 of 131, u.k.k. 90 / 107 of 109.

What goes wrong with pdftotext (checked on KC, KP, KK, u.ś.u.d.e.):

- **Superscripts become plain digits.** In these PDFs "Art. 22¹" is printed by pdftotext as "Art. 221.", and
  "§ 1¹" as "§ 11" (KP DU/2023/1465: art. 22 § 1¹ at line 652 of the output; art. 22¹ᶜ has a real § 11), also in
  references ("art. 221c § 6–9"). In KC DU/2024/1061, `grep "Art. 221\."` finds two lines: line 161 is
  art. 22¹ (the definition of a consumer), line 1159 is art. 221. "Art. 4491." is art. 449¹ (there is no
  art. 4491). In the 12 texts, 194 articles have a number that, flattened, is also the number of another article
  (KC 68, KPC 54, KP 42, KSH 28, PrAut 2). The measurement matches such articles in order of occurrence, so the
  table does not count this; a reader of grep output has to tell them apart.
- **Footnotes inside the article.** The text of a footnote ("W brzmieniu ustalonym przez art. 1 pkt 2 ustawy …")
  is printed at the bottom of the page, i.e. inside whichever article is there. The footnote marker is printed as a
  digit next to the text: "Art. 22¹ᶜ.⁴⁾ § 1." in KP comes out as "Art. 221c.4) § 1.".
- **Page headers** ("Dziennik Ustaw –12– Poz. 1061") inside every article that crosses a page (raw only).

Newer PDFs can differ. The newest consolidated texts of 8 of these acts are only in PDF (no HTML, so not measured
here). In three of them pdftotext prints superscripts in brackets ("Art. 22[1]."), so the numbers do not collide:
KC DU/2026/795, KP DU/2026/1245, KPC DU/2026/468. In PrAut DU/2025/24 they are flattened: 92 articles with a
superscript ("Art. 35¹" as "Art. 351."), of them 6 collide with another article (6¹, 6², 6³ and 61, 62, 63):
`grep "Art. 61\."` finds line 240 (art. 6¹) before line 1432 (art. 61).
KK DU/2025/383, DU/2026/85, DU/2026/1244 and DU/2025/1362 have no articles with superscripts. Footnote texts are
inside the articles in all of them.

Limits: the baseline segmentation is mine (a simple one, as a grep user would read it); a better cleanup of
pdftotext output is possible. The heading limits of the measurement described in tj_articles_0.6.17.md apply to both
sides.
