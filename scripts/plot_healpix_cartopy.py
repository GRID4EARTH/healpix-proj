#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cartopy map in PROJ's ellipsoidal HEALPix projection
====================================================

`HEALPix` is a cartopy CRS for `+proj=healpix`. Passing the PROJ string to a
bare `ccrs.Projection` fails because cartopy also needs the map domain
(`boundary`, `x_limits`, `y_limits`); this class supplies the HEALPix outline
(the equatorial band plus the four polar triangles at each pole), so the usual
cartopy tools work on it: `coastlines`, `stock_img`, `add_feature`, gridlines,
and any data passed with `transform=ccrs.PlateCarree()`.

healpix-geo cells are already projected (via `Projection.cells` from
`verify_healpix_proj.py`), so they are drawn straight in data coordinates;
letting cartopy re-project them would make it re-cut cells at the facet seams.

Usage
-----
    python scripts/plot_healpix_cartopy.py
    python scripts/plot_healpix_cartopy.py --depth 3 -o out.png
"""

from __future__ import annotations

import argparse

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import shapely.geometry as sgeom
from matplotlib.collections import PolyCollection

from verify_healpix_proj import Projection


class HEALPix(ccrs.Projection):
    """Cartopy CRS for PROJ's `+proj=healpix` (ellipsoidal HEALPix).

    Only multiples of 90° for `central_longitude` line up with healpix-geo
    cells (see the README).
    """

    def __init__(self, central_longitude: float = 0.0, globe: ccrs.Globe | None = None):
        globe = globe or ccrs.Globe(ellipse="WGS84")
        super().__init__([("proj", "healpix"), ("lon_0", central_longitude)], globe=globe)

        # x spans [-πR, πR] (R: authalic radius); x(lon_0 + 90°) = πR / 2
        w = 2.0 * self.transform_point(central_longitude + 90.0, 0.0, self.as_geodetic())[0]
        q = w / 4.0
        self._half_width = w

        # Outline, counter-clockwise from the bottom-left corner: the equatorial
        # band |y| <= w/4 plus a triangle of height w/4 over each polar facet.
        xs = np.linspace(-w, w, 9)
        top = [(x, q if i % 2 == 0 else 2 * q) for i, x in enumerate(xs)]
        bottom = [(x, -q if i % 2 == 0 else -2 * q) for i, x in enumerate(xs)]
        self._boundary = sgeom.LinearRing(bottom + top[::-1])
        self._threshold = w / 1e4

    @property
    def boundary(self):
        return self._boundary

    @property
    def x_limits(self):
        return (-self._half_width, self._half_width)

    @property
    def y_limits(self):
        return (-self._half_width / 2, self._half_width / 2)

    @property
    def threshold(self):
        return self._threshold


def add_healpix_cells(ax, crs: HEALPix, depth: int, ellipsoid: str = "WGS84", **style):
    """Draw healpix-geo cell outlines on a HEALPix GeoAxes; return the cells."""
    proj = Projection(ellipsoid, crs.proj4_params["lon_0"])
    ipix = np.arange(12 * 4**depth, dtype=np.uint64)
    x, y, cx, cy = proj.cells(ipix, depth)
    # cells sticking out of one map edge are repeated at the other
    polys = [np.c_[x[i] + s, y[i]]
             for i in range(len(ipix))
             for s in (-2 * proj.half_width, 0.0, 2 * proj.half_width)
             if (x[i] + s).max() > -proj.half_width and (x[i] + s).min() < proj.half_width]
    ax.add_collection(PolyCollection(polys, transform=ax.transData, **style))
    return ipix, cx, cy


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("-o", "--output", default="docs/images/healpix_cartopy.png")
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    crs = HEALPix()
    fig = plt.figure(figsize=(16, 8.6))
    ax = fig.add_subplot(projection=crs)
    ax.set_global()
    ax.stock_img()
    ax.coastlines(resolution="110m", linewidth=0.6)
    ax.gridlines(color="white", alpha=0.4, linewidth=0.5)

    # data given in lon/lat is reprojected by cartopy as usual
    cities = {"Brest": (-4.49, 48.39), "Tokyo": (139.69, 35.69),
              "Cape Town": (18.42, -33.92), "Lima": (-77.04, -12.05)}
    for name, (lon, lat) in cities.items():
        ax.plot(lon, lat, "o", color="crimson", ms=5, transform=ccrs.PlateCarree())
        ax.text(lon + 3, lat, name, transform=ccrs.PlateCarree(), fontsize=10,
                color="crimson", fontweight="bold")

    add_healpix_cells(ax, crs, args.depth, facecolor="none", edgecolor="black",
                      linewidth=0.4, alpha=0.7)
    add_healpix_cells(ax, crs, 0, facecolor="none", edgecolor="black", linewidth=1.4)

    ax.set_title(f"cartopy GeoAxes in +proj=healpix +ellps=WGS84, "
                 f"with healpix-geo cells (depth {args.depth})", fontsize=14)
    fig.savefig(args.output, dpi=args.dpi, bbox_inches="tight")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
