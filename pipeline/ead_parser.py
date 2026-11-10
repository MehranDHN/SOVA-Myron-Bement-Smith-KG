"""Parse FSA.A.04 EAD XML into a nested Python structure."""

from __future__ import annotations

import html
import re
from lxml import etree

from pipeline import NS
from pipeline.paths import SRCDATA

EAD = NS["ead"]
XLINK = NS["xlink"]


def q(tag: str) -> str:
    return f"{{{EAD}}}{tag}"


def text_of(el) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def local(el) -> str:
    return etree.QName(el).localname


def xlink_href(el) -> str | None:
    return el.get(f"{{{XLINK}}}href")


def xlink_title(el) -> str | None:
    return el.get(f"{{{XLINK}}}title")


def xlink_role(el) -> str | None:
    return el.get(f"{{{XLINK}}}role")


def parse_named(el) -> dict:
    """persname / corpname / geogname / subject / genreform / title / famname."""
    rec = {
        "element": local(el),
        "text": text_of(el),
        "normal": el.get("normal"),
        "role": el.get("role") or None,
        "source": el.get("source"),
        "authfilenumber": el.get("authfilenumber"),
        "altrender": el.get("altrender"),
        "rules": el.get("rules"),
    }
    rec["uri"] = normalize_auth_uri(rec["source"], rec["authfilenumber"])
    return rec


def normalize_auth_uri(source: str | None, auth: str | None) -> str | None:
    if not auth:
        return None
    auth = auth.strip()
    if auth.startswith("http://") or auth.startswith("https://"):
        return auth.replace("http://id.loc.gov", "https://id.loc.gov")
    if source == "wikidata" or re.fullmatch(r"Q\d+", auth):
        return f"http://www.wikidata.org/entity/{auth}"
    if source == "aat":
        m = re.search(r"(\d{6,})", auth)
        if m:
            return f"http://vocab.getty.edu/aat/{m.group(1)}"
        return None
    if source == "tgn":
        m = re.search(r"(\d+)", auth)
        if m:
            return f"http://vocab.getty.edu/tgn/{m.group(1)}"
        return None
    if source in {"lcsh", "lcnaf", "naf"} and auth.startswith("sh"):
        return f"https://id.loc.gov/authorities/subjects/{auth}"
    if source in {"lcsh", "lcnaf", "naf"} and re.match(r"n\d", auth):
        return f"https://id.loc.gov/authorities/names/{auth}"
    if source == "lcshac":
        return f"https://id.loc.gov/authorities/childrensSubjects/{auth}"
    return None


def parse_dao(el) -> dict:
    href = xlink_href(el) or ""
    kind = "other"
    ids_id = None
    eadrefid = None
    if "ids.si.edu" in href and "id=" in href:
        kind = "ids-image"
        ids_id = href.split("id=", 1)[-1].split("&", 1)[0]
    elif "edan.si.edu/slideshow" in href:
        kind = "edan-slideshow"
        if "eadrefid=" in href:
            eadrefid = href.split("eadrefid=", 1)[-1].split("&", 1)[0]
    role = xlink_role(el) or ""
    if role == "representative-image" and kind == "ids-image":
        kind = "representative-image"
    title = xlink_title(el) or text_of(el.find(q("daodesc")))
    if title:
        title = re.sub(r"<[^>]+>", "", html.unescape(title))
    return {
        "id": el.get("id"),
        "href": href,
        "title": title,
        "role": role or None,
        "kind": kind,
        "ids_id": ids_id,
        "eadrefid": eadrefid,
    }


def parse_container(el) -> dict:
    return {
        "id": el.get("id"),
        "parent": el.get("parent"),
        "type": el.get("type"),
        "label": el.get("label"),
        "value": text_of(el),
    }


def parse_unitdate(el) -> dict:
    return {
        "text": text_of(el),
        "normal": el.get("normal"),
        "type": el.get("type"),
        "datechar": el.get("datechar"),
        "calendar": el.get("calendar"),
        "era": el.get("era"),
    }


def parse_physdesc(el) -> dict:
    extents = []
    for ext in el.findall(q("extent")):
        extents.append({"type": ext.get("type"), "text": text_of(ext)})
    return {
        "id": el.get("id"),
        "altrender": el.get("altrender"),
        "extents": extents,
        "dimensions": text_of(el.find(q("dimensions"))) or None,
        "physfacet": text_of(el.find(q("physfacet"))) or None,
        "text": text_of(el),
    }


def parse_did(did) -> dict:
    if did is None:
        return {}
    origination = []
    for orig in did.findall(q("origination")):
        agents = []
        for child in orig:
            if local(child) in {"persname", "corpname", "famname", "name"}:
                agents.append(parse_named(child))
        origination.append(
            {
                "label": orig.get("label"),
                "agents": agents,
                "text": text_of(orig),
            }
        )
    unitids = []
    ark = None
    local_id = None
    for uid in did.findall(q("unitid")):
        href = None
        ext = uid.find(q("extref"))
        if ext is not None:
            href = xlink_href(ext)
        rec = {
            "type": uid.get("type"),
            "text": text_of(uid),
            "href": href,
        }
        unitids.append(rec)
        if uid.get("type") == "ark" and href:
            ark = href
        elif not uid.get("type") and rec["text"]:
            local_id = rec["text"]
    unittitle = did.find(q("unittitle"))
    title_entities = []
    if unittitle is not None:
        for child in unittitle:
            if local(child) in {"persname", "corpname", "geogname", "famname", "subject"}:
                title_entities.append(parse_named(child))
    languages = []
    langmaterial = did.find(q("langmaterial"))
    if langmaterial is not None:
        for lang in langmaterial.findall(q("language")):
            languages.append({"code": lang.get("langcode"), "text": text_of(lang)})
    return {
        "id": did.get("id"),
        "unittitle": text_of(unittitle),
        "title_entities": title_entities,
        "unitids": unitids,
        "ark": ark,
        "local_id": local_id,
        "origination": origination,
        "unitdates": [parse_unitdate(d) for d in did.findall(q("unitdate"))],
        "containers": [parse_container(c) for c in did.findall(q("container"))],
        "physdescs": [parse_physdesc(p) for p in did.findall(q("physdesc"))],
        "languages": languages,
        "daos": [parse_dao(d) for d in did.findall(q("dao"))],
        "abstract": text_of(did.find(q("abstract"))) or None,
        "repository": text_of(did.find(q("repository"))) or None,
        "materialspec": text_of(did.find(q("materialspec"))) or None,
        "physloc": text_of(did.find(q("physloc"))) or None,
    }


def parse_controlaccess(el) -> dict:
    if el is None:
        return {"subjects": [], "places": [], "agents": [], "genres": [], "titles": []}
    out = {"subjects": [], "places": [], "agents": [], "genres": [], "titles": []}
    for child in el:
        name = local(child)
        rec = parse_named(child)
        if name == "subject":
            out["subjects"].append(rec)
        elif name == "geogname":
            out["places"].append(rec)
        elif name in {"persname", "corpname", "famname", "name"}:
            out["agents"].append(rec)
        elif name == "genreform":
            out["genres"].append(rec)
        elif name == "title":
            out["titles"].append(rec)
    return out


NOTE_TAGS = (
    "scopecontent",
    "bioghist",
    "arrangement",
    "accessrestrict",
    "userestrict",
    "custodhist",
    "acqinfo",
    "prefercite",
    "processinfo",
    "relatedmaterial",
    "altformavail",
    "odd",
    "note",
    "bibliography",
    "otherfindaid",
    "originalsloc",
    "phystech",
    "fileplan",
)


def parse_notes(el) -> dict:
    notes = {}
    for tag in NOTE_TAGS:
        blocks = []
        for n in el.findall(q(tag)):
            paragraphs = [text_of(p) for p in n.findall(q("p")) if text_of(p)]
            blocks.append(
                {
                    "id": n.get("id"),
                    "head": text_of(n.find(q("head"))),
                    "text": text_of(n),
                    "paragraphs": paragraphs,
                    "entities": [
                        parse_named(c)
                        for c in n.iter()
                        if local(c) in {"persname", "corpname", "geogname", "famname", "subject"}
                    ],
                }
            )
        if blocks:
            notes[tag] = blocks
    return notes


def parse_component(el, parent_id: str | None = None, depth: int = 0) -> dict:
    did = parse_did(el.find(q("did")))
    daos = list(did.get("daos") or [])
    for dao in el.findall(q("dao")):
        daos.append(parse_dao(dao))
    children = []
    for child in el.findall(q("c")):
        children.append(parse_component(child, parent_id=el.get("id"), depth=depth + 1))
    digitized_kinds = sorted({d["kind"] for d in daos if d.get("kind") and d["kind"] != "other"})
    digitized = any(d.get("kind") not in {None, "other"} or d.get("href") for d in daos)
    if daos and not digitized:
        digitized = True
    kind = "none"
    if any(d["kind"] == "edan-slideshow" for d in daos):
        kind = "edan-slideshow"
    if any(d["kind"] in {"ids-image", "representative-image"} for d in daos):
        if kind == "edan-slideshow":
            kind = "mixed"
        else:
            kind = "ids-image"
    elif any(d["kind"] == "representative-image" for d in daos):
        kind = "ids-image"
    return {
        "id": el.get("id") or did.get("id") or "collection",
        "level": el.get("level") or "collection",
        "otherlevel": el.get("otherlevel"),
        "parent_id": parent_id,
        "depth": depth,
        "did": did,
        "controlaccess": parse_controlaccess(el.find(q("controlaccess"))),
        "notes": parse_notes(el),
        "daos": daos,
        "digitized": digitized,
        "digitization_kind": kind if digitized else "none",
        "children": children,
    }


def parse_header(root) -> dict:
    header = root.find(q("eadheader"))
    if header is None:
        return {}
    eadid = header.find(q("eadid"))
    titleproper = [
        text_of(t)
        for t in header.findall(f".//{q('titleproper')}")
    ]
    return {
        "eadid": text_of(eadid),
        "eadid_url": eadid.get("url") if eadid is not None else None,
        "countrycode": eadid.get("countrycode") if eadid is not None else None,
        "mainagencycode": eadid.get("mainagencycode") if eadid is not None else None,
        "titleproper": titleproper,
        "author": text_of(header.find(f".//{q('author')}")),
        "publisher": text_of(header.find(f".//{q('publisher')}")),
        "creation": text_of(header.find(f".//{q('creation')}")),
        "descrules": text_of(header.find(f".//{q('descrules')}")),
    }


def parse_ead(path=None) -> dict:
    path = path or SRCDATA
    tree = etree.parse(str(path))
    root = tree.getroot()
    archdesc = root.find(q("archdesc"))
    collection = parse_component(archdesc, parent_id=None, depth=0)
    collection["id"] = "FSA.A.04"
    collection["level"] = "collection"
    dsc = archdesc.find(q("dsc"))
    if dsc is not None:
        collection["children"] = [
            parse_component(c, parent_id=collection["id"], depth=1) for c in dsc.findall(q("c"))
        ]
    return {
        "header": parse_header(root),
        "collection": collection,
    }


def walk(node, parent=None):
    yield node, parent
    for child in node.get("children") or []:
        yield from walk(child, node)
