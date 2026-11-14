"""Smoke tests for the EAD parser and IIIF derivation."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.ead_parser import parse_ead, walk
from pipeline.iiif import derive_from_dao
from pipeline.paths import SRCDATA


def test_collection_identity():
    data = parse_ead(SRCDATA)
    assert data["header"]["eadid"] == "FSA.A.04"
    assert "Myron Bement Smith" in (data["collection"]["did"]["unittitle"] or "")
    series = [n for n, _ in walk(data["collection"]) if n["level"] == "series"]
    assert len(series) == 3


def test_digitized_flag_on_known_item():
    data = parse_ead(SRCDATA)
    found = {n["id"]: n for n, _ in walk(data["collection"])}
    masjid = found["ref7856"]
    assert masjid["digitized"] is True
    assert masjid["digitization_kind"] == "edan-slideshow"
    cv = masjid["did"]["unittitle"]
    assert "Masjid-i Jomeh" in cv
    boxes = [c["value"] for c in masjid["did"]["containers"] if c["type"] == "Box"]
    assert boxes == ["84"]


def test_iiif_derivation_from_ids():
    rec = derive_from_dao(
        {
            "kind": "ids-image",
            "ids_id": "FS-FSA_A.4_2.12.GN.00.02-000004",
            "href": "https://ids.si.edu/ids/deliveryService?id=FS-FSA_A.4_2.12.GN.00.02-000004",
        }
    )
    assert rec["viewer"] == "https://ids.si.edu/ids/deliveryService?id=FS-FSA_A.4_2.12.GN.00.02-000004"
    assert rec["iiif_image_service"].endswith("FS-FSA_A.4_2.12.GN.00.02-000004")
    assert rec["iiif_manifest"] == "https://ids.si.edu/ids/manifest/FS-FSA_A.4_2.12.GN.00.02-000004"
    assert rec["access_media"] == "jpeg"


def test_slideshow_pdf_pages():
    from pipeline.iiif import derive_from_dao, parse_slideshow_html

    html = '''
    <div id="images" class="grid" data-num-found="25" data-num-pages="3">
      <span class="metadata" data-uan="FS-FSA-2025-017794"></span>
      <span class="metadata" data-uan="FS-FSA-2025-017795"></span>
    </div>
    '''
    parsed = parse_slideshow_html(html)
    assert parsed["ids_ids"] == ["FS-FSA-2025-017794", "FS-FSA-2025-017795"]
    assert parsed["num_found"] == 25
    rec = derive_from_dao(
        {
            "kind": "edan-slideshow",
            "eadrefid": "FSA.A.04_ref6601",
            "href": "https://edan.si.edu/slideshow/viewer/?eadrefid=FSA.A.04_ref6601",
        },
        pages={"FSA.A.04_ref6601": {"ids_ids": parsed["ids_ids"], "page_count": 2}},
    )
    assert rec["viewer"].endswith("eadrefid=FSA.A.04_ref6601")
    assert rec["access_media"] == "pdf"
    assert rec["iiif_manifest"] is None
    assert rec["page_manifests_pending"] is False
    assert rec["pages"][0]["iiif_manifest"].endswith("FS-FSA-2025-017794")
    pending = derive_from_dao(
        {"kind": "edan-slideshow", "eadrefid": "FSA.A.04_ref6601", "href": "x"},
        pages={},
    )
    assert pending["page_manifests_pending"] is True


def test_file_vs_item_levels():
    data = parse_ead(SRCDATA)
    found = {n["id"]: n for n, _ in walk(data["collection"])}
    letter = found["ref6378"]
    assert letter["level"] == "file"
    masjid = found["ref7856"]
    assert masjid["level"] == "item"
    sevruguin = found["ref9914"]
    assert sevruguin["level"] == "item"
    papers = found["ref6173"]
    assert "scopecontent" in (papers.get("notes") or {})
    coll = data["collection"]
    assert coll["did"].get("abstract")
    assert coll["notes"].get("scopecontent")


def test_kg_curie_is_turtle_safe():
    from rdflib import Graph
    from pipeline.namespaces import CRM, KG, collection_slug, kg_name, kg_uri, safe_local
    from pipeline.map_crm import bind
    from pipeline.util import slugify

    assert kg_name("event", "digitization", "fs-fsa-a-04") == "event_digitization_fs_fsa_a_04"
    assert kg_name("component", "FSA.A.04") == "component_FSA_A_04"
    assert kg_name("physical", "FSA.A.06") == "physical_FSA_A_06"
    assert collection_slug("FSA.A.04") == "FSA_A_04"
    uri = str(kg_uri("component", "ref7856"))
    assert uri == "https://w3id.org/sova/fsa_a_04#component_ref7856"
    assert str(KG) == "https://w3id.org/sova/fsa_a_04#"
    assert "-" not in uri.split("#", 1)[1]
    assert "." not in str(kg_uri("component", "FSA.A.04")).split("#", 1)[1]
    assert slugify("FS-FSA_A.4_2.12.GN.00.02-000004") == "fs_fsa_a_4_2_12_gn_00_02_000004"
    assert safe_local("E22_Human-Made_Object") == "E22_Human_Made_Object"
    assert str(CRM["E22_Human-Made_Object"]).endswith("E22_Human_Made_Object")
    assert str(CRM["E52_Time-Span"]).endswith("E52_Time_Span")
    assert str(CRM["P4_has_time-span"]).endswith("P4_has_time_span")
    g = bind(Graph())
    g.add((kg_uri("event", "digitization", "fs-fsa-a-04"), KG["p"], kg_uri("digital", "fs-fsa-a-04")))
    g.add((kg_uri("physical", "FSA.A.04"), CRM["P4_has_time-span"], kg_uri("time", "FSA.A.04")))
    ttl = g.serialize(format="turtle")
    if isinstance(ttl, bytes):
        ttl = ttl.decode("utf-8")
    assert "@prefix kg: <https://w3id.org/sova/fsa_a_04#> ." in ttl
    assert "kg:event_digitization_fs_fsa_a_04" in ttl
    assert "kg:physical_FSA_A_04" in ttl
    assert "kg:event-digitization" not in ttl
    assert "kg:physical_FSA.A.04" not in ttl
    assert "crm:P4_has_time_span" in ttl
    assert "crm:P4_has_time-span" not in ttl


def test_islamic_archives_and_glass_negatives():
    from rdflib import Graph, RDF
    from pipeline.map_crm import (
        EXTENT_MEDIA,
        ISLAMIC_ARCHIVES_SUBCOLLECTIONS,
        bind,
        emit_islamic_archives,
        is_islamic_archives,
        islamic_archives_uri,
    )
    from pipeline.namespaces import AAT, MBS, kg_uri

    assert is_islamic_archives("Islamic Archives")
    assert is_islamic_archives("The Archive for Islamic Culture and Art")
    assert not is_islamic_archives("Columbia University")
    assert str(islamic_archives_uri()).endswith("#collection_islamic_archives")
    assert EXTENT_MEDIA["glass negatives"] == AAT["300134674"]
    eadids = {row["eadid"] for row in ISLAMIC_ARCHIVES_SUBCOLLECTIONS}
    assert eadids == {"FSA.A.04", "FSA.A.06"}
    g = bind(Graph())
    emit_islamic_archives(g, mapped_eadid="FSA.A.04")
    holding = islamic_archives_uri()
    a04 = kg_uri("component", "FSA.A.04")
    a06 = kg_uri("component", "FSA.A.06")
    assert str(a04).endswith("component_FSA_A_04")
    assert str(a06).endswith("component_FSA_A_06")
    assert (holding, MBS.hasSubCollection, a04) in g
    assert (holding, MBS.hasSubCollection, a06) in g
    assert (a06, RDF.type, MBS.ArchivalComponent) in g
    assert (a04, RDF.type, MBS.ArchivalComponent) not in g


def test_seed_skos_and_idempotent():
    from rdflib import Graph, RDF, SKOS, URIRef
    from pipeline.namespaces import AAT, ICONCLASS, bind_graph, kg_uri
    from pipeline.seed import emit_vocabulary, parse_seed

    v1 = parse_seed()
    v2 = parse_seed()
    assert [e["id"] for e in v1["entries"]] == [e["id"] for e in v2["entries"]]
    wet = v1["by_id"]["wet_collodion_negatives"]
    generic = v1["by_id"]["glass_negatives"]
    dry = v1["by_id"]["dry_collodion_negatives"]
    assert str(wet["uri"]).endswith("concept_aat_300134674")
    assert str(generic["uri"]).endswith("concept_aat_300010898")
    assert generic["uri"] in wet["intra_uris"]["broader"]
    assert dry["uri"] in wet["intra_uris"]["related"]
    assert AAT["300010898"] not in [URIRef(x) if not isinstance(x, URIRef) else x for x in wet["intra_uris"]["broader"]]
    mosques = v1["by_id"]["mosques"]
    close = mosques["mapping"]["closeMatch"]
    assert str(ICONCLASS["11Q71"]) in close
    assert "exactMatch" not in mosques["mapping"] or str(ICONCLASS["11Q71"]) not in mosques["mapping"].get("exactMatch", [])

    g = bind_graph(Graph())
    emit_vocabulary(g, v1)
    n1 = len(g)
    emit_vocabulary(g, v1)
    assert len(g) == n1
    g2 = bind_graph(Graph())
    emit_vocabulary(g2, v2)
    assert set(g) == set(g2)

    wet_uri = wet["uri"]
    gen_uri = generic["uri"]
    assert (wet_uri, SKOS.broader, gen_uri) in g
    assert (wet_uri, SKOS.broadMatch, AAT["300010898"]) not in g
    assert (wet_uri, SKOS.exactMatch, AAT["300134674"]) in g
    assert (wet_uri, SKOS.related, dry["uri"]) in g
    sch = kg_uri("scheme", "islamic_archives")
    assert (sch, RDF.type, SKOS.ConceptScheme) in g
    assert (mosques["uri"], SKOS.closeMatch, ICONCLASS["11Q71"]) in g
    iran_arch = v1["by_id"]["architecture_iran"]
    architecture = v1["by_id"]["architecture"]
    assert architecture["uri"] in iran_arch["intra_uris"]["broader"]


if __name__ == "__main__":
    test_collection_identity()
    test_digitized_flag_on_known_item()
    test_iiif_derivation_from_ids()
    test_slideshow_pdf_pages()
    test_file_vs_item_levels()
    test_kg_curie_is_turtle_safe()
    test_islamic_archives_and_glass_negatives()
    test_seed_skos_and_idempotent()
    print("ok")
