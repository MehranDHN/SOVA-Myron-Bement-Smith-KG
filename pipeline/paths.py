"""Project paths."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRCDATA = ROOT / "srcdata" / "FSA.A.04-ead.xml"
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
