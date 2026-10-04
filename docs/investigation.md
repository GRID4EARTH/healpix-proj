# Investigation: can healpix-geo data be written to GeoTIFF?

This document records how the question was investigated and what was found.
The short version is in the [README](../README.md).

## 1. Background

**Starting question:** can data expressed on healpix-geo (an ellipsoid-aware
HEALPix DGGS implementation) be written to a GeoTIFF?

### 1.1 GeoTIFF and HEALPix are structurally different

- GeoTIFF assumes a regular 2-D grid, an affine transform (pixel space ↔
  projected plane coordinates) and a CRS referenced through GeoKeys (e.g. an
  EPSG code).
- HEALPix as used by healpix-geo is a hierarchical cell index on the sphere
  (NESTED / RING / ZUNIQ schemes), not a row/column grid.
- Neither the GeoTIFF nor the EPSG registry has a GeoKey or EPSG code for the
  standard HEALPix projection, so there is no standard way to write it
  "as is".

### 1.2 PROJ already implements an ellipsoidal HEALPix projection

- PROJ (used by GDAL, QGIS, ...) implements `+proj=healpix` (added by Alex
  Raichev around 2011).
- It is the composition *ellipsoid → authalic sphere (equal-area latitude
  conversion) → spherical HEALPix* (the HPX formulas of Calabretta & Roukema
  2007), which is the same construction healpix-geo uses for ellipsoidal
  cell geometry.
- Any ellipsoid can be given (e.g. `+ellps=WGS84`), and both forward and
  inverse are implemented.

### 1.3 rHEALPix as an alternative, and its limits

- Standard HEALPix (the HPX projection) is an *interrupted* projection: a
  Lambert cylindrical equal-area equatorial band plus four interrupted
  Colignon-like facets at each pole. Crossing a facet seam makes real-world
  neighbours jump apart on the plane.
- **rHEALPix** (Gibb, Raichev & Speth) is a derived DGGS designed to remove
  these seams: the polar facets are cut and rearranged into a single
  rectangle without interruptions. This fits GeoTIFF much better and is the
  approach used by DGGSTools.
- But rHEALPix has important limits:
  - Rearranging the polar facets **loses the iso-latitude property**. That
    property is at the core of HEALPix's design and is what makes fast
    spherical harmonic transforms possible (e.g. CMB power spectra).
    rHEALPix favours rectangular GIS compatibility and is not suited to
    spherical harmonic analysis.
  - Cells are refined **3×3 (aperture 9, N_side=3 by default)** instead of
    standard HEALPix's 2×2 (aperture 4); the standard examples of the
    `rhealpixdggs` library use N_side=3. The resolution series and hierarchy
    differ completely, and healpix-geo cell IDs do not map simply to rHEALPix
    cell IDs.
  - Conclusion: healpix-geo (ellipsoidal HEALPix) and rHEALPix look related
    but are different DGGSs. Converting to rHEALPix for GeoTIFF compatibility
    is a re-gridding onto another DGGS, not a format conversion.

### 1.4 Does PROJ's healpix projection match healpix-geo exactly?

If PROJ's `+proj=healpix` (with the ellipsoid correction) is **geometrically
identical** to healpix-geo's ellipsoidal HEALPix, standard HEALPix could be
used as a GeoTIFF CRS directly, keeping iso-latitude, with no conversion to
rHEALPix. This was tested in code.

## 2. Method and results

`healpix-geo` and `pyproj` (PROJ's Python binding) were installed and three
tests were run (`scripts/verify_healpix_proj.py`):

1. **Shape test:** project the 4 vertices (geodetic lon/lat) of healpix-geo
   cells with `+proj=healpix +ellps=<same ellipsoid>` and check they form a
   square (diamond): equal width and height, equal diagonals. Done for the
   equatorial, north polar and south polar zones at several depths.
2. **Tiling test:** check that every pair of edge neighbours still shares
   an edge (2 vertices) after projection, i.e. no gaps or overlaps, except
   pairs across a cut between two polar triangles.
3. **Round-trip test:** check that PROJ forward → inverse returns the
   original lon/lat to numerical precision.

### Results

- **Cells inside a facet match exactly between healpix-geo and PROJ**
  (round-trip error ~10⁻¹⁴ degrees) in the equatorial, north and south polar
  zones. The scale (cell side length with the WGS84 semi-major axis) matches
  the theoretical value exactly.
- A first version of the check reported some polar cells as distorted
  (`SEAM`). This turned out to be an artefact of the test, not a mismatch
  between healpix-geo and PROJ: HEALPix/HPX is an interrupted projection, and
  a vertex lying exactly on a cut (a pole, a polar facet boundary meridian
  every 90° from `lon_0`, or the map edge) has no unique plane coordinate,
  so PROJ may put it on a neighbouring facet. Moving every vertex a tiny
  fraction (10⁻⁷ of its offset) towards its own cell centre before
  projecting puts each cell entirely on its own facet. With this, **every
  cell** at depth 1–4 is square (max error ~5·10⁻⁸), every pair of edge
  neighbours shares its edge, and the only pairs that do not are exactly
  those across a cut between two polar triangles.
- The check is sensitive to real mismatches: `lon_0=45` or `lon_0=10`
  makes the polar cells non-square, and pairing healpix-geo's sphere with
  PROJ's WGS84 makes every cell non-square (error ~4·10⁻³).
- The figure in the README, drawn by projecting healpix-geo vertices with
  PROJ only, shows the cells tiling the plane without gaps or overlaps.
- **Conclusion:** PROJ's `+proj=healpix` is mathematically consistent with
  healpix-geo's ellipsoidal HEALPix and can be used as a GeoTIFF CRS while
  staying on standard HEALPix (keeping iso-latitude).

## 3. Practical notes for writing GeoTIFFs

1. **Use exactly the same ellipsoid parameters** in healpix-geo and PROJ
   (`+ellps=` / `+a=` / `+rf=`).
2. **`lon_0` must be a multiple of 90°.** healpix-geo cells are fixed on the
   globe (base cell 0 is centred on 45°E), and PROJ's facets only line up
   with them when `lon_0` is a multiple of 90°. At depth 1, `lon_0=10` or
   `lon_0=45` leaves 24 of 48 cells non-square; `lon_0=0` and `lon_0=90`
   leave none. `lon_0=0` is the natural default.
3. **Pixels are diamonds rotated 45°** with respect to the projected axes.
   Mapping one pixel to one HEALPix cell needs an affine transform with a
   rotation term (e.g. GeoTIFF's ModelTransformationTag); a simple north-up
   geotransform does not work.
4. **Resolution and origin must be aligned to the nside (depth)
   subdivision** explicitly; this does not happen automatically.
5. **No EPSG code and no GeoKeys:** the CRS has to be a custom WKT. GDAL
   keeps it in a `.aux.xml` side-car file, so a .tif copied on its own has no
   CRS. `scripts/healpix_geotiff.py` also stores the WKT (with the depth,
   ellipsoid and indexing scheme) in the TIFF metadata and restores it from
   there. Portability outside PROJ-based software (the GDAL family) is
   limited.
6. **Regions crossing a facet seam:** because the projection is interrupted,
   naive interpolation or resampling across a seam gives wrong results.
   Changing `lon_0` cannot remove the seams (see point 2); it only chooses
   which equatorial base cell is split by the map edge. Split the data at
   the seam instead.
7. **Reprojecting with GDAL:** GDAL estimates the source window for each
   output chunk; across the cuts that estimate is too small and leaves
   wedge-shaped holes. The warp option `SOURCE_EXTRA` set to the raster size
   fixes it; every output pixel then gets the value of the cell containing it.
