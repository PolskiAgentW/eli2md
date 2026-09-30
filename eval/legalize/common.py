"""Shared helpers for the legalize-pipeline PL PDF work (prototype + measurement). Uses the legalize venv."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

CACHE = Path.home() / "cache" / "eli"
API = "https://api.sejm.gov.pl/eli/acts"


def act_dir(eli: str) -> Path:
    pub, year, pos = eli.split("/")
    return CACHE / pub / year / pos


def meta_bytes(eli: str) -> bytes:
    f = act_dir(eli) / "meta.json"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f"{API}/{eli}", timeout=60) as r:
            f.write_bytes(r.read())
    return f.read_bytes()


def html_input(eli: str) -> bytes:
    """text.html with the marker EliClient.get_text() injects."""
    meta = json.loads(meta_bytes(eli))
    pub, year, pos = eli.split("/")
    marker = f"<!--LEGALIZE norm_id={pub}-{year}-{pos} pub_date={meta.get('announcementDate', '')}-->\n"
    return marker.encode() + (act_dir(eli) / "text.html").read_bytes()


def render(eli: str, blocks) -> str:
    from legalize.fetcher.pl.parser import EliMetadataParser
    from legalize.transformer.markdown import render_norm_at_date
    from legalize.transformer.xml_parser import extract_reforms

    pub, year, pos = eli.split("/")
    meta = EliMetadataParser().parse(meta_bytes(eli), f"{pub}-{year}-{pos}")
    reforms = extract_reforms(blocks)
    return render_norm_at_date(meta, blocks, reforms[0].date if reforms else meta.publication_date,
                               include_all=True)


def body(md: str) -> str:
    """Markdown after the front matter."""
    return md.split("\n---\n", 1)[1] if md.startswith("---\n") else md
