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


def clean_title(title: str | None) -> str | None:
    """The ELI title without what the API appends after a tab: "…Prawosławnego\t2023-03-23\tPobierz dokument
    D2023000054401.pdf" (DU/2023/544), "…Pieniężnej\t202" (MP/2022/971); 14 of 128 084 DU and MP titles, 2026-10-13."""
    return title.split("\t", 1)[0].rstrip() if title and "\t" in title else title


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


def fetch(eli: str, delay: float = 1.0, refresh: bool = False, change_date: str | None = None) -> tuple[dict, Path]:
    """Return (metadata, path to text.pdf), using the on-disk cache unless `refresh` or unless the cached metadata has
    another changeDate than `change_date` (the act's changeDate in the API year list: a cache from before a correction in
    the API gave the old date and title, MP/2018/438, DU/2025/1099). The title is cleaned (clean_title)."""
    pub, year, pos = parse_eli(eli)
    d = CACHE / pub / str(year) / str(pos)
    d.mkdir(parents=True, exist_ok=True)
    meta_f, pdf_f = d / "meta.json", d / "text.pdf"
    if change_date and meta_f.exists() and json.loads(meta_f.read_text()).get("changeDate") != change_date:
        refresh = True
    if refresh:
        meta_f.unlink(missing_ok=True)
        pdf_f.unlink(missing_ok=True)
    if not meta_f.exists():
        meta_f.write_bytes(get(f"{API}/{pub}/{year}/{pos}"))
        time.sleep(delay)
    meta = json.loads(meta_f.read_text())
    meta["title"] = clean_title(meta.get("title"))
    if not meta.get("textPDF"):
        raise LookupError(f"{eli}: no PDF text in the ELI API")
    if not pdf_f.exists() or pdf_f.stat().st_size == 0:
        pdf_f.write_bytes(get(f"{API}/{pub}/{year}/{pos}/text.pdf"))
        time.sleep(delay)
    return meta, pdf_f
