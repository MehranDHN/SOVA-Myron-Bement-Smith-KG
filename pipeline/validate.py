"""SHACL validation of generated RDF against shapes/mbs.shacl.ttl."""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import Graph

from pipeline.namespaces import PREFIXES
from pipeline.paths import ONTOLOGY, RDF_DIR, REPORTS_DIR, SHAPES


def load_data() -> Graph:
    g = Graph()
    for pfx, ns in PREFIXES.items():
        g.bind(pfx, ns)
    if ONTOLOGY.exists():
        g.parse(ONTOLOGY, format="turtle")
    for ttl in sorted(RDF_DIR.glob("*.ttl")):
        g.parse(ttl, format="turtle")
    return g


def run() -> dict:
    try:
        from pyshacl import validate
    except ImportError:
        return {"ok": False, "error": "pyshacl is not installed"}
    data = load_data()
    shapes = Graph().parse(SHAPES, format="turtle")
    conforms, report_graph, report_text = validate(
        data_graph=data,
        shacl_graph=shapes,
        inference="rdfs",
        abort_on_first=False,
    )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "shacl-report.txt").write_text(report_text, encoding="utf-8")
    report_graph.serialize(REPORTS_DIR / "shacl-report.ttl", format="turtle")
    return {"ok": bool(conforms), "triples": len(data), "report": str(REPORTS_DIR / "shacl-report.txt")}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
