"""Akty DU 1990-1999 z >= 2 nagłówkami rodzaju aktu (linia wersalikami zaczynająca się od rodzaju aktu samodzielnego)
w treści: kandydaci na usterkę „akt z początkiem następnego aktu”. Miara zgrubna (tekst jednolity w obwieszczeniu
albo umowa w załączniku też dają 2 nagłówki)."""
import re, sys
from collections import Counter
from pathlib import Path
KINDS = ("ROZPORZĄDZENIE", "USTAWA", "OBWIESZCZENIE", "UCHWAŁA", "ZARZĄDZENIE", "POSTANOWIENIE", "DEKRET",
         "OŚWIADCZENIE RZĄDOWE", "ORZECZENIE", "KOMUNIKAT", "WYROK")
pat = re.compile(r"^(?:#+ )?(?:%s)\b(?! Z DNIA \d+ \w+ \d{4} R\. O ZMIANIE)" % "|".join(KINDS))
if __name__ == "__main__":
    root = Path(sys.argv[1])
    per, ex = Counter(), {}
    tot = Counter()
    for f in sorted(root.glob("DU/*/*.md")):
        y = f.parent.name
        body = f.read_text(encoding="utf-8").split("\n---\n", 1)[-1]
        n = sum(1 for l in body.splitlines() if pat.match(l.strip()) and l.strip().upper() == l.strip())
        tot[y] += 1
        if n >= 2:
            per[y] += 1; ex.setdefault(y, []).append(f.stem)
    for y in sorted(tot):
        print(y, per[y], tot[y], " ".join(ex.get(y, [])[:6]))
    print("razem", sum(per.values()), sum(tot.values()))
