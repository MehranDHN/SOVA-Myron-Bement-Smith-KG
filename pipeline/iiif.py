"""Derive Smithsonian IIIF and media-access URIs from EAD dao links.

Digitized *file* units are PDFs reached through the EDAN slideshow.
Each PDF page is a separate IDS image with its own IIIF Manifest
(``https://ids.si.edu/ids/manifest/{IDS-ID}``). Page IDS identifiers are
not computable from the eadrefid; they are harvested from the slideshow
HTML, supplied in ``data/iiif-pages.yml``, or left pending.

Digitized *item* units are single JPEGs on ids.si.edu, with viewer
``https://ids.si.edu/ids/deliveryService?id={ID}`` and manifest
``https://ids.si.edu/ids/manifest/{ID}``.

Default rebuild is offline (cache + YAML). ``--fetch-slideshow`` walks
EDAN pager HTML. ``--probe-iiif`` HEAD/GETs derived IIIF URLs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from pipeline.paths import CACHE_DIR, IIIF_PAGES

IDS_IIIF = "https://ids.si.edu/ids/iiif/"
IDS_MANIFEST = "https://ids.si.edu/ids/manifest/"
IDS_VIEWER = "https://ids.si.edu/ids/deliveryService?id="
SLIDESHOW_VIEWER = "https://edan.si.edu/slideshow/viewer/?eadrefid="
SLIDESHOW_PAGER = "https://edan.si.edu/slideshow/viewer/pager?eadrefid="
SLIDESHOW_PDF = "https://edan.si.edu/slideshow/viewer/pdf?eadrefid="

_UAN = re.compile(r'data-uan="([^"]+)"')
_NUM_PAGES = re.compile(r'data-num-pages="(\d+)"')
_NUM_FOUND = re.compile(r'data-num-found="(\d+)"')

CACHE_FILE = "slideshow-pages.json"


def jpeg_viewer(ids_id: str) -> str:
    return IDS_VIEWER + ids_id


def jpeg_manifest(ids_id: str) -> str:
    return IDS_MANIFEST + ids_id


def jpeg_service(ids_id: str) -> str:
    return IDS_IIIF + ids_id


def slideshow_viewer(eadrefid: str) -> str:
    return SLIDESHOW_VIEWER + eadrefid


def slideshow_pdf_request(eadrefid: str) -> str:
    return SLIDESHOW_PDF + eadrefid


def parse_slideshow_html(html: str) -> dict:
    """Pull ordered unique IDS identifiers and pager metadata from EDAN HTML."""
    ids_ids = []
    seen = set()
    for match in _UAN.finditer(html or ""):
        uan = match.group(1).strip()
        if uan and uan not in seen:
            seen.add(uan)
            ids_ids.append(uan)
    n_pages = None
    n_found = None
    m = _NUM_PAGES.search(html or "")
    if m:
        n_pages = int(m.group(1))
    m = _NUM_FOUND.search(html or "")
    if m:
        n_found = int(m.group(1))
    return {"ids_ids": ids_ids, "num_pages": n_pages, "num_found": n_found}


def _http_get(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "SOVA-Myron-Bement-Smith-KG/0.1"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def fetch_slideshow_pages(eadrefid: str, timeout: int = 30) -> dict:
    """Walk EDAN slideshow pager pages and collect every IDS id."""
    html = _http_get(slideshow_viewer(eadrefid), timeout=timeout)
    first = parse_slideshow_html(html)
    ids_ids = list(first["ids_ids"])
    n_pages = first.get("num_pages") or 1
    for page in range(2, n_pages + 1):
        pager = f"{SLIDESHOW_PAGER}{eadrefid}&page={page}"
        chunk = parse_slideshow_html(_http_get(pager, timeout=timeout))
        for uan in chunk["ids_ids"]:
            if uan not in ids_ids:
                ids_ids.append(uan)
    return {
        "eadrefid": eadrefid,
        "ids_ids": ids_ids,
        "page_count": len(ids_ids),
        "viewer": slideshow_viewer(eadrefid),
        "pdf_request": slideshow_pdf_request(eadrefid),
        "source": "edan-slideshow-html",
    }


def load_yaml_pages() -> dict:
    path = IIIF_PAGES
    if not path.exists():
        return {}
    import yaml

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for key, rec in raw.items():
        if key.startswith("#") or not isinstance(rec, dict):
            continue
        ids_ids = rec.get("ids_ids") or rec.get("pages") or []
        out[key] = {
            "eadrefid": key,
            "ids_ids": list(ids_ids),
            "page_count": rec.get("page_count") or len(ids_ids),
            "source": "yaml",
        }
    return out


def load_slideshow_cache() -> dict:
    path = CACHE_DIR / CACHE_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_slideshow_cache(data: dict) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / CACHE_FILE
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def page_index() -> dict:
    """YAML overrides the harvested cache."""
    merged = dict(load_slideshow_cache())
    merged.update(load_yaml_pages())
    return merged


def derive_from_dao(dao: dict, pages: dict | None = None) -> dict:
    kind = dao.get("kind")
    ids_id = dao.get("ids_id")
    eadrefid = dao.get("eadrefid")
    href = dao.get("href")
    rec = {
        "kind": kind,
        "href": href,
        "ids_id": ids_id,
        "eadrefid": eadrefid,
        "iiif_image_service": None,
        "iiif_info": None,
        "iiif_manifest": None,
        "iiif_manifest_candidate": False,
        "iiif_resolved": None,
        "viewer": href,
        "pdf_request": None,
        "pages": [],
        "page_count": None,
        "page_manifests_pending": False,
        "access_media": None,
    }
    if ids_id:
        rec["viewer"] = jpeg_viewer(ids_id)
        rec["iiif_image_service"] = jpeg_service(ids_id)
        rec["iiif_info"] = jpeg_service(ids_id) + "/info.json"
        rec["iiif_manifest"] = jpeg_manifest(ids_id)
        rec["iiif_manifest_candidate"] = True
        rec["access_media"] = "jpeg"
    elif eadrefid:
        rec["viewer"] = slideshow_viewer(eadrefid)
        rec["pdf_request"] = slideshow_pdf_request(eadrefid)
        rec["access_media"] = "pdf"
        rec["iiif_manifest"] = None
        rec["iiif_manifest_candidate"] = False
        known = (pages or {}).get(eadrefid) or {}
        ids_ids = known.get("ids_ids") or []
        rec["pages"] = [
            {
                "ids_id": pid,
                "viewer": jpeg_viewer(pid),
                "iiif_manifest": jpeg_manifest(pid),
                "iiif_image_service": jpeg_service(pid),
                "page_number": n,
            }
            for n, pid in enumerate(ids_ids, start=1)
        ]
        rec["page_count"] = known.get("page_count") or (len(ids_ids) or None)
        rec["page_manifests_pending"] = not bool(ids_ids)
    return rec


def probe(url: str, timeout: int = 12) -> bool:
    try:
        import requests
    except ImportError:
        return False
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code < 400:
            return True
        r = requests.get(url, timeout=timeout, allow_redirects=True)
        return r.status_code < 400
    except Exception:
        return False


def enrich_daos(daos: list[dict], do_probe: bool = False, pages: dict | None = None) -> list[dict]:
    index = pages if pages is not None else page_index()
    out = []
    for dao in daos:
        rec = derive_from_dao(dao, pages=index)
        if do_probe and rec.get("iiif_info"):
            rec["iiif_resolved"] = probe(rec["iiif_info"])
            if rec["iiif_resolved"] is False and rec.get("iiif_manifest"):
                rec["iiif_resolved"] = probe(rec["iiif_manifest"])
        out.append({**dao, **rec})
    return out


def harvest_from_ead(nodes, resume: bool = True, limit: int | None = None) -> dict:
    """Fetch slideshow page lists for every edan-slideshow dao."""
    cache = load_slideshow_cache() if resume else {}
    seen = set()
    fetched = 0
    for node in nodes:
        for dao in node.get("daos") or []:
            eadrefid = dao.get("eadrefid")
            if not eadrefid or eadrefid in seen:
                continue
            seen.add(eadrefid)
            if eadrefid in cache and cache[eadrefid].get("ids_ids"):
                continue
            try:
                cache[eadrefid] = fetch_slideshow_pages(eadrefid)
            except Exception as exc:
                cache[eadrefid] = {
                    "eadrefid": eadrefid,
                    "ids_ids": [],
                    "page_count": None,
                    "error": str(exc),
                    "source": "edan-slideshow-html",
                }
            save_slideshow_cache(cache)
            fetched += 1
            if limit and fetched >= limit:
                return cache
    save_slideshow_cache(cache)
    return cache
