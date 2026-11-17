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
EAD_SOURCES = DATA_DIR / "ead-sources.yml"
ANALYZE_DIR = REPORTS_DIR / "analyze"
REMOTE_EAD_CACHE = CACHE_DIR / "ead-remote"
SHAPES = ROOT / "shapes" / "mbs.shacl.ttl"
QUERIES = ROOT / "queries"


def inventory_path(eadid: str | None = None) -> Path:
    """Per-collection inventory JSON (``inventory-FSA_A_04.json``)."""
    from pipeline.namespaces import collection_slug

    return REPORTS_DIR / f"inventory-{collection_slug(eadid or DEFAULT_EADID)}.json"


def list_local_eads() -> list[Path]:
    """Finding aids on disk, collection-id order (A.04 before A.06)."""
    files = sorted(SRCDATA_DIR.glob("*-ead.xml"))
    return files


def ead_path(eadid: str | None = None) -> Path:
    """Finding-aid XML for an ArchivesSpace identifier such as FSA.A.04."""
    return SRCDATA_DIR / f"{eadid or DEFAULT_EADID}-ead.xml"


def rdf_dir_for(eadid: str | None = None) -> Path:
    """Per-collection Turtle directory: ``data/rdf/fsa_a_04/``, ``data/rdf/fsa_a_06/``."""
    from pipeline.namespaces import collection_slug

    return RDF_DIR / collection_slug(eadid or DEFAULT_EADID).lower()


def vocabulary_ttl() -> Path:
    """Shared SKOS graph (not sharded by collection)."""
    return RDF_DIR / "vocabulary.ttl"


def iter_rdf_ttls() -> list[Path]:
    """vocabulary.ttl plus every ``data/rdf/<slug>/*.ttl`` shard."""
    files = []
    voc = vocabulary_ttl()
    if voc.exists():
        files.append(voc)
    for sub in sorted(p for p in RDF_DIR.iterdir() if p.is_dir()):
        files.extend(sorted(sub.glob("*.ttl")))
    return files
