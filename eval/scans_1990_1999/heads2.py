"""Klasy kandydatów z heads.py: A = przed pierwszym nagłówkiem rodzaju aktu są akapity treści (końcówka poprzedniego
aktu), B = nagłówek rodzaju aktu po linii podpisu (*...*) (początek następnego aktu)."""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from heads import pat
root = Path(sys.argv[1])
A, B, other = [], [], []
for f in sorted(root.glob("DU/*/*.md")):
    body = f.read_text(encoding="utf-8").split("\n---\n", 1)[-1].splitlines()
    heads = [i for i, l in enumerate(body) if pat.match(l.strip()) and l.strip().upper() == l.strip()]
    if len(heads) < 2:
        continue
    pre = [l for l in body[:heads[0]] if l.strip() and not l.startswith(("# ", "> "))]
    a = len(pre) >= 2
    b = any(any(l.strip().startswith("*") and l.strip().endswith("*") for l in body[max(0, h - 4):h] if l.strip())
            for h in heads[1:])
    (A if a else B if b else other).append(f.stem) if not (a and b) else A.append(f.stem + "+B")
print("A", len(A), " ".join(A)); print("B", len(B), " ".join(B)); print("inne", len(other), " ".join(other))
