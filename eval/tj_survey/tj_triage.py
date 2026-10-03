"""Podział artykułów „do oceny” z tj_survey.py na klasy po wzorcu różnicy (dokładne fragmenty, nie kontekst).

    /tmp/lc-venv/bin/python tools/legalcite/tj_triage.py tools/legalcite/survey_v2

Klasy (pierwsza pasująca):
  przypis_w_tresci   MD ma w artykule treść przypisu z etykietą nie-liczbową („I) Niniejsza ustawa wdraża…”),
                     albo PDF ma ją w nadmiarze, bo w MD trafiła do innego artykułu
  zakres_artykulow   MD ma doklejoną linię „Art. 22–28. (pominięte|uchylone)” (brak nagłówka zakresu)
  art_z_l            artykuł z literą „ł” (art. 106ł) bez własnego nagłówka, doklejony do poprzedniego
  naglowek_w_tresci  nagłówek struktury (CZĘŚĆ KOŃCOWA, TYTUŁ VI …) albo dopisek „* Ostatnia pozycja” w treści artykułu
  indeks_z_litera    PDF ma po literze indeks z literą/kropką („T1b”, „T4.1b”), którego w MD brak
  wzor               różnica w zapisie wzoru (znaki matematyczne, „wzoru:”)
  uklad              wszystkie różnice ≤ 3 znaki (etykiety „a)”, dzielenie wyrazów, numery odnośników)
  brak_naglowka      w PDF nie ma nagłówka artykułu
  inne               do obejrzenia ręcznie
Wynik: OUT/triage.jsonl + liczby na stdout.
"""
import collections, json, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tj_compare import md_artykuly  # noqa: E402
from tj_pdfcheck2 import ocen, przypisy_md, norm, ODN  # noqa: E402

ROOT = pathlib.Path.home() / "data/dziennik-ustaw-md"
CACHE = pathlib.Path.home() / "cache/eli"
SC = pathlib.Path.home() / "cache/tjsurvey"
MATH = re.compile(r"[\U0001D400-\U0001D7FF∑∗⋅≤≥×√∆]")


def klasa(kat, ops, md, P):
    if kat == "brak_naglowka":
        return "brak_naglowka"
    seg = [(op, md[i1:i2], P[j1:j2]) for op, i1, i2, j1, j2 in ops]
    tekst = " ".join(a + " " + b for _, a, b in seg)
    if re.search(r"Niniejszaustawa|Niniejszeobwieszczenie|Zmian[ay]tekstujednolitego|Zmian[ay]wymienion|"
                 r"I+dyrektyw", tekst):
        return "przypis_w_tresci"
    if any(re.search(r"Art\.\d+[a-z]*-(Art\.)?\d+[a-z]*\.(\((pominięte|uchylone))?$", a) for _, a, _ in seg):
        return "zakres_artykulow"
    if any(re.match(r"Art\.\d+ł\.", a) for _, a, _ in seg):
        return "art_z_l"
    if any(op == "delete" and re.match(r"(CZĘŚĆ|TYTUŁ|KSIĘGA|DZIAŁ|Rozdział)[A-ZĄĆĘŁŃÓŚŹŻIVXL\d]|\*Ostatniapozycja", a)
           for op, a, _ in seg):
        return "naglowek_w_tresci"
    if any(op in ("insert", "replace") and re.fullmatch(r"[\d.]*\d[a-z]+|\d+\.\d+[a-z]*", b.strip(",")) for op, a, b in seg):
        return "indeks_z_litera"
    if MATH.search(tekst) or "wzoru" in tekst:
        return "wzor"
    if all(max(len(a), len(b)) <= 3 for _, a, b in seg):
        return "uklad"
    return "inne"


def main():
    out = pathlib.Path(sys.argv[1])
    rows = [json.loads(l) for l in open(out / "do_oceny.jsonl")]
    by_act = collections.defaultdict(list)
    for r in rows:
        by_act[r["md"]].append(r["art"])
    wynik, cnt, akty = [], collections.Counter(), collections.defaultdict(set)
    for eli, arts in sorted(by_act.items()):
        y, p = eli.split("/")[1:]
        md_path = ROOT / "DU" / y / f"DU-{y}-{p}.md"
        md_d = {}
        for k, _, b in md_artykuly(md_path):
            md_d.setdefault(k, b)
        pdf = CACHE / "DU" / y / p / "text.pdf"
        if not pdf.exists():
            pdf = SC / "DU" / y / p / "text.pdf"
        T = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
        prz = przypisy_md(md_path.read_text())
        for a in arts:
            kat, ops, P = ocen(md_d[a], a, T, prz)
            md = ODN.sub("", norm(md_d[a]))
            k = klasa(kat, ops, md, P)
            cnt[k] += 1
            akty[k].add(eli)
            wynik.append(dict(md=eli, art=a, klasa=k, ops=[(op, md[i1:i2][:120], P[j1:j2][:120])
                                                          for op, i1, i2, j1, j2 in ops[:4]]))
    with open(out / "triage.jsonl", "w") as f:
        for w in wynik:
            f.write(json.dumps(w, ensure_ascii=False) + "\n")
    print(json.dumps({k: {"artykuly": v, "akty": len(akty[k])} for k, v in cnt.most_common()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
