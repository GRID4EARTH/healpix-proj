#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Geometric consistency check: healpix-geo vs PROJ (+proj=healpix)
================================================================

Purpose
-------
Check numerically whether the (ellipsoidal) HEALPix cell coordinates computed
by healpix-geo can be used consistently as a GeoTIFF grid when expressed in
PROJ's `+proj=healpix` projection.

Checks
------
1. [Shape test] Project the 4 vertices of every cell with PROJ and check that
   they form a square (diamond): equal diagonals, width == height. Done for
   the equatorial, north polar and south polar zones at several depths.
2. [Tiling test] Check that every pair of edge neighbours still shares an
   edge after projection (vertices coincide; no gaps or overlaps), except
   pairs whose shared edge is one of the projection's cuts.
3. [Round-trip test] Check that forward then inverse projection returns the
   original lon/lat (consistency of PROJ's forward/inverse).
4. Run for both the sphere and an ellipsoid (WGS84) and compare.

Seams
-----
HEALPix (HPX) is an interrupted projection: the map edge (lon_0 ± 180°) and
the gaps between the polar triangles (lon_0 + k·90°, poleward of ~42°) are
cuts. A vertex lying exactly on a cut has no unique projected position, so
every vertex is nudged a tiny fraction towards its own cell centre before
projection. Each cell then lands entirely on its own facet, and no cell needs
special treatment.

Requirements
------------
    pip install healpix-geo pyproj numpy

Usage
-----
    python scripts/verify_healpix_proj.py
    python scripts/verify_healpix_proj.py --ellipsoid sphere
    python scripts/verify_healpix_proj.py --ellipsoid WGS84 --depths 1 2 3 4 5
    python scripts/verify_healpix_proj.py --lon-0 45   # expected to fail
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

import numpy as np

try:
    import healpix_geo.nested as hpg
except ImportError as exc:  # pragma: no cover
    sys.exit(
        "healpix-geo not found; run `pip install healpix-geo`."
        f" ({exc})"
    )

try:
    from pyproj import CRS, Transformer
except ImportError as exc:  # pragma: no cover
    sys.exit(f"pyproj not found; run `pip install pyproj`. ({exc})")


# Fraction of the vertex-to-centre offset by which each vertex is moved
# towards its cell centre before projection (see "Seams" above).
NUDGE = 1e-7

# Relative tolerances (with respect to the cell size).
SHAPE_TOL = 1e-6
GAP_TOL = 1e-6
ROUNDTRIP_TOL_DEG = 1e-6

ZONES = ("north polar", "equatorial", "south polar")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def zone_of(depth: int, ipix: np.ndarray) -> np.ndarray:
    """Return the zone (north polar / equatorial / south polar) of NESTED ipix."""
    base = np.asarray(ipix, dtype=np.int64) // 4**depth
    return np.asarray(ZONES)[base // 4]


def proj_string(ellipsoid: str, lon_0: float = 0.0) -> str:
    """Build the PROJ string for an ellipsoid name.

    healpix-geo's ellipsoid="sphere" is the unit sphere, so it maps to a
    PROJ sphere of radius 1 (+R=1). Ellipsoid names such as "WGS84" are
    passed through to +ellps=.
    """
    if ellipsoid.lower() == "sphere":
        return f"+proj=healpix +R=1 +lon_0={lon_0}"
    return f"+proj=healpix +ellps={ellipsoid} +lon_0={lon_0}"


@dataclass
class Projection:
    """PROJ forward transform plus the half width of the projected plane."""

    ellipsoid: str
    lon_0: float

    def __post_init__(self) -> None:
        crs = CRS.from_proj4(proj_string(self.ellipsoid, self.lon_0))
        self.fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self.inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        # x spans [-πR, πR] (R: authalic radius); x(lon_0 + 90°) = πR / 2
        self.half_width = 2.0 * self.fwd.transform(self.lon_0 + 90.0, 0.0)[0]

    def wrap_x(self, x: np.ndarray, ref: np.ndarray) -> np.ndarray:
        """Shift x by multiples of the plane width to lie next to `ref`."""
        period = 2.0 * self.half_width
        return x - period * np.round((x - ref) / period)

    def cells(self, ipix: np.ndarray, depth: int):
        """Project the vertices and centres of cells.

        Returns x, y of shape (N, 4) and cx, cy of shape (N,). Vertex x values
        are kept on the same side of the map edge as the cell centre.
        """
        ipix = np.asarray(ipix, dtype=np.uint64)
        lon, lat = hpg.vertices(ipix, depth, ellipsoid=self.ellipsoid)
        clon, clat = hpg.healpix_to_lonlat(ipix, depth, ellipsoid=self.ellipsoid)
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)

        # unwrap longitudes around the cell centre, then nudge towards it
        lon = clon[:, None] + (lon - clon[:, None] + 180.0) % 360.0 - 180.0
        lon = lon + (clon[:, None] - lon) * NUDGE
        lat = lat + (clat[:, None] - lat) * NUDGE

        x, y = self.fwd.transform(lon, lat)
        cx, cy = self.fwd.transform(clon, clat)
        x, y, cx, cy = map(np.asarray, (x, y, cx, cy))
        return self.wrap_x(x, cx[:, None]), y, cx, cy


@dataclass
class ShapeResult:
    depth: int
    zone: str
    n_cells: int
    side: float  # mean cell width in projected units
    max_shape_err: float  # max relative deviation from a square
    n_bad: int

    @property
    def ok(self) -> bool:
        return self.n_bad == 0


@dataclass
class Report:
    ellipsoid: str
    shape_results: list = field(default_factory=list)
    adjacency: dict = field(default_factory=dict)
    roundtrip_max_err_deg: float = 0.0

    @property
    def shape_ok(self) -> bool:
        return all(r.ok for r in self.shape_results)

    @property
    def tiling_ok(self) -> bool:
        adj = self.adjacency
        return adj.get("n_bad", 1) == 0 and adj.get("n_cut_bad", 1) == 0

    @property
    def roundtrip_ok(self) -> bool:
        return self.roundtrip_max_err_deg < ROUNDTRIP_TOL_DEG

    @property
    def ok(self) -> bool:
        return self.shape_ok and self.tiling_ok and self.roundtrip_ok


# ---------------------------------------------------------------------------
# 1. Shape test
# ---------------------------------------------------------------------------

def check_cell_shapes(proj: Projection, depths: list[int]) -> list[ShapeResult]:
    """For each depth and zone, check that every cell projects to a square (diamond)."""
    results: list[ShapeResult] = []
    for depth in depths:
        ipix = np.arange(12 * 4**depth, dtype=np.uint64)
        x, y, _, _ = proj.cells(ipix, depth)

        width = x.max(axis=1) - x.min(axis=1)
        height = y.max(axis=1) - y.min(axis=1)
        # vertices are ordered around the cell: 0-2 and 1-3 are the diagonals
        d02 = np.hypot(x[:, 0] - x[:, 2], y[:, 0] - y[:, 2])
        d13 = np.hypot(x[:, 1] - x[:, 3], y[:, 1] - y[:, 3])
        err = np.maximum(np.abs(width / height - 1.0), np.abs(d02 / d13 - 1.0))

        zones = zone_of(depth, ipix)
        for zone in ZONES:
            sel = zones == zone
            results.append(
                ShapeResult(
                    depth=depth,
                    zone=zone,
                    n_cells=int(sel.sum()),
                    side=float(width[sel].mean()),
                    max_shape_err=float(err[sel].max()),
                    n_bad=int((err[sel] > SHAPE_TOL).sum()),
                )
            )
    return results


# ---------------------------------------------------------------------------
# 2. Tiling test (consistency of neighbouring cells)
# ---------------------------------------------------------------------------

def is_cut_pair(depth: int, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """True where cells a and b share an edge that is a cut of the projection.

    Those are neighbours in two different polar base cells of the same
    hemisphere (e.g. base cells 0 and 1): on the globe they share a meridian
    edge, on the plane they lie in two separate polar triangles.
    """
    base_a = np.asarray(a, dtype=np.int64) // 4**depth
    base_b = np.asarray(b, dtype=np.int64) // 4**depth
    polar = (base_a // 4 != 1) & (base_a // 4 == base_b // 4)
    return polar & (base_a != base_b)


def check_adjacency(proj: Projection, depth: int) -> dict:
    """Check that every pair of edge neighbours shares an edge (2 vertices)
    after projection.

    Pairs across a cut (see `is_cut_pair`) are expected to be separated on the
    plane; they are counted separately and must *not* share an edge.

    Returns
    -------
    dict
        n_pairs, max_gap, n_bad (pairs that should touch but don't),
        n_cut, min_cut_gap, n_cut_bad (cut pairs that unexpectedly touch).
        Gaps are relative to the cell size.
    """
    ipix = np.arange(12 * 4**depth, dtype=np.uint64)
    x, y, cx, _ = proj.cells(ipix, depth)
    side = np.median(x.max(axis=1) - x.min(axis=1))

    nb = np.asarray(hpg.neighbours(ipix, depth, connectivity="edge"))
    a, k = np.nonzero(nb >= 0)
    b = nb[a, k].astype(np.int64)
    # each unordered pair once
    keep = a < b
    a, b = a[keep], b[keep]

    # put cell b on the same side of the map edge as cell a
    xb = proj.wrap_x(x[b], cx[a][:, None])
    # distance from each vertex of b to the nearest vertex of a; the two
    # smallest are the shared vertices
    dist = np.hypot(xb[:, :, None] - x[a][:, None, :],
                    y[b][:, :, None] - y[a][:, None, :]).min(axis=2)
    gap = np.sort(dist, axis=1)[:, :2].max(axis=1) / side

    cut = is_cut_pair(depth, a, b)
    return {
        "n_pairs": int((~cut).sum()),
        "max_gap": float(gap[~cut].max()),
        "n_bad": int((gap[~cut] > GAP_TOL).sum()),
        "n_cut": int(cut.sum()),
        "min_cut_gap": float(gap[cut].min()) if cut.any() else float("nan"),
        "n_cut_bad": int((gap[cut] <= GAP_TOL).sum()),
    }


# ---------------------------------------------------------------------------
# 3. Round-trip test
# ---------------------------------------------------------------------------

def check_roundtrip(proj: Projection, depth: int, n_samples: int = 200, seed: int = 0) -> float:
    """Return the max round-trip error (degrees) of PROJ forward/inverse."""
    rng = np.random.default_rng(seed)
    npix_total = 12 * 4**depth
    ipix = rng.integers(0, npix_total, size=n_samples, dtype=np.int64).astype("uint64")

    lon, lat = hpg.healpix_to_lonlat(ipix, depth, ellipsoid=proj.ellipsoid)
    x, y = proj.fwd.transform(lon, lat)
    lon2, lat2 = proj.inv.transform(x, y)

    # longitude is periodic (0° == 360°): take the shortest difference
    dlon = (np.asarray(lon2) - np.asarray(lon) + 180.0) % 360.0 - 180.0
    dlat = np.asarray(lat2) - np.asarray(lat)
    return float(np.max(np.hypot(dlon, dlat)))


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def run(ellipsoid: str, depths: list[int], lon_0: float) -> Report:
    report = Report(ellipsoid=ellipsoid)
    proj = Projection(ellipsoid, lon_0)

    print(f"\n{'=' * 70}")
    print(f" ellipsoid = {ellipsoid!r}, lon_0 = {lon_0:g}")
    print(f"{'=' * 70}")

    # 1. Shape test
    print("\n[1] Shape test (does every cell project to a square/diamond?)")
    report.shape_results = check_cell_shapes(proj, depths)
    print(f"{'depth':>5} {'zone':>12} {'cells':>7} {'side':>16} {'max error':>11} {'result':>7}")
    for r in report.shape_results:
        status = "OK" if r.ok else f"NG({r.n_bad})"
        print(
            f"{r.depth:5d} {r.zone:>12} {r.n_cells:7d} "
            f"{r.side:16.6f} {r.max_shape_err:11.3e} {status:>7}"
        )
    print(f"  -> {'all cells square [OK]' if report.shape_ok else 'non-square cells [NG]'}")

    # 2. Tiling test (at a representative depth)
    test_depth = depths[len(depths) // 2]
    print(f"\n[2] Tiling test (do all edge neighbours share an edge at depth={test_depth}?)")
    adj = check_adjacency(proj, test_depth)
    report.adjacency = adj
    print(f"  neighbour pairs: {adj['n_pairs']}, max gap / cell size = {adj['max_gap']:.3e}")
    print(
        f"  pairs across a polar cut: {adj['n_cut']}, min gap / cell size = "
        f"{adj['min_cut_gap']:.3e} (separate polar triangles, must not touch)"
    )
    if adj["n_cut_bad"]:
        print(f"  {adj['n_cut_bad']} cut pairs unexpectedly share an edge")
    print(f"  -> {'all edges shared, cuts where expected [OK]' if report.tiling_ok else 'mismatch [NG]'}")

    # 3. Round-trip test
    print(f"\n[3] Round-trip test (depth={test_depth})")
    report.roundtrip_max_err_deg = check_roundtrip(proj, test_depth)
    print(f"  forward->inverse max error: {report.roundtrip_max_err_deg:.3e} deg")
    print(f"  -> {'round trip consistent [OK]' if report.roundtrip_ok else 'round-trip error [NG]'}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check the geometric consistency of healpix-geo and PROJ (+proj=healpix)"
    )
    parser.add_argument(
        "--ellipsoid",
        nargs="+",
        default=["sphere", "WGS84"],
        help="ellipsoid(s) to check, using names accepted by healpix-geo "
        "(e.g. sphere, WGS84, GRS80). Default: sphere WGS84",
    )
    parser.add_argument(
        "--depths",
        nargs="+",
        type=int,
        default=[1, 2, 3, 4],
        help="HEALPix depths (resolutions) to check. Default: 1 2 3 4",
    )
    parser.add_argument(
        "--lon-0",
        type=float,
        default=0.0,
        help="central meridian of the projection. Only multiples of 90 line "
        "up with healpix-geo cells. Default: 0",
    )
    args = parser.parse_args()

    all_reports = [run(e, args.depths, args.lon_0) for e in args.ellipsoid]

    print(f"\n{'=' * 70}")
    print(" Summary")
    print(f"{'=' * 70}")
    for rep in all_reports:
        print(f"  ellipsoid={rep.ellipsoid:>10}: {'OK' if rep.ok else 'NG'}")

    all_ok = all(rep.ok for rep in all_reports)
    if all_ok:
        print(
            "\nhealpix-geo and PROJ (+proj=healpix) are geometrically "
            "consistent over the tested range."
        )
    else:
        print(
            "\nInconsistency detected. Check the ellipsoid/lon_0 parameters "
            "and the PROJ and healpix-geo versions."
        )
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
