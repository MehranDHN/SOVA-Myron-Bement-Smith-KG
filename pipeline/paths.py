"""Project paths."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRCDATA_DIR = ROOT / "srcdata"
DEFAULT_EADID = "FSA.A.04"
SRCDATA = SRCDATA_DIR / "FSA.A.04-ead.xml"
SRCDATA_A06 = SRCDATA_DIR / "FSA.A.06-ead.xml"
ONTOLOGY = ROOT / "ontology" / "mbs.ttl"
CATALOG = ROOT / "ontology" / "catalog.ttl"
MAPPINGS = ROOT / "mappings" / "ead-to-crm.yml"
SEED_VOCAB = ROOT / "vocab" / "seed.yml"
CACHE_DIR = ROOT / "vocab" / "cache"
DATA_DIR = ROOT / "data"
RDF_DIR = DATA_DIR / "rdf"
REPORTS_DIR = DATA_DIR / "reports"
IIIF_PAGES = DATA_DIR / "iiif-pages.yml"
SHAPES = ROOT / "shapes" / "mbs.shacl.ttl"
QUERIES = ROOT / "queries"


def ead_path(eadid: str | None = None) -> Path:
    """Finding-aid XML for an ArchivesSpace identifier such as FSA.A.04."""
    return SRCDATA_DIR / f"{eadid or DEFAULT_EADID}-ead.xml"


def rdf_dir_for(eadid: str | None = None) -> Path:
    """RDF output directory. FSA.A.04 stays at data/rdf/; siblings get a slug subfolder."""
    ident = eadid or DEFAULT_EADID
    if ident == DEFAULT_EADID:
        return RDF_DIR
    from pipeline.namespaces import collection_slug

    return RDF_DIR / collection_slug(ident).lower()
