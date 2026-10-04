"""Porównanie artykuł po artykule: mój Markdown najnowszego t.j. (z PDF) vs HTML
starszego t.j., którego używa legal-cite-pl (core._jednostki_html).

Artykuły niezmienione między t.j. powinny mieć identyczny tekst, więc odsetek
zgodnych to dolna granica poprawności konwersji; różnice = nowelizacje albo
błędy konwersji (do oceny ręcznej na próbce).

    /tmp/lc-venv/bin/python tools/legalcite/tj_compare.py [--dump DIR]
"""
import asyncio, json, pathlib, re, sys

LC = pathlib.Path.home() / "ext/legal-cite-pl"
sys.path.insert(0, str(LC))
from legal_cite import core  # noqa: E402

MD = pathlib.Path.home() / "data/dziennik-ustaw-md/DU/2026"
AKTY = {"KPC": "DU-2026-468.md", "KC": "DU-2026-795.md", "KP": "DU-2026-1245.md"}
SUPL = str.maketrans("ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ", "abcdefghijklmnoprstuvwxyz")
# nagłówki struktury jako zwykła linia; tytułowa pisownia tylko z numerem („Tytuł wykonawczy…” to treść art. 803 k.p.c.)
STRUKT = re.compile(r"^(?:(?:KSIĘGA|CZĘŚĆ|TYTUŁ|DZIAŁ|ROZDZIAŁ|ODDZIAŁ)\b"
                    r"|(?:Księga|Część|Tytuł|Dział|Rozdział|Oddział) [IVXLC\d¹²³⁴⁵⁶⁷⁸⁹⁰]+[A-Za-zᵃᵇᶜᵈᵉᶠᵍ]*(?:\s|$)).*$", re.M)
HEAD = re.compile(r"^##### Art\. (\S+?(?:\s*[–-]\s*Art\.\s*\S+?)?)\.\s*$", re.M)  # też „Art. 41a–Art. 41i.”


def kanon(num):
    n = num.translate(SUPL)
    n = re.sub(r"([¹²³⁴⁵⁶⁷⁸⁹⁰]+)([a-z]*)", lambda m: "_" + m.group(1).translate(core._SUP)
               + ("_" + m.group(2) if m.group(2) else ""), n)
    return n.lower()


def norm(s):
    s = re.sub(r"\[\^\w+\]", " ", s)            # znaczniki przypisów w MD ([^12], [^1_2], [^a])
    s = s.replace("\xad", "")
    s = re.sub(r"[‐‑‒–—−]", "-", s)
    s = re.sub(r"[„”“\"]", '"', s)
    s = s.translate(core._SUP).translate(SUPL)
    s = re.sub(r"\s+", "", s)                  # bez białych znaków: „1 1 .” ≡ „1¹.”, „x ,” ≡ „x,”
    return s


def md_artykuly(path):
    t = path.read_text()
    t = re.split(r"^\[\^\w+\]:", t, maxsplit=1, flags=re.M)[0]  # definicje przypisów na końcu
    ms = list(HEAD.finditer(t))
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(t)
        body = t[m.end():end]
        body = re.split(r"^#{1,4} ", body, maxsplit=1, flags=re.M)[0]  # nagłówki działów itd.
        body = re.split(STRUKT, body, maxsplit=1)[0]  # TYTUŁ/DZIAŁ/Rozdział jako zwykła linia
        out.append((kanon(m.group(1)), m.group(1), body))
    return out


def html_body(num, txt):
    # tekst jednostki zaczyna się od „Art. N." — zdejmujemy nagłówek
    return re.sub(r"^\s*Art\.\s*[0-9a-z ]+?\s*\.\s*", "", txt, count=1)


def klucz_sort(k):
    m = re.fullmatch(r"(\d+)([a-z]*)(?:_(\d+)([a-z]*))?", k)
    if not m:
        return None
    return (int(m.group(1)), m.group(2), int(m.group(3) or 0), m.group(4) or "")


async def main():
    dump = pathlib.Path(sys.argv[sys.argv.index("--dump") + 1]) if "--dump" in sys.argv else None
    wynik = {}
    for kod, plik in AKTY.items():
        info = core.PL_ACTS[kod]
        await core._fetch_pl(info)
        key = core._klucz_pl(info)
        zr = core._zrodlo.get(key)
        html = {}
        for unit in core._jednostki_html(key, core._html_cache[key]):  # 06c82da: (num, text, date)
            html.setdefault(unit[0], unit[1])   # pierwsze brzmienie = obowiązujące
        md = md_artykuly(MD / plik)
        md_d = {}
        dup = []
        for k, raw, b in md:
            if k in md_d:
                dup.append(raw)
            md_d.setdefault(k, b)
        # kolejność numeracji w MD
        klucze = [klucz_sort(k) for k, _, _ in md]
        zle = sum(1 for k in klucze if k is None)
        nierosnace = [md[i][1] for i in range(1, len(md))
                      if klucze[i] and klucze[i - 1] and klucze[i] <= klucze[i - 1]]
        wspolne = [k for k in md_d if k in html]
        zgodne, rozne = [], []
        for k in wspolne:
            a, b = norm(md_d[k]), norm(html_body(k, html[k]))
            (zgodne if a == b else rozne).append(k)
        r = dict(tj_html=zr[0] if zr else None, tj_html_data=zr[1] if zr else None,
                 nowelizacji_po=zr[2] if zr else None,
                 md_art=len(md), md_unikalne=len(md_d), md_duplikaty=dup[:20], md_zly_numer=zle,
                 md_nierosnace=nierosnace[:20], html_art=len(html), wspolne=len(wspolne),
                 tylko_md=[k for k in md_d if k not in html][:400],
                 tylko_html=[k for k in html if k not in md_d][:400],
                 zgodne=len(zgodne), rozne=len(rozne))
        wynik[kod] = r
        print(kod, json.dumps({k: (v if not isinstance(v, list) else (len(v), v[:12])) for k, v in r.items()},
                              ensure_ascii=False))
        if dump:
            dump.mkdir(parents=True, exist_ok=True)
            with open(dump / f"{kod}_rozne.jsonl", "w") as f:
                for k in rozne:
                    f.write(json.dumps(dict(art=k, md=norm(md_d[k]), html=norm(html_body(k, html[k]))),
                                       ensure_ascii=False) + "\n")
            (dump / f"{kod}_wynik.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
