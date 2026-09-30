# Articles of consolidated texts: PDF conversion vs official HTML (eli2md 0.6.17, 2026-10-01)

`python eval/tj_articles.py --out eval/tj_articles_0.6.17.json`

Acts: the 12 consolidated texts (teksty jednolite) that legal-cite (apiotrowski-afk/legal-cite-pl) uses on
2026-10-01, i.e. for each of its acts the newest consolidated text that has HTML. Reference: top-level articles of
the consolidated text in the ELI HTML. Compared: words (case-folded, punctuation ignored), footnotes left out.

| Act | Consolidated text | Articles | Same words |
|---|---|---:|---:|
| KC | DU/2024/1061 | 1296 | 1294 |
| KP | DU/2023/1465 | 512 | 508 |
| KSH | DU/2024/18 | 941 | 937 |
| KPC | DU/2024/1568 | 2010 | 2003 |
| KK | DU/2024/17 | 456 | 453 |
| PrAut | DU/2022/2509 | 175 | 175 |
| u.r.p. | DU/2024/499 | 150 | 149 |
| u.ś.u.d.e. | DU/2024/1513 | 31 | 29 |
| u.z.n.k. | DU/2022/1233 | 44 | 44 |
| u.p.k. | DU/2024/1796 | 74 | 74 |
| UODO | DU/2019/1781 | 131 | 130 |
| u.k.k. | DU/2024/1497 | 109 | 107 |
| **Total** | | **5929** | **5903 (99.6%)** |

The other 26, checked one by one:

- **Conversion errors, 6.** In each, the words of the article are all there, but text that is not part of it
  follows:
  - a heading glued to the paragraph "(uchylony)" of the article before it: KC art. 109⁹ ("(uchylony) TYTUŁ V
    Termin"), KC art. 449¹¹, KPC art. 1102;
  - the footnote to the title of the consolidated text (the list of EU directives) after the last article, as body
    text: KPC art. 1217, KK art. 363, UODO art. 176.
- **Errors in the HTML, 5.** Missing spaces ("wsprawie", KK art. 37b; "rejonowymiejsca", KPC art. 447;
  "wrazie", u.r.p. art. 65¹); KPC art. 15 marked as "Art. 1522." (id arti_1522); u.ś.u.d.e. art. 15 inside
  the unit of art. 14.
- **The measurement, 15.** Headings of chapters and parts that the script does not recognise (with a footnote
  marker, "Oddział", "CZĘŚĆ WOJSKOWA", "Art. 266–280 (uchylone)") and so counts as part of the article before them
  (12). Superscript indexes split into different tokens on the two sides (3).

The Markdown in PolskiAgentW/dziennik-ustaw-md for the newest consolidated texts of 8 of these acts (DU/2026/795,
2026/1245, 2026/468, 2025/383, 2025/24, 2026/85, 2026/1244, 2025/1362) was converted with eli2md 0.6.7. Their
articles have the same words as with 0.6.17 (all 4702).
