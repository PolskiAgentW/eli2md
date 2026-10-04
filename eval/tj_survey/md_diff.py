"""Two conversions of the same acts (e.g. tj_convert.py with two versions of eli2md): which files differ beyond
the `converter:` line, and the changed lines, for review.

    python eval/tj_survey/md_diff.py OLD_DIR NEW_DIR [--out REPORT.txt]

Prints counts; the report has every changed file with its changed lines (difflib, no context).
"""
import difflib, pathlib, sys


def lines(path):
    return [l for l in path.read_text(encoding="utf-8").split("\n") if not l.startswith("converter: ")]


def main():
    old, new = map(pathlib.Path, sys.argv[1:3])
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    files = sorted(p.relative_to(old) for p in old.rglob("*.md"))
    same, changed, missing, report = 0, [], [], []
    for rel in files:
        if not (new / rel).exists():
            missing.append(str(rel))
            continue
        a, b = lines(old / rel), lines(new / rel)
        if a == b:
            same += 1
            continue
        changed.append(str(rel))
        report.append(f"=== {rel}")
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            report.append(f"@@ {tag} old {i1 + 1}-{i2} new {j1 + 1}-{j2}")
            report += ["- " + l for l in a[i1:i2]] + ["+ " + l for l in b[j1:j2]]
    print(f"files {len(files)}: same {same}, changed {len(changed)}, missing in new {len(missing)}")
    for rel in changed:
        print("  changed", rel)
    for rel in missing:
        print("  missing", rel)
    if out:
        pathlib.Path(out).write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
