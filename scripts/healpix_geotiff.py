#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Write ellipsoidal HEALPix data to a GeoTIFF, read it back and plot it
=====================================================================

On the `+proj=healpix` plane every healpix-geo cell is a square rotated by
45°. A raster whose pixels are rotated the same way, with pixel centres on
cell centres, therefore holds exactly one cell per pixel. GeoTIFF supports
this through a rotated affine transform (stored as ModelTransformationTag),
and the CRS is the PROJ string with the ellipsoid parameters, embedded as
WKT since there is no EPSG code.

This script
1. computes a value on every cell at the given depth (here the WGS84 geodesic
   distance from Brest to the cell centre),
2. writes it to a GeoTIFF on the rotated HEALPix grid,
3. reads the file back and checks that every cell appears exactly once with
   its value, and that GDAL can reproject it to lon/lat,
4. plots the GeoTIFF on the HEALPix plane (pixels drawn as the exact cells)
   next to GDAL's reprojection to EPSG:4326.

Pixels outside the projection's domain (the gaps between the polar triangles)
are nodata. Cells cut by the map edge (lon_0 ± 180°) appear at both edges.

GeoTIFF has no GeoKeys for the HEALPix projection, so GDAL keeps the CRS in a
side-car file (`<name>.tif.aux.xml`). Copy it along with the .tif; to make the
.tif self-contained anyway, the CRS (WKT) is also stored in the TIFF metadata
(`healpix_crs_wkt`), next to the depth, ellipsoid and indexing scheme, and
`healpix_crs` restores it when the side-car is missing.

When warping, GDAL estimates which part of the source it needs for each output
chunk; across the projection's cuts that estimate is too small and leaves
wedge-shaped holes. Enlarging the source window with the warp option
SOURCE_EXTRA (`gdalwarp -wo SOURCE_EXTRA=<raster size>`) fixes it, and the
result then matches the cell of every output pixel exactly.

Usage
-----
    python scripts/healpix_geotiff.py
    python scripts/healpix_geotiff.py --depth 6 --tiff out.tif -o out.png
"""

from __future__ import annotations

import argparse

import numpy as np
import rasterio
from pyproj import Geod
from rasterio.crs import CRS
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject

import healpix_geo.nested as hpg
from verify_healpix_proj import Projection, proj_string

BREST = (-4.49, 48.39)


def healpix_grid(depth: int, ellipsoid: str = "WGS84", lon_0: float = 0.0):
    """Rotated raster grid on the HEALPix plane with one pixel per cell.

    Returns the affine transform, the raster shape (rows, cols) and the CRS.
    """
    proj = Projection(ellipsoid, lon_0)
    w = proj.half_width
    d = w / 2 ** (depth + 1)  # diagonal of a cell on the plane

    # Moving one column goes to the south-east neighbour, one row to the
    # south-west neighbour: each pixel is a diamond with diagonals d.
    a, b, dd, e = d / 2, -d / 2, -d / 2, -d / 2

    # Align a pixel centre with the centre of cell 0, then extend the grid so
    # that it covers the whole plane [-w, w] x [-w/2, w/2].
    x0, y0 = proj.fwd.transform(*hpg.healpix_to_lonlat(np.array([0], "uint64"), depth,
                                                       ellipsoid=ellipsoid))
    unit = Affine(a, b, x0[0], dd, e, y0[0]) * Affine.translation(-0.5, -0.5)
    corners = np.array([[-w, -w / 2], [-w, w / 2], [w, -w / 2], [w, w / 2]])
    col, row = ~unit * (corners[:, 0], corners[:, 1])
    col0, row0 = np.floor(col.min()), np.floor(row.min())
    transform = unit * Affine.translation(col0, row0)
    shape = (int(np.ceil(row.max()) - row0), int(np.ceil(col.max()) - col0))

    crs = CRS.from_proj4(proj_string(ellipsoid, lon_0))
    return transform, shape, crs, proj


def pixel_cells(transform, shape, proj: Projection, depth: int):
    """Cell id of every pixel (-1 outside the projection's domain)."""
    rows, cols = np.indices(shape)
    x, y = transform * (cols + 0.5, rows + 0.5)
    lon, lat = proj.inv.transform(x, y)

    # keep points that PROJ maps back to themselves (x modulo the plane width)
    x2, y2 = proj.fwd.transform(lon, lat)
    with np.errstate(invalid="ignore"):
        tol = 1e-6 * proj.half_width
        inside = (np.abs(proj.wrap_x(x2, x) - x) < tol) & (np.abs(y2 - y) < tol)

    cells = np.full(shape, -1, dtype=np.int64)
    cells[inside] = hpg.lonlat_to_healpix(lon[inside], lat[inside], depth,
                                          ellipsoid=proj.ellipsoid).astype(np.int64)
    return cells


def check_pixel_centres(transform, cells, proj: Projection, depth: int) -> float:
    """Max distance between pixel centres and their cell centres, in pixels."""
    rows, cols = np.nonzero(cells >= 0)
    px, py = transform * (cols + 0.5, rows + 0.5)
    clon, clat = hpg.healpix_to_lonlat(cells[rows, cols].astype("uint64"), depth,
                                       ellipsoid=proj.ellipsoid)
    cx, cy = proj.fwd.transform(clon, clat)
    d = proj.half_width / 2 ** (depth + 1)
    return float(np.max(np.hypot(proj.wrap_x(cx, px) - px, cy - py)) / d)


def healpix_crs(src) -> CRS:
    """CRS of a HEALPix GeoTIFF, from the side-car file or the TIFF metadata."""
    return src.crs or CRS.from_wkt(src.tags()["healpix_crs_wkt"])


def warp_to_lonlat(src, resolution: float = 0.5):
    """Reproject a HEALPix GeoTIFF to a global EPSG:4326 grid with GDAL."""
    transform = from_origin(-180.0, 90.0, resolution, resolution)
    out = np.full((round(180 / resolution), round(360 / resolution)), np.nan, "float32")
    reproject(src.read(1), out, src_transform=src.transform, src_crs=healpix_crs(src),
              dst_transform=transform, dst_crs="EPSG:4326", src_nodata=src.nodata,
              dst_nodata=np.nan, resampling=Resampling.nearest,
              SOURCE_EXTRA=max(src.width, src.height))
    return out, transform


def plot(tiff: str, output: str, dpi: int) -> None:
    import cartopy.crs as ccrs
    import matplotlib.pyplot as plt
    from plot_healpix_cartopy import HEALPix, add_healpix_cells

    with rasterio.open(tiff) as src:
        values = src.read(1, masked=True)
        transform = src.transform
        depth = int(src.tags()["healpix_depth"])
        lonlat, _ = warp_to_lonlat(src)

    crs = HEALPix()
    rows, cols = np.indices((values.shape[0] + 1, values.shape[1] + 1))
    xc, yc = transform * (cols, rows)
    style = dict(cmap="viridis", vmin=0, vmax=float(values.max()))

    fig = plt.figure(figsize=(16, 14))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.15, 1])

    def add_geotiff(ax, **kw):
        # the corners are already projected: use matplotlib's pcolormesh
        # directly, since cartopy's would re-project and re-cut the seams
        return plt.Axes.pcolormesh(ax, xc, yc, values, **{**style, **kw})

    # (a) the GeoTIFF on its own CRS
    ax = fig.add_subplot(grid[0, :], projection=crs)
    ax.set_global()
    mesh = add_geotiff(ax)
    ax.coastlines(linewidth=0.5, color="white")
    ax.plot(*BREST, "r*", ms=12, transform=ccrs.PlateCarree())
    ax.set_title("(a) GeoTIFF on its own CRS (+proj=healpix +ellps=WGS84), "
                 f"rotated pixels, depth {depth}", fontsize=13)
    fig.colorbar(mesh, ax=ax, shrink=0.7, label="geodesic distance from Brest [km]")

    # (b) zoom: GeoTIFF pixels (black) vs healpix-geo cell outlines (red)
    ax = fig.add_subplot(grid[1, 0], projection=crs)
    bx, by = crs.transform_point(*BREST, ccrs.PlateCarree())
    half = 3.5 * crs.x_limits[1] / 2 ** (depth + 1)
    ax.set_extent((bx - half, bx + half, by - half, by + half), crs=crs)
    zoom = add_geotiff(ax, edgecolors="black", linewidth=0.6, vmax=1.5 * half / 1e3)
    add_healpix_cells(ax, crs, depth, facecolor="none", edgecolor="red",
                      linewidth=1.2, linestyle="--")
    ax.coastlines(linewidth=0.8, color="white")
    ax.plot(*BREST, "r*", ms=14, transform=ccrs.PlateCarree())
    fig.colorbar(zoom, ax=ax, shrink=0.8, label="km")
    ax.set_title("(b) around Brest: GeoTIFF pixels (black)\n"
                 "= healpix-geo cells (red dashed); white: gap between polar triangles",
                 fontsize=11)

    # (c) the same file reprojected by GDAL to lon/lat
    ax = fig.add_subplot(grid[1, 1], projection=ccrs.PlateCarree())
    ax.set_global()
    ax.imshow(lonlat, extent=(-180, 180, -90, 90), origin="upper", **style,
              transform=ccrs.PlateCarree(), interpolation="nearest")
    ax.coastlines(linewidth=0.5, color="white")
    ax.plot(*BREST, "r*", ms=12, transform=ccrs.PlateCarree())
    ax.set_title("(c) the same GeoTIFF reprojected by GDAL to EPSG:4326", fontsize=11)

    fig.savefig(output, dpi=dpi, bbox_inches="tight")
    print(f"wrote {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--ellipsoid", default="WGS84")
    parser.add_argument("--tiff", default="healpix_wgs84.tif")
    parser.add_argument("-o", "--output", default="docs/images/healpix_geotiff.png")
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args()

    # 1. a value on every cell, computed on the ellipsoid
    ncells = 12 * 4**args.depth
    ipix = np.arange(ncells, dtype="uint64")
    lon, lat = hpg.healpix_to_lonlat(ipix, args.depth, ellipsoid=args.ellipsoid)
    # TODO: use healpix-geo's geodesic distance once GRID4EARTH/healpix-geo#301 is merged
    _, _, dist = Geod(ellps="WGS84").inv(np.full(ncells, BREST[0]),
                                         np.full(ncells, BREST[1]), lon, lat)
    cell_values = (dist / 1e3).astype("float32")

    # 2. rasterise on the rotated HEALPix grid and write the GeoTIFF
    transform, shape, crs, proj = healpix_grid(args.depth, args.ellipsoid)
    cells = pixel_cells(transform, shape, proj, args.depth)
    image = np.where(cells >= 0, cell_values[np.maximum(cells, 0)], np.nan).astype("float32")

    profile = dict(driver="GTiff", width=shape[1], height=shape[0], count=1,
                   dtype="float32", crs=crs, transform=transform, nodata=np.nan,
                   compress="deflate")
    with rasterio.open(args.tiff, "w", **profile) as dst:
        dst.write(image, 1)
        dst.update_tags(healpix_depth=args.depth, healpix_ellipsoid=args.ellipsoid,
                        healpix_indexing_scheme="nested", healpix_crs_wkt=crs.to_wkt())
    print(f"wrote {args.tiff}: {shape[1]} x {shape[0]} pixels, {crs.to_proj4()}")

    # 3. read back and check
    with rasterio.open(args.tiff) as src:
        back = src.read(1)
        assert src.transform.almost_equals(transform)
        assert src.crs == crs
        assert CRS.from_wkt(src.tags()["healpix_crs_wkt"]) == crs
        lonlat, ll_transform = warp_to_lonlat(src)

    # every lon/lat pixel must get the value of the cell containing its centre
    rows, cols = np.indices(lonlat.shape)
    plon, plat = ll_transform * (cols + 0.5, rows + 0.5)
    expected = cell_values[hpg.lonlat_to_healpix(plon.ravel(), plat.ravel(), args.depth,
                                                 ellipsoid=args.ellipsoid)]
    warped_ok = np.array_equal(lonlat.ravel(), expected)

    present = np.unique(cells[cells >= 0])
    duplicated = cells.size - np.isnan(image).sum() - present.size
    offset = check_pixel_centres(transform, cells, proj, args.depth)
    same = np.array_equal(back, image, equal_nan=True)
    print(f"cells present: {present.size} / {ncells}")
    print(f"pixels repeating a cell at the map edge: {duplicated}")
    print(f"max offset of pixel centre from cell centre: {offset:.1e} pixel")
    print(f"values read back unchanged: {same}")
    print(f"GDAL reprojection to EPSG:4326 gives the right cell everywhere: {warped_ok}")
    ok = present.size == ncells and offset < 1e-6 and same and warped_ok
    print("OK" if ok else "MISMATCH")

    if not args.no_plot:
        plot(args.tiff, args.output, args.dpi)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
