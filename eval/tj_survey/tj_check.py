"""Check an eli2md Markdown of a consolidated text (tekst jednolity), article by article.

    python tj_check.py NEW.md --pdf NEW.pdf [--html OLD.html --legal-cite DIR | --md-other OTHER.md]
                       [--json OUT.json] [--show N]

NEW.md     eli2md Markdown of the act (e.g. DU-2026-1245.md, from your own run or from dziennik-ustaw-md).
--pdf      the PDF the Markdown was made from; its text layer (`pdftotext`, poppler) is the independent reading.
--html     reference: an earlier consolidated text of the same act in HTML (ELI `text.html`). Article units come
           from `legal_cite.core._jednostki_html` (legal-cite-pl, works with a855ad1 and 06c82da); --legal-cite is
           the checkout to import it from. An article no amendment touched in between must have the same text.
--md-other reference: another eli2md Markdown of the same act (e.g. your run vs the dataset file). Both come from
           the same converter, so this shows differences between converter versions, not errors they share.

Without a reference, every article is checked against the PDF. With one, articles identical to the reference
are "same as reference" and only the others are checked against the PDF. Comparison after removing all whitespace
and footnote markers, with superscripts as digits; an article printed in two versions (brzmienia) matches if any
version on one side equals any version on the other.

Classes of the PDF check:
  pdf_exact     same as the PDF text of the article
  pdf_layout    same after dropping from the PDF side what it has in excess: page headers, footnote texts
                (taken from the Markdown's footnotes), structure headings after the article; `N)` dropped on both
                sides (a footnote number and a point number look the same in pdftotext)
  review        other differences; printed with context (--show N per article, default 4)
  no_heading    no `Art. N.` heading for the article in the PDF text layer
Only what the PDF has in excess is dropped, so text missing from the Markdown still shows up as a difference.
Limits: an error the PDF text layer shares is not seen; a formula or table flattened differently by the two
extractors ends up in "review".

Measured on dziennik-ustaw-md KPC (Dz.U. 2026 poz. 468), KC (2026/795), KP (2026/1245), 3 793 articles, 2026-10-04:
  --html (t.j. 2024/1568, 2024/1061, 2023/1465): 3 635 same as reference, 145 checked against the PDF,
    3 to review = the 3 defects found by hand (KPC 1096, KP 265, KP 305), nothing else.
  no reference: 8 to review or without a heading = those 3 + 5 pdftotext artefacts (superscripts moved to another
    line: KPC 388¹, 598¹⁵, 693¹¹, 913, KP 237⁶; all 5 identical to the HTML text).

Requires: Python 3.10+, pdftotext. No network access.
"""
import argparse, difflib, json, pathlib, re, subprocess, sys
from collections import Counter

SUP = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ₀₁₂₃₄₅₆₇₈₉",
                    "1234567890abcdefghijklmnoprstuvwxyz0123456789")
SUP_DIGITS = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")
SUP_LETTERS = str.maketrans("ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ", "abcdefghijklmnoprstuvwxyz")

# eli2md: article heading as `##### Art. N.`, higher structure as `#`–`####`; some headings stay plain lines.
# Title case only with a number ("Tytuł wykonawczy…" is the text of art. 803 k.p.c.).
MD_HEAD = re.compile(r"^##### Art\. (\S+?)\.\s*$", re.M)
MD_STRUCT = re.compile(r"^(?:(?:KSIĘGA|CZĘŚĆ|TYTUŁ|DZIAŁ|ROZDZIAŁ|ODDZIAŁ)\b"
                       r"|(?:Księga|Część|Tytuł|Dział|Rozdział|Oddział) [IVXLC\d¹²³⁴⁵⁶⁷⁸⁹⁰]+[A-Za-zᵃᵇᶜᵈᵉᶠᵍ]*(?:\s|$)).*$",
                       re.M)
PDF_STRUCT = re.compile(r"^(?:(?:DZIAŁ|TYTUŁ|KSIĘGA|CZĘŚĆ|ROZDZIAŁ|ODDZIAŁ)\b|(?:Rozdział|Oddział|Dział|Tytuł|Księga|Część)"
                        r"\s+[IVXLC\d\[\]]+[a-z]*\s*$)", re.M)
# page header in pdftotext: separate lines "Dziennik Ustaw", "– 39 –", "Poz. 1245" (or one line); removed from the
# lines BEFORE normalisation: without spaces "Poz. 1245" + "9a)" is "Poz.12459a)" and cannot be split
PDF_PAGE = re.compile(r"^[ \t\f]*(?:Dziennik Ustaw(?:[ \t]*[–-][ \t]*\d+[ \t]*[–-][ \t]*Poz\.[ \t]*\d+)?|[–-][ \t]*\d+[ \t]*[–-]"
                      r"|Poz\.[ \t]*\d+)[ \t]*$", re.M)
LABEL = re.compile(r"(?<!\d)\d{1,3}\)|\)")  # "39)" (footnote or point number) and ")" — removed on BOTH sides


def norm(s):
    s = re.sub(r"\[\^\w+\]", "", s)              # Markdown footnote markers
    s = re.sub(r"\[(\d+[a-z]*)\]", r"\1", s)     # pdftotext superscript: 986[5]
    s = s.replace("\xad", "")
    s = re.sub(r"[‐‑‒–—−]", "-", s)
    s = re.sub(r"[„”“\"]", '"', s)
    return re.sub(r"\s+", "", s.translate(SUP))


def key(num):
    """Article number as legal-cite writes it: 'Art. 479⁴⁵' → '479_45', '18³ᵈ' → '18_3_d', '3b' → '3b'."""
    n = num.translate(SUP_LETTERS)
    n = re.sub(r"([¹²³⁴⁵⁶⁷⁸⁹⁰]+)([a-z]*)",
               lambda m: "_" + m.group(1).translate(SUP_DIGITS) + ("_" + m.group(2) if m.group(2) else ""), n)
    return n.lower()


def pdf_num(k):  # '986_5' → '986[5]', '18_3_a' → '18[3a]'
    p = k.split("_")
    return p[0] + (f"[{''.join(p[1:])}]" if len(p) > 1 else "")


def md_articles(text):
    """{key: [body, …]} in document order (two versions of an article → two bodies)."""
    text = re.split(r"^\[\^\w+\]:", text, maxsplit=1, flags=re.M)[0]  # footnote definitions at the end
    heads = list(MD_HEAD.finditer(text))
    out = {}
    for i, m in enumerate(heads):
        body = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        body = re.split(r"^#{1,4} ", body, maxsplit=1, flags=re.M)[0]
        body = MD_STRUCT.split(body, maxsplit=1)[0]
        out.setdefault(key(m.group(1)), []).append(body)
    return out


def md_footnotes(text):
    """Normalised footnote texts of the Markdown; the PDF prints them inside the text at the bottom of the page.
    A footnote may span paragraphs and pages, so each paragraph separately."""
    out = []
    for m in re.finditer(r"^\[\^\w+\]:(.*?)(?=^\[\^\w+\]:|\Z)", text, re.M | re.S):
        out += [norm(p) for p in re.split(r"\n\s*\n", m.group(1))]
    return sorted({LABEL.sub("", f) for f in out if len(f) > 15}, key=len, reverse=True)


def html_articles(path, legal_cite):
    if legal_cite:
        sys.path.insert(0, str(legal_cite))
    from legal_cite import core
    out = {}
    for unit in core._jednostki_html("tj_check:" + str(path), pathlib.Path(path).read_text(errors="replace")):
        num, txt = unit[0], unit[1]  # a855ad1: (num, text); 06c82da: (num, text, date)
        out.setdefault(num, []).append(re.sub(r"^\s*Art\.\s*[0-9a-z ]+?\s*\.\s*", "", txt, count=1))
    return out


def pdf_heads(k, T, keys):
    """Headings of article k in T. pdftotext writes a superscript as "986[5]"; when the superscript is on its own
    line it gives "Art. 237 ." and some PDFs print it inline ("Art. 61." = art. 6¹, unless art. 61 exists)."""
    pats = [rf"^Art\. {re.escape(pdf_num(k))}\."]
    if "_" in k:
        pats.append(rf"^Art\. {re.escape(k.split('_')[0])} \.")
        if k.replace("_", "") not in keys:
            pats.append(rf"^Art\. {re.escape(k.replace('_', ''))}\.")
    for p in pats:
        heads = list(re.finditer(p, T, re.M))
        if heads:
            return heads
    return []


def pdf_check(bodies, k, T, footnotes, keys):
    """(class, ops, md, pdf) for the best-matching heading of article k in the pdftotext text T."""
    corpus = "\x00".join(footnotes)
    heads = pdf_heads(k, T, keys)
    if not heads:
        return "no_heading", [], "", ""
    best = None
    for h in heads:
        nxt = re.compile(r"^Art\. \d", re.M).search(T, h.end())
        frag = T[h.end():nxt.start() if nxt else len(T)]
        st = PDF_STRUCT.search(frag)
        if st:
            frag = frag[:st.start()]
        P0 = norm(frag)
        P = LABEL.sub("", norm(PDF_PAGE.sub("", frag)))
        for f in footnotes:
            P = P.replace(f, "")
        for b in bodies:
            md0 = norm(b)
            md = LABEL.sub("", md0)
            ops = [o for o in difflib.SequenceMatcher(None, md, P, autojunk=False).get_opcodes() if o[0] != "equal"]
            # PDF excess that is part of a footnote text (split between pages differently than the paragraphs)
            ops = [o for o in ops if not (o[0] == "insert" and o[4] - o[3] >= 12 and P[o[3]:o[4]] in corpus)]
            score = (md0 != P0, len(ops))
            if best is None or score < best[0]:
                best = (score, ops, md, P)
    (inexact, _), ops, md, P = best
    return ("pdf_exact" if not inexact else "pdf_layout" if not ops else "review"), ops, md, P


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("md")
    ap.add_argument("--pdf", required=True)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--html")
    g.add_argument("--md-other")
    ap.add_argument("--legal-cite", help="legal-cite-pl checkout (if legal_cite is not importable)")
    ap.add_argument("--json", help="write per-article results here")
    ap.add_argument("--show", type=int, default=4, help="differences shown per article to review")
    a = ap.parse_args()

    md_text = pathlib.Path(a.md).read_text()
    new = md_articles(md_text)
    if a.html:
        ref = html_articles(a.html, a.legal_cite)
    elif a.md_other:
        ref = md_articles(pathlib.Path(a.md_other).read_text())
    else:
        ref = None
    T = subprocess.run(["pdftotext", a.pdf, "-"], capture_output=True, text=True, check=True).stdout
    footnotes = md_footnotes(md_text)

    res = {}
    for k, bodies in new.items():
        if ref is not None:
            if k not in ref:
                res[k] = {"class": "only_new"}
                continue
            if {norm(b) for b in bodies} & {norm(b) for b in ref[k]}:
                res[k] = {"class": "same_as_reference"}
                continue
        c, ops, md, P = pdf_check(bodies, k, T, footnotes, new)
        r = {"class": c, "versions": len(bodies)}
        if c == "review":
            r["diff"] = [[op, md[max(0, i1 - 25):i2 + 10], P[max(0, j1 - 25):j2 + 10]] for op, i1, i2, j1, j2 in ops]
        res[k] = r
    only_ref = [k for k in (ref or {}) if k not in new]

    counts = Counter(r["class"] for r in res.values())
    print(f"articles in {a.md}: {len(new)}" + (f"; in reference: {len(ref)}, only there: {len(only_ref)}" if ref else ""))
    for c in ("same_as_reference", "pdf_exact", "pdf_layout", "review", "no_heading", "only_new"):
        if counts[c]:
            print(f"  {c:18} {counts[c]}")
    for k, r in res.items():
        if r["class"] == "review":
            print(f"art. {k}: {len(r['diff'])} difference(s) to review")
            for op, m, p in r["diff"][:a.show]:
                print(f"    {op:7} MD: {m!r}\n            PDF: {p!r}")
        elif r["class"] == "no_heading":
            print(f"art. {k}: no heading 'Art. {pdf_num(k)}.' in the PDF text layer")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(
            {"md": a.md, "pdf": a.pdf, "reference": a.html or a.md_other, "counts": dict(counts),
             "only_reference": only_ref, "articles": res}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
