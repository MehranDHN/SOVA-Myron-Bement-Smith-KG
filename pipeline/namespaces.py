"""RDF namespaces used across the knowledge graph.

Instance resources live in the hash namespace ``kg:`` so Turtle serializes
prefixed names (``kg:event_digitization_fs_fsa_a_04``) rather than full IRIs.
Local names use underscore separators; hyphens are not used in kg: or mbs: IRIs.
"""

from __future__ import annotations

import re

from rdflib import Namespace, URIRef

BASE = "https://w3id.org/sova/fsa_a_04/"
# Hash namespace must be BASE without the trailing slash, otherwise rdflib
# binds kg: to https://w3id.org/sova/fsa_a_04/# (extra slash).
KG = Namespace("https://w3id.org/sova/fsa_a_04#")
MBS = Namespace(BASE + "ontology#")
CRM = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
CRMDIG = Namespace("http://www.ics.forth.gr/isl/CRMdig/")
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
DCT = Namespace("http://purl.org/dc/terms/")
PROV = Namespace("http://www.w3.org/ns/prov#")
WD = Namespace("http://www.wikidata.org/entity/")
AAT = Namespace("http://vocab.getty.edu/aat/")
TGN = Namespace("http://vocab.getty.edu/tgn/")
LCSH = Namespace("http://id.loc.gov/authorities/subjects/")
LCNAF = Namespace("http://id.loc.gov/authorities/names/")
LANG = Namespace("http://id.loc.gov/vocabulary/iso639-2/")
LA = Namespace("https://linked.art/ns/terms/")
RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")

PREFIXES = {
    "kg": KG,
    "mbs": MBS,
    "crm": CRM,
    "crmdig": CRMDIG,
    "skos": SKOS,
    "dct": DCT,
    "prov": PROV,
    "wd": WD,
    "aat": AAT,
    "tgn": TGN,
    "lcsh": LCSH,
    "lcnaf": LCNAF,
    "lang": LANG,
    "la": LA,
    "rico": RICO,
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._]+")


def kg_name(*parts: str) -> str:
    """Build a Turtle-safe local name using underscores (no hyphens)."""
    chunks = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip().replace("-", "_").replace("/", "_").replace(" ", "_")
        text = _UNSAFE.sub("_", text)
        text = re.sub(r"_{2,}", "_", text).strip("._")
        if text:
            chunks.append(text)
    name = "_".join(chunks) or "unnamed"
    if not re.match(r"[A-Za-z_]", name[0]):
        name = "n_" + name
    return name


def kg_uri(*parts: str) -> URIRef:
    return KG[kg_name(*parts)]
