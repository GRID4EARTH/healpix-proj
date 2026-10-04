# Standardising the HEALPix CRS: EPSG and GeoTIFF

This document looks at how a HEALPix CRS (`+proj=healpix`) could be stored in
a GeoTIFF in a standard way, so that a `.tif` keeps its CRS without the
`.aux.xml` side-car (see [investigation.md](investigation.md), §3.5). It
covers the current state of the registries and standards, the EPSG and
GeoTIFF change procedures, and the options.

Status as of 2026-10-05. Statements marked **[fact]** come from the linked
sources; **[inference]** marks our own reading of them; **unverified** marks
open questions.

## Summary

1. No registry has a HEALPix (or rHEALPix) projection method or CRS: not
   EPSG, ESRI or IAU_2015. There is no record of a past EPSG proposal.
2. GeoTIFF 1.1 projection method codes are GeoTIFF's own list (1–27).
   Adding one needs a revision of the standard, and the GeoTIFF SWG has
   declined such additions before.
3. **[inference]** If EPSG registered a projected CRS (e.g. "WGS 84 /
   HEALPix") with a code ≤ 32766, GeoTIFF could reference it through
   `ProjectedCRSGeoKey` without any revision, and GDAL would write it with
   its current code. PROJ would need an EPSG-method → `healpix` mapping.
4. EPSG has rejected grid systems (2010) and the Goode Homolosine (2019).
   A proposal should present HEALPix as one fully specified equal-area
   projection, not as a DGGS, and show use by several organisations. The
   coordinate-scale question in
   [PROJ#4789](https://github.com/OSGeo/PROJ/issues/4789) should be settled
   first.
5. **[inference]** Short term: keep the current workaround and use CF /
   GeoZarr as the primary formats. In parallel, prepare an EPSG request, and
   support the GeoTIFF "embed WKT" proposals for the cases EPSG cannot cover.

## 1. Current state

### EPSG [fact]

- An EPSG API search for "healpix" returns no coordinate operation method
  (217 methods in total) and no CRS.
  - <https://apps.epsg.org/api/v1/CoordOperationMethod/?keywords=healpix>
  - <https://apps.epsg.org/api/v1/CoordRefSystem/?keywords=healpix>
- The change-request log has nothing for healpix, rHEALPix, HPX, Calabretta
  or DGGS: <https://apps.epsg.org/api/v1/Change/?keywords=healpix>
- The closest methods are Equal Earth (1078), Lambert Cylindrical Equal Area
  (9835/9834), Lambert Azimuthal Equal Area (9820/1027) and Albers (9822).
- EASE-Grid 2.0 Global (EPSG:6933) is registered as a plain projected CRS on
  method 9835, without any grid semantics:
  <https://apps.epsg.org/api/v1/ProjectedCrs/6933/>
- Current dataset version: v13.103, 2026-09-11 (<https://epsg.org/whatsnew.html>).
  `proj.db` of PROJ 9.8.0 (EPSG v12.049) has no "heal" entry in any
  authority.

### ESRI, IAU [fact]

- ESRI: not in the ArcGIS Pro list of supported projections
  (<https://doc.esri.com/en/arcgis-pro/latest/help/mapping/properties/list-of-supported-map-projections.html>)
  nor in the projection engine list
  (<https://raw.githubusercontent.com/Esri/projection-engine-db-doc/main/csv/pe_list_projection.csv>).
- IAU_2015 (planetary CRSs in PROJ and at OGC) uses Equirectangular,
  Sinusoidal, polar stereographic, Mollweide, Robinson, Mercator and a few
  "AUTO" projections; no HEALPix
  (<https://www.hou.usra.edu/meetings/lpsc2025/pdf/1659.pdf>).

### OGC DGGS [fact]

- Topic 21 Part 1 (OGC 20-040r3 = ISO 19170-1:2021) builds on ISO 19111 and
  ISO 19112; rHEALPix only appears as an example figure, and "EPSG" does not
  appear (<https://docs.ogc.org/as/20-040r3/20-040r3.html>).
- OGC API – DGGS Part 1 (21-038r1, published 2025-10-03), informative Annex
  B.8, defines the HEALPix DGGRS with
  `"projString": "+proj=healpix +ellps=WGS84"`, ellipsoid EPSG:7030, and
  conversion to authalic latitude before projection. The projString is
  described as a stop-gap until the CRS is registered and referenceable by
  URI. (<https://docs.ogc.org/is/21-038r1/21-038r1.html>)
- The OGC DGGRS register has had HEALPix and rHEALPix as "valid" since
  2026-02-02: <https://www.opengis.net/def/dggrs/OGC/1.0/HEALPix>

### GDAL / PROJ discussions [fact]

- No GDAL, libgeotiff or opengeospatial/geotiff issue mentions HEALPix.
- A 2013 gdal-dev thread on rHEALPix in GeoTIFF was answered with
  `+wktext`: <https://lists.osgeo.org/pipermail/gdal-dev/2013-July/036703.html>
- [PROJ#4789](https://github.com/OSGeo/PROJ/issues/4789) (open, 2026-06):
  (r)HEALPix output coordinates are not true metres; they carry a constant
  factor √(8/(3π)) ≈ 0.9213.

## 2. EPSG registration

### Procedure [fact]

- The EPSG Dataset is maintained by the Geodesy Subcommittee of the IOGP
  Geomatics Committee, which normally meets monthly except in August and
  December (<https://epsg.org/home.html>; GN 7-1 §4.1,
  <https://www.iogp.org/bookstore/wp-content/uploads/sites/2/woocommerce_uploads/2017/01/373-07-1.pdf>).
- Anyone can submit: fill in the data-submission template (Excel) and email
  it to feedback@epsg.org, or point to a public web page with the
  information. No account is needed. Requests are acknowledged within about
  a working week; complete requests are aimed to be processed within one
  release cycle (<https://epsg.org/dataset-change-requests.html>).
- For a new method the template asks for the name, the parameters, at least
  one test point offset from the projection origin, and the full formulas as
  an attachment.
- The Equal Earth method record shows what a published method contains:
  formulas, a peer-reviewed source, a forward and reverse WGS 84 example
  with intermediate values, and parameters 8802/8806/8807
  (<https://apps.epsg.org/api/v1/CoordOperationMethod/1078/>). Formulas are
  also added to Guidance Note 7-2 (<https://epsg.org/guidance-notes.html>).

### Scope and precedents [fact]

GN 7-1 §4.2: the focus is national systems and systems "used across multiple
organisations"; small-scale "atlas" projections get minimal coverage; a
projection is included only when a CRS or coordinate operation uses it.

| Request | Outcome | Time | Source |
|---|---|---|---|
| 2018.048 Equal Earth (Esri) | accepted: method 1078, CRSs 8857–8859 | ~6.5 weeks | <https://apps.epsg.org/api/v1/Change/2018.048/> |
| 2007.078 Lambert Cylindrical Equal Area | accepted (ellipsoidal form preferred); user-specific CRS in the same request rejected | ~10 weeks | <https://apps.epsg.org/api/v1/Change/2007.078/> |
| 2023.004 Equidistant Conic | accepted | ~5.5 months | <https://apps.epsg.org/api/v1/Change/2023.004/> |
| 2019.068 Goode Homolosine | rejected: "no standard for the projection interruption(s)" | — | <https://apps.epsg.org/api/v1/Change/2019.068/> |
| 2010.077 / 2010.078 MGRS, Marsden squares, c-squares | rejected: grid systems are out of scope | — | <https://apps.epsg.org/api/v1/Change/2010.078/> |
| 2005.09, 2006.32 atlas / ESRI world projections | not added: wide use not shown | — | <https://apps.epsg.org/api/v1/Change/2005.09/> |

EPSG released new versions almost every month in 2026.

### Parameters

- **[fact]** PROJ `+proj=healpix` takes `lon_0`, `x_0`, `y_0`, `rot_xy` and
  the ellipsoid; `north_square` / `south_square` are rHEALPix only. On an
  ellipsoid it converts to authalic latitude, applies the unit-sphere HPX
  projection and scales by the authalic radius R_q
  (<https://proj.org/en/stable/operations/projections/healpix.html>,
  <https://github.com/OSGeo/PROJ/blob/master/src/projections/healpix.cpp>).
- **[fact]** PROJ maps EPSG methods to its implementations in
  `src/iso19111/operation/parammappings.cpp` (e.g. Equal Earth → `eqearth`);
  there is no HEALPix entry.
- **[inference]** An EPSG "HEALPix" method would need:
  - Longitude of natural origin (8802) ↔ `lon_0`
  - False easting (8806) ↔ `x_0`
  - False northing (8807) ↔ `y_0`
  - the ellipsoid from the base geodetic CRS, as for every EPSG method.
- **[inference]** The polar facet layout (H = 4, K = 3) is fixed inside the
  method. rHEALPix would be a separate method with polar-square parameters.
- **[inference]** `rot_xy` should stay out of the CRS. The 45° rotation
  belongs in the GeoTIFF affine transform (`ModelTransformationTag`), as in
  [`scripts/healpix_geotiff.py`](../scripts/healpix_geotiff.py).
- **[inference]** The authalic latitude, R_q and the inverse series are
  already in the Equal Earth record and GN 7-2, so they can be reused.

## 3. GeoTIFF

### GeoTIFF 1.1 [fact]

Source: <https://docs.ogc.org/is/19-008r4/19-008r4.html>

- `ProjMethodGeoKey` (3075):
  - 1–27 are GeoTIFF's own method codes (Req 27.3). 28–32766 are reserved,
    32767 is user-defined and 32768–65535 are private.
  - The standard notes that it does not reference EPSG method codes.
  - There is no HEALPix code.
- `ProjectedCRSGeoKey` (3072):
  - 1024–32766 are EPSG projected CRS codes (Req 12.4).
  - Codes added to EPSG after publication may be used (Annex B.3.1).
  - User-defined projections are not guaranteed to be interoperable (Annex
    B.3.2).
- A new method code needs a revision of the standard. The SWG closed
  [#3](https://github.com/opengeospatial/geotiff/issues/3) and
  [#89](https://github.com/opengeospatial/geotiff/issues/89), treating EPSG
  codes plus user-defined CRSs as sufficient. There is no register of GeoKey
  codes ([#111](https://github.com/opengeospatial/geotiff/issues/111)).

### GeoTIFF SWG [fact]

- Repository: <https://github.com/opengeospatial/geotiff>. Its README says
  work is aimed at version 1.2.
- Charter conveners: Emmanuel Devys (IGN), Chuck Heazel, Even Rouault
  (<https://github.com/opengeospatial/geotiff/blob/master/GeoTIFF_charter/GeoTIFF_swg_charter.adoc>).
  Joan Masó speaks as chair in #56.
- Changes are proposed through GitHub issues or the OGC change request form:
  <https://portal.ogc.org/public_ogc/change_request.php>
- [#56](https://github.com/opengeospatial/geotiff/issues/56) "GeoTIFF v2:
  embed WKT" is open:
  - In 2025 consensus on embedding WKT was reported, even though it breaks
    compatibility.
  - In 2026-05 Esri asked for an official method too.
  - GDAL would use 2.0 only when 1.x cannot express the CRS.
- Open PR [#121](https://github.com/opengeospatial/geotiff/issues/121) would
  let the CRS keys point to an `AUTHORITY:CODE` or WKT string.

### GDAL / libgeotiff [fact]

Source:
<https://github.com/OSGeo/gdal/blob/master/frmts/gtiff/gt_wkt_srs.cpp>,
`gtiffdataset_write.cpp`, `gtiffdataset_read.cpp`

- **Writing:**
  - A projected CRS with an EPSG code is written as
    `ProjectedCSTypeGeoKey=<code>` only, whatever its method.
  - Otherwise the CRS is exported to WKT1. If that contains `custom_proj4`
    (as `+proj=healpix` does), the CRS goes to PAM (`.aux.xml`).
  - The ESRI_PE retry runs only when the WKT1 export fails.
- **Reading:** `ProjectedCSTypeGeoKey` is resolved with `importFromEPSG`.
  GDAL never reads a CRS from `GDAL_METADATA`, so the WKT stored there is
  only used by our own scripts.
- **[inference]** This is why `GEOTIFF_KEYS_FLAVOR=ESRI_PE` and
  `GEOTIFF_VERSION=1.1` did not help: the HEALPix WKT1 export succeeds (as
  `custom_proj4`), so the retry never runs.
- **[inference]** After an EPSG registration, GDAL itself should need no
  change. PROJ needs the method constants, a `parammappings.cpp` entry and
  an updated `proj.db`. Any CRS other than the registered one (another
  ellipsoid or `lon_0`) would still fall back to PAM.

## 4. Evidence of use

EPSG asks for systems used across several organisations, so the request
should list them. **[fact]** unless marked otherwise:

- **EUMETSAT / NOAA / JMA – GEO-Ring** (test data V1, 16 Apr 2026):
  - It merges GOES ABI, Himawari AHI and Meteosat SEVIRI for 2019–2024 at
    about 5 km² and 30 min. The grid is nested HEALPix, stored as Zarr and
    read with xdggs.
  - The page notes that on an ellipsoid each point is transformed to the
    authalic sphere, "properly handled by the widely used PROJ library".
  - It cites Calabretta & Roukema 2007 and Górski et al. 2005.
  - Sources: <https://user.eumetsat.int/resources/user-guides/geo-ring-test-data>;
    Heidinger et al. 2026, BAMS 107, E291–E308,
    <https://doi.org/10.1175/BAMS-D-24-0161.1>
- **Destination Earth Climate DT (ECMWF and partners):**
  - ICON, IFS-NEMO and IFS-FESOM output goes to a common HEALPix grid, H1024
    nested for 5 km and H512 for 10 km.
  - Source: Doblas-Reyes et al. 2026, GMD 19, 2821–2848,
    <https://doi.org/10.5194/gmd-19-2821-2026>
- **WCRP Global km-scale Hackathon 2025** (May 2025, about 700
  participants at 10 nodes):
  - Output from 6–8 km-scale models was put on a common HEALPix grid and
    stored as Zarr.
  - The paper describes HEALPix as a spherical grid (Górski et al. 2005) and
    does not mention an ellipsoid or authalic latitude. Kilometre-scale model
    output on HEALPix is spherical today.
  - Source: Gettelman et al. 2026, "Hacking Kilometer-Scale Models: A
    Participative Model for Climate Information", BAMS 107(7),
    <https://doi.org/10.1175/BAMS-D-25-0183.1> (accepted manuscript:
    <https://www.osti.gov/pages/biblio/3399558>)
- **Kilometre-scale hackathon 2027 (draft statement):**
  - The "Specification Toward a Unified Grid System Standard for Earth
    Observation and Modelling" (draft 2026.07.18_00) proposes ellipsoidal
    HEALPix: geodetic latitude mapped to authalic latitude on an explicitly
    identified ellipsoid, with CF 1.13 HEALPix grid-mapping metadata.
  - Its aim is to analyse km-scale simulations together with satellite
    observations.
  - Source: <https://pad.gwdg.de/JLI_XMEYQ_GAzHZPIzthfw> (a working draft;
    cite a stable version once there is one).
- **GRID4EARTH** (ESA contract 4000147951/25/I-NS; Ifremer, CNRS, University
  of Tartu, GEORODE, LifeWatch ERIC):
  - It builds infrastructure for Copernicus Sentinel and Destination Earth
    data on ellipsoidal HEALPix (authalic sphere on WGS84).
  - The ecosystem (healpix-geo, healpix-resample, healpix-plot,
    healpix-analyse) has been applied to Sentinel-2, Sentinel-3, ERA5, CAMS
    and DestinE Climate DT output. It follows CF 1.13 and the Zarr DGGS
    convention.
  - Sources: Odaka et al. 2026, "Grid4Earth: An Open-Source Python Ecosystem
    for Geospatial Data Integration Using an Ellipsoidal HEALPix DGGS",
    ISPRS Archives L-4/W1-2026, 189–195,
    <https://doi.org/10.5194/isprs-archives-L-4-W1-2026-189-2026>;
    <https://grid4earth.eu/>
- **Standards that already name HEALPix:**
  - OGC API – DGGS and the OGC DGGRS register (§1).
  - CF Conventions 1.13 (2025-12) Appendix F, `grid_mapping_name = healpix`.
    Latitudes on an ellipsoid are authalic.
    (<https://github.com/cf-convention/cf-conventions/pull/605>)
  - FITS WCS "HPX" (Calabretta & Roukema 2007,
    <https://doi.org/10.1111/j.1365-2966.2007.12297.x>).
- **Software:** PROJ, healpix-geo, xdggs.

**[inference]** Several of these use HEALPix on a sphere or only as a grid.
For EPSG, the strongest evidence is ellipsoidal use through the authalic
sphere with PROJ-compatible coordinates: GEO-Ring, GRID4EARTH, OGC
API – DGGS and CF 1.13. The km-scale community's planned move from sphere
to ellipsoid shows that the user base is growing.

## 5. Options

The assessments in this table are **[inference]**.

| | Effort | Time | Effect | Risks |
|---|---|---|---|---|
| (a) EPSG registration | High: formulas, examples, evidence, PROJ PR | 1.5–10 months to a decision (precedents), then a PROJ release and uptake | A `.tif` keeps its CRS in GDAL/PROJ-based software (QGIS, rasterio, …); Esri etc. depend on their own support | Rejection as a grid system or niche; only the registered CRS is covered; code ≤ 32766 not confirmed |
| (b) New GeoTIFF method code | High | Long; the SWG has declined this | Needs a revision plus libgeotiff and GDAL work | Unlikely. The realistic form is supporting #56 / #121 |
| (c) Keep `.aux.xml` + TIFF metadata | None | Now | GDAL reads it when the `.aux.xml` travels with the file | A lone `.tif` loses its CRS |
| (d) CF / GeoZarr as primary formats, GeoTIFF for export | Medium | Now to months | CF 1.13 has `healpix`; GeoZarr carries WKT2 / PROJJSON (<https://github.com/zarr-conventions/geo-proj>) | Does not reach GeoTIFF-only users |

## 6. Next steps

1. **Settle the coordinate scale** in
   [PROJ#4789](https://github.com/OSGeo/PROJ/issues/4789) with the PROJ
   maintainers, so the EPSG formulas and PROJ agree.
2. **Pre-submission enquiry** to feedback@epsg.org. Ask:
   - whether HEALPix fits the scope as a projection;
   - whether the projected CRS code can be ≤ 32766;
   - whether `rot_xy` can be left out.
3. **Collect the evidence** in §4. Possibly ask the OGC DGGS SWG for a
   supporting statement, since OGC API – DGGS expects a registered CRS URI.
4. **Submit** the template to feedback@epsg.org with:
   - the formula document (forward and inverse, polar facets, authalic
     latitude, R_q);
   - references (Calabretta & Roukema 2007, Górski et al. 2005);
   - a WGS 84 worked example with intermediate values, built from this
     repository's tests;
   - the proposed CRS "WGS 84 / HEALPix".
5. **Prepare the PROJ PR** (constants, `parammappings.cpp`, tests) and open
   it once EPSG publishes, together with the `proj.db` update.
6. **Check GDAL:** a `.tif` with the registered CRS should carry only
   `ProjectedCRSGeoKey` and read back in GDAL, QGIS and rasterio.
7. **GeoTIFF SWG:** add the HEALPix use case to #56 / #121 for the CRSs EPSG
   will not cover (other ellipsoids, other `lon_0`).
8. **Meanwhile:** keep (c), and use CF 1.13 / GeoZarr as primary formats (d).

## Open questions

- Whether EPSG would accept HEALPix, and which code range it would assign.
- What the admission criteria in GN 7-6 say (the download requires a form).
- Any informal IOGP or OGC Planetary DWG discussion of HEALPix.
- The current GeoTIFF SWG meeting cadence and charter status.
- Whether hand-written `GTModelTypeGeoKey=32767` plus an
  "ESRI PE String = <WKT>" citation would be read by GDAL. Untested, and not
  standard.
