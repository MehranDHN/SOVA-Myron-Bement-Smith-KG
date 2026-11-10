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
    from pipeline.namespaces import KG, kg_name, kg_uri
    from pipeline.map_crm import bind
    from pipeline.util import slugify

    assert kg_name("event", "digitization", "fs-fsa-a-04") == "event_digitization_fs_fsa_a_04"
    uri = str(kg_uri("component", "ref7856"))
    assert uri == "https://w3id.org/sova/fsa_a_04#component_ref7856"
    assert str(KG) == "https://w3id.org/sova/fsa_a_04#"
    assert "-" not in uri.split("#", 1)[1]
    assert slugify("FS-FSA_A.4_2.12.GN.00.02-000004") == "fs_fsa_a_4_2_12_gn_00_02_000004"
    g = bind(Graph())
    g.add((kg_uri("event", "digitization", "fs-fsa-a-04"), KG["p"], kg_uri("digital", "fs-fsa-a-04")))
    ttl = g.serialize(format="turtle")
    if isinstance(ttl, bytes):
        ttl = ttl.decode("utf-8")
    assert "@prefix kg: <https://w3id.org/sova/fsa_a_04#> ." in ttl
    assert "kg:event_digitization_fs_fsa_a_04" in ttl
    assert "kg:event-digitization" not in ttl


def test_islamic_archives_and_glass_negatives():
    from pipeline.map_crm import EXTENT_MEDIA, is_islamic_archives, islamic_archives_uri
    from pipeline.namespaces import AAT

    assert is_islamic_archives("Islamic Archives")
    assert is_islamic_archives("The Archive for Islamic Culture and Art")
    assert not is_islamic_archives("Columbia University")
    assert str(islamic_archives_uri()).endswith("#collection_islamic_archives")
    assert EXTENT_MEDIA["glass negatives"] == AAT["300134674"]


if __name__ == "__main__":
    test_collection_identity()
    test_digitized_flag_on_known_item()
    test_iiif_derivation_from_ids()
    test_slideshow_pdf_pages()
    test_file_vs_item_levels()
    test_kg_curie_is_turtle_safe()
    test_islamic_archives_and_glass_negatives()
    print("ok")
