# PDF path for legalize-pipeline (Poland): same act, HTML path vs PDF path

Measurement behind the legalize-pipeline branch
[`PolskiAgentW:pl-pdf-fallback`](https://github.com/PolskiAgentW/legalize-pipeline/tree/pl-pdf-fallback):
acts of the Dziennik Ustaw without HTML (every act since 2025) go through their PDF, converted by eli2md 0.6.17
(vendored there as `src/legalize/fetcher/pl/pdf/`) and mapped to legalize's blocks (`parser_pdf.py`).

## What is compared

2024 acts have both an official HTML and the PDF. For each act of a sample, both go through legalize:
the HTML through the existing `EliTextParser` HTML path, the PDF through the new path (marker + PDF, as
`EliClient.get_text` returns it for acts without HTML). Both are rendered by legalize's `render_norm_at_date`.
The measure (`compare.py`) runs on the Markdown body below the front matter and the `# title` line:

- **text**: word tokens (`\w+`, case-folded, punctuation ignored), aligned with difflib.
  R = matched / HTML tokens, P = matched / PDF tokens. `P_noref`: P with publication references
  "(Dz. U. … poz. …)" removed from the PDF side first; the Sejm HTML leaves them out, the PDF has them.
- **lines** (structure): each non-empty line reduced to its shape (heading level + first words; otherwise
  indentation + list marker `N.`, `N)`, `x)`, `–`), aligned the same way. Lines of quoted text (`> `) are
  left out: the HTML gives a whole quoted provision as one line (up to 100 000 characters in DU/2024/303),
  the PDF path keeps its paragraphs.
- Main text (up to the first `## Załącz…` heading) and annexes are scored separately.
- Acts whose HTML contains `[patrz oryginał]` (part of the text only as a link to the PDF) are counted apart:
  their HTML is not a complete reference.

## Samples

- `dev_2024_n40_s20260930.json`: 40 acts drawn from the 749 2024 acts that earlier eli2md samples used. Used to
  build the mapping (5 runs).
- `test_2024_n100_s20261001.json`: 100 acts drawn from the other 1235 2024 acts (seed 20261001), drawn and
  committed before the first measurement. Measured **once**, on legalize-pipeline commit `fc9aac1`.

## Results (test sample, 2026-09-30)

| acts | part | text R | text P | text P_noref | lines R | lines P |
|---|---|---:|---:|---:|---:|---:|
| 80 with complete HTML | main text | 0.9983 | 0.9525 | 0.9872 | 0.9655 | 0.9477 |
| 80 with complete HTML | annexes (37 acts have annex text in HTML) | 0.9959 | 0.8887 | 0.8997 | 0.9765 | 0.8355 |
| 20 with `[patrz oryginał]` in HTML | main text | 0.8780 | 0.9426 | 0.9759 | 0.8679 | 0.9583 |

Micro-averages over tokens / lines. Per act: `results_test_2024_n100_s20261001_fc9aac1.{json,txt}`. Main text of the
80 acts: median R 1.0, none below 0.95, 2 below 0.99. Dev sample, same code: main text R 0.9965, P_noref 0.9923
(`results_dev_…`).

Where the two paths differ (read in the diffs of the dev sample, `compare.py ELI --show`):

- tables: the PDF path gives them as paragraphs, row by row; the HTML path as pipe tables (most of the lower
  annex P and R, e.g. DU/2024/1493);
- tirets: the HTML uses two conventions (`unit_tire` → `      – ` and `<ul>` → `- ` two spaces deeper, with nested
  tirets on one line); the PDF path always the first (most of the lower lines R, e.g. DU/2024/165);
- quotation marks „…” around quoted provisions and "(Dz. U. …)" references are kept from the PDF;
- footnotes and signatures are dropped in both.

## Reproduce

In a Python 3.12 venv with legalize-pipeline (branch above, `pip install -e .[dev]`) and eli2md installed:

    python fetch.py test_2024_n100_s20261001.json      # text.html, text.pdf, meta.json into ~/cache/eli
    python compare.py $(python -c "import json; print(' '.join(json.load(open('test_2024_n100_s20261001.json'))))")
    python check_vendored.py ~/cache/eli/DU/2025/*/text.pdf   # vendored copy == eli2md (100 of 100 PDFs checked)

`vendor.py` makes the vendored copy from this repository (OCR and front matter left out, legalize's ruff rules).
`du_text_coverage_2026-09-30.json`: per year, DU acts in the API / with HTML / PDF only / neither.
