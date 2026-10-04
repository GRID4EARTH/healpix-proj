#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Draw ellipsoidal HEALPix (healpix-geo) cells on the PROJ +proj=healpix plane
============================================================================

The cell vertices returned by healpix-geo (geodetic lon/lat, WGS84) are
projected as-is with `+proj=healpix +ellps=WGS84` to make a "flat Earth" map.
No hand-written unfolding is used, so the fact that the cells tile cleanly is
itself a visual check that healpix-geo and PROJ agree.

- background colour: depth-0 base cells (0-11)
- thin lines and numbers: NESTED cell IDs at the requested depth
- grey lines: Natural Earth coastlines (only if cartopy is installed)

Usage
-----
    python scripts/plot_healpix_map.py                      # depth=1
    python scripts/plot_healpix_map.py --depth 2 -o out.png
"""

from __future__ import annotations

import argparse

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Polygon

from verify_healpix_proj import Projection

ELLIPSOID = "WGS84"
# Vertices are nudged towards their cell centre before projection; see
# `Projection.cells` in verify_healpix_proj.py. Cell edges are straight lines
# on the HEALPix plane, so the 4 vertices are enough.
PROJ = Projection(ELLIPSOID, 0.0)
HALF_WIDTH = PROJ.half_width
TO_PROJ = PROJ.fwd

BASE_COLORS = [
    "#cfe3f5", "#d9ecd0", "#f7dccb", "#e6d9f2",  # north polar 0-3
    "#fbefc4", "#d3ece9", "#f6d4de", "#dde3c9",  # equatorial 4-7
    "#d6dcf3", "#efe0c9", "#d0e8d8", "#f1d5ea",  # south polar 8-11
]


def cell_polygons(depth: int):
    """Return each cell's boundary and centre in projected coordinates."""
    ipix = np.arange(12 * 4**depth, dtype=np.uint64)
    return (ipix, *PROJ.cells(ipix, depth))


def add_cells(ax, depth: int, **style):
    """Draw cells; cells sticking out of one edge are repeated at the other."""
    ipix, x, y, cx, cy = cell_polygons(depth)
    for i in range(len(ipix)):
        for shift in (-2 * HALF_WIDTH, 0.0, 2 * HALF_WIDTH):
            xs = x[i] + shift
            if xs.max() < -HALF_WIDTH or xs.min() > HALF_WIDTH:
                continue
            fc = style.get("facecolor")
            if callable(fc):
                fc = fc(int(ipix[i]))
            ax.add_patch(Polygon(np.c_[xs, y[i]], closed=True,
                                 **{**style, "facecolor": fc}))
    return ipix, cx, cy


def add_coastlines(ax):
    try:
        import cartopy.feature as cfeature
    except ImportError:
        print("cartopy not installed: skipping coastlines")
        return
    for geom in cfeature.COASTLINE.with_scale("110m").geometries():
        parts = geom.geoms if hasattr(geom, "geoms") else [geom]
        for part in parts:
            lon, lat = np.asarray(part.coords).T
            x, y = TO_PROJ.transform(lon, lat)
            # don't join points across a facet seam
            jump = np.hypot(np.diff(x), np.diff(y)) > 0.05 * HALF_WIDTH
            for seg_x, seg_y in zip(np.split(x, np.where(jump)[0] + 1),
                                    np.split(y, np.where(jump)[0] + 1)):
                if len(seg_x) > 1:
                    ax.plot(seg_x, seg_y, color="0.35", lw=0.6, zorder=3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--depth", type=int, default=1,
                        help="depth whose cell IDs are drawn (default: 1)")
    parser.add_argument("-o", "--output",
                        default="docs/images/healpix_wgs84_depth{depth}.png")
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args()

    fig, ax = plt.subplots(figsize=(16, 8.6))

    add_cells(ax, 0, facecolor=lambda c: BASE_COLORS[c],
              edgecolor="none", zorder=0)
    add_coastlines(ax)
    if args.depth > 0:
        add_cells(ax, args.depth, facecolor="none", edgecolor="0.55",
                  lw=0.5, zorder=4)
    base, bx, by = add_cells(ax, 0, facecolor="none", edgecolor="black",
                             lw=1.6, zorder=5)

    # NESTED cell IDs; the base cell of an ID is ID // 4**depth
    ipix, _, _, cx, cy = cell_polygons(args.depth)
    fontsize = {0: 22, 1: 13, 2: 7}.get(args.depth, 0)
    if fontsize:
        for i, xx, yy in zip(ipix, cx, cy):
            ax.text(xx, yy, str(i), ha="center", va="center",
                    fontsize=fontsize, zorder=6,
                    fontweight="bold" if args.depth == 0 else "normal")
    if args.depth > 0:
        # label each base cell at its centre (the vertex shared by its 4 children)
        for b, xx, yy in zip(base, bx, by):
            for shift in (-2 * HALF_WIDTH, 0.0, 2 * HALF_WIDTH):
                if abs(xx + shift) > HALF_WIDTH:
                    continue
                ax.text(xx + shift, yy, f"base {b}", ha="center",
                        va="center", fontsize=9, color="0.2", style="italic",
                        zorder=6, bbox=dict(boxstyle="round,pad=0.25",
                                            fc="white", ec="0.6", lw=0.5))

    ax.set_xlim(-HALF_WIDTH, HALF_WIDTH)
    ax.set_ylim(-HALF_WIDTH / 2, HALF_WIDTH / 2)
    ax.set_aspect("equal")
    ticks = np.linspace(-HALF_WIDTH, HALF_WIDTH, 9)
    ax.set_xticks(ticks, [f"{t / 1e3:,.0f}" for t in ticks])
    yt = np.linspace(-HALF_WIDTH / 2, HALF_WIDTH / 2, 5)
    ax.set_yticks(yt, [f"{t / 1e3:,.0f}" for t in yt])
    ax.set_xlabel("x [km]  (+proj=healpix +ellps=WGS84)")
    ax.set_ylabel("y [km]")
    ax.set_title(f"healpix-geo WGS84 cells on PROJ +proj=healpix — "
                 f"NESTED cell IDs, depth={args.depth}", fontsize=14)
    for s in ax.spines.values():
        s.set_visible(False)

    out = args.output.format(depth=args.depth)
    fig.savefig(out, dpi=args.dpi, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
