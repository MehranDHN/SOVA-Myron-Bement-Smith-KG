"""Flatten unique agents, places, subjects, genres from the EAD tree."""

from __future__ import annotations

import json
from collections import OrderedDict

from pipeline.ead_parser import parse_ead, walk
from pipeline.paths import CACHE_DIR, SRCDATA
from pipeline.util import slugify


def _key(rec: dict) -> str:
    uri = rec.get("uri") or ""
    text = (rec.get("text") or rec.get("normal") or "").strip().lower()
    kind = rec.get("element") or ""
    return f"{kind}|{uri}|{text}"


def _add(bucket: OrderedDict, rec: dict, component_id: str, field: str):
    if not rec.get("text") and not rec.get("uri"):
        return
    k = _key(rec)
    if k not in bucket:
        bucket[k] = {
            "element": rec.get("element"),
            "text": rec.get("text"),
            "normal": rec.get("normal"),
            "role": rec.get("role"),
            "source": rec.get("source"),
            "authfilenumber": rec.get("authfilenumber"),
            "uri": rec.get("uri"),
            "slug": slugify(rec.get("normal") or rec.get("text") or rec.get("uri") or "entity"),
            "occurrences": [],
        }
    bucket[k]["occurrences"].append({"component": component_id, "field": field})


def extract(path=None) -> dict:
    data = parse_ead(path or SRCDATA)
    agents: OrderedDict = OrderedDict()
    places: OrderedDict = OrderedDict()
    subjects: OrderedDict = OrderedDict()
    genres: OrderedDict = OrderedDict()
    for node, _ in walk(data["collection"]):
        cid = node["id"]
        did = node.get("did") or {}
        for orig in did.get("origination") or []:
            for rec in orig.get("agents") or []:
                rec = dict(rec)
                rec["role"] = rec.get("role") or orig.get("label")
                _add(agents, rec, cid, "origination")
        for rec in did.get("title_entities") or []:
            el = rec.get("element")
            if el == "geogname":
                _add(places, rec, cid, "unittitle")
            elif el in {"persname", "corpname", "famname"}:
                _add(agents, rec, cid, "unittitle")
            else:
                _add(subjects, rec, cid, "unittitle")
        ca = node.get("controlaccess") or {}
        for rec in ca.get("agents") or []:
            _add(agents, rec, cid, "controlaccess")
        for rec in ca.get("places") or []:
            _add(places, rec, cid, "controlaccess")
        for rec in ca.get("subjects") or []:
            _add(subjects, rec, cid, "controlaccess")
        for rec in ca.get("genres") or []:
            _add(genres, rec, cid, "controlaccess")
        for tag, blocks in (node.get("notes") or {}).items():
            for b in blocks:
                for rec in b.get("entities") or []:
                    el = rec.get("element")
                    if el == "geogname":
                        _add(places, rec, cid, tag)
                    elif el in {"persname", "corpname", "famname"}:
                        _add(agents, rec, cid, tag)
    payload = {
        "agents": list(agents.values()),
        "places": list(places.values()),
        "subjects": list(subjects.values()),
        "genres": list(genres.values()),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "entities.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    p = extract()
    print(
        json.dumps(
            {k: len(v) for k, v in p.items()},
            indent=2,
        )
    )
