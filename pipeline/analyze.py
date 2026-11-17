"""Compare local EAD XML, optional live SOVA XML, and harvested RDF.

Standalone::

    python -m pipeline.analyze
    python -m pipeline.analyze --ead srcdata/FSA.A.06-ead.xml
    python -m pipeline.analyze --live-ead

The run is idempotent: it only writes ``data/reports/analyze/`` (and a
remote-EAD cache when ``--live-ead`` is set). It never mutates ``srcdata/``,
``data/rdf/``, or ``vocab/seed.yml``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pipeline.ead_parser import digital_source_id, parse_ead, walk
from pipeline.inventory import from_parsed, write_report
from pipeline.namespaces import collection_slug, kg_name
from pipeline.paths import (
    ANALYZE_DIR,
    DEFAULT_EADID,
    EAD_SOURCES,
    REMOTE_EAD_CACHE,
    ROOT,
    list_local_eads,
    rdf_dir_for,
)
from pipeline.util import slugify

SAMPLE = 40
COMPONENT_RE = re.compile(r"\bkg:(component_[A-Za-z0-9_]+)")
DIGITAL_RE = re.compile(r"\bkg:(digital_[A-Za-z0-9_]+)")
EADREF_RE = re.compile(r'\bmbs:eadRef\s+"([^"]+)"')
D1_RE = re.compile(r"crmdig:D1_Digital_Object")
USER_AGENT = "SOVA-Myron-Bement-Smith-KG/0.1 (research KG; +https://w3id.org/sova/fsa_a_04)"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sample(items, n: int = SAMPLE) -> list:
    seq = list(items)
    return seq[:n]


def _norm_label(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().lower()


def load_sources() -> dict:
    cfg = {"user_agent": USER_AGENT, "collections": []}
    if EAD_SOURCES.exists():
        import yaml

        raw = yaml.safe_load(EAD_SOURCES.read_text(encoding="utf-8")) or {}
        cfg["user_agent"] = raw.get("user_agent") or USER_AGENT
        cfg["collections"] = list(raw.get("collections") or [])
    by_id = {row["eadid"]: row for row in cfg["collections"] if row.get("eadid")}
    for path in list_local_eads():
        eadid = path.name.replace("-ead.xml", "")
        if eadid not in by_id:
            by_id[eadid] = {
                "eadid": eadid,
                "local": str(path.relative_to(ROOT)).replace("\\", "/"),
                "xml_urls": default_xml_urls(eadid),
            }
            cfg["collections"].append(by_id[eadid])
        row = by_id[eadid]
        row.setdefault("local", str(path.relative_to(ROOT)).replace("\\", "/"))
        row.setdefault("xml_urls", default_xml_urls(eadid))
        row["path"] = path
    cfg["by_id"] = by_id
    return cfg


def default_xml_urls(eadid: str) -> list[str]:
    lower = eadid.lower()
    dashed = lower.replace(".", "-")
    return [
        f"https://sova.si.edu/record/{eadid}.xml",
        f"https://sova.si.edu/record/{lower}.xml",
        f"https://sova.si.edu/record/{dashed}.xml",
    ]


def local_path_for(eadid: str, sources: dict | None = None) -> Path:
    sources = sources or load_sources()
    row = (sources.get("by_id") or {}).get(eadid)
    if row and row.get("path"):
        return Path(row["path"])
    return ROOT / "srcdata" / f"{eadid}-ead.xml"


def ead_snapshot(data: dict) -> dict:
    """Flatten the parsed tree into comparable component and DAO indexes."""
    components = OrderedDict()
    daos = []
    named = Counter()
    named_labels = Counter()
    named_unseeded_pool = []
    for node, parent in walk(data["collection"]):
        did = node.get("did") or {}
        cid = node["id"]
        dao_rows = []
        for i, dao in enumerate(node.get("daos") or [], start=1):
            source = digital_source_id(dao, cid, i)
            rec = {
                "component": cid,
                "kind": dao.get("kind"),
                "href": dao.get("href"),
                "ids_id": dao.get("ids_id"),
                "eadrefid": dao.get("eadrefid"),
                "damspath": dao.get("damspath"),
                "damspath_id": dao.get("damspath_id"),
                "source_id": source,
                "digital_local": kg_name("digital", slugify(source)),
            }
            dao_rows.append(rec)
            daos.append(rec)
        components[cid] = {
            "id": cid,
            "level": node.get("level"),
            "parent_id": parent["id"] if parent else None,
            "title": did.get("unittitle"),
            "ark": did.get("ark"),
            "digitized": bool(node.get("digitized")),
            "digitization_kind": node.get("digitization_kind"),
            "component_local": kg_name("component", cid),
            "dao_count": len(dao_rows),
            "daos": dao_rows,
            "containers": [
                {"type": c.get("type"), "value": c.get("value")}
                for c in did.get("containers") or []
            ],
        }
        from pipeline.inventory import _all_named

        for rec in _all_named(node):
            el = rec.get("element") or "unknown"
            named[el] += 1
            label = rec.get("text") or rec.get("normal") or ""
            if label:
                named_labels[(el, _norm_label(label))] += 1
                named_unseeded_pool.append(
                    {
                        "element": el,
                        "text": label,
                        "uri": rec.get("uri"),
                        "source": rec.get("source"),
                        "component": cid,
                    }
                )
    inventory = from_parsed(data)
    return {
        "eadid": inventory.get("eadid"),
        "title": inventory.get("title"),
        "header": data.get("header") or {},
        "path": data.get("path"),
        "inventory": inventory,
        "components": components,
        "daos": daos,
        "named_elements": dict(named),
        "named_pool": named_unseeded_pool,
        "named_label_counts": named_labels,
    }


def scan_rdf_dir(eadid: str) -> dict:
    """Index ``kg:component_`` / ``kg:digital_`` local names from Turtle shards."""
    out_dir = rdf_dir_for(eadid)
    files = sorted(p for p in out_dir.glob("*.ttl") if p.is_file())
    components = set()
    digitals = set()
    ead_refs = set()
    d1 = 0
    file_stats = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        c_hits = set(COMPONENT_RE.findall(text))
        d_hits = set(DIGITAL_RE.findall(text))
        r_hits = set(EADREF_RE.findall(text))
        d1_hits = len(D1_RE.findall(text))
        components.update(c_hits)
        digitals.update(d_hits)
        ead_refs.update(r_hits)
        d1 += d1_hits
        file_stats.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "components": len(c_hits),
                "digital_objects": len(d_hits),
                "d1_mentions": d1_hits,
            }
        )
    mapped = (out_dir / "collection.ttl").exists() and any(
        p.name.startswith("series-") for p in files
    )
    stub_local = kg_name("component", eadid)
    return {
        "eadid": eadid,
        "dir": str(out_dir.relative_to(ROOT)).replace("\\", "/"),
        "mapped": mapped,
        "stub_in_parent": stub_local in components,
        "files": file_stats,
        "component_locals": components,
        "digital_locals": digitals,
        "ead_refs": ead_refs,
        "d1_mentions": d1,
        "file_count": len(files),
    }


def compare_ead_rdf(snap: dict, rdf: dict) -> dict:
    ead_locals = {c["component_local"] for c in snap["components"].values()}
    rdf_comps = set(rdf.get("component_locals") or [])
    missing_rdf = sorted(ead_locals - rdf_comps)
    extra_rdf = sorted(rdf_comps - ead_locals)
    expected_digital = {d["digital_local"] for d in snap["daos"]}
    rdf_digital = set(rdf.get("digital_locals") or [])
    dao_missing = sorted(expected_digital - rdf_digital)
    digital_extra = sorted(rdf_digital - expected_digital)
    digitized_no_d1 = []
    for cid, rec in snap["components"].items():
        if rec["digitized"] and rec["component_local"] not in rdf_comps:
            digitized_no_d1.append(
                {
                    "id": cid,
                    "title": rec["title"],
                    "kind": rec["digitization_kind"],
                    "dao_count": rec["dao_count"],
                }
            )
        elif rec["digitized"] and not any(d["digital_local"] in rdf_digital for d in rec["daos"]):
            digitized_no_d1.append(
                {
                    "id": cid,
                    "title": rec["title"],
                    "kind": rec["digitization_kind"],
                    "dao_count": rec["dao_count"],
                }
            )
    kind_counts = Counter((d.get("kind") or "other") for d in snap["daos"])
    return {
        "ead_components": len(ead_locals),
        "rdf_components": len(rdf_comps),
        "ead_daos": len(snap["daos"]),
        "rdf_digital_locals": len(rdf_digital),
        "components_in_ead_missing_from_rdf": {
            "count": len(missing_rdf),
            "sample": _sample(missing_rdf),
        },
        "components_in_rdf_missing_from_ead": {
            "count": len(extra_rdf),
            "sample": _sample(extra_rdf),
        },
        "digital_keys_in_ead_missing_from_rdf": {
            "count": len(dao_missing),
            "sample": _sample(dao_missing),
        },
        "digital_keys_in_rdf_missing_from_ead": {
            "count": len(digital_extra),
            "sample": _sample(digital_extra),
        },
        "digitized_components_without_d1": {
            "count": len(digitized_no_d1),
            "sample": _sample(digitized_no_d1),
        },
        "dao_kinds": dict(kind_counts),
        "mapped": rdf.get("mapped"),
    }


def compare_ead_trees(local: dict, remote: dict) -> dict:
    loc = local["components"]
    rem = remote["components"]
    loc_ids = set(loc)
    rem_ids = set(rem)
    added = sorted(rem_ids - loc_ids)
    removed = sorted(loc_ids - rem_ids)
    changed = []
    for cid in sorted(loc_ids & rem_ids):
        a, b = loc[cid], rem[cid]
        diffs = []
        for key in ("title", "level", "digitized", "digitization_kind", "ark"):
            if a.get(key) != b.get(key):
                diffs.append(key)
        loc_hrefs = {d["href"] for d in a.get("daos") or []}
        rem_hrefs = {d["href"] for d in b.get("daos") or []}
        if loc_hrefs != rem_hrefs:
            diffs.append("daos")
        if diffs:
            changed.append({"id": cid, "fields": diffs, "title": b.get("title") or a.get("title")})
    loc_daos = {d["href"] for d in local["daos"] if d.get("href")}
    rem_daos = {d["href"] for d in remote["daos"] if d.get("href")}
    new_daos = sorted(rem_daos - loc_daos)
    lost_daos = sorted(loc_daos - rem_daos)
    loc_header = (local.get("header") or {}).get("creation")
    rem_header = (remote.get("header") or {}).get("creation")
    return {
        "local_components": len(loc),
        "remote_components": len(rem),
        "added_components": {"count": len(added), "sample": _sample(added)},
        "removed_components": {"count": len(removed), "sample": _sample(removed)},
        "changed_components": {"count": len(changed), "sample": _sample(changed)},
        "new_dao_hrefs": {"count": len(new_daos), "sample": _sample(new_daos)},
        "removed_dao_hrefs": {"count": len(lost_daos), "sample": _sample(lost_daos)},
        "local_creation": loc_header,
        "remote_creation": rem_header,
        "creation_changed": loc_header != rem_header,
    }


def vocabulary_gaps(snap: dict) -> dict:
    from pipeline.seed import load_index

    seed = load_index()
    seeded = set()
    for bucket in ("agent", "place", "genre", "subject"):
        seeded.update(seed.get(bucket) or {})
    for mon in seed.get("monument") or []:
        for lab in mon.get("labels") or []:
            seeded.add(_norm_label(lab))
        if mon.get("text"):
            seeded.add(_norm_label(mon["text"]))
    kind_map = {
        "persname": "agent",
        "corpname": "agent",
        "famname": "agent",
        "name": "agent",
        "geogname": "place",
        "genreform": "genre",
        "subject": "subject",
        "title": "subject",
    }
    unseeded = Counter()
    with_uri = 0
    without_uri = 0
    examples = {}
    for rec in snap.get("named_pool") or []:
        label = rec.get("text") or ""
        n = _norm_label(label)
        if rec.get("uri"):
            with_uri += 1
        else:
            without_uri += 1
        if n and n not in seeded:
            key = (kind_map.get(rec.get("element"), "other"), n)
            unseeded[key] += 1
            examples.setdefault(key, rec)
    top = [
        {
            "kind": kind,
            "label": label,
            "occurrences": count,
            "example_component": (examples.get((kind, label)) or {}).get("component"),
            "example_uri": (examples.get((kind, label)) or {}).get("uri"),
        }
        for (kind, label), count in unseeded.most_common(SAMPLE)
    ]
    return {
        "named_mentions": len(snap.get("named_pool") or []),
        "named_with_uri": with_uri,
        "named_without_uri": without_uri,
        "unseeded_label_types": len(unseeded),
        "unseeded_top": top,
        "seed_agents": len(seed.get("agent") or {}),
        "seed_places": len(seed.get("place") or {}),
        "seed_genres": len(seed.get("genre") or {}),
        "seed_subjects": len(seed.get("subject") or {}),
    }


def fetch_url(url: str, user_agent: str, timeout: int = 60) -> tuple[int, bytes, str]:
    req = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/xml, text/xml, */*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        ctype = resp.headers.get("Content-Type") or ""
        return resp.status, body, ctype


def looks_like_ead(body: bytes) -> bool:
    head = body[:4000].lstrip().lower()
    return b"<ead" in head or b"urn:isbn:1-931666-22-9" in head


def fetch_remote_ead(
    eadid: str,
    sources: dict,
    refresh: bool = False,
    timeout: int = 90,
) -> dict:
    """Download published EAD XML if reachable; cache under vocab/cache/ead-remote/."""
    row = (sources.get("by_id") or {}).get(eadid) or {}
    urls = list(row.get("xml_urls") or default_xml_urls(eadid))
    ua = sources.get("user_agent") or USER_AGENT
    REMOTE_EAD_CACHE.mkdir(parents=True, exist_ok=True)
    dest = REMOTE_EAD_CACHE / f"{eadid}-ead.xml"
    meta_path = REMOTE_EAD_CACHE / f"{eadid}.json"
    if dest.exists() and not refresh:
        body = dest.read_bytes()
        meta = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "status": "cache",
            "path": str(dest),
            "url": meta.get("url"),
            "sha256": _sha256(body),
            "bytes": len(body),
            "cached": True,
        }
    errors = []
    for url in urls:
        try:
            status, body, ctype = fetch_url(url, ua, timeout=timeout)
        except HTTPError as exc:
            errors.append({"url": url, "error": f"HTTP {exc.code}"})
            continue
        except (URLError, TimeoutError, OSError) as exc:
            errors.append({"url": url, "error": str(exc)})
            continue
        if status >= 400 or not looks_like_ead(body):
            errors.append(
                {
                    "url": url,
                    "error": f"status {status} content-type {ctype} not EAD",
                }
            )
            continue
        digest = _sha256(body)
        dest.write_bytes(body)
        meta = {
            "eadid": eadid,
            "url": url,
            "sha256": digest,
            "bytes": len(body),
            "fetched": _now(),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return {
            "status": "fetched",
            "path": str(dest),
            "url": url,
            "sha256": digest,
            "bytes": len(body),
            "cached": False,
            "attempts": errors,
        }
    return {"status": "unavailable", "path": None, "attempts": errors}


def file_digest(path: Path) -> str:
    return _sha256(path.read_bytes())


def analyze_collection(
    eadid: str,
    sources: dict,
    live_ead: bool = False,
    refresh: bool = False,
) -> dict:
    local = local_path_for(eadid, sources)
    data = parse_ead(local)
    snap = ead_snapshot(data)
    write_report(snap["inventory"])
    rdf = scan_rdf_dir(eadid)
    rdf_cmp = compare_ead_rdf(snap, rdf)
    vocab = vocabulary_gaps(snap)
    remote = {"status": "skipped", "live": False}
    remote_cmp = None
    if live_ead:
        remote = fetch_remote_ead(eadid, sources, refresh=refresh)
        remote["live"] = True
        if remote.get("path"):
            rdata = parse_ead(remote["path"])
            rsnap = ead_snapshot(rdata)
            remote_cmp = compare_ead_trees(snap, rsnap)
            remote["eadid"] = rsnap.get("eadid")
            remote["title"] = rsnap.get("title")
            remote["components"] = rsnap["inventory"]["components"]
            remote["digitized_components"] = rsnap["inventory"]["digitized_components"]
            remote["local_sha256"] = file_digest(local)
            remote["same_bytes"] = remote.get("sha256") == remote["local_sha256"]
    row = (sources.get("by_id") or {}).get(eadid) or {}
    return {
        "eadid": eadid,
        "title": snap.get("title"),
        "label": row.get("label"),
        "sova": row.get("sova"),
        "ark": row.get("ark") or (snap.get("header") or {}).get("eadid_url"),
        "local": str(local.relative_to(ROOT)).replace("\\", "/"),
        "local_sha256": file_digest(local),
        "header": snap.get("header"),
        "inventory": {
            k: snap["inventory"][k]
            for k in snap["inventory"]
            if k not in {"header", "written"}
        },
        "rdf": {
            "dir": rdf["dir"],
            "mapped": rdf["mapped"],
            "stub_in_parent": rdf["stub_in_parent"],
            "file_count": rdf["file_count"],
            "files": rdf["files"],
            "components": len(rdf["component_locals"]),
            "digital_objects": len(rdf["digital_locals"]),
            "d1_mentions": rdf["d1_mentions"],
        },
        "compare_rdf": rdf_cmp,
        "vocabulary": vocab,
        "remote": remote,
        "compare_remote": remote_cmp,
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# EAD / RDF collection analysis",
        "",
        f"Generated `{summary.get('generated')}`.",
        "",
        "Offline by default. `--live-ead` fetches published SOVA XML and diffs it against `srcdata/`.",
        "Reports are rewritten in full each run (idempotent: same inputs → same counts).",
        "",
    ]
    for coll in summary.get("collections") or []:
        inv = coll.get("inventory") or {}
        rdf = coll.get("rdf") or {}
        cmp = coll.get("compare_rdf") or {}
        vocab = coll.get("vocabulary") or {}
        remote = coll.get("remote") or {}
        lines += [
            f"## {coll.get('eadid')} — {coll.get('title') or coll.get('label') or ''}",
            "",
            f"- Local: `{coll.get('local')}`",
            f"- SOVA: {coll.get('sova') or '—'}",
            f"- Mapped RDF: `{rdf.get('dir')}` ({'yes' if rdf.get('mapped') else 'stub / unmapped'})",
            f"- Components: **{inv.get('components')}** "
            f"(digitized **{inv.get('digitized_components')}**, "
            f"undigitized **{inv.get('undigitized_components')}**)",
            f"- Levels: `{inv.get('levels')}`",
            f"- DAO kinds: `{cmp.get('dao_kinds')}`",
            f"- Distinct boxes: {inv.get('distinct_boxes')}; folder mentions: {inv.get('folder_mentions')}",
            f"- RDF components / D1 locals: {rdf.get('components')} / {rdf.get('digital_objects')}",
            f"- EAD components missing from RDF: **{(cmp.get('components_in_ead_missing_from_rdf') or {}).get('count')}**",
            f"- Digitized components without a harvested D1: **{(cmp.get('digitized_components_without_d1') or {}).get('count')}**",
            f"- Named mentions with URI / without: {vocab.get('named_with_uri')} / {vocab.get('named_without_uri')}",
            f"- Unseeded label types (candidates for `vocab/seed.yml`): **{vocab.get('unseeded_label_types')}**",
            f"- Live XML: `{remote.get('status')}`",
            "",
        ]
        series = inv.get("series") or []
        if series:
            lines.append("| Series | Title | Children | Digitized |")
            lines.append("| --- | --- | ---: | --- |")
            for s in series:
                lines.append(
                    f"| `{s.get('id')}` | {s.get('title') or ''} | {s.get('children')} | {s.get('digitized')} |"
                )
            lines.append("")
        top = vocab.get("unseeded_top") or []
        if top:
            lines.append("Unseeded labels (top):")
            lines.append("")
            for row in top[:15]:
                lines.append(
                    f"- `{row.get('kind')}` **{row.get('label')}** ×{row.get('occurrences')} "
                    f"(e.g. `{row.get('example_component')}`)"
                )
            lines.append("")
        rcmp = coll.get("compare_remote")
        if rcmp:
            lines += [
                "Live XML vs local:",
                "",
                f"- Added components: {rcmp['added_components']['count']}",
                f"- Removed components: {rcmp['removed_components']['count']}",
                f"- Changed components: {rcmp['changed_components']['count']}",
                f"- New DAO hrefs: {rcmp['new_dao_hrefs']['count']}",
                f"- Finding-aid creation date changed: {rcmp.get('creation_changed')}",
                "",
            ]
    return "\n".join(lines) + "\n"


def run(
    path=None,
    live_ead: bool = False,
    refresh: bool = False,
) -> dict:
    sources = load_sources()
    if path:
        data = parse_ead(path)
        eadids = [data["header"].get("eadid") or Path(path).name.replace("-ead.xml", "")]
        if eadids[0] not in (sources.get("by_id") or {}):
            sources.setdefault("by_id", {})[eadids[0]] = {
                "eadid": eadids[0],
                "path": Path(path),
                "xml_urls": default_xml_urls(eadids[0]),
            }
        else:
            sources["by_id"][eadids[0]]["path"] = Path(path)
    else:
        eadids = [row["eadid"] for row in sources.get("collections") or []]
        if not eadids:
            eadids = [DEFAULT_EADID]
    collections = []
    for eadid in eadids:
        collections.append(
            analyze_collection(eadid, sources, live_ead=live_ead, refresh=refresh)
        )
    summary = {
        "generated": _now(),
        "live_ead": live_ead,
        "collections": collections,
        "totals": {
            "collections": len(collections),
            "components": sum((c.get("inventory") or {}).get("components") or 0 for c in collections),
            "digitized": sum(
                (c.get("inventory") or {}).get("digitized_components") or 0 for c in collections
            ),
            "unmapped": [c["eadid"] for c in collections if not (c.get("rdf") or {}).get("mapped")],
        },
    }
    ANALYZE_DIR.mkdir(parents=True, exist_ok=True)
    (ANALYZE_DIR / "summary.json").write_text(
        json.dumps(_jsonable(summary), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for coll in collections:
        dest = ANALYZE_DIR / f"{collection_slug(coll['eadid'])}.json"
        dest.write_text(json.dumps(_jsonable(coll), indent=2, ensure_ascii=False), encoding="utf-8")
    md = render_markdown(summary)
    (ANALYZE_DIR / "report.md").write_text(md, encoding="utf-8")
    summary["written"] = {
        "summary": str((ANALYZE_DIR / "summary.json").relative_to(ROOT)).replace("\\", "/"),
        "report": str((ANALYZE_DIR / "report.md").relative_to(ROOT)).replace("\\", "/"),
    }
    return summary


def _jsonable(obj):
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_jsonable(v) for v in obj)
    return obj


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze local/live EAD XML against harvested RDF (idempotent reports)."
    )
    parser.add_argument("--ead", default=None, help="Limit to one finding aid XML path")
    parser.add_argument(
        "--live-ead",
        action="store_true",
        help="Fetch published SOVA EAD XML and diff against srcdata/",
    )
    parser.add_argument(
        "--refresh-ead",
        action="store_true",
        help="Re-download cached remote EAD even if a copy exists",
    )
    args = parser.parse_args(argv)
    summary = run(path=args.ead, live_ead=args.live_ead, refresh=args.refresh_ead)
    print(json.dumps(summary.get("written"), indent=2))
    print(f"collections: {summary['totals']['collections']}")
    for coll in summary["collections"]:
        inv = coll["inventory"]
        cmp = coll["compare_rdf"]
        print(
            f"  {coll['eadid']}: components={inv['components']} "
            f"digitized={inv['digitized_components']} "
            f"mapped={coll['rdf']['mapped']} "
            f"missing_from_rdf={cmp['components_in_ead_missing_from_rdf']['count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
