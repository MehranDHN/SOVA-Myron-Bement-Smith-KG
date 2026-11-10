"""Reconcile extracted entities against seed vocabularies and embedded URIs.

Live AAT/TGN/LCSH/Wikidata lookups are opt-in (--live) so the default
build is reproducible offline from seed.yml + EAD authfilenumber values.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from pipeline.extract_entities import extract
from pipeline.paths import CACHE_DIR, SEED_VOCAB
from pipeline.ead_parser import normalize_auth_uri


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ʿ", "").replace("'", "'")
    return s


def load_seed() -> dict:
    raw = yaml.safe_load(SEED_VOCAB.read_text(encoding="utf-8"))
    index = {"agent": {}, "place": {}, "genre": {}, "subject": {}, "monument": []}
    for row in raw.get("agents") or []:
        index["agent"][_norm(row["label"])] = row
    for row in raw.get("places") or []:
        index["place"][_norm(row["label"])] = row
    for row in raw.get("genres") or []:
        index["genre"][_norm(row["label"])] = row
    for row in raw.get("subjects") or []:
        index["subject"][_norm(row["label"])] = row
    for row in raw.get("monuments") or []:
        index["monument"].append(row)
    return index


def _uris_from_seed(row: dict) -> dict:
    out = {}
    if row.get("wikidata"):
        out["wikidata"] = f"http://www.wikidata.org/entity/{row['wikidata']}"
    if row.get("aat"):
        out["aat"] = f"http://vocab.getty.edu/aat/{row['aat']}"
    if row.get("aat_broader"):
        out["aat_broader"] = f"http://vocab.getty.edu/aat/{row['aat_broader']}"
    related = row.get("aat_related")
    if related:
        if isinstance(related, str):
            related = [related]
        out["aat_related"] = [f"http://vocab.getty.edu/aat/{r}" for r in related]
    if row.get("tgn"):
        out["tgn"] = f"http://vocab.getty.edu/tgn/{row['tgn']}"
    if row.get("lcsh"):
        out["lcsh"] = f"https://id.loc.gov/authorities/subjects/{row['lcsh']}"
    if row.get("lcnaf"):
        out["lcnaf"] = f"https://id.loc.gov/authorities/names/{row['lcnaf']}"
    return out


def _monument_hit(text: str, monuments: list) -> dict | None:
    t = _norm(text)
    for row in monuments:
        for lab in row.get("labels") or []:
            if _norm(lab) and _norm(lab) in t:
                return row
    return None


def reconcile_record(rec: dict, kind: str, seed: dict) -> dict:
    matches = {}
    method = []
    confidence = 0.0
    if rec.get("uri"):
        matches["source_uri"] = rec["uri"]
        method.append("ead-authfilenumber")
        confidence = 0.95
        if "wikidata.org" in rec["uri"]:
            matches["wikidata"] = rec["uri"]
        elif "vocab.getty.edu/aat" in rec["uri"]:
            matches["aat"] = rec["uri"]
        elif "vocab.getty.edu/tgn" in rec["uri"]:
            matches["tgn"] = rec["uri"]
        elif "authorities/subjects" in rec["uri"]:
            matches["lcsh"] = rec["uri"]
        elif "authorities/names" in rec["uri"]:
            matches["lcnaf"] = rec["uri"]
    label = rec.get("text") or rec.get("normal") or ""
    n = _norm(label)
    bucket = {
        "agents": "agent",
        "places": "place",
        "genres": "genre",
        "subjects": "subject",
    }[kind]
    seed_row = seed[bucket].get(n)
    if seed_row:
        matches.update(_uris_from_seed(seed_row))
        method.append("seed")
        confidence = max(confidence, 0.9)
    if kind in {"places", "subjects"}:
        mon = _monument_hit(label, seed["monument"])
        if mon:
            matches.update(_uris_from_seed(mon))
            if mon.get("tgn_place"):
                matches.setdefault("tgn", f"http://vocab.getty.edu/tgn/{mon['tgn_place']}")
            method.append("seed-monument")
            confidence = max(confidence, 0.85)
            rec["monument"] = True
    rec = dict(rec)
    rec["matches"] = matches
    rec["method"] = method
    rec["confidence"] = confidence
    rec["kind"] = kind[:-1] if kind.endswith("s") else kind
    return rec


def run(path=None, live: bool = False) -> dict:
    entities = extract(path)
    seed = load_seed()
    out = {}
    for kind in ("agents", "places", "subjects", "genres"):
        out[kind] = [reconcile_record(rec, kind, seed) for rec in entities[kind]]
    if live:
        out = _live_enrich(out)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "reconciled.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    summary = {
        kind: {
            "total": len(rows),
            "with_match": sum(1 for r in rows if r.get("matches")),
            "wikidata": sum(1 for r in rows if r.get("matches", {}).get("wikidata")),
            "aat": sum(1 for r in rows if r.get("matches", {}).get("aat")),
            "tgn": sum(1 for r in rows if r.get("matches", {}).get("tgn")),
            "lcsh_or_lcnaf": sum(
                1
                for r in rows
                if r.get("matches", {}).get("lcsh") or r.get("matches", {}).get("lcnaf")
            ),
        }
        for kind, rows in out.items()
    }
    (CACHE_DIR / "reconciliation-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return out


def _live_enrich(out: dict) -> dict:
    """Optional live lookup. Kept conservative: only fills empty matches."""
    try:
        import requests
    except ImportError:
        return out
    session = requests.Session()
    session.headers["User-Agent"] = "SOVA-Myron-Bement-Smith-KG/0.1 (research KG)"
    for rec in out["places"]:
        if rec["matches"].get("tgn") or rec["matches"].get("wikidata"):
            continue
        label = rec.get("text")
        if not label:
            continue
        try:
            query = (
                "SELECT ?s WHERE { ?s a <http://vocab.getty.edu/ontology#Subject> ; "
                "<http://www.w3.org/2004/02/skos/core#prefLabel> "
                '"' + label.replace('"', "") + '"@en . '
                'FILTER(CONTAINS(STR(?s), "/tgn/")) } LIMIT 1'
            )
            r = session.get(
                "https://vocab.getty.edu/sparql.json",
                params={"query": query},
                timeout=20,
            )
            if r.ok:
                bindings = r.json().get("results", {}).get("bindings", [])
                if bindings:
                    rec["matches"]["tgn"] = bindings[0]["s"]["value"]
                    rec["method"].append("getty-sparql")
                    rec["confidence"] = max(rec["confidence"], 0.7)
        except Exception:
            continue
    return out


if __name__ == "__main__":
    run()
    print((CACHE_DIR / "reconciliation-summary.json").read_text(encoding="utf-8"))
