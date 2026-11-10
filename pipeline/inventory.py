"""Produce inventory statistics from the parsed EAD tree."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from pipeline.ead_parser import parse_ead, walk
from pipeline.paths import REPORTS_DIR, SRCDATA


def run(path=None) -> dict:
    data = parse_ead(path or SRCDATA)
    coll = data["collection"]
    levels = Counter()
    digitized = Counter()
    dao_kinds = Counter()
    container_types = Counter()
    sources = Counter()
    named_elements = Counter()
    with_ark = 0
    with_controlaccess = 0
    with_dao = 0
    total = 0
    series = []
    boxes = set()
    folders = 0
    auth_with_uri = 0
    auth_without_uri = 0

    for node, _parent in walk(coll):
        total += 1
        levels[node["level"]] += 1
        digitized[bool(node["digitized"])] += 1
        if node["digitized"]:
            with_dao += 1
        dao_kinds[node.get("digitization_kind") or "none"] += 1
        did = node.get("did") or {}
        if did.get("ark"):
            with_ark += 1
        ca = node.get("controlaccess") or {}
        if any(ca.get(k) for k in ("subjects", "places", "agents", "genres", "titles")):
            with_controlaccess += 1
        for c in did.get("containers") or []:
            container_types[c.get("type") or "unknown"] += 1
            if (c.get("type") or "").lower() == "box":
                boxes.add(c.get("value"))
            if (c.get("type") or "").lower() == "folder":
                folders += 1
        for dao in node.get("daos") or []:
            dao_kinds["dao:" + (dao.get("kind") or "other")] += 1
        for rec in _all_named(node):
            named_elements[rec["element"]] += 1
            if rec.get("source"):
                sources[rec["source"]] += 1
            if rec.get("uri"):
                auth_with_uri += 1
            elif rec.get("text"):
                auth_without_uri += 1
        if node["level"] == "series":
            series.append(
                {
                    "id": node["id"],
                    "title": did.get("unittitle"),
                    "unitid": did.get("local_id"),
                    "children": len(node.get("children") or []),
                    "digitized": node["digitized"],
                }
            )

    report = {
        "eadid": data["header"].get("eadid"),
        "title": (coll.get("did") or {}).get("unittitle"),
        "components": total,
        "levels": dict(levels),
        "digitized_components": digitized[True],
        "undigitized_components": digitized[False],
        "digitization_kinds": dict(dao_kinds),
        "with_ark": with_ark,
        "with_controlaccess": with_controlaccess,
        "container_types": dict(container_types),
        "distinct_boxes": len(boxes),
        "folder_mentions": folders,
        "authority_sources": dict(sources),
        "named_elements": dict(named_elements),
        "named_with_uri": auth_with_uri,
        "named_without_uri": auth_without_uri,
        "series": series,
        "header": data["header"],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "inventory.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _all_named(node):
    did = node.get("did") or {}
    for orig in did.get("origination") or []:
        yield from orig.get("agents") or []
    yield from did.get("title_entities") or []
    ca = node.get("controlaccess") or {}
    for key in ("subjects", "places", "agents", "genres", "titles"):
        yield from ca.get(key) or []
    for blocks in (node.get("notes") or {}).values():
        for b in blocks:
            yield from b.get("entities") or []


if __name__ == "__main__":
    r = run()
    print(json.dumps({k: r[k] for k in r if k != "header"}, indent=2, ensure_ascii=False))
