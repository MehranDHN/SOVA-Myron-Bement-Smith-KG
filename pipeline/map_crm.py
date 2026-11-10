"""Map the parsed EAD tree to CIDOC CRM + CRMdig + mbs RDF."""

from __future__ import annotations

import json
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, XSD

from pipeline.ead_parser import parse_ead, walk
from pipeline.iiif import enrich_daos, page_index
from pipeline.namespaces import AAT, CRM, CRMDIG, KG, LANG, MBS, PREFIXES, SKOS, kg_uri
from pipeline.paths import CACHE_DIR, RDF_DIR, SRCDATA
from pipeline.reconcile import run as reconcile
from pipeline.util import slugify, split_normal_date


def bind(g: Graph) -> Graph:
    g.bind("kg", KG)
    for pfx, ns in PREFIXES.items():
        g.bind(pfx, ns)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("owl", OWL)
    g.bind("xsd", XSD)
    g.bind("dct", DCTERMS)
    return g


def component_uri(eid: str) -> URIRef:
    return kg_uri("component", eid)


def physical_uri(eid: str) -> URIRef:
    return kg_uri("physical", eid)


def sova_url(eid: str) -> str:
    if eid in {"FSA.A.04", "collection"}:
        return "https://sova.si.edu/record/fsa.a.04"
    return f"https://sova.si.edu/record/fsa.a.04/{eid}"


def load_reconciled() -> dict:
    path = CACHE_DIR / "reconciled.json"
    if not path.exists():
        return reconcile()
    return json.loads(path.read_text(encoding="utf-8"))


def index_reconciled(data: dict) -> dict:
    idx = {}

    def richer(a: dict, b: dict) -> bool:
        am, bm = a.get("matches") or {}, b.get("matches") or {}
        if len(am) != len(bm):
            return len(am) > len(bm)
        if a.get("uri") and not b.get("uri"):
            return True
        return False

    for kind, rows in data.items():
        for rec in rows:
            key = (rec.get("text") or "").strip().lower()
            if key:
                k = (kind, key)
                if k not in idx or richer(rec, idx[k]):
                    idx[k] = rec
            if rec.get("uri"):
                idx[("uri", rec["uri"])] = rec
    return idx


def entity_uri(kind: str, rec: dict) -> URIRef:
    text = (rec.get("text") or "").lower()
    if kind in {"genre", "genres"} and "glass negative" in text:
        return kg_uri("concept", "aat", "300134674")
    matches = rec.get("matches") or {}
    if matches.get("wikidata") and kind in {"agent", "agents"}:
        qid = matches["wikidata"].rsplit("/", 1)[-1]
        return kg_uri("agent", qid)
    if matches.get("tgn") and kind in {"place", "places"}:
        tid = matches["tgn"].rsplit("/", 1)[-1]
        return kg_uri("place", "tgn", tid)
    if matches.get("aat") and kind in {"genre", "genres", "subject", "subjects"}:
        aid = matches["aat"].rsplit("/", 1)[-1]
        return kg_uri("concept", "aat", aid)
    if matches.get("lcsh"):
        lid = matches["lcsh"].rstrip("/").rsplit("/", 1)[-1]
        return kg_uri("concept", "lcsh", lid)
    slug = rec.get("slug") or slugify(rec.get("text") or "entity")
    folder = {
        "agent": "agent",
        "agents": "agent",
        "place": "place",
        "places": "place",
    }.get(kind, "concept")
    return kg_uri(folder, slug)


def link_matches(g: Graph, subject: URIRef, rec: dict):
    matches = rec.get("matches") or {}
    for key, uri in matches.items():
        if not uri or key in {"source_uri", "aat_broader"}:
            continue
        if key == "aat_related":
            continue
        g.add((subject, OWL.sameAs, URIRef(uri)))
        g.add((subject, MBS.reconciledTo, URIRef(uri)))
    if rec.get("confidence"):
        g.add((subject, MBS.matchConfidence, Literal(rec["confidence"], datatype=XSD.decimal)))
    if rec.get("text"):
        g.add((subject, MBS.sourceString, Literal(rec["text"])))


ISLAMIC_ARCHIVES_NAMES = {
    "islamic archives",
    "the islamic archives",
    "archive for islamic culture and art",
    "the archive for islamic culture and art",
}


def is_islamic_archives(text: str) -> bool:
    n = " ".join((text or "").strip().lower().split())
    return n in ISLAMIC_ARCHIVES_NAMES


def islamic_archives_uri() -> URIRef:
    return kg_uri("collection", "islamic_archives")


def emit_islamic_archives(g: Graph, rec: dict | None = None) -> URIRef:
    """Islamic Archives is the parent holding that FSA.A.04 belongs to.

    EAD corpname 'Islamic Archives' names that larger collection, not a
    corporate body. Further sub-collections will be attached with
    mbs:hasSubCollection later.
    """
    uri = islamic_archives_uri()
    coll = component_uri("FSA.A.04")
    g.add((uri, RDF.type, MBS.HoldingCollection))
    g.add((uri, RDF.type, CRM["E78_Curated_Holding"]))
    g.add((uri, RDF.type, CRM["E73_Information_Object"]))
    g.add((uri, RDFS.label, Literal("Islamic Archives")))
    g.add((uri, SKOS.altLabel, Literal("The Archive for Islamic Culture and Art")))
    g.add((uri, RDFS.comment, Literal(
        "Parent holding of the Myron Bement Smith Collection (FSA.A.04). "
        "Further sub-collections of the Islamic Archives will be added as siblings of FSA.A.04."
    )))
    g.add((uri, MBS.hasSubCollection, coll))
    g.add((uri, CRM["P106_is_composed_of"], coll))
    g.add((coll, MBS.isPartOfCollection, uri))
    g.add((coll, CRM["P106i_forms_part_of"], uri))
    if rec:
        if rec.get("text"):
            g.add((uri, MBS.sourceString, Literal(rec["text"])))
        link_matches(g, uri, rec)
    return uri


def emit_agent(g: Graph, rec: dict) -> URIRef:
    text = rec.get("text") or ""
    if is_islamic_archives(text):
        return emit_islamic_archives(g, rec)
    uri = entity_uri("agent", rec)
    classes = CRM["E21_Person"]
    if rec.get("element") == "corpname" or "Institute" in text or "University" in text:
        classes = CRM["E74_Group"]
    g.add((uri, RDF.type, classes))
    g.add((uri, RDFS.label, Literal(text)))
    link_matches(g, uri, rec)
    return uri


def emit_place(g: Graph, rec: dict) -> URIRef:
    uri = entity_uri("place", rec)
    g.add((uri, RDF.type, CRM["E53_Place"]))
    g.add((uri, RDFS.label, Literal(rec.get("text") or "")))
    link_matches(g, uri, rec)
    return uri


def emit_concept(g: Graph, rec: dict, kind: str) -> URIRef:
    uri = entity_uri(kind, rec)
    g.add((uri, RDF.type, CRM["E55_Type"]))
    g.add((uri, RDF.type, SKOS.Concept))
    g.add((uri, RDFS.label, Literal(rec.get("text") or "")))
    link_matches(g, uri, rec)
    label = (rec.get("text") or "").lower()
    if "glass negative" in label:
        wet = AAT["300134674"]
        g.add((uri, OWL.sameAs, wet))
        g.add((uri, MBS.reconciledTo, wet))
        g.add((uri, SKOS.exactMatch, wet))
        g.add((uri, SKOS.broader, AAT["300010898"]))
        g.add((uri, SKOS.related, AAT["300241140"]))
        g.add((wet, RDFS.label, Literal("wet collodion negatives")))
        g.add((AAT["300010898"], RDFS.label, Literal("glass negatives")))
        g.add((AAT["300241140"], RDFS.label, Literal("dry collodion negatives")))
        g.add((uri, RDFS.comment, Literal(
            "EAD Genre Form 'Glass negatives' is mapped to AAT wet collodion negatives "
            "(300134674). Dry collodion negatives (300241140) is the sibling process."
        )))
    matches = rec.get("matches") or {}
    if matches.get("aat_broader"):
        g.add((uri, SKOS.broader, URIRef(matches["aat_broader"])))
    related = matches.get("aat_related")
    if isinstance(related, str):
        related = [related]
    for rel in related or []:
        g.add((uri, SKOS.related, URIRef(rel)))
    return uri


def emit_storage(g: Graph, containers: list[dict]) -> list[URIRef]:
    box_uri = None
    folder_uri = None
    extra = []
    for c in containers:
        typ = (c.get("type") or "").lower()
        val = c.get("value") or ""
        if typ == "box":
            box_uri = kg_uri("box", val)
            g.add((box_uri, RDF.type, MBS.Box))
            g.add((box_uri, RDFS.label, Literal(f"Box {val}")))
            g.add((box_uri, MBS.boxNumber, Literal(val)))
        elif typ == "folder":
            parent = next((x["value"] for x in containers if (x.get("type") or "").lower() == "box"), "x")
            folder_uri = kg_uri("folder", parent, val)
            g.add((folder_uri, RDF.type, MBS.Folder))
            g.add((folder_uri, RDFS.label, Literal(f"Folder {val}")))
            g.add((folder_uri, MBS.folderNumber, Literal(val)))
            if box_uri:
                g.add((folder_uri, MBS.housedIn, box_uri))
                g.add((box_uri, CRM["P46_is_composed_of"], folder_uri))
        elif typ == "item":
            item_uri = kg_uri("storage-item", val)
            g.add((item_uri, RDF.type, MBS.StorageItem))
            g.add((item_uri, RDFS.label, Literal(f"Item {val}")))
            extra.append(item_uri)
        elif typ in {"oversize", "roll", "map-rolled"}:
            cls = MBS.Oversize if typ == "oversize" else MBS.Roll
            item_uri = kg_uri("storage", typ, val or typ)
            g.add((item_uri, RDF.type, cls))
            g.add((item_uri, RDFS.label, Literal(f"{c.get('type')} {val}".strip())))
            extra.append(item_uri)
    uris = [x for x in (folder_uri, box_uri) if x] + extra
    return uris


def emit_timespan(g: Graph, component_id: str, dates: list[dict]) -> URIRef | None:
    if not dates:
        return None
    ts = kg_uri("time", component_id)
    g.add((ts, RDF.type, CRM["E52_Time-Span"]))
    labels = []
    begins, ends = [], []
    for d in dates:
        if d.get("text"):
            labels.append(d["text"])
        b, e = split_normal_date(d.get("normal"))
        if b:
            begins.append(b)
        if e:
            ends.append(e)
    if labels:
        g.add((ts, RDFS.label, Literal("; ".join(labels))))
        g.add((ts, CRM["P78_is_identified_by"], Literal(labels[0])))
    if begins:
        g.add((ts, CRM["P82a_begin_of_the_begin"], Literal(min(begins))))
    if ends:
        g.add((ts, CRM["P82b_end_of_the_end"], Literal(max(ends))))
    return ts


def _add_iiif(g: Graph, d1: URIRef, rec: dict):
    if rec.get("viewer"):
        g.add((d1, MBS.viewerUrl, Literal(rec["viewer"], datatype=XSD.anyURI)))
        g.add((d1, RDFS.seeAlso, URIRef(rec["viewer"])))
    elif rec.get("href"):
        g.add((d1, RDFS.seeAlso, URIRef(rec["href"])))
    if rec.get("iiif_image_service"):
        g.add((d1, MBS.iiifImageService, Literal(rec["iiif_image_service"], datatype=XSD.anyURI)))
    if rec.get("iiif_manifest"):
        g.add((d1, MBS.iiifManifest, Literal(rec["iiif_manifest"], datatype=XSD.anyURI)))
    if rec.get("iiif_resolved") is not None:
        g.add((d1, MBS.iiifResolved, Literal(bool(rec["iiif_resolved"]), datatype=XSD.boolean)))


def emit_digital(g: Graph, component: URIRef, node: dict, daos: list[dict]):
    eid = node["id"]
    level = node.get("level") or ""
    for i, dao in enumerate(daos, start=1):
        did = dao.get("ids_id") or dao.get("eadrefid") or f"{eid}_{i}"
        d1 = kg_uri("digital", slugify(did))
        g.add((d1, RDF.type, CRMDIG["D1_Digital_Object"]))
        g.add((d1, RDFS.label, Literal(dao.get("title") or did)))
        g.add((component, MBS.hasDigitalObject, d1))
        g.add((d1, CRM["P70i_is_documented_in"], component))
        pages = dao.get("pages") or []
        is_slideshow = bool(dao.get("eadrefid") and dao.get("kind") == "edan-slideshow")
        if dao.get("ids_id") and not is_slideshow:
            g.add((d1, RDF.type, MBS.JpegSurrogate))
            g.add((d1, MBS.mediaType, AAT["300266239"]))
            g.add((d1, CRM["P2_has_type"], AAT["300266239"]))
        elif is_slideshow and level == "file":
            g.add((d1, RDF.type, MBS.PdfSurrogate))
            g.add((d1, MBS.mediaType, AAT["300028477"]))
            g.add((d1, CRM["P2_has_type"], AAT["300028477"]))
            if dao.get("pdf_request"):
                g.add((d1, MBS.pdfRequestUrl, Literal(dao["pdf_request"], datatype=XSD.anyURI)))
        elif is_slideshow:
            g.add((d1, RDF.type, MBS.ImageSet))
        _add_iiif(g, d1, dao)
        if dao.get("page_count"):
            g.add((d1, MBS.pageCount, Literal(int(dao["page_count"]), datatype=XSD.integer)))
        if dao.get("page_manifests_pending"):
            g.add((d1, MBS.pageManifestsPending, Literal(True, datatype=XSD.boolean)))
        for page in pages:
            pnode = kg_uri("digital", slugify(did), "page", str(page["page_number"]))
            g.add((pnode, RDF.type, CRMDIG["D1_Digital_Object"]))
            g.add((pnode, RDF.type, MBS.PdfPage if level == "file" else MBS.JpegSurrogate))
            g.add((pnode, RDFS.label, Literal(f"page {page['page_number']} of {did}")))
            g.add((pnode, MBS.pageNumber, Literal(int(page["page_number"]), datatype=XSD.integer)))
            g.add((d1, MBS.hasPage, pnode))
            g.add((d1, CRM["P106_is_composed_of"], pnode))
            _add_iiif(g, pnode, page)
        proc = kg_uri("event", "digitization", slugify(did))
        g.add((proc, RDF.type, CRMDIG["D2_Digitization_Process"]))
        g.add((proc, CRM["P108_has_produced"], d1))
        g.add((proc, CRM["P16_used_specific_object"], physical_uri(eid)))


NOTE_TYPE = {
    "scopecontent": MBS.ScopeContent,
    "bioghist": MBS.BiogHist,
    "abstract": MBS.Abstract,
    "arrangement": MBS.Arrangement,
    "accessrestrict": MBS.AccessRestrict,
    "userestrict": MBS.UseRestrict,
    "custodhist": MBS.CustodHist,
    "acqinfo": MBS.AcqInfo,
    "prefercite": MBS.PreferCite,
    "processinfo": MBS.ProcessInfo,
    "relatedmaterial": MBS.RelatedMaterial,
    "altformavail": MBS.AltFormAvail,
    "odd": MBS.OddNote,
    "note": MBS.GeneralNote,
    "bibliography": MBS.Bibliography,
    "otherfindaid": MBS.OtherFindAid,
    "originalsloc": MBS.OriginalsLoc,
    "phystech": MBS.PhysTech,
    "fileplan": MBS.FilePlan,
}

EXTENT_MEDIA = {
    "glass negatives": AAT["300134674"],
    "photographic prints": AAT["300127104"],
    "albumen prints": AAT["300127121"],
    "gelatin silver prints": AAT["300128695"],
    "lantern slides": AAT["300127024"],
    "color slides": AAT["300128377"],
    "slides": AAT["300128371"],
    "negatives": AAT["300127173"],
    "architectural drawings": AAT["300034787"],
    "drawings": AAT["300033973"],
    "maps": AAT["300028094"],
    "notebooks": AAT["300264354"],
    "correspondence": AAT["300026877"],
    "notes": AAT["300027200"],
}

TITLE_MEDIA = (
    ("glass negative", AAT["300134674"]),
    ("negative", AAT["300127173"]),
    ("lantern slide", AAT["300127024"]),
    ("color slide", AAT["300128377"]),
    ("photograph", AAT["300046300"]),
    ("photo", AAT["300046300"]),
    ("drawing", AAT["300033973"]),
    ("ground plan", AAT["300034787"]),
    ("plan", AAT["300034787"]),
    ("sketch", AAT["300015425"]),
    ("notebook", AAT["300264354"]),
    ("map", AAT["300028094"]),
    ("letter", AAT["300026877"]),
    ("correspondence", AAT["300026877"]),
)


def emit_languages(g: Graph, intel: URIRef, languages: list[dict], linguistic=None):
    for lang in languages:
        code = (lang.get("code") or "").lower()
        if not code:
            continue
        uri = LANG[code]
        g.add((uri, RDF.type, CRM["E56_Language"]))
        g.add((uri, RDFS.label, Literal(lang.get("text") or code)))
        g.add((intel, DCTERMS.language, Literal(code)))
        for node in linguistic or []:
            g.add((node, CRM["P72_has_language"], uri))


def emit_linguistic(g: Graph, intel: URIRef, eid: str, tag: str, block: dict, index: int, languages=None):
    text = (block.get("text") or "").strip()
    if not text:
        return
    note = kg_uri("note", eid, tag, str(index))
    g.add((note, RDF.type, CRM["E33_Linguistic_Object"]))
    head = block.get("head") or tag
    g.add((note, RDFS.label, Literal(head)))
    g.add((note, RDF.value, Literal(text)))
    ntype = NOTE_TYPE.get(tag, MBS.GeneralNote)
    g.add((note, MBS.noteType, ntype))
    g.add((note, CRM["P2_has_type"], ntype))
    g.add((intel, MBS.hasLinguisticObject, note))
    g.add((intel, CRM["P67_refers_to"], note))
    g.add((intel, CRM["P3_has_note"], Literal(text)))
    emit_languages(g, intel, languages or [], linguistic=[note])
    for i, para in enumerate(block.get("paragraphs") or []):
        if not para or para == text:
            continue
        pnode = kg_uri("note", eid, tag, str(index), "p", str(i))
        g.add((pnode, RDF.type, CRM["E33_Linguistic_Object"]))
        g.add((pnode, RDF.value, Literal(para)))
        g.add((note, CRM["P148_has_component"], pnode))
        emit_languages(g, intel, languages or [], linguistic=[pnode])


def apply_ead_level(g: Graph, intel: URIRef, phys: URIRef, level: str, did: dict):
    """file vs item is a media distinction, not only an archival depth flag."""
    title = (did.get("unittitle") or "").lower()
    if level == "file":
        g.add((intel, RDF.type, MBS.FileUnit))
        g.add((phys, RDF.type, MBS.DocumentaryFile))
        g.add((phys, MBS.mediaType, AAT["300027182"]))
        g.add((phys, CRM["P2_has_type"], AAT["300027182"]))
        g.add((intel, CRM["P2_has_type"], AAT["300027182"]))
    elif level == "item":
        g.add((intel, RDF.type, MBS.ItemUnit))
        g.add((phys, RDF.type, MBS.DiscreteItem))
        media = _infer_item_media(did, title)
        if media:
            g.add((phys, MBS.mediaType, media))
            g.add((phys, CRM["P2_has_type"], media))
            g.add((intel, CRM["P2_has_type"], media))


def _infer_item_media(did: dict, title: str):
    for p in did.get("physdescs") or []:
        for e in p.get("extents") or []:
            key = (e.get("type") or e.get("text") or "").strip().lower()
            for label, uri in EXTENT_MEDIA.items():
                if label in key:
                    return uri
        facet = (p.get("physfacet") or "").lower()
        for label, uri in EXTENT_MEDIA.items():
            if label in facet:
                return uri
    for label, uri in TITLE_MEDIA:
        if label in title:
            return uri
    return None


def emit_component(g: Graph, node: dict, parent: dict | None, idx: dict, probe_iiif: bool, pages=None):
    eid = node["id"]
    did = node.get("did") or {}
    intel = component_uri(eid)
    phys = physical_uri(eid)
    title = did.get("unittitle") or eid
    level = node.get("level") or "item"

    g.add((intel, RDF.type, MBS.ArchivalComponent))
    g.add((intel, RDF.type, CRM["E73_Information_Object"]))
    g.add((phys, RDF.type, MBS.PhysicalComponent))
    g.add((phys, RDF.type, CRM["E22_Human-Made_Object"]))
    g.add((intel, MBS.hasPhysicalUnit, phys))
    g.add((intel, RDFS.label, Literal(title)))
    g.add((phys, RDFS.label, Literal(title)))
    g.add((intel, MBS.archivalLevel, Literal(level)))
    g.add((intel, MBS.eadRef, Literal(eid)))
    g.add((intel, MBS.sovaUrl, Literal(sova_url(eid), datatype=XSD.anyURI)))
    g.add((intel, RDFS.seeAlso, URIRef(sova_url(eid))))
    g.add((intel, MBS.digitized, Literal(bool(node.get("digitized")), datatype=XSD.boolean)))
    kind = node.get("digitization_kind") or "none"
    g.add((intel, MBS.digitizationKind, MBS[kind.replace("-", "_")]))

    apply_ead_level(g, intel, phys, level, did)

    if did.get("ark"):
        ident = kg_uri("id", "ark", eid)
        g.add((ident, RDF.type, CRM["E42_Identifier"]))
        g.add((ident, RDFS.label, Literal(did["ark"])))
        g.add((intel, CRM["P48_has_preferred_identifier"], ident))
        g.add((intel, OWL.sameAs, URIRef(did["ark"])))
        g.add((phys, OWL.sameAs, URIRef(did["ark"])))
    if did.get("local_id"):
        g.add((intel, DCTERMS.identifier, Literal(did["local_id"])))
    title_app = kg_uri("title", eid)
    g.add((title_app, RDF.type, CRM["E35_Title"]))
    g.add((title_app, RDF.type, CRM["E33_Linguistic_Object"]))
    g.add((title_app, RDFS.label, Literal(title)))
    g.add((title_app, RDF.value, Literal(title)))
    g.add((intel, CRM["P102_has_title"], title_app))
    g.add((intel, CRM["P1_is_identified_by"], title_app))
    emit_languages(g, intel, did.get("languages") or [], linguistic=[title_app])
    if did.get("abstract"):
        emit_linguistic(
            g, intel, eid, "abstract",
            {"head": "Abstract", "text": did["abstract"], "id": None},
            0,
            languages=did.get("languages") or [],
        )
    if did.get("materialspec"):
        g.add((phys, CRM["P3_has_note"], Literal("materialspec: " + did["materialspec"])))
    if did.get("physloc"):
        g.add((phys, CRM["P3_has_note"], Literal("physloc: " + did["physloc"])))
    if did.get("repository"):
        g.add((intel, DCTERMS.publisher, Literal(did["repository"])))

    if parent:
        g.add((intel, MBS.hasParentComponent, component_uri(parent["id"])))
        g.add((component_uri(parent["id"]), MBS.hasChildComponent, intel))
        g.add((component_uri(parent["id"]), CRM["P106_is_composed_of"], intel))
        g.add((physical_uri(parent["id"]), CRM["P46_is_composed_of"], phys))

    storage = emit_storage(g, did.get("containers") or [])
    for s in storage:
        g.add((phys, MBS.housedIn, s))
        g.add((s, CRM["P46_is_composed_of"], phys))

    ts = emit_timespan(g, eid, did.get("unitdates") or [])
    prod = None
    originations = did.get("origination") or []
    if ts or originations:
        prod = kg_uri("event", "production", eid)
        g.add((prod, RDF.type, CRM["E12_Production"]))
        g.add((prod, RDFS.label, Literal(f"Production of {title}")))
        g.add((prod, CRM["P108_has_produced"], phys))
        if ts:
            g.add((prod, CRM["P4_has_time-span"], ts))
        for orig in originations:
            for rec in orig.get("agents") or []:
                agent_rec = idx.get(("agents", (rec.get("text") or "").strip().lower()), rec)
                agent = emit_agent(g, agent_rec)
                g.add((prod, CRM["P14_carried_out_by"], agent))
                role = (rec.get("role") or orig.get("label") or "").lower()
                if "pht" in role or "photograph" in role:
                    g.add((prod, CRM["P32_used_general_technique"], AAT["300054225"]))
                if "col" in role or "collector" in role:
                    acq = kg_uri("event", "custody", eid)
                    g.add((acq, RDF.type, CRM["E10_Transfer_of_Custody"]))
                    g.add((acq, CRM["P29_custody_received_by"], agent))
                    g.add((acq, CRM["P30_transferred_custody_of"], phys))

    for rec in did.get("title_entities") or []:
        _attach_named(g, intel, rec, idx, "unittitle")

    ca = node.get("controlaccess") or {}
    for rec in ca.get("agents") or []:
        agent = emit_agent(g, idx.get(("agents", (rec.get("text") or "").strip().lower()), rec))
        g.add((intel, CRM["P67_refers_to"], agent))
    for rec in ca.get("places") or []:
        place = emit_place(g, idx.get(("places", (rec.get("text") or "").strip().lower()), rec))
        g.add((intel, CRM["P67_refers_to"], place))
        if prod:
            g.add((prod, CRM["P7_took_place_at"], place))
    for rec in ca.get("subjects") or []:
        concept = emit_concept(
            g, idx.get(("subjects", (rec.get("text") or "").strip().lower()), rec), "subjects"
        )
        g.add((intel, CRM["P129_is_about"], concept))
        g.add((phys, CRM["P2_has_type"], concept))
    for rec in ca.get("genres") or []:
        concept = emit_concept(
            g, idx.get(("genres", (rec.get("text") or "").strip().lower()), rec), "genres"
        )
        g.add((phys, CRM["P2_has_type"], concept))
        g.add((intel, CRM["P2_has_type"], concept))
        g.add((phys, MBS.mediaType, concept))
    for rec in ca.get("titles") or []:
        work = kg_uri("work", slugify(rec.get("text") or "title"))
        g.add((work, RDF.type, CRM["E33_Linguistic_Object"]))
        g.add((work, RDFS.label, Literal(rec.get("text") or "")))
        g.add((intel, CRM["P129_is_about"], work))

    notes = node.get("notes") or {}
    for tag, blocks in notes.items():
        for i, block in enumerate(blocks):
            emit_linguistic(g, intel, eid, tag, block, i, languages=did.get("languages") or [])
            for rec in block.get("entities") or []:
                _attach_named(g, intel, rec, idx, tag)

    daos = enrich_daos(node.get("daos") or [], do_probe=probe_iiif, pages=pages)
    if daos:
        emit_digital(g, intel, node, daos)

    for ext in _extents(did):
        dim = BNode()
        g.add((phys, CRM["P43_has_dimension"], dim))
        g.add((dim, RDF.type, CRM["E54_Dimension"]))
        g.add((dim, RDFS.label, Literal(ext)))


def _extents(did: dict) -> list[str]:
    out = []
    for p in did.get("physdescs") or []:
        for e in p.get("extents") or []:
            if e.get("text"):
                out.append(e["text"])
        if p.get("dimensions"):
            out.append(p["dimensions"])
    return out


def _attach_named(g, intel, rec, idx, field):
    el = rec.get("element")
    key = (rec.get("text") or "").strip().lower()
    if el == "geogname":
        place = emit_place(g, idx.get(("places", key), rec))
        g.add((intel, CRM["P67_refers_to"], place))
        mon = idx.get(("places", key), rec)
        if mon.get("monument") or (mon.get("matches") or {}).get("wikidata"):
            if "mosque" in key or "masjid" in key:
                built = kg_uri("built", slugify(rec.get("text") or "monument"))
                g.add((built, RDF.type, CRM["E22_Human-Made_Object"]))
                g.add((built, RDFS.label, Literal(rec.get("text"))))
                g.add((built, CRM["P2_has_type"], AAT["300007691"]))
                if (mon.get("matches") or {}).get("wikidata"):
                    g.add((built, OWL.sameAs, URIRef(mon["matches"]["wikidata"])))
                g.add((intel, CRM["P67_refers_to"], built))
                g.add((intel, CRM["P138_represents"], built))
    elif el in {"persname", "corpname", "famname"}:
        agent = emit_agent(g, idx.get(("agents", key), rec))
        g.add((intel, CRM["P67_refers_to"], agent))


def emit_finding_aid(g: Graph, header: dict, collection_id: str):
    fa = kg_uri("finding-aid")
    g.add((fa, RDF.type, MBS.FindingAid))
    g.add((fa, RDF.type, CRM["E31_Document"]))
    g.add((fa, RDFS.label, Literal("Myron Bement Smith Collection finding aid")))
    g.add((fa, CRM["P70_documents"], component_uri(collection_id)))
    if header.get("eadid_url"):
        g.add((fa, OWL.sameAs, URIRef(header["eadid_url"])))
        g.add((fa, RDFS.seeAlso, URIRef(header["eadid_url"])))
    if header.get("author"):
        g.add((fa, DCTERMS.creator, Literal(header["author"])))
    if header.get("publisher"):
        g.add((fa, DCTERMS.publisher, Literal(header["publisher"])))
    g.add((fa, DCTERMS.source, Literal(str(SRCDATA.name))))


def run(path=None, probe_iiif: bool = False, limit: int | None = None) -> dict:
    data = parse_ead(path or SRCDATA)
    idx = index_reconciled(load_reconciled())
    pages = page_index()
    RDF_DIR.mkdir(parents=True, exist_ok=True)

    graphs = {
        "collection": bind(Graph()),
        "series-1": bind(Graph()),
        "series-2": bind(Graph()),
        "series-3": bind(Graph()),
        "vocab": bind(Graph()),
    }
    emit_finding_aid(graphs["collection"], data["header"], data["collection"]["id"])
    emit_islamic_archives(graphs["collection"])

    count = 0
    current_series = "collection"

    def series_key(node, parent):
        if node.get("level") == "series":
            title = (node.get("did") or {}).get("unittitle") or ""
            if title.startswith("Papers"):
                return "series-1"
            if "Islamic" in title:
                return "series-2"
            return "series-3"
        if parent is None:
            return "collection"
        return None

    series_of = {data["collection"]["id"]: "collection"}

    for node, parent in walk(data["collection"]):
        sk = series_key(node, parent)
        pid = parent["id"] if parent else None
        if sk and sk != "collection":
            current_series = sk
            series_of[node["id"]] = sk
        elif node["id"] not in series_of:
            series_of[node["id"]] = series_of.get(pid, current_series)
        gname = series_of[node["id"]]
        if gname not in graphs:
            gname = "collection"
        emit_component(graphs[gname], node, parent, idx, probe_iiif, pages=pages)
        count += 1
        if limit and count >= limit:
            break

    written = {}
    for name, g in graphs.items():
        if len(g) == 0:
            continue
        dest = RDF_DIR / f"{name}.ttl"
        g.serialize(dest, format="turtle")
        written[name] = {"triples": len(g), "path": str(dest)}
    return {"components": count, "graphs": written}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
