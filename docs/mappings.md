# EAD to CIDOC CRM mapping

This document is the human-readable form of `mappings/ead-to-crm.yml`. It records how `srcdata/FSA.A.04-ead.xml` becomes RDF.

## Namespaces

Instance IRIs use the hash namespace `kg:` (`https://w3id.org/sova/fsa_a_04#`) so Turtle writes CURIEs such as `kg:event_digitization_fs_fsa_a_04` instead of angle-bracket paths. Local names use underscores.

| Prefix | IRI |
| --- | --- |
| `kg:` | `https://w3id.org/sova/fsa_a_04#` |
| `mbs:` | `https://w3id.org/sova/fsa_a_04/ontology#` |
| `crm:` | `http://www.cidoc-crm.org/cidoc-crm/` |
| `crmdig:` | `http://www.ics.forth.gr/isl/CRMdig/` |
| `lang:` | `http://id.loc.gov/vocabulary/iso639-2/` |

## Two individuals per component

Every EAD `<c>` (and the collection `<archdesc>`) is two CRM things:

| Individual | Class | CURIE |
| --- | --- | --- |
| Intellectual | `mbs:ArchivalComponent` subclass of `crm:E73_Information_Object` | `kg:component_{ref}` |
| Physical | `mbs:PhysicalComponent` subclass of `crm:E22_Human-Made_Object` | `kg:physical_{ref}` |

They are linked by `mbs:hasPhysicalUnit`. The finding aid is a third thing: `mbs:FindingAid` / `crm:E31_Document`.

This split is required for photographs: the glass negative is not the mosque it depicts.

## Hierarchy

| EAD | RDF |
| --- | --- |
| Nested `<c>` | Parent `crm:P106_is_composed_of` child (information) |
| Nested `<c>` | Parent physical `crm:P46_is_composed_of` child physical |
| `@level` | `mbs:archivalLevel` (`collection`, `series`, `subseries`, `file`, `item`) |
| `@level=file` | `mbs:FileUnit` + physical `mbs:DocumentaryFile` + AAT files (document groupings) `aat:300027182`. A file is an aggregating documentary media type (correspondence folders, mixed papers). |
| `@level=item` | `mbs:ItemUnit` + physical `mbs:DiscreteItem`. Media type from `genreform`, `physdesc/extent@type`, or title (photograph, glass negative, drawing, notebook, …). |
| ArchivesSpace `@id` | `mbs:eadRef` |
| SOVA page | `mbs:sovaUrl`, `rdfs:seeAlso` |
| ARK | `crm:P48_has_preferred_identifier` + `owl:sameAs` |

RiC-O alignment: `mbs:ArchivalComponent owl:equivalentClass rico:RecordSet` in the ontology (class level).

## Description fields

| EAD | CRM path |
| --- | --- |
| `unittitle` | `rdfs:label` ; `crm:P1_is_identified_by` |
| `unitdate/@normal` | `crm:E12_Production` → `crm:P4_has_time-span` → `crm:E52_Time-Span` (`P82a`/`P82b`) |
| `origination` Creator | Production `crm:P14_carried_out_by` `crm:E21_Person` / `E74_Group` |
| role photographer (`pht`) | same production, technique photography |
| role collector (`col`) | `crm:E10_Transfer_of_Custody` |
| `geogname` | `crm:P67_refers_to` `crm:E53_Place` |
| monument in title (Masjid-i Jomeh) | additional `crm:E22` built work + `crm:P138_represents` |
| `subject` | `crm:P129_is_about` `crm:E55_Type` |
| `genreform` | `crm:P2_has_type` (AAT) |
| `scopecontent`, `bioghist`, `abstract`, `odd`, restrictions, and other EAD notes | `crm:E33_Linguistic_Object` via `mbs:hasLinguisticObject`; `rdf:value` holds the full text; `mbs:noteType` records the EAD element; paragraphs are `crm:P148_has_component` |
| `langmaterial/language` | `crm:P72_has_language` `crm:E56_Language` (`lang:eng`, `lang:fre`, …) |
| `unittitle` as linguistic object | `crm:E35_Title` + `crm:P102_has_title` |
| `extent` / dimensions | `crm:P43_has_dimension` `crm:E54_Dimension` |

## Box and folder

| EAD | RDF |
| --- | --- |
| `container[@type=Box]` | `mbs:Box` `kg:box_{n}` |
| `container[@type=Folder]` | `mbs:Folder` `kg:folder_{box}_{n}` |
| `corpname` Islamic Archives | `mbs:HoldingCollection` `kg:collection_islamic_archives`; FSA.A.04 `mbs:isPartOfCollection` that holding |
| `genreform` Glass negatives | `aat:300134674` wet collodion negatives; `skos:broader` `aat:300010898`; `skos:related` `aat:300241140` |
| Folder in box | `mbs:housedIn` + `crm:P46_is_composed_of` |
| Physical unit in folder/box | `mbs:housedIn` |

Series 3 map-case rows use `mbs:StorageItem`.

## Digitization and IIIF

`mbs:digitized true` if and only if the component has a `<dao>` with an `xlink:href`.

| dao pattern | `mbs:digitizationKind` | Digital object |
| --- | --- | --- |
| `ids.si.edu/ids/deliveryService?id={ID}` (EAD **item**) | `mbs:ids_image` / `mbs:JpegSurrogate` | Viewer `deliveryService?id={ID}`; Image API `https://ids.si.edu/ids/iiif/{ID}`; Manifest `https://ids.si.edu/ids/manifest/{ID}` |
| `edan.si.edu/slideshow/...?eadrefid=` (EAD **file**) | `mbs:edan_slideshow` / `mbs:PdfSurrogate` | Slideshow viewer; PDF request `.../viewer/pdf?eadrefid=`; each page `mbs:PdfPage` with its own `ids/manifest/{page-IDS-ID}` |
| none | `mbs:none` | no `D1` |

A `crmdig:D2_Digitization_Process` produces each `D1` from the physical unit. Manifest URIs are **candidates**. `mbs:iiifResolved` is set only when the pipeline is run with `--probe-iiif`.

## Reconciliation

Existing EAD `@authfilenumber` values are kept (`owl:sameAs`). Seed file `vocab/seed.yml` fills TGN, AAT, LCSH, and Wikidata where the EAD is silent (notably TGN, which is absent from the source). Live APIs are opt-in (`--live`).

## Worked example: Masjid-i Jomeh folder (`ref7856`)

EAD: Series 2.2 item, Box 84 Folder 1, EDAN slideshow dao.

RDF sketch:

```turtle
kg:component_ref7856
    a mbs:ArchivalComponent, mbs:ItemUnit, crm:E73_Information_Object ;
    rdfs:label "Persia Geographic File, Isfahan Masjid-i Jomeh, general, sahn, iwans, riwaqs and domes" ;
    mbs:archivalLevel "item" ;
    mbs:eadRef "ref7856" ;
    mbs:digitized true ;
    mbs:digitizationKind mbs:edan_slideshow ;
    mbs:hasPhysicalUnit kg:physical_ref7856 ;
    crm:P67_refers_to kg:place_tgn_7001374 ;
    crm:P138_represents kg:built_isfahan_masjid_i_jomeh ;
    mbs:hasDigitalObject kg:digital_fsa_a_04_ref7856 .

kg:physical_ref7856
    a mbs:PhysicalComponent, mbs:DiscreteItem, crm:E22_Human-Made_Object ;
    mbs:housedIn kg:box_84, kg:folder_84_1 .
```

## Worked example: Sevruguin glass negative (`ref9914`)

EAD: Subseries 2.12.01 item `FSA A.04 2.12.GN.00.02`, IDS image `FS-FSA_A.4_2.12.GN.00.02-000004`, Wikidata photographer Q382319, LCSH Tehran.

RDF sketch:

```turtle
kg:component_ref9914
    a mbs:ArchivalComponent, mbs:ItemUnit ;
    mbs:digitized true ;
    mbs:digitizationKind mbs:ids_image ;
    mbs:hasDigitalObject kg:digital_fs_fsa_a_4_2_12_gn_00_02_000004 .

kg:digital_fs_fsa_a_4_2_12_gn_00_02_000004
    a crmdig:D1_Digital_Object ;
    mbs:iiifImageService "https://ids.si.edu/ids/iiif/FS-FSA_A.4_2.12.GN.00.02-000004"^^xsd:anyURI ;
    mbs:iiifManifest "https://ids.si.edu/ids/manifest/FS-FSA_A.4_2.12.GN.00.02-000004"^^xsd:anyURI .

kg:event_production_ref9914
    a crm:E12_Production ;
    crm:P108_has_produced kg:physical_ref9914 ;
    crm:P14_carried_out_by kg:agent_Q382319 .
```
