"""Copy eli2md's converter (pdf.py, tree.py) into legalize-pipeline as src/legalize/fetcher/pl/pdf/.

Changes, all without effect on the output for PDFs with a text layer (checked by check_vendored.py):
- OCR is left out (it needs tesseract, which legalize does not install): _image_text, _ocr_lines, the `ocr`
  argument of convert(); pages without a text layer get eli2md's note, as in eli2md without --ocr.
- frontmatter() and the `meta` argument of to_markdown() are left out (legalize renders its own front matter).
- ruff rules of legalize: variables named `l` renamed to `ln` (E741), zip(..., strict=False) (B905), ruff format.
Usage: python vendor.py ELI2MD_DIR LEGALIZE_DIR
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

HEADER = '''"""{what}

Vendored from eli2md {version} ({file}), https://github.com/PolskiAgentW/eli2md, MIT licence.
Changes: OCR left out (no tesseract here), no front matter, ruff rules of this repository
(``l`` -> ``ln``, ``zip(strict=False)``, ruff format). Otherwise the code is eli2md's; fixes belong there first.
"""
'''


def cut(s: str, start: str, end: str) -> str:
    i = s.index(start)
    j = s.index(end, i)
    return s[:i] + s[j:]


def replace(s: str, old: str, new: str) -> str:
    assert s.count(old) == 1, old[:60]
    return s.replace(old, new)


def rename_l(src: str) -> str:
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    lines = src.splitlines(keepends=True)
    for t in reversed(toks):  # right to left keeps earlier columns valid
        if t.type == tokenize.NAME and t.string == "l":
            (row, col), (_, ecol) = t.start, t.end
            ln = lines[row - 1]
            lines[row - 1] = ln[:col] + "ln" + ln[ecol:]
    out = "".join(lines)
    assert not re.search(r"\bln\b", src), "name ln already used"
    return out


def strict_zip(src: str) -> str:
    """zip(a, b) -> zip(a, b, strict=False): walk to the matching parenthesis."""
    out, i = [], 0
    for m in re.finditer(r"\bzip\(", src):
        if m.start() < i:
            continue
        depth, j = 0, m.end() - 1
        while True:
            c = src[j]
            depth += c == "("
            depth -= c == ")"
            if depth == 0:
                break
            j += 1
        out.append(src[i:j] + ", strict=False")
        i = j
    out.append(src[i:])
    return "".join(out)


def main() -> None:
    eli, leg = Path(sys.argv[1]), Path(sys.argv[2])
    version = re.search(r'version = "([^"]+)"', (eli / "pyproject.toml").read_text()).group(1)
    pdf = (eli / "eli2md" / "pdf.py").read_text()
    tree = (eli / "eli2md" / "tree.py").read_text()

    pdf = cut(pdf, "def _image_text(", "MAC_PL_FONT = ")
    pdf = cut(pdf, "def _ocr_lines(", "def convert(")
    pdf = replace(pdf, '''def convert(path: str, ocr: str | None = None, position: int | None = None,
            _doc_gutter: tuple[float, float] | None = None) -> Document:
    """ocr: "auto" or tesseract language(s), e.g. "pol+eng", to read pages without a text layer
    (see ocr.py); None (default) = no OCR, such pages only get a note.
''', '''def convert(path: str, position: int | None = None,
            _doc_gutter: tuple[float, float] | None = None) -> Document:
    """Pages without a text layer only get a note (this copy has no OCR).
''')
    pdf = replace(pdf, '''    if ocr:
        from . import ocr as ocr_mod
        doc.ocr_engine = f"tesseract {ocr_mod.check(ocr)}"
''', "")
    pdf = replace(pdf, '''                read = ocr_mod.ocr_page(page, ocr) if ocr else None
                if read and ocr_mod.usable(read):
                    doc.no_text_pages.append(pno)
                    doc.ocr_pages.append(pno)
                    doc.ocr_langs[pno] = read.lang
                    b = _ocr_lines(read.paragraphs, pno, page.width, page.height, position)
                elif layer and (layer[0] or layer[1]):''', '''                if layer and (layer[0] or layer[1]):''')
    pdf = replace(pdf, '''                if ocr and (read := _image_text(page, ocr)):  # an image of text: its OCR text replaces the note
                    doc.image_ocr_pages.append(pno)
                    doc.ocr_langs[pno] = read.lang
                    m = [Line(pno, img, img, 0.0, 1.0, t, page.width, page.height, mark="ocr") for t in read.paragraphs]
''', "")
    pdf = replace(pdf, "return convert(path, ocr, position, _doc_gutter=g)", "return convert(path, position, _doc_gutter=g)")
    pdf = cut(pdf, "def frontmatter(", "FN_LABEL = ")
    pdf = replace(pdf, "import json\n", "")
    pdf = replace(pdf, "def to_markdown(doc: Document, meta: dict | None = None) -> str:", "def to_markdown(doc: Document) -> str:")
    pdf = replace(pdf, '''    if meta:
        out += [frontmatter(meta, no_text_pages=doc.no_text_pages, image_pages=doc.image_pages,
                            ocr_pages=doc.ocr_pages, ocr_engine=doc.ocr_engine, unmapped_pages=doc.unmapped_pages,
                            image_ocr_pages=doc.image_ocr_pages),
                "# " + meta["title"]]
''', "")
    assert "ocr_mod" not in pdf and "__version__" not in pdf
    tree = replace(tree, "from .pdf import", "from .convert import")

    out = leg / "src" / "legalize" / "fetcher" / "pl" / "pdf"
    out.mkdir(parents=True, exist_ok=True)
    for name, src, what in (("convert.py", pdf, "PDF of an act of the Dziennik Ustaw -> paragraphs, footnotes, Markdown."),
                            ("tree.py", tree, "Tree of units (Art., §, ust., pkt, lit., tiret) from the converter's Markdown.")):
        doc = re.match(r'"""(.*?)"""\n', src, re.S)
        body = strict_zip(rename_l(src[doc.end():]))
        (out / name).write_text(HEADER.format(what=what, version=version, file=f"eli2md/{'pdf' if name == 'convert.py' else 'tree'}.py")
                                + f'\n# eli2md module docstring:\n' + "".join(f"# {x}".rstrip() + "\n" for x in doc.group(1).strip().splitlines())
                                + body)
    ruff = Path(sys.executable).parent / "ruff"
    subprocess.run([str(ruff), "format", str(out)], check=True, cwd=leg)
    subprocess.run([str(ruff), "check", str(out)], check=True, cwd=leg)


if __name__ == "__main__":
    main()
