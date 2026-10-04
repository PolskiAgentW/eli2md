"""Konwersja t.j. z listy tj_survey.py daną wersją eli2md (do porównania wersji konwertera na tych samych PDF).

    .venv/bin/python eval/tj_survey/tj_convert.py SRC AKTY.jsonl OUT_DIR [--jobs N]

SRC: katalog z pakietem eli2md (np. `git archive v0.6.24` rozpakowany albo bieżące drzewo).
AKTY.jsonl: akty.jsonl z tj_survey.py (pole `md` = ELI t.j.) albo inna lista {"md": "MP/2024/5"}. PDF i metadane
z cache eli2md (~/cache/eli).
Wynik: OUT_DIR/<DU|MP>/<rok>/<DU|MP>-<rok>-<poz>.md (już istniejące pomija), OUT_DIR/convert.jsonl (czas, błąd).
Potem: TJ_MD_ROOT=OUT_DIR tj_survey.py OUT2 --acts AKTY.jsonl
"""
import json, pathlib, sys, time
from concurrent.futures import ProcessPoolExecutor


def init(src):
    sys.path.insert(0, src)


def one(args):
    eli, out = args
    from eli2md.eli import fetch
    from eli2md.pdf import convert, to_markdown
    pub, y, p = eli.split("/")
    f = pathlib.Path(out) / pub / y / f"{pub}-{y}-{p}.md"
    if f.exists():
        return dict(md=eli, skipped=True)
    t = time.time()
    try:
        meta, pdf = fetch(eli)
        md = to_markdown(convert(str(pdf), position=meta.get("pos")), meta)
    except Exception as e:
        return dict(md=eli, error=repr(e)[:300])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(md, encoding="utf-8")
    return dict(md=eli, s=round(time.time() - t, 1))


def main():
    src, akty, out = sys.argv[1:4]
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 6
    elis = [json.loads(l)["md"] for l in open(akty)]
    pathlib.Path(out).mkdir(parents=True, exist_ok=True)
    t = time.time()
    with ProcessPoolExecutor(jobs, initializer=init, initargs=(src,)) as ex, \
            open(pathlib.Path(out) / "convert.jsonl", "a") as log:
        for i, r in enumerate(ex.map(one, [(e, out) for e in elis])):
            log.write(json.dumps(r, ensure_ascii=False) + "\n"); log.flush()
            if i % 50 == 0 or "error" in r:
                print(i, r, flush=True)
    print(f"done {len(elis)} in {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
