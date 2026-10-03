"""Jak tj_pdfcheck.py, ale artykuł w PDF szukany po nagłówku „Art. N." (pdftotext
zapisuje indeks górny jako „986[5]"), do następnego nagłówka artykułu. Wstawki po
stronie PDF będące odnośnikami (numer „N)", treść przypisu, nagłówek strony)
liczone osobno jako „przypis/układ"; reszta wypisywana do oceny ręcznej.

    python3 tools/legalcite/tj_pdfcheck2.py /tmp/tjc /tmp/tjpdf
"""
import difflib, json, pathlib, re, sys

PLIKI = {"KPC": "468", "KC": "795", "KP": "1245"}
SUP = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ₀₁₂₃₄₅₆₇₈₉", "1234567890abcdefghijklmnoprstuvwxyz0123456789")
PRZYPIS = re.compile(r"(\d+\))+|.*(brzmieniu|Zezmian|Dodany|Dodana|Uchylony|Uchylona|Zmianytekstu|Utracił|Uznany|"
                     r"Obecnie|Napodstawie|Zmiana|DziennikUstaw|Poz\.\d+|Wtymbrzmieniu|ogłoszon).*")


def norm(s):
    s = re.sub(r"\[\^\w+\]", "", s)
    s = re.sub(r"\[(\d+[a-z]*)\]", r"\1", s)
    s = re.sub(r"[‐‑‒–—−]", "-", s)
    s = re.sub(r"[„”“\"]", '"', s).replace("\xad", "")
    return re.sub(r"\s+", "", s.translate(SUP))


def pdf_num(art):  # '986_5' → '986[5]', '18_3_a' → '18[3a]', '709_11' → '709[11]'
    p = art.split("_")
    return p[0] + (f"[{''.join(p[1:])}]" if len(p) > 1 else "")


NAGL_STRUKT = re.compile(r"^(?:(?:DZIAŁ|TYTUŁ|KSIĘGA|CZĘŚĆ|ROZDZIAŁ|ODDZIAŁ)\b|(?:Rozdział|Oddział|Dział|Tytuł|Księga|Część)"
                         r"\s+[IVXLC\d\[\]]+[a-z]*\s*$)", re.M)
# nagłówek strony w pdftotext: osobne linie „Dziennik Ustaw”, „– 39 –”, „Poz. 1245” (albo jedna); usuwany z linii PRZED
# normalizacją — po zdjęciu spacji „Poz. 1245” + „9a)” to „Poz.12459a)” i liczby nie da się rozdzielić
NAGL_STRONY = re.compile(r"^[ \t\f]*(?:Dziennik Ustaw(?:[ \t]*[–-][ \t]*\d+[ \t]*[–-][ \t]*Poz\.[ \t]*\d+)?|[–-][ \t]*\d+[ \t]*[–-]"
                         r"|Poz\.[ \t]*\d+)[ \t]*$", re.M)
ODN = re.compile(r"(?<!\d)\d{1,3}\)|\)")   # „39)” (odnośnik albo numer punktu) i „)” — usuwane po OBU stronach


def przypisy_md(md_text):
    """Znormalizowane treści przypisów z MD ([^N]: …) — PDF wstawia je w tekst na dole strony."""
    # przypis bywa wieloakapitowy (lista dyrektyw w [^1]) i PDF dzieli go między strony → każdy akapit osobno
    out = []
    for m in re.finditer(r"^\[\^\w+\]:(.*?)(?=^\[\^\w+\]:|\Z)", md_text, re.M | re.S):
        out += [norm(a) for a in re.split(r"\n\s*\n", m.group(1))]
    return sorted({ODN.sub("", f) for f in out if len(f) > 15}, key=len, reverse=True)


def ocen(md_raw, art, T, przypisy=()):
    """Artykuł MD vs tekst PDF (pdftotext) T: ('zgodne'|'tylko_przypisy'|'do_oceny'|'brak_naglowka', istotne, P).

    Po stronie PDF usuwane: treści przypisów (z MD), nagłówki stron, nagłówki struktury za artykułem.
    Po obu stronach: same numery „N)” (odnośnik i numer punktu nie do odróżnienia w pdftotext).
    Usuwane jest tylko to, co PDF ma W NADMIARZE, więc tekst zgubiony w MD nadal wychodzi jako różnica."""
    korpus = "\x00".join(przypisy)
    md0 = norm(md_raw)
    md = ODN.sub("", md0)
    hs = list(re.finditer(rf"^Art\. {re.escape(pdf_num(art))}\.", T, re.M))
    if not hs and "_" in art:  # część PDF ma indeks górny bez nawiasów: „Art. 61.” = art. 6¹ (najlepsze dopasowanie niżej)
        hs = list(re.finditer(rf"^Art\. {re.escape(art.replace('_', ''))}\.", T, re.M))
    if not hs:
        return "brak_naglowka", [], ""
    best = None
    for h in hs:  # dwa brzmienia → kilka nagłówków; najlepsze dopasowanie
        nxt = re.compile(r"^Art\. \d", re.M).search(T, h.end())
        frag = T[h.end():nxt.start() if nxt else len(T)]
        st = NAGL_STRUKT.search(frag)
        if st:
            frag = frag[:st.start()]
        P0 = norm(frag)
        P = ODN.sub("", norm(NAGL_STRONY.sub("", frag)))
        for f in przypisy:  # też po ODN.sub, więc postać jak w P
            P = P.replace(f, "")
        sm = difflib.SequenceMatcher(None, md, P, autojunk=False)
        ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
        # nadmiar w PDF, który jest fragmentem treści przypisu (przypis podzielony między strony inaczej niż akapity MD)
        ops = [o for o in ops if not (o[0] == "insert" and o[4] - o[3] >= 12 and P[o[3]:o[4]] in korpus)]
        if best is None or len(ops) < len(best[0]):
            best = (ops, P, md0 == P0)
    ops, P, dokladnie = best
    if dokladnie:
        return "zgodne", [], P
    if not ops:
        return "tylko_przypisy", [], P
    return "do_oceny", ops, P


def main():
    dump, pdfdir = map(pathlib.Path, sys.argv[1:3])
    tot = dict(art=0, zgodne=0, tylko_przypisy=0, do_oceny=0, brak_naglowka=0)
    for kod, n in PLIKI.items():
        T = (pdfdir / f"{n}.txt").read_text()
        prz = przypisy_md((pathlib.Path.home() / f"data/dziennik-ustaw-md/DU/2026/DU-2026-{n}.md").read_text())
        for line in open(dump / f"{kod}_rozne.jsonl"):
            r = json.loads(line)
            tot["art"] += 1
            kat, istotne, P = ocen(r["md"], r["art"], T, prz)
            tot[kat] += 1
            if kat == "brak_naglowka":
                print(f"{kod} {r['art']}: brak nagłówka „Art. {pdf_num(r['art'])}.” w PDF")
            elif kat == "do_oceny":
                md = ODN.sub("", norm(r["md"]))
                print(f"{kod} {r['art']}: {len(istotne)} różnic do oceny")
                for op, i1, i2, j1, j2 in istotne[:4]:
                    print(f"    {op} MD:{md[max(0,i1-25):i2+10]!r} | PDF:{P[max(0,j1-25):j2+10]!r}")
    print(json.dumps(tot))


if __name__ == "__main__":
    main()
