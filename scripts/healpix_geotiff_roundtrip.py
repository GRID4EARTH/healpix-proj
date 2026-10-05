#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
healpix-geo data -> GeoTIFF in +proj=healpix -> cell ids again
=============================================================

End-to-end check of the lossless GeoTIFF path:

1. build the rotated, cell-aligned sampling grid in PROJ's ellipsoidal
   HEALPix projection (``AffineSamplingGrid.from_healpix``, one pixel per cell),
2. resample a field onto it and write it with rioxarray (``.rio.to_raster``),
3. read the file back with rasterio and recover the cell id of every pixel
   from its position alone (``raster_cell_ids``),
4. check that the CRS, the transform, and every cell's value survived.

Requires healpix-plot with the CRS-aware ``AffineSamplingGrid`` (see the
patch in ``patches/``), plus ``rasterio`` and ``rioxarray``.

Usage
-----
    python scripts/healpix_geotiff_roundtrip.py
    python scripts/healpix_geotiff_roundtrip.py --level 6 --ellipsoid WGS84 \
        -o healpix_wgs84_depth6.tif --figure docs/images/healpix_plot_geotiff.png
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--level", type=int, default=5, help="HEALPix level (>= 1)")
    parser.add_argument("--ellipsoid", default="WGS84", help="healpix-geo ellipsoid name")
    parser.add_argument("-o", "--output", default="healpix_roundtrip.tif", help="GeoTIFF path")
    parser.add_argument("--figure", default=None, help="save a figure to this PNG")
    args = parser.parse_args()

    import pyproj
    import rasterio
    import rioxarray
    from healpix_plot import AffineSamplingGrid, HealpixGrid, resample
    from healpix_plot.raster import raster_cell_ids, to_dataarray

    healpix_grid = HealpixGrid(level=args.level, indexing_scheme="nested", ellipsoid=args.ellipsoid)
    npix = 12 * 4**args.level
    cell_ids = np.arange(npix, dtype="uint64")
    lon, lat = healpix_grid.operations.healpix_to_lonlat(cell_ids, **healpix_grid.as_keyword_params())
    data = np.cos(3 * np.deg2rad(lon)) * np.sin(2 * np.deg2rad(lat))

    # 1. the cell-aligned grid, 2. resample and write
    t0 = time.perf_counter()
    grid = AffineSamplingGrid.from_healpix(healpix_grid)
    target, image = resample(
        cell_ids, data, sampling_grid=grid, healpix_grid=healpix_grid,
        interpolation="nearest", agg="first",
    )
    raster = to_dataarray(image, target, healpix_grid, name="field")
    raster.rio.write_nodata(np.nan, inplace=True)
    raster.rio.to_raster(args.output, compress="deflate")
    t_write = time.perf_counter() - t0

    # 3. read back, 4. check
    t0 = time.perf_counter()
    with rasterio.open(args.output) as src:
        crs_ok = pyproj.CRS.from_user_input(src.crs) == grid.crs
        transform_ok = src.transform.almost_equals(grid.transform)
        shape_ok = (src.height, src.width) == grid.shape
        back = src.read(1)
        ids = raster_cell_ids(src, healpix_grid)
    t_read = time.perf_counter() - t0

    valid = ~np.ma.getmaskarray(ids)
    hits = np.bincount(np.ma.getdata(ids)[valid], minlength=npix)
    recovered = np.full(npix, np.nan)
    recovered[np.ma.getdata(ids)[valid]] = back[valid]
    max_err = float(np.nanmax(np.abs(recovered - data)))
    values_ok = np.all(np.isfinite(recovered)) and max_err < 1e-6  # float32 storage
    nodata_ok = bool(np.all(np.isnan(back[~valid])))
    once_ok = bool(np.all(hits == 1))

    print(f"level {args.level}, ellipsoid {args.ellipsoid}: {npix} cells")
    print(f"raster {grid.shape[0]} x {grid.shape[1]} pixels, {int(valid.sum())} on the globe")
    print(f"CRS: {grid.crs.to_proj4()}")
    print(f"file: {args.output} ({os.path.getsize(args.output) / 1e6:.2f} MB)")
    print(f"write {t_write:.2f} s, read + decode {t_read:.2f} s")
    checks = {
        "CRS round-trips through the GeoTIFF": crs_ok,
        "transform round-trips through the GeoTIFF": transform_ok,
        "shape round-trips through the GeoTIFF": shape_ok,
        "every cell is exactly one pixel": once_ok,
        "pixels off the globe are nodata": nodata_ok,
        f"values recovered (max |err| {max_err:.1e})": values_ok,
    }
    for name, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")

    if args.figure:
        import matplotlib

        matplotlib.use("Agg")
        import cartopy.crs as ccrs
        import matplotlib.pyplot as plt
        from healpix_plot import HEALPix, plot

        projection = HEALPix(ellipsoid=healpix_grid.ellipsoid)
        fig, axes = plt.subplots(
            2, 1, figsize=(11, 10), subplot_kw={"projection": projection}, layout="constrained"
        )
        # the data, drawn by healpix-plot on the cell-aligned grid
        mappable = plot(
            cell_ids, data, healpix_grid=healpix_grid, sampling_grid=grid,
            ax=axes[0], cmap="RdBu_r", vmin=-1, vmax=1,
        )
        axes[0].coastlines(linewidth=0.5)
        axes[0].set_title(f"healpix_plot.plot on AffineSamplingGrid.from_healpix (level {args.level}, {args.ellipsoid})")
        # the GeoTIFF, read back with rioxarray and drawn with its own georeferencing
        reopened = rioxarray.open_rasterio(args.output).squeeze("band", drop=True)
        file_grid = AffineSamplingGrid.from_raster(reopened).resolve(None, healpix_grid)
        corner_x, corner_y = file_grid.corners()
        axes[1].set_global()
        axes[1].pcolormesh(
            corner_x, corner_y, reopened.values, transform=ccrs.Projection(file_grid.crs),
            cmap="RdBu_r", vmin=-1, vmax=1, shading="flat",
        )
        axes[1].coastlines(linewidth=0.5)
        axes[1].set_title(f"{os.path.basename(args.output)} read back with rioxarray ({reopened.shape[0]} x {reopened.shape[1]} rotated pixels)")
        for ax in axes:
            ax.gridlines(xlocs=range(-180, 181, 90), ylocs=[-41.81, 0, 41.81], linewidth=0.4, color="k")
        fig.colorbar(mappable, ax=axes, shrink=0.6, label="cos(3 lon) sin(2 lat)")
        fig.savefig(args.figure, dpi=110)
        print(f"figure: {args.figure}")

    sys.exit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
