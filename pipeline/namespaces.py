"""RDF namespaces used across the knowledge graph.

Instance resources live in the hash namespace ``kg:`` so Turtle serializes
prefixed names (``kg:event_digitization_fs_fsa_a_04``) rather than full IRIs.
Local names use underscore separators. Dots and hyphens are not used in
``kg:``, ``mbs:``, or the GraphDB-safe CIDOC CRM local names (``crm:``),
because Ontotext GraphDB and SPARQL treat ``.`` as a statement terminator
and ``-`` as minus in prefixed names.
"""

from __future__ import annotations

import re

from rdflib import Namespace, URIRef

BASE = "https://w3id.org/sova/fsa_a_04/"
# Hash namespace must be BASE without the trailing slash, otherwise rdflib
# binds kg: to https://w3id.org/sova/fsa_a_04/# (extra slash).
KG = Namespace("https://w3id.org/sova/fsa_a_04#")
MBS = Namespace(BASE + "ontology#")
CRM_NS = Namespace("http://www.cidoc-crm.org/cidoc-crm/")
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
ICONCLASS = Namespace("https://iconclass.org/")
LA = Namespace("https://linked.art/ns/terms/")
RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")


class SafeLocalNamespace:
    """Namespace whose local names replace ``.`` and ``-`` with ``_``.

    Official CIDOC CRM 7.1.3 IRIs keep the hyphens (for example
    ``E22_Human-Made_Object``). Instance data and this project's Turtle use
    the underscore form; ``ontology/mbs.ttl`` declares ``owl:equivalentClass``
    / ``owl:equivalentProperty`` to the official hyphenated IRIs.
    """

    def __init__(self, ns: Namespace):
        self.ns = ns

    def __getitem__(self, name: str) -> URIRef:
        return self.ns[safe_local(name)]

    def __getattr__(self, name: str) -> URIRef:
        if name.startswith("_") or name == "ns":
            raise AttributeError(name)
        return self[name]


def safe_local(name: str) -> str:
    """Replace ``.`` and ``-`` so prefixed names import into GraphDB."""
    text = (name or "").replace(".", "_").replace("-", "_")
    text = re.sub(r"_{2,}", "_", text).strip("_")
    return text or "unnamed"


CRM = SafeLocalNamespace(CRM_NS)

PREFIXES = {
    "kg": KG,
    "mbs": MBS,
    "crm": CRM_NS,
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
    "iconclass": ICONCLASS,
    "la": LA,
    "rico": RICO,
}


def bind_graph(g):
    """Bind kg/mbs/crm/skos and common prefixes for Turtle output."""
    from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

    g.bind("kg", KG)
    for pfx, ns in PREFIXES.items():
        g.bind(pfx, ns)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("owl", OWL)
    g.bind("xsd", XSD)
    g.bind("dct", DCTERMS)
    return g

_UNSAFE = re.compile(r"[^A-Za-z0-9_]+")


def kg_name(*parts: str) -> str:
    """Build a Turtle-safe local name using underscores (no dots or hyphens)."""
    chunks = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        text = text.replace("-", "_").replace(".", "_").replace("/", "_").replace(" ", "_")
        text = _UNSAFE.sub("_", text)
        text = re.sub(r"_{2,}", "_", text).strip("_")
        if text:
            chunks.append(text)
    name = "_".join(chunks) or "unnamed"
    if not re.match(r"[A-Za-z_]", name[0]):
        name = "n_" + name
    return name


def kg_uri(*parts: str) -> URIRef:
    return KG[kg_name(*parts)]


def collection_slug(eadid: str) -> str:
    """``FSA.A.04`` → ``FSA_A_04``; used in component and finding-aid local names."""
    return kg_name(eadid or "collection")


def sova_record_key(eadid: str) -> str:
    """``FSA.A.04`` → ``fsa.a.04`` (SOVA path segment; dots stay in the URL)."""
    return (eadid or "").strip().lower()
