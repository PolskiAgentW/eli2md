"""Download text.html, text.pdf and meta.json of the acts in a sample file into ~/cache/eli (skips cached files)."""
import json
import sys
import time
import urllib.request

from common import API, act_dir, meta_bytes

for eli in json.load(open(sys.argv[1])):
    d = act_dir(eli)
    meta_bytes(eli)
    for name in ("text.html", "text.pdf"):
        f = d / name
        if f.exists():
            continue
        for attempt in range(3):
            try:
                with urllib.request.urlopen(f"{API}/{eli}/{name}", timeout=120) as r:
                    f.write_bytes(r.read())
                break
            except Exception as exc:  # noqa: BLE001
                print(eli, name, "retry", attempt, exc, flush=True)
                time.sleep(5)
        time.sleep(0.5)
    print(eli, "ok", flush=True)
print("FETCH_DONE", flush=True)
