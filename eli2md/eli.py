"""Fetch act metadata and PDF text from the Sejm ELI API (https://api.sejm.gov.pl/eli)."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

API = "https://api.sejm.gov.pl/eli/acts"
UA = "eli2md/0.1 (+https://github.com/PolskiAgentW/eli2md)"
CACHE = Path(os.environ.get("ELI2MD_CACHE", Path.home() / "cache" / "eli"))
ELI_ID = re.compile(r"^(?:https?://[^/]+/eli/acts/)?(DU|MP)/(\d{4})/(\d+)/?$")


def parse_eli(s: str) -> tuple[str, int, int]:
    m = ELI_ID.match(s.strip())
    if not m:
        raise ValueError(f"not an ELI id like DU/2025/900: {s!r}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def get(url: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 5)
    raise AssertionError("unreachable")


def fetch(eli: str, delay: float = 1.0, refresh: bool = False) -> tuple[dict, Path]:
    """Return (metadata, path to text.pdf), using the on-disk cache unless `refresh`."""
    pub, year, pos = parse_eli(eli)
    d = CACHE / pub / str(year) / str(pos)
    d.mkdir(parents=True, exist_ok=True)
    meta_f, pdf_f = d / "meta.json", d / "text.pdf"
    if refresh:
        meta_f.unlink(missing_ok=True)
        pdf_f.unlink(missing_ok=True)
    if not meta_f.exists():
        meta_f.write_bytes(get(f"{API}/{pub}/{year}/{pos}"))
        time.sleep(delay)
    meta = json.loads(meta_f.read_text())
    if not meta.get("textPDF"):
        raise LookupError(f"{eli}: no PDF text in the ELI API")
    if not pdf_f.exists() or pdf_f.stat().st_size == 0:
        pdf_f.write_bytes(get(f"{API}/{pub}/{year}/{pos}/text.pdf"))
        time.sleep(delay)
    return meta, pdf_f
