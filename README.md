# Myron Bement Smith Collection Knowledge Graph

CIDOC CRM and OWL knowledge graph of the **Myron Bement Smith Collection** (Smithsonian National Museum of Asian Art Archives, identifier **FSA.A.04**).

The source is the ArchivesSpace EAD 2002 finding aid in [`srcdata/FSA.A.04-ead.xml`](srcdata/FSA.A.04-ead.xml). The public hierarchical rendering of the same data is [SOVA FSA.A.04](https://sova.si.edu/record/fsa-a-04). This repository turns that finding aid into Linked Open Data: archival box/folder structure, agents, places, subjects, a digitization flag, and Smithsonian IIIF access points, reconciled to **AAT**, **TGN**, **LCSH/LCNAF**, and **Wikidata**.

Collection ARK: <https://n2t.net/ark:/65665/dc3c8c950fe-250b-40df-b8c7-bcf788073968>

## Why this collection

Smith (1897–1970) documented Islamic architecture in Iran in the 1930s and spent the rest of his career building the **Islamic Archives**: photographs, lantern slides, 35 mm slides, negatives, notebooks, correspondence, and architectural plans covering Iran and the wider Islamic world. Subseries 2.12 holds Antoin Sevruguin’s glass negatives and prints. The finding aid already carries a minimum of agent, date, place, and topical encoding. The graph keeps that encoding, fills gaps (especially TGN and monument identities), and makes digitization and IIIF queryable.

## Ontology

The stored model is **CIDOC CRM 7.1.3 (OWL)** plus **CRMdig**, with a thin application ontology [`ontology/mbs.ttl`](ontology/mbs.ttl).

| Layer | Prefix | Role |
| --- | --- | --- |
| CIDOC CRM 7.1.3 | `crm:` | Things, people, places, time-spans, production, types |
| CRMdig | `crmdig:` | Digitization process and digital surrogates |
| Application profile | `mbs:` | Archival level, box/folder, `digitized` flag, IIIF convenience properties |
| SKOS | `skos:` | Concepts |
| PROV-O | `prov:` | (reserved) reconciliation provenance |
| DCTERMS / RDFS | `dct:` `rdfs:` | Labels and identifiers |

[Records in Contexts (RiC-O)](https://www.ica.org/standards/RiC/ontology) and [Linked Art](https://linked.art/) are alignments, not the native graph. `mbs:ArchivalComponent` is declared `owl:equivalentClass` `rico:RecordSet` so an export is possible later.

CRM is the native model because the collection is event-centred cultural heritage (making a photograph, field research in Isfahan, acquiring Sevruguin plates, digitization at the Smithsonian). The archival tree is expressed with CRM composition (`P106` for information objects, `P46` for physical units) plus `mbs:archivalLevel`.

### Two nodes per EAD component

Each series, subseries, file, or item is:

1. an **intellectual** `mbs:ArchivalComponent` (`crm:E73_Information_Object`)
2. a **physical** `mbs:PhysicalComponent` (`crm:E22_Human-Made_Object`)

A glass negative is not the Friday Mosque it depicts. The mosque is a separate `crm:E22` built work, linked with `crm:P67_refers_to` / `crm:P138_represents`, and reconciled to Wikidata (Jameh Mosque of Isfahan `Q1227533`) and AAT mosques (`aat:300007691`).

The EAD document itself is `mbs:FindingAid` / `crm:E31_Document`.

Full field mapping: [`docs/mappings.md`](docs/mappings.md) and [`mappings/ead-to-crm.yml`](mappings/ead-to-crm.yml).

### Box, folder, digitized, IIIF

- `container[@type=Box|Folder]` → `mbs:Box` / `mbs:Folder`. The physical unit `mbs:housedIn` the folder; the folder `mbs:housedIn` the box.
- `mbs:digitized true` **if and only if** the component has an EAD `<dao>`.
- Digitized **`file`** units are PDFs. Access is the EDAN slideshow `https://edan.si.edu/slideshow/viewer/?eadrefid=FSA.A.04_{ref}`. Each PDF page is a separate IDS JPEG with its own IIIF Manifest `https://ids.si.edu/ids/manifest/{page-IDS-ID}` (`mbs:PdfSurrogate` → `mbs:hasPage` → `mbs:PdfPage`). Page IDS ids are harvested (`python -m pipeline.cli slideshow`) or listed in `data/iiif-pages.yml`; until then `mbs:pageManifestsPending true`.
- Digitized **`item`** units are single JPEGs: viewer `https://ids.si.edu/ids/deliveryService?id={ID}` and manifest `https://ids.si.edu/ids/manifest/{ID}` (`mbs:JpegSurrogate`).
- Smithsonian Image API: `https://ids.si.edu/ids/iiif/{ID}`. The pipeline does not invent page IDS identifiers. `--probe-iiif` sets `mbs:iiifResolved` from a live HTTP check.

### Namespaces and URIs

Instance resources use the hash namespace **`kg:`** (`https://w3id.org/sova/fsa_a_04#`) so Turtle serializes prefixed names instead of long angle-bracket IRIs. Local names use underscores (no hyphens).

```turtle
@prefix kg:     <https://w3id.org/sova/fsa_a_04#> .
@prefix mbs:    <https://w3id.org/sova/fsa_a_04/ontology#> .
@prefix crm:    <http://www.cidoc-crm.org/cidoc-crm/> .
@prefix crmdig: <http://www.ics.forth.gr/isl/CRMdig/> .
@prefix lang:   <http://id.loc.gov/vocabulary/iso639-2/> .

kg:event_digitization_fs_fsa_a_04 a crmdig:D2_Digitization_Process ;
    crm:P108_has_produced kg:digital_fs_fsa_a_04 .
```

| Resource | CURIE |
| --- | --- |
| Component | `kg:component_{ead-ref}` |
| Physical unit | `kg:physical_{ead-ref}` |
| Box / folder | `kg:box_{n}` / `kg:folder_{n}_{m}` |
| Agent | `kg:agent_Q{id}` when Wikidata is known |
| Place | `kg:place_tgn_{id}` when TGN is known |
| Linguistic note | `kg:note_{ref}_{ead-element}_{n}` |
| Digital object | `kg:digital_{ids-id}` |
| Islamic Archives (parent holding) | `kg:collection_islamic_archives` |

Smithsonian ARKs remain `owl:sameAs` full IRIs. SOVA pages are `mbs:sovaUrl` / `rdfs:seeAlso` (`https://sova.si.edu/record/fsa.a.04/{ref}`).

### File versus item (media type)

EAD `@level` is not only hierarchy depth. In this collection:

- **`file`** (`mbs:FileUnit` / `mbs:DocumentaryFile`) is an aggregating documentary unit — a correspondence folder, a dossier of mixed papers. Typed with AAT *files (document groupings)* (`aat:300027182`).
- **`item`** (`mbs:ItemUnit` / `mbs:DiscreteItem`) is a single resource. Media type is taken from `genreform`, `physdesc/extent@type` (glass negatives, albumen prints, …), or the title (photograph, drawing, notebook, plan).

### Islamic Archives (parent holding)

EAD `corpname` **Islamic Archives** names a larger holding, not a corporate body. FSA.A.04 is one sub-collection of that holding (`kg:collection_islamic_archives` `mbs:hasSubCollection` `kg:component_FSA.A.04`). Further sub-collections of the Islamic Archives will be attached the same way.

### Linguistic descriptions

Every EAD prose field — `abstract`, `scopecontent`, `bioghist`, `arrangement`, access/use restrictions, custodial history, `odd`, and related notes — is a `crm:E33_Linguistic_Object` linked by `mbs:hasLinguisticObject`. `langmaterial` becomes `crm:P72_has_language` (`lang:eng`, `lang:fre`, …). Titles are `crm:E35_Title`.

## Source data

The EAD is DACS-compliant, produced in ArchivesSpace (export dated 2026-10-15). Structure:

- **Series 1** Papers (1.1 biographic … 1.8 Katharine Dennis Smith)
- **Series 2** The Islamic Archives (2.1 history … 2.12 Sevruguin photographs)
- **Series 3** Outsize and miscellaneous (map-case, rolled items, freezer, Smithsonian copy negatives)

Levels used: `collection`, `series`, `subseries`, `file`, `item`. Housing is almost always Box + Folder; Series 3 also uses Item locations.

Authority encoding already in the EAD (uneven):

- Wikidata Q-ids on many `persname` values
- LCSH / LCNAF on subjects and some places (mix of full URIs and bare labels)
- AAT on `genreform`. EAD “Glass negatives” is mapped to wet collodion negatives (`aat:300134674`), with generic glass negatives (`aat:300010898`) as SKOS broader and dry collodion (`aat:300241140`) as related.
- **No TGN** in the source — spatial enhancement is a pipeline goal
- Inline `persname` / `geogname` in titles (Masjid-i Jomeh, Isfahan, Palmyra, …) are harvested in addition to `<controlaccess>`

Digitization appears as:

1. Direct IDS images, e.g. Sevruguin `https://ids.si.edu/ids/deliveryService?id=FS-FSA_A.4_2.12.GN.00.02-000004`
2. EDAN slideshows, e.g. Masjid-i Jomeh folder `https://edan.si.edu/slideshow/viewer/?eadrefid=FSA.A.04_ref7856`

## Repository layout

```
srcdata/FSA.A.04-ead.xml     EAD source of truth
ontology/mbs.ttl             Local OWL application profile
ontology/catalog.ttl         Prefix / import catalog
mappings/ead-to-crm.yml      Machine mapping table
docs/mappings.md             Human mapping + Turtle examples
pipeline/                    Python transform
vocab/seed.yml               High-confidence AAT/TGN/LCSH/Wikidata seeds
vocab/cache/                 Extracted entities + reconciliation (generated)
data/rdf/*.ttl               CIDOC CRM graph (generated)
data/reports/                Inventory and SHACL reports (generated)
shapes/mbs.shacl.ttl         SHACL
queries/*.rq                 Example SPARQL
tests/test_parser.py         Parser / IIIF smoke tests
```

## Install and run

Python 3.10+ from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```powershell
python -m pipeline.cli all
```

Stages (any one can be run alone):

| Stage | Command | Output |
| --- | --- | --- |
| Inventory | `python -m pipeline.cli inventory` | `data/reports/inventory.json` |
| Extract | `python -m pipeline.cli extract` | `vocab/cache/entities.json` |
| Reconcile | `python -m pipeline.cli reconcile` | `vocab/cache/reconciled.json` |
| Map to CRM | `python -m pipeline.cli map` | `data/rdf/*.ttl` |
| Slideshow pages | `python -m pipeline.cli slideshow` | `vocab/cache/slideshow-pages.json` |
| SHACL | `python -m pipeline.cli validate` | `data/reports/shacl-report.txt` |

Optional flags:

- `--live` — call Getty SPARQL for places still unmatched (default is **offline**: EAD URIs + `vocab/seed.yml`)
- `--probe-iiif` — HTTP-check derived IIIF `info.json` / manifest URLs
- `--fetch-slideshow` — harvest per-page IDS ids from EDAN slideshow HTML
- `--limit N` — map only the first N components (useful while developing)

Smoke tests:

```powershell
python tests/test_parser.py
```

## Reconciliation

1. Keep every `@authfilenumber` already in the EAD (Wikidata Q-ids, `id.loc.gov`, `vocab.getty.edu/aat`).
2. Match labels against [`vocab/seed.yml`](vocab/seed.yml) (Iran/Isfahan/Tehran/Palmyra TGN, Masjid-i Jomeh Wikidata, AAT for glass negatives, correspondence, lantern slides, …).
3. Harvest inline names in titles and notes, not only `<controlaccess>`.
4. Write a reviewable cache under `vocab/cache/` so rebuilds are deterministic.
5. Unmatched strings remain first-class local resources (`mbs:sourceString`).

`--live` is additive and conservative. It does not overwrite seed or EAD URIs.

## SPARQL examples

Load `ontology/mbs.ttl` and `data/rdf/*.ttl` into a store (Oxigraph, GraphDB, Fuseki, or `rdflib`).

Digitized items that refer to a place, with IIIF:

```sparql
PREFIX mbs:  <https://w3id.org/sova/fsa_a_04/ontology#>
PREFIX crm:  <http://www.cidoc-crm.org/cidoc-crm/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?title ?placeLabel ?manifest WHERE {
  ?c a mbs:ArchivalComponent ; mbs:digitized true ; rdfs:label ?title ;
     crm:P67_refers_to ?p .
  ?p a crm:E53_Place ; rdfs:label ?placeLabel .
  OPTIONAL { ?c mbs:hasDigitalObject ?d . ?d mbs:iiifManifest ?manifest }
}
```

More queries:

- [`queries/masjid.rq`](queries/masjid.rq) — Masjid / mosque titles and digitization
- [`queries/boxes-architectural.rq`](queries/boxes-architectural.rq) — boxes/folders of plans and drawings
- [`queries/agents-wikidata.rq`](queries/agents-wikidata.rq) — agents with Wikidata links
- [`queries/digitized-by-place.rq`](queries/digitized-by-place.rq) — digitized components by place
- [`queries/islamic-archives.rq`](queries/islamic-archives.rq) — Islamic Archives parent holding and sub-collections
- [`queries/digitized-access.rq`](queries/digitized-access.rq) — PDF slideshow files vs JPEG items

## Generated RDF files

| File | Contents | Triples |
| --- | --- | --- |
| `data/rdf/collection.ttl` | Collection node, finding aid, Islamic Archives holding | 603 |
| `data/rdf/series-1.ttl` | Series 1 Papers | 62,944 |
| `data/rdf/series-2.ttl` | Series 2 Islamic Archives | 365,224 |
| `data/rdf/series-3.ttl` | Series 3 outsize / miscellaneous | 4,108 |

Agents, places, and concepts are written into the series file that first mentions them. Rebuild time is a few minutes (`python -m pipeline.cli map`).

Current inventory (`python -m pipeline.cli inventory` against the 2026-10-15 EAD):

| | Count |
| --- | --- |
| Components | 4131 |
| collection / series / subseries / file / item | 1 / 3 / 132 / 625 / 3370 |
| Digitized (`dao` present) | 1195 (861 IDS images, 334 EDAN slideshows) |
| Not digitized | 2936 |
| Components with ARK | 4131 (all) |
| Distinct boxes | 234 |
| Named entities with URI / without | 6692 / 7080 |
| Unique agents / places / subjects / genres extracted | 1053 / 452 / 59 / 8 |
| RDF triples (collection + 3 series) | 432,879 |
| FileUnit / ItemUnit | 625 / 3,370 |

Housing types in the EAD: Box, Folder, Oversize, Roll, Map-rolled, Item.

## Licence and citation

- **Code** in this repository: [GNU GPL v3](LICENSE).
- **Finding aid text and archival metadata**: Smithsonian / National Museum of Asian Art Archives. Permission to publish, quote, or reproduce collection materials must be secured from the repository ([conditions of use](https://sova.si.edu/record/fsa-a-04)).
- **Many Smithsonian digital images** are released under CC0; check the object page. This project stores URIs, not image binaries.

Preferred citation of the collection:

> The Myron Bement Smith Collection, FSA A.04. National Museum of Asian Art Archives. Smithsonian Institution, Washington, D.C. Gift of Katharine Dennis Smith.

Finding aid author: Dr. Elizabeth Graves (2015). Related SOVA collections (Herzfeld FSA.A.06, Bier, Sevruguin albums) are recorded as `relatedmaterial` in the EAD and are out of scope for v1 except as textual notes.

## Scope of v1

In scope: full EAD parse, CRM mapping of every component, box/folder, digitized flag, derived IIIF URIs, seed reconciliation to AAT/TGN/LCSH/Wikidata, SHACL, example SPARQL, public README.

Out of scope: OCR, computer vision, a hosted SPARQL endpoint, rewriting Smithsonian manifests, transforming related collections.
