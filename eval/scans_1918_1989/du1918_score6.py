#!/usr/bin/env python3
"""Pomiar 6 (journal/du1918_jakosc.md): wynik z journal/du1918/wyniki6_A-H.jsonl wg progu z GOAL.md
„Refleksja 09.10 00:0x”: mediana >= 95%, >= 58/64 aktów >= 90%, <= 8/64 aktów z usterką
(this_act=false albo other_act_text=true albo columns_ok=false). Akt oceniony 2 razy: bierze ostatnią linię."""
import json, statistics, sys
from pathlib import Path
J = Path(__file__).resolve().parent
rows = {}
for g in 'ABCDEFGH':
    f = J / f'wyniki6_{g}.jsonl'
    if not f.exists():
        continue
    for line in f.read_text().splitlines():
        if line.strip():
            r = json.loads(line); r['group'] = g; rows[r['eli'].replace('-', '/')] = r
n = len(rows)
acc = [float(r['accuracy']) for r in rows.values()]
ge90 = sum(a >= 0.90 for a in acc)
bad = {e: r for e, r in rows.items() if not r['this_act'] or r['other_act_text'] or not r['columns_ok']}
print(f'ocenionych: {n}/64')
if n:
    print(f'mediana: {statistics.median(acc):.3f}  (próg >= 0.95)')
    print(f'>= 90%: {ge90}/{n}  (próg >= 58/64)')
    print(f'usterki: {len(bad)}/{n}  (próg <= 8/64): inny akt {sum(1 for r in bad.values() if r["other_act_text"])}, '
          f'łamy {sum(1 for r in bad.values() if not r["columns_ok"])}, nie ten początek {sum(1 for r in bad.values() if not r["this_act"])}')
    for e, r in sorted(bad.items()):
        print(f'  {e} ({r["group"]}): this={r["this_act"]} other={r["other_act_text"]} cols={r["columns_ok"]} acc={r["accuracy"]}')
    low = sorted((a, e) for e, r in rows.items() if (a := float(r['accuracy'])) < 0.90)
    print('< 90%:', ', '.join(f'{e} {a:.2f}' for a, e in low))
