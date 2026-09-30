"""Score the JSON unit tree (eli2md.tree) against the unit tree in the official HTML (2024 acts).

Reference: every element with class `unit` and an id in the HTML. Its type and number come from
the id segments ("chpt_2-arti_41_1-pass_2-pint_3a-lett_b"); the path is the sequence of
segments of the types below (chapters, branches and untyped "none_" segments are dropped, the
JSON does not nest units in chapters). Units quoted in amendments or cited in announcements
(class `pro-rplc-text` / `pro-cite-text`, or inside such a unit) are not units of the act and are
left out. Main text = <h1> + first section, annexes = the other sections, except annexes the HTML
only links to as PDF (as in evaluate.py / structure.py). Footnotes are dropped.

Type mapping HTML -> JSON: arti -> art, para -> par (§), pass -> ust, pint -> pkt, lett -> lit,
tire -> tir, slet (lit. under lit.) -> slit (the JSON has no such type, so these are always missed).
Untyped HTML units (id "none_N", numbered paragraphs in annexes that are not legal text, e.g.
"1. Zasady ogólne") are typed by their printed label, as the JSON does: "N." -> ust, "N)" -> pkt.
Other untyped units ("1.1.", "I.", "A.", "Tabela 1") are left out and dropped from paths: the JSON
has no type for them (their text stays in the text of the enclosing node). Their count is printed.
Number normalisation: lower case; superscripts "41¹" in the JSON are written "41_1" as in the HTML
ids. Tirets have no number in the text; the JSON numbers them by order, the HTML does the same
where it marks them (in the dev samples it never does).

Hypothesis: the JSON is linearised in document order (unit label "Art. 5." / "§ 5." / "5." / "5)" /
"a)" followed by the unit's text, then its children; text/heading/signature nodes by their text;
notes about missing content and footnotes are dropped). Both token streams are tokenized as in
evaluate.py and aligned with difflib (autojunk off). A unit starts at its first token (for § and
tiret, whose sign is not a word token, that is the number / the first word).

  recall     share of reference units whose first token is aligned to the first token of a
             JSON unit node with the SAME path;
  precision  share of JSON unit nodes (not text/heading/...) whose first token is aligned to the
             first token of a reference unit with the same path.
Units whose first token is not aligned at all are counted apart ("unaligned") and not in the rates:
that is a word error, which evaluate.py measures. Misses are split into "none" (nothing starts
there on the other side) and "path" (a unit starts there, but with another path, e.g. a wrong
number or a wrong parent). Scored per type and separately for main text and annexes.

Usage: python eval/tree_eval.py SAMPLE_JSON [--md-cache DIR] [--show POS] [--out FILE]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eli2md.pdf import SUP_CHARS, convert, to_markdown  # noqa: E402
from eli2md.tree import RANK, md_to_tree  # noqa: E402
from evaluate import CACHE, tokens  # noqa: E402

HTML_TYPE = {"arti": "art", "para": "par", "pass": "ust", "pint": "pkt", "lett": "lit", "tire": "tir", "slet": "slit"}
TYPES = ("art", "par", "ust", "pkt", "lit", "tir", "slit")
QUOTED_CLASSES = {"pro-rplc-text", "pro-cite-text"}
SUP = str.maketrans({c: f"_{p}" for c, p in zip(SUP_CHARS, "0123456789abcdefghijklmnoprstuvwxyz")})  # 22¹ᵃ: 22_1a
LABEL = {"art": "Art. {}.", "par": "§ {}.", "ust": "{}.", "pkt": "{})", "lit": "{})", "tir": "–"}


def norm_num(num: str) -> str:
    """"41¹" -> "41_1" (HTML id style); "41¹⁰" -> "41_10"."""
    out = num.lower().translate(SUP)
    head, _, tail = out.partition("_")
    return head + ("_" + tail.replace("_", "") if tail else "")


NONE_NUM = re.compile(r"\d+[a-z]*")


def none_type(tag: Tag) -> str | None:
    """Untyped HTML unit ("none_1"): typed by its printed label when that is one the JSON uses
    ("1." -> ust, "1)" -> pkt); None for "1.1.", "I.", "A.", "Tabela 1" etc."""
    num = tag["id"].split("-")[-1].partition("_")[2]
    if not NONE_NUM.fullmatch(num):
        return None
    first = " ".join(tag.get_text(" ").split())
    if re.match(rf"^{re.escape(num)}\s*\.(?!\s*\d)", first):
        return "ust"
    if re.match(rf"^{re.escape(num)}\s*\)", first):
        return "pkt"
    return None


def html_path(uid: str, none_types: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Path from an id; `none_types` maps id prefixes of untyped units to their inferred type."""
    segs, prefix = [], ""
    for part in uid.split("-"):
        prefix = f"{prefix}-{part}" if prefix else part
        typ, _, num = part.partition("_")
        if typ in HTML_TYPE:
            segs.append((HTML_TYPE[typ], num.lower()))
        elif typ == "none" and prefix in none_types:
            segs.append((none_types[prefix], num.lower()))
    return tuple(segs)


def json_path(path: str) -> tuple[tuple[str, str], ...]:
    return tuple((seg.split("_", 1)[0], norm_num(seg.split("_", 1)[1])) for seg in path.split("/"))


def _is_unit(tag: Tag) -> bool:
    return "unit" in tag.get("class", []) and bool(tag.get("id"))


def _owner(node, none_types: dict[str, str]) -> tuple:
    """Path of the unit a piece of text belongs to: the innermost typed unit that is not quoted and not
    inside a quoted unit (text of a quoted unit belongs to the unit that quotes it)."""
    chain = [t for t in node.parents if isinstance(t, Tag) and _is_unit(t)]  # innermost first
    q = max((k for k, t in enumerate(chain) if QUOTED_CLASSES & set(t.get("class", []))), default=-1)
    for t in chain[q + 1:]:
        last = t["id"].split("-")[-1].partition("_")[0]
        if last in HTML_TYPE or (last == "none" and t["id"] in none_types):
            return html_path(t["id"], none_types)
    return ()


def _walk(roots: list[Tag]) -> dict:
    toks: list[str] = []
    owners: list[tuple] = []  # per token: path of the unit it belongs to
    units: list[tuple[int, tuple, str]] = []  # (token index, path, type)
    quoted_n = none_n = 0
    none_types: dict[str, str] = {}  # parents come before children in document order
    for root in roots:
        for node in root.descendants:
            if isinstance(node, NavigableString):
                new = tokens(str(node))
                if new:
                    toks.extend(new)
                    owners.extend([_owner(node, none_types)] * len(new))
                continue
            if not isinstance(node, Tag) or not _is_unit(node):
                continue
            last = node["id"].split("-")[-1].partition("_")[0]
            if last == "none" and (nt := none_type(node)):
                none_types[node["id"]] = nt
                typ = nt
                none_n += 1
            elif last in HTML_TYPE:
                typ = HTML_TYPE[last]
            else:
                continue
            quoted = any(QUOTED_CLASSES & set(t.get("class", [])) for t in [node, *node.parents]
                         if isinstance(t, Tag) and _is_unit(t))
            if quoted:
                quoted_n += 1
                continue
            units.append((len(toks), html_path(node["id"], none_types), typ))
    return {"tokens": toks, "owners": owners, "units": units, "quoted": quoted_n, "none_typed": none_n}


def html_units(html: str) -> dict | None:
    s = BeautifulSoup(html, "html.parser")
    if "null Pokaż całość" in " ".join(s.get_text(" ").split()):
        return None
    for sel in ["script", "style", ".tooltip-text", "ul.toc", "h2.part", ".show-all", "a.gloss-link",
                ".gloss-section"]:
        for t in s.select(sel):
            t.decompose()
    h1 = s.find("h1")
    sections = s.select("section[id^=part_]")
    main = _walk(([h1] if h1 else []) + sections[:1])
    if len(main["tokens"]) < 10:
        return None
    annex = _walk([sec for sec in sections[1:]
                   if not any(a.get("href", "").endswith("text.pdf") for a in sec.find_all("a"))])
    return {"main": main, "annex": annex}


def _linear(nodes: list[dict], part: dict, parent: tuple = ()) -> None:
    toks, owners = part["tokens"], part["owners"]
    for n in nodes:
        t = n["type"]
        if t == "note":
            continue
        own = parent
        if t in RANK:
            own = json_path(n["path"])
            part["units"].append((len(toks), own, t))
            new = tokens(LABEL[t].format(n["num"]) + " " + n["text"])
        else:
            if t == "text" and n["text"].strip():
                part["texts"].append((len(toks), parent))
            new = tokens(n.get("label", "") + " " + n["text"])
        toks.extend(new)
        owners.extend([own] * len(new))
        _linear(n.get("children", []), part, own)


def json_units(tree: dict) -> dict:
    title = tokens(tree.get("title") or "")
    main: dict = {"tokens": title, "owners": [()] * len(title), "units": [], "texts": []}
    _linear(tree["body"], main)
    annex: dict = {"tokens": [], "owners": [], "units": [], "texts": []}
    for a in tree["annexes"]:
        head = tokens(a["heading"])
        annex["tokens"].extend(head)
        annex["owners"].extend([()] * len(head))
        _linear(a["body"], annex)
    return {"main": main, "annex": annex}


def align(ref: list[str], hyp: list[str]) -> tuple[list[int], list[int]]:
    r2h, h2r = [-1] * len(ref), [-1] * len(hyp)
    for a, b, n in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_matching_blocks():
        for k in range(n):
            r2h[a + k], h2r[b + k] = b + k, a + k
    return r2h, h2r


def _fmt(path: tuple) -> str:
    return "/".join(f"{t}_{n}" for t, n in path)


def score_part(ref: dict, hyp: dict, c: Counter, label: str, bad: list | None = None) -> None:
    """Add counts for one part to c: {label}.{R|P}.{type}_{n|hit|unal|none|path}."""
    r2h, h2r = align(ref["tokens"], hyp["tokens"])
    ref_at: dict[int, set] = {}
    for i, p, _ in ref["units"]:
        ref_at.setdefault(i, set()).add(p)
    hyp_at: dict[int, set] = {}
    for j, p, _ in hyp["units"]:
        hyp_at.setdefault(j, set()).add(p)
    # attachment: the unit a text paragraph (not a unit start) hangs under, and the unit of every word.
    # Tirets are dropped from both paths: the HTML does not mark them (see above).
    def notir(path: tuple) -> tuple:
        return tuple(seg for seg in path if seg[0] != "tir")

    for j, p in hyp.get("texts", []):
        i = h2r[j] if j < len(h2r) else -1
        if i < 0:
            c[f"{label}.text_unal"] += 1
            continue
        c[f"{label}.text_n"] += 1
        if notir(ref["owners"][i]) == notir(p):
            c[f"{label}.text_hit"] += 1
        elif bad is not None:
            bad.append((label, "T", "attach", _fmt(p), [_fmt(ref["owners"][i])], i))
    for i, j in enumerate(r2h):
        if j >= 0:
            c[f"{label}.word_n"] += 1
            c[f"{label}.word_hit"] += notir(ref["owners"][i]) == notir(hyp["owners"][j])
    c[f"{label}.quoted_ref"] += ref.get("quoted", 0)
    c[f"{label}.none_typed_ref"] += ref.get("none_typed", 0)
    for side, units, m, other in (("R", ref["units"], r2h, hyp_at), ("P", hyp["units"], h2r, ref_at)):
        for i, p, t in units:
            k = f"{label}.{side}.{t}"
            j = m[i] if i < len(m) else -1
            if j < 0:
                c[k + "_unal"] += 1
                continue
            c[k + "_n"] += 1
            if p in other.get(j, ()):
                c[k + "_hit"] += 1
                continue
            kind = "path" if other.get(j) else "none"
            c[f"{k}_{kind}"] += 1
            if bad is not None:
                i_ref = i if side == "R" else j
                got = sorted(_fmt(q) for q in other.get(j, ()))
                bad.append((label, side, kind, _fmt(p), got, i_ref))


def md_for(pos: int, md_cache: Path | None, year: int = 2024) -> str:
    if md_cache:
        f = md_cache / (f"{pos}.md" if year == 2024 else f"{year}_{pos}.md")
        if f.exists():
            return f.read_text(encoding="utf-8")
    md = to_markdown(convert(str(CACHE / "DU" / str(year) / str(pos) / "text.pdf")))
    if md_cache:
        md_cache.mkdir(parents=True, exist_ok=True)
        f.write_text(md, encoding="utf-8")
    return md


def evaluate_act(pos: int, md_cache: Path | None = None, show: bool = False, year: int = 2024) -> dict:
    ref = html_units((CACHE / "DU" / str(year) / str(pos) / "text.html").read_text(encoding="utf-8"))
    if ref is None:
        return {"pos": pos, "skipped": "html_unusable"}
    hyp = json_units(md_to_tree(md_for(pos, md_cache, year)))
    c: Counter = Counter()
    bad: list = []
    for label in ("main", "annex"):
        score_part(ref[label], hyp[label], c, label, bad)
    if show:
        order = {"R": 0, "P": 1, "T": 2}  # unit misses first, then paragraphs under the wrong unit
        for label, side, kind, p, got, i in sorted(bad, key=lambda b: order[b[1]])[:200]:
            rt = ref[label]["tokens"]
            what = {"R": "missed", "P": "false ", "T": "text  "}[side]
            print(f"{label:5} {what} {kind:4} {p:32} other: {','.join(got) or '-':32} "
                  f"...{' '.join(rt[max(0, i - 6):i])} | {' '.join(rt[i:i + 8])}")
    return {"pos": pos, "counts": dict(c), "errors": [b[:5] for b in bad]}


def rate(c: Counter, key: str) -> str:
    n = c[key + "_n"]
    return f"{c[key + '_hit'] / n:.4f} ({c[key + '_hit']}/{n})" if n else "-"


def summed(c: Counter, part: str, side: str, types: tuple, what: str) -> int:
    return sum(c[f"{part}.{side}.{t}_{what}"] for t in types)


def report(total: Counter, out) -> None:
    core = ("art", "par", "ust", "pkt", "lit")
    for part in ("main", "annex"):
        agg = Counter()
        for side in ("R", "P"):
            for w in ("n", "hit", "unal", "none", "path"):
                agg[f"{side}_{w}"] = summed(total, part, side, core, w)
        print(f"TOTAL {part:5} all (art,par,ust,pkt,lit)  R={rate(agg, 'R')}  P={rate(agg, 'P')}  "
              f"R miss none/path {agg['R_none']}/{agg['R_path']}  P miss none/path {agg['P_none']}/{agg['P_path']}  "
              f"unaligned ref {agg['R_unal']}, json {agg['P_unal']}; quoted ref units left out: "
              f"{total[part + '.quoted_ref']}; untyped HTML units typed by label: "
              f"{total[part + '.none_typed_ref']}", file=out)
        print(f"TOTAL {part:5} attach  text paragraphs under the right unit: {rate(total, part + '.text')} "
              f"(unaligned {total[part + '.text_unal']}); words in the right unit: {rate(total, part + '.word')}",
              file=out)
        for t in TYPES:
            r, p = f"{part}.R.{t}", f"{part}.P.{t}"
            if not (total[r + "_n"] or total[p + "_n"] or total[r + "_unal"] or total[p + "_unal"]):
                continue
            if not (total[r + "_n"] or total[r + "_unal"]):  # e.g. tirets: the HTML does not mark them
                print(f"TOTAL {part:5} {t:4}  no reference units in the HTML, not scored; JSON nodes: "
                      f"{total[p + '_n'] + total[p + '_unal']}", file=out)
                continue
            print(f"TOTAL {part:5} {t:4}  R={rate(total, r):22}  P={rate(total, p):22}  "
                  f"R miss none/path {total[r + '_none']}/{total[r + '_path']}  "
                  f"P miss none/path {total[p + '_none']}/{total[p + '_path']}  "
                  f"unaligned ref {total[r + '_unal']}, json {total[p + '_unal']}", file=out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("--md-cache", type=Path, help="reuse / store converted Markdown here (<pos>.md)")
    ap.add_argument("--show", type=int, help="print misses for one act (pos)")
    ap.add_argument("--out", help="write per-act counts and errors (JSON) here")
    a = ap.parse_args()
    items = json.loads(Path(a.sample).read_text())
    if a.show:
        items = [i for i in items if i["pos"] == a.show]
    rows, total = [], Counter()
    core = ("art", "par", "ust", "pkt", "lit")
    for it in items:
        r = evaluate_act(it["pos"], a.md_cache, show=bool(a.show), year=it.get("year", 2024))
        r["type"] = it["type"]
        rows.append(r)
        if "skipped" in r:
            print(f"{it['pos']:5} SKIPPED: HTML reference unusable", flush=True)
            continue
        c = Counter(r["counts"])
        total.update(c)
        cols = []
        for part in ("main", "annex"):
            agg = Counter({f"{s}_{w}": summed(c, part, s, core, w) for s in "RP" for w in ("n", "hit")})
            if agg["R_n"] or agg["P_n"]:
                cols.append(f"{part}: R={rate(agg, 'R')} P={rate(agg, 'P')}")
        print(f"{it['pos']:5} {it['type'][:14]:14} " + "  ".join(cols), flush=True)
    done = [r for r in rows if "skipped" not in r]
    print(f"scored {len(done)}/{len(rows)} acts")
    report(total, sys.stdout)
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
