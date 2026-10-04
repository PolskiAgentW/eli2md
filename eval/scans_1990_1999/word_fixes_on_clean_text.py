import csv, random, sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, sys.argv[1])
from eli2md.ocr import fix_words, SPELL_WORD, language
root=Path('/home/ai/data/dziennik-ustaw-2000-2011-md')
rows=[r for r in csv.DictReader(open(root/'index.csv',encoding='utf-8')) if r['status']=='ok' and not int(r['ocr_pages'] or 0) and not int(r['no_text_pages'] or 0)]
random.Random(5).shuffle(rows)
words=0; lost=Counter(); by_type=Counter()
for r in rows[:300]:
    t=(root/'DU'/r['year']/f"DU-{r['year']}-{r['pos']}.md").read_text(encoding='utf-8').split('\n---\n',1)[-1]
    for para in t.split('\n\n'):
        a=Counter(SPELL_WORD.findall(para)); words+=sum(a.values())
        d=a-Counter(SPELL_WORD.findall(fix_words(para)))
        lost.update(d); by_type[r['type']]+=sum(d.values())
print('words',words,'changed words',sum(lost.values()), f"{sum(lost.values())/words:.5f}")
print('by act type', by_type.most_common(5))
print(lost.most_common(30))
