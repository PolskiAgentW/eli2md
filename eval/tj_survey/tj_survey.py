"""Przegląd jakości zbioru dziennik-ustaw-md na tekstach jednolitych ustaw.

Dla każdej ustawy: najnowszy t.j. w zbiorze (MD z PDF) vs najnowszy wcześniejszy t.j. tej ustawy, który API ELI
ma w HTML (artykuły wg `_jednostki_html` z legal-cite-pl). Artykuły niezmienione między t.j. powinny mieć
identyczny tekst. Różniące się sprawdzane z warstwą tekstową PDF (pdftotext) tego samego t.j. (tj_pdfcheck2.ocen):
zgodne z PDF → różnica wobec HTML to zmiana stanu prawnego, nie błąd konwersji.

    /tmp/lc-venv/bin/python tools/legalcite/tj_survey.py OUT_DIR [--limit N] [--acts AKTY.jsonl]

--acts: lista ustaw (baza, md) z akty.jsonl wcześniejszego przebiegu zamiast wyboru z index.csv (ten sam zbiór).
TJ_MD_ROOT=DIR: Markdown brany z DIR/DU/<rok>/DU-<rok>-<poz>.md (np. z tj_convert.py) zamiast ze zbioru.

Wynik: OUT_DIR/akty.jsonl (wiersz na ustawę), OUT_DIR/do_oceny.jsonl (artykuły do oceny ręcznej), podsumowanie na stdout.
Pobrania (metadane, HTML) w ~/cache/tjsurvey/, 0,3 s przerwy między zapytaniami do API.
"""
import asyncio, csv, json, os, pathlib, re, subprocess, sys, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from tj_compare import core, md_artykuly, html_body, norm  # noqa: E402
from tj_pdfcheck2 import ocen, przypisy_md, ODN  # noqa: E402

ROOT = pathlib.Path.home() / "data/dziennik-ustaw-md"
CACHE = pathlib.Path.home() / "cache/eli"
SC = pathlib.Path.home() / "cache/tjsurvey"
MD_ROOT = pathlib.Path(os.environ.get("TJ_MD_ROOT", ROOT))
API = "https://api.sejm.gov.pl/eli/acts"


def fetch(url, path):
    if path.exists():
        return path.read_bytes()
    time.sleep(0.3)
    req = urllib.request.Request(url, headers={"User-Agent": "dziennik-ustaw-md quality check"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def meta(eli):
    p = CACHE / eli / "meta.json"
    if p.exists():
        return json.loads(p.read_text())
    return json.loads(fetch(f"{API}/{eli}", SC / eli / "meta.json"))


def wybierz():
    """Najnowszy t.j. ustawy w zbiorze dla każdej ustawy bazowej: {baza: (data, eli)}."""
    out = {}
    for r in csv.DictReader(open(ROOT / "index.csv")):
        if "jednolitego tekstu ustawy" not in r["title"] or r["status"] != "ok":
            continue
        m = meta(r["eli"])
        b = [e["id"] for e in (m.get("references") or {}).get("Tekst jednolity dla aktu", [])]
        if b and (b[0] not in out or r["announcement_date"] > out[b[0]][0]):
            out[b[0]] = (r["announcement_date"], r["eli"])
    return out


def html_tj(baza, przed):
    """Najnowszy t.j. ustawy `baza` z HTML, ogłoszony przed `przed`: (eli, data) albo None."""
    kand = []
    for e in (meta(baza).get("references") or {}).get("Inf. o tekście jednolitym", []):
        try:
            m = meta(e["id"])
        except Exception:
            continue
        if m.get("textHTML") and (m.get("announcementDate") or "") < przed:
            kand.append((m.get("announcementDate") or "", e["id"]))
    return max(kand) if kand else None


def jeden(baza, eli_md):
    rec = dict(baza=baza, md=eli_md)
    y, p = eli_md.split("/")[1:]
    md_path = MD_ROOT / "DU" / y / f"DU-{y}-{p}.md"
    md = md_artykuly(md_path)
    rec["md_art"] = len(md)
    data_md = meta(eli_md).get("announcementDate") or ""
    h = html_tj(baza, data_md)
    if not h:
        rec["html"] = None
        return rec, []
    rec["html"], rec["html_data"] = h[1], h[0]
    raw = fetch(f"{API}/{h[1]}/text.html", SC / h[1] / "text.html").decode("utf-8", "replace")
    key = "S:" + h[1]
    core._jedn_cache.clear()
    html = {}
    for unit in core._jednostki_html(key, raw):  # a855ad1: (num, text); 06c82da: (num, text, date)
        html.setdefault(unit[0], unit[1])
    md_d = {}
    for k, _, b in md:
        md_d.setdefault(k, b)
    wsp = [k for k in md_d if k in html]
    rozne = [k for k in wsp if norm(md_d[k]) != norm(html_body(k, html[k]))]
    rec.update(html_art=len(html), md_unik=len(md_d), wspolne=len(wsp), zgodne=len(wsp) - len(rozne),
               rozne=len(rozne), tylko_md=len(md_d) - len(wsp), tylko_html=len(html) - len(wsp))
    kat = dict(zgodne=0, tylko_przypisy=0, do_oceny=0, brak_naglowka=0)
    do_oceny = []
    if rozne:
        pdf = CACHE / "DU" / y / p / "text.pdf"
        if not pdf.exists():
            pdf = SC / "DU" / y / p / "text.pdf"
            fetch(f"{API}/DU/{y}/{p}/text.pdf", pdf)
        T = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
        prz = przypisy_md(md_path.read_text())
        for k in rozne:
            c, istotne, P = ocen(md_d[k], k, T, prz)
            kat[c] += 1
            if c in ("do_oceny", "brak_naglowka"):
                mdn = ODN.sub("", norm(md_d[k]))
                do_oceny.append(dict(md=eli_md, art=k, kat=c, ops=[
                    (op, mdn[max(0, i1 - 25):i2 + 10], P[max(0, j1 - 25):j2 + 10]) for op, i1, i2, j1, j2 in istotne[:4]]))
    rec["pdf"] = kat
    return rec, do_oceny


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    if "--acts" in sys.argv:
        wyb = [(r["baza"], (None, r["md"])) for r in map(json.loads, open(sys.argv[sys.argv.index("--acts") + 1]))]
    else:
        wyb = sorted(wybierz().items(), key=lambda kv: kv[1][1])
    print("ustaw z t.j. w zbiorze:", len(wyb), flush=True)
    done = set()
    akty_f = out / "akty.jsonl"
    if akty_f.exists():
        done = {json.loads(l)["md"] for l in open(akty_f)}
    with open(akty_f, "a") as fa, open(out / "do_oceny.jsonl", "a") as fo:
        for i, (baza, (_, eli_md)) in enumerate(wyb[:limit]):
            if eli_md in done:
                continue
            try:
                rec, dz = jeden(baza, eli_md)
            except Exception as e:
                rec, dz = dict(baza=baza, md=eli_md, error=repr(e)[:300]), []
            fa.write(json.dumps(rec, ensure_ascii=False) + "\n"); fa.flush()
            for d in dz:
                fo.write(json.dumps(d, ensure_ascii=False) + "\n")
            fo.flush()
            if i % 20 == 0:
                print(i, eli_md, {k: rec.get(k) for k in ("md_art", "html", "wspolne", "zgodne", "rozne", "pdf")},
                      flush=True)
    podsumuj(out)


def podsumuj(out):
    recs = [json.loads(l) for l in open(out / "akty.jsonl")]
    s = dict(ustaw=len(recs), bledy=sum(1 for r in recs if "error" in r),
             bez_html=sum(1 for r in recs if r.get("html") is None and "error" not in r),
             md_bez_artykulow=sum(1 for r in recs if r.get("md_art") == 0))
    por = [r for r in recs if r.get("wspolne")]
    for k in ("wspolne", "zgodne", "rozne", "tylko_md", "tylko_html"):
        s[k] = sum(r[k] for r in por)
    for k in ("zgodne", "tylko_przypisy", "do_oceny", "brak_naglowka"):
        s["pdf_" + k] = sum(r["pdf"][k] for r in por)
    s["porownane_ustawy"] = len(por)
    print(json.dumps(s, ensure_ascii=False))
    (out / "podsumowanie.json").write_text(json.dumps(s, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
