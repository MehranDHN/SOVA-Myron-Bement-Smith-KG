"""Shared Islamic Archives control vocabulary (vocab/seed.yml).

Manual, high-confidence terms used by every sub-collection (FSA.A.04,
FSA.A.06, …). Loading and emitting the seed is idempotent: the same id
or label always mints the same kg: URI and the same SKOS triples.

SKOS usage
----------
Intra-scheme (links among kg: concepts in this seed):

* ``broader`` / ``narrower`` — hierarchy inside this scheme
* ``related`` — associative link inside this scheme

Cross-scheme mapping (links to AAT, TGN, LCSH, LCNAF, Wikidata, Iconclass):

* ``exactMatch`` — same meaning in another scheme
* ``closeMatch`` — nearly the same; not identity
* ``broadMatch`` — this concept is narrower than an *external* concept
  (use this, not ``broader``, when the parent lives only in AAT/LCSH/…)
* ``narrowMatch`` — this concept is broader than an external concept
* ``relatedMatch`` — associative mapping to an external concept

``skos:broader`` and ``skos:broadMatch`` are not interchangeable.
``broader`` stays inside kg:; ``broadMatch`` points at another vocabulary.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from pipeline.namespaces import (
    AAT,
    CRM,
    ICONCLASS,
    LCNAF,
    LCSH,
    MBS,
    TGN,
    WD,
    bind_graph,
    kg_name,
    kg_uri,
)
from pipeline.paths import CACHE_DIR, RDF_DIR, SEED_VOCAB
from pipeline.util import slugify

AUTHORITY_IRI = {
    "aat": lambda i: str(AAT[str(i)]),
    "tgn": lambda i: str(TGN[str(i)]),
    "lcsh": lambda i: f"https://id.loc.gov/authorities/subjects/{i}",
    "lcnaf": lambda i: f"https://id.loc.gov/authorities/names/{i}",
    "wikidata": lambda i: str(WD[_qid(i)]),
    "iconclass": lambda i: str(ICONCLASS[str(i).lstrip("/")]),
    "uri": lambda i: str(i),
}

# YAML keys → SKOS mapping property (external vocabularies)
MAPPING_ALIASES = {
    "exact": "exactMatch",
    "exactmatch": "exactMatch",
    "exact_match": "exactMatch",
    "close": "closeMatch",
    "closematch": "closeMatch",
    "close_match": "closeMatch",
    "broadmatch": "broadMatch",
    "broad_match": "broadMatch",
    "broadermatch": "broadMatch",
    "broader_match": "broadMatch",
    "narrowmatch": "narrowMatch",
    "narrow_match": "narrowMatch",
    "relatedmatch": "relatedMatch",
    "related_match": "relatedMatch",
}

# YAML keys → SKOS semantic relation (local seed ids / labels)
INTRA_ALIASES = {
    "broader": "broader",
    "broader_local": "broader",
    "narrower": "narrower",
    "related": "related",
    "related_local": "related",
}

SKOS_MAP_PROP = {
    "exactMatch": SKOS.exactMatch,
    "closeMatch": SKOS.closeMatch,
    "broadMatch": SKOS.broadMatch,
    "narrowMatch": SKOS.narrowMatch,
    "relatedMatch": SKOS.relatedMatch,
}

SKOS_INTRA_PROP = {
    "broader": SKOS.broader,
    "narrower": SKOS.narrower,
    "related": SKOS.related,
}

KIND_SECTIONS = (
    ("agents", "agent"),
    ("places", "place"),
    ("genres", "genre"),
    ("subjects", "subject"),
    ("monuments", "monument"),
    ("concepts", "concept"),
)


def _qid(value: str) -> str:
    text = str(value).strip()
    if text.startswith("http"):
        return text.rsplit("/", 1)[-1]
    if not text.startswith("Q"):
        return "Q" + text
    return text


def _norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ʿ", "").replace("'", "'")
    return s


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _expand_authority(scheme: str, value) -> list[str]:
    fn = AUTHORITY_IRI.get(scheme)
    if not fn:
        return []
    out = []
    for item in _as_list(value):
        if item is None or item == "":
            continue
        text = str(item).strip()
        if text.startswith("http://") or text.startswith("https://"):
            out.append(text)
        else:
            out.append(fn(text))
    return out


def _merge_mapping(dst: dict, src: dict):
    for key, vals in src.items():
        bucket = dst.setdefault(key, [])
        for v in vals:
            if v not in bucket:
                bucket.append(v)


def _merge_entry(dst: dict, src: dict) -> dict:
    """Union lists and fill empty scalars. Later rows do not clobber ids."""
    if not dst.get("id") and src.get("id"):
        dst["id"] = src["id"]
    if src.get("kind") and dst.get("kind") in {None, "concept"}:
        dst["kind"] = src["kind"]
    for lab in src.get("labels") or []:
        if lab not in dst["labels"]:
            dst["labels"].append(lab)
    if src.get("prefLabel") and not dst.get("prefLabel"):
        dst["prefLabel"] = src["prefLabel"]
    if src.get("note") and not dst.get("note"):
        dst["note"] = src["note"]
    _merge_mapping(dst["mapping"], src.get("mapping") or {})
    for rel, ids in (src.get("intra") or {}).items():
        bucket = dst["intra"].setdefault(rel, [])
        for i in ids:
            if i not in bucket:
                bucket.append(i)
    for c in src.get("collections") or []:
        if c not in dst["collections"]:
            dst["collections"].append(c)
    return dst


def _mapping_from_row(row: dict) -> dict:
    mapping = {k: [] for k in SKOS_MAP_PROP}
    # Shorthand top-level authority ids are exactMatch.
    for scheme in AUTHORITY_IRI:
        if scheme in row and scheme not in MAPPING_ALIASES and scheme not in INTRA_ALIASES:
            mapping["exactMatch"].extend(_expand_authority(scheme, row[scheme]))
    # Nested mapping blocks: exact: {aat: "…", iconclass: "11Q71"}
    for raw_key, values in row.items():
        canon = MAPPING_ALIASES.get(raw_key.lower().replace("-", "_"))
        if not canon:
            continue
        if isinstance(values, dict):
            for scheme, val in values.items():
                mapping[canon].extend(_expand_authority(scheme, val))
        else:
            mapping[canon].extend(_expand_authority("uri", values))
    # Legacy AAT hierarchy keys were used as if they were intra-scheme.
    # They name *external* AAT concepts, so they are mapping properties.
    if row.get("aat_broader"):
        mapping["broadMatch"].extend(_expand_authority("aat", row["aat_broader"]))
    if row.get("aat_related"):
        mapping["relatedMatch"].extend(_expand_authority("aat", row["aat_related"]))
    if row.get("tgn_place"):
        mapping["exactMatch"].extend(_expand_authority("tgn", row["tgn_place"]))
    return {k: v for k, v in mapping.items() if v}


def _intra_from_row(row: dict) -> dict:
    intra = {k: [] for k in SKOS_INTRA_PROP}
    for raw_key, values in row.items():
        canon = INTRA_ALIASES.get(raw_key.lower().replace("-", "_"))
        if not canon:
            continue
        if isinstance(values, dict):
            # related: {id: glass_negatives} is not used; skip authority-shaped dicts
            continue
        for item in _as_list(values):
            text = str(item).strip()
            if text:
                intra[canon].append(text)
    return {k: v for k, v in intra.items() if v}


def _labels_of(row: dict) -> list[str]:
    labels = []
    for key in ("prefLabel", "label"):
        if row.get(key):
            labels.append(str(row[key]).strip())
    for lab in _as_list(row.get("altLabels") or row.get("labels")):
        if lab:
            labels.append(str(lab).strip())
    seen = set()
    out = []
    for lab in labels:
        n = _norm(lab)
        if n and n not in seen:
            seen.add(n)
            out.append(lab)
    return out


def _new_entry(kind: str, row: dict) -> dict:
    labels = _labels_of(row)
    pref = row.get("prefLabel") or row.get("label") or (labels[0] if labels else "")
    ident = row.get("id") or None
    if ident:
        ident = kg_name(str(ident))
    return {
        "id": ident,
        "kind": kind,
        "prefLabel": pref,
        "labels": labels,
        "note": row.get("note") or row.get("definition"),
        "mapping": _mapping_from_row(row),
        "intra": _intra_from_row(row),
        "collections": [str(c) for c in _as_list(row.get("collections"))],
        "raw": row,
    }


def parse_seed(path=None) -> dict:
    """Load seed.yml, merge duplicate ids/labels, return a canonical vocab."""
    path = Path(path) if path else SEED_VOCAB
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    scheme = raw.get("scheme") or {}
    scheme.setdefault("id", "islamic_archives")
    scheme.setdefault("prefLabel", "Islamic Archives control vocabulary")

    by_id = {}
    by_label = {}
    by_exact = {}
    order = []

    def ingest(kind: str, row: dict):
        if not row:
            return
        entry = _new_entry(kind, row)
        existing = None
        if entry["id"] and entry["id"] in by_id:
            existing = by_id[entry["id"]]
        if existing is None:
            for lab in entry["labels"]:
                hit = by_label.get(_norm(lab))
                if hit:
                    existing = hit
                    break
        if existing is None:
            for iri in (entry.get("mapping") or {}).get("exactMatch") or []:
                hit = by_exact.get((kind, iri))
                if hit:
                    existing = hit
                    break
        if existing is None:
            order.append(entry)
            existing = entry
        else:
            _merge_entry(existing, entry)
        if existing.get("id"):
            by_id[existing["id"]] = existing
        for lab in existing["labels"]:
            by_label[_norm(lab)] = existing
        for iri in (existing.get("mapping") or {}).get("exactMatch") or []:
            by_exact[(existing["kind"], iri)] = existing

    for section, kind in KIND_SECTIONS:
        for row in raw.get(section) or []:
            ingest(kind, row)

    for entry in order:
        if not entry.get("id"):
            entry["id"] = kg_name(entry.get("prefLabel") or "concept")
            by_id.setdefault(entry["id"], entry)
        entry["uri"] = mint_uri(entry)

    # Resolve intra-scheme ids/labels to URIs.
    def resolve(ref: str) -> URIRef | None:
        key = kg_name(ref) if re.match(r"^[A-Za-z0-9._:\-]+$", ref) and " " not in ref else None
        if key and key in by_id:
            return by_id[key]["uri"]
        hit = by_label.get(_norm(ref))
        if hit:
            return hit["uri"]
        if key and key in by_id:
            return by_id[key]["uri"]
        # already a slug id
        if ref in by_id:
            return by_id[ref]["uri"]
        slug = kg_name(ref)
        if slug in by_id:
            return by_id[slug]["uri"]
        return None

    for entry in order:
        resolved = {}
        for rel, refs in entry["intra"].items():
            uris = []
            for ref in refs:
                uri = resolve(ref)
                if uri is not None and uri not in uris:
                    uris.append(uri)
            if uris:
                resolved[rel] = uris
        entry["intra_uris"] = resolved

    return {"scheme": scheme, "entries": order, "by_id": by_id, "by_label": by_label}


def mint_uri(entry: dict) -> URIRef:
    """Stable kg: URI. Authority ids win so EAD reconcile merges onto the same node."""
    kind = entry.get("kind") or "concept"
    mapping = entry.get("mapping") or {}
    exact = mapping.get("exactMatch") or []

    def first(scheme: str) -> str | None:
        prefixes = {
            "wikidata": ("http://www.wikidata.org/entity/",),
            "tgn": ("http://vocab.getty.edu/tgn/",),
            "aat": ("http://vocab.getty.edu/aat/",),
            "lcsh": (
                "https://id.loc.gov/authorities/subjects/",
                "http://id.loc.gov/authorities/subjects/",
            ),
            "lcnaf": (
                "https://id.loc.gov/authorities/names/",
                "http://id.loc.gov/authorities/names/",
            ),
        }[scheme]
        for iri in exact:
            for prefix in prefixes:
                if iri.startswith(prefix):
                    return iri.rstrip("/").rsplit("/", 1)[-1]
        return None

    if kind == "agent":
        qid = first("wikidata")
        if qid:
            return kg_uri("agent", qid)
        return kg_uri("agent", entry.get("id") or slugify(entry.get("prefLabel") or "agent"))
    if kind == "place":
        tid = first("tgn")
        if tid:
            return kg_uri("place", "tgn", tid)
        return kg_uri("place", entry.get("id") or slugify(entry.get("prefLabel") or "place"))
    if kind == "monument":
        qid = first("wikidata")
        if qid:
            return kg_uri("built", qid)
        return kg_uri("built", entry.get("id") or slugify(entry.get("prefLabel") or "monument"))
    aid = first("aat")
    if aid:
        return kg_uri("concept", "aat", aid)
    lid = first("lcsh")
    if lid:
        return kg_uri("concept", "lcsh", lid)
    return kg_uri("concept", entry.get("id") or slugify(entry.get("prefLabel") or "concept"))


def load_index(path=None) -> dict:
    """Label index compatible with pipeline.reconcile (agents/places/genres/…)."""
    vocab = parse_seed(path)
    index = {"agent": {}, "place": {}, "genre": {}, "subject": {}, "monument": [], "concept": {}}
    for entry in vocab["entries"]:
        kind = entry["kind"]
        rec = _reconcile_view(entry)
        if kind == "monument":
            index["monument"].append(rec)
        bucket = {
            "agent": "agent",
            "place": "place",
            "genre": "genre",
            "subject": "subject",
            "concept": "concept",
        }.get(kind)
        if bucket:
            for lab in entry["labels"]:
                index[bucket][_norm(lab)] = rec
    index["_vocab"] = vocab
    return index


def _reconcile_view(entry: dict) -> dict:
    """Flatten mapping IRIs into the matches dict reconcile/map already consume."""
    exact = entry.get("mapping", {}).get("exactMatch") or []
    matches = {}
    for iri in exact:
        if "wikidata.org" in iri:
            matches["wikidata"] = iri
        elif "/aat/" in iri:
            matches.setdefault("aat", iri)
        elif "/tgn/" in iri:
            matches["tgn"] = iri
        elif "/subjects/" in iri:
            matches.setdefault("lcsh", iri)
        elif "/names/" in iri:
            matches["lcnaf"] = iri
        elif "iconclass.org" in iri:
            matches.setdefault("iconclass", iri)
    mapping = entry.get("mapping") or {}
    if mapping.get("broadMatch"):
        matches["broadMatch"] = list(mapping["broadMatch"])
    if mapping.get("relatedMatch"):
        matches["relatedMatch"] = list(mapping["relatedMatch"])
    if mapping.get("closeMatch"):
        matches["closeMatch"] = list(mapping["closeMatch"])
    if mapping.get("narrowMatch"):
        matches["narrowMatch"] = list(mapping["narrowMatch"])
    rec = {
        "id": entry.get("id"),
        "label": entry.get("prefLabel"),
        "labels": list(entry.get("labels") or []),
        "kind": entry.get("kind"),
        "note": entry.get("note"),
        "matches": matches,
        "seed_id": entry.get("id"),
        "seed_uri": str(entry.get("uri") or ""),
        "intra_uris": {k: [str(u) for u in v] for k, v in (entry.get("intra_uris") or {}).items()},
        "skos": {
            "mapping": {k: list(v) for k, v in (entry.get("mapping") or {}).items()},
            "intra": {k: [str(u) for u in v] for k, v in (entry.get("intra_uris") or {}).items()},
        },
    }
    # Compat keys still read by older emit_concept paths.
    if matches.get("aat"):
        rec["aat"] = matches["aat"].rsplit("/", 1)[-1]
    if matches.get("wikidata"):
        rec["wikidata"] = matches["wikidata"].rsplit("/", 1)[-1]
    if matches.get("tgn"):
        rec["tgn"] = matches["tgn"].rsplit("/", 1)[-1]
    if matches.get("lcsh"):
        rec["lcsh"] = matches["lcsh"].rsplit("/", 1)[-1]
    if matches.get("lcnaf"):
        rec["lcnaf"] = matches["lcnaf"].rsplit("/", 1)[-1]
    rec["label"] = entry.get("prefLabel")
    rec["labels"] = list(entry.get("labels") or [])
    rec["note"] = entry.get("note")
    rec["tgn_place"] = (matches.get("tgn") or "").rsplit("/", 1)[-1] or None
    return rec


def uris_from_seed_row(row: dict) -> dict:
    """Build the legacy matches dict from a raw YAML row or a reconcile view."""
    if row.get("matches") and row.get("seed_id"):
        return dict(row["matches"])
    entry = _new_entry(row.get("kind") or "concept", row)
    return _reconcile_view(entry)["matches"]


def apply_skos(g: Graph, subject: URIRef, rec: dict):
    """Assert SKOS mapping and intra-scheme relations from a seed/reconcile record."""
    skos = rec.get("skos") or {}
    mapping = skos.get("mapping") or {}
    if not mapping and rec.get("matches"):
        mapping = {}
        m = rec["matches"]
        if m.get("aat"):
            mapping.setdefault("exactMatch", []).append(m["aat"])
        if m.get("lcsh"):
            mapping.setdefault("exactMatch", []).append(m["lcsh"])
        if m.get("iconclass"):
            mapping.setdefault("exactMatch", []).append(m["iconclass"])
        if m.get("wikidata") and rec.get("kind") in {"genre", "subject", "concept", "monument"}:
            mapping.setdefault("exactMatch", []).append(m["wikidata"])
        for key in ("broadMatch", "relatedMatch", "closeMatch", "narrowMatch"):
            if m.get(key):
                mapping[key] = list(_as_list(m[key]))
        # Legacy
        if m.get("aat_broader"):
            mapping.setdefault("broadMatch", []).append(m["aat_broader"])
        if m.get("aat_related"):
            mapping.setdefault("relatedMatch", []).extend(_as_list(m["aat_related"]))
    for prop, iris in mapping.items():
        pred = SKOS_MAP_PROP.get(prop)
        if not pred:
            continue
        for iri in iris:
            g.add((subject, pred, URIRef(iri)))
    intra = skos.get("intra") or rec.get("intra_uris") or {}
    for prop, iris in intra.items():
        pred = SKOS_INTRA_PROP.get(prop)
        if not pred:
            continue
        for iri in iris:
            g.add((subject, pred, URIRef(iri)))
            if prop == "broader":
                g.add((URIRef(iri), SKOS.narrower, subject))
            elif prop == "narrower":
                g.add((URIRef(iri), SKOS.broader, subject))
            elif prop == "related":
                g.add((URIRef(iri), SKOS.related, subject))


def scheme_uri(scheme: dict) -> URIRef:
    return kg_uri("scheme", scheme.get("id") or "islamic_archives")


def emit_vocabulary(g: Graph, vocab=None) -> dict:
    """Write every seed concept into ``g``. Safe to call twice (RDF set semantics)."""
    vocab = vocab or parse_seed()
    scheme = vocab["scheme"]
    sch = scheme_uri(scheme)
    g.add((sch, RDF.type, SKOS.ConceptScheme))
    g.add((sch, RDFS.label, Literal(scheme.get("prefLabel") or "Islamic Archives control vocabulary")))
    g.add((sch, DCTERMS.title, Literal(scheme.get("prefLabel") or "Islamic Archives control vocabulary")))
    if scheme.get("note"):
        g.add((sch, RDFS.comment, Literal(scheme["note"])))
    g.add((sch, DCTERMS.subject, kg_uri("collection", "islamic_archives")))
    g.add((sch, MBS.usedByCollection, kg_uri("component", "FSA.A.04")))
    g.add((sch, MBS.usedByCollection, kg_uri("component", "FSA.A.06")))

    counts = {"entries": 0, "triples_before": len(g)}
    for entry in vocab["entries"]:
        uri = entry["uri"]
        kind = entry["kind"]
        label = entry.get("prefLabel") or entry["id"]
        if kind == "agent":
            g.add((uri, RDF.type, CRM["E21_Person"]))
        elif kind == "place":
            g.add((uri, RDF.type, CRM["E53_Place"]))
        elif kind == "monument":
            g.add((uri, RDF.type, CRM["E22_Human-Made_Object"]))
            g.add((uri, RDF.type, SKOS.Concept))
        else:
            g.add((uri, RDF.type, CRM["E55_Type"]))
            g.add((uri, RDF.type, SKOS.Concept))
            g.add((uri, SKOS.inScheme, sch))
        g.add((uri, RDFS.label, Literal(label)))
        g.add((uri, SKOS.prefLabel, Literal(label, lang="en")))
        for lab in entry.get("labels") or []:
            if lab != label:
                g.add((uri, SKOS.altLabel, Literal(lab, lang="en")))
        if entry.get("note"):
            g.add((uri, SKOS.definition, Literal(entry["note"])))
            g.add((uri, RDFS.comment, Literal(entry["note"])))
        if entry.get("id"):
            g.add((uri, MBS.seedId, Literal(entry["id"])))
        apply_skos(g, uri, _reconcile_view(entry))
        # Agents and places: owl:sameAs the exact Wikidata / TGN / LCNAF IRI.
        if kind in {"agent", "place"}:
            for iri in (entry.get("mapping") or {}).get("exactMatch") or []:
                if any(s in iri for s in ("wikidata.org", "/tgn/", "/names/")):
                    g.add((uri, OWL.sameAs, URIRef(iri)))
                    g.add((uri, MBS.reconciledTo, URIRef(iri)))
        else:
            exact = (entry.get("mapping") or {}).get("exactMatch") or []
            if exact:
                g.add((uri, MBS.reconciledTo, URIRef(exact[0])))
        counts["entries"] += 1
    counts["triples"] = len(g) - counts.pop("triples_before")
    return counts


def run(path=None) -> dict:
    """Parse seed.yml and write data/rdf/vocabulary.ttl (idempotent)."""
    vocab = parse_seed(path)

    RDF_DIR.mkdir(parents=True, exist_ok=True)
    dest = RDF_DIR / "vocabulary.ttl"
    g = bind_graph(Graph())
    stats = emit_vocabulary(g, vocab)
    g.serialize(dest, format="turtle")
    # Second pass: parse+emit again into a fresh graph and compare.
    g2 = bind_graph(Graph())
    emit_vocabulary(g2, parse_seed(path))
    identical = set(g) == set(g2)
    summary = {
        "path": str(dest),
        "entries": stats["entries"],
        "triples": len(g),
        "idempotent": identical,
        "scheme": vocab["scheme"].get("id"),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "vocabulary-summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
