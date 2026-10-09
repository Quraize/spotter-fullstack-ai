"""
Geometry along a route.

- Great-circle distances and cumulative mileage along a polyline.
- Checkpoints every N miles (plus the destination), positioned on the polyline.
- A travel-time profile built from the routing provider's progress entries
  (point index → seconds), so the ETA at any mile is a linear interpolation
  between the provider's own timing points.
- Douglas–Peucker simplification for sending geometry to the browser.

Coordinates are (lat, lon) tuples throughout the domain layer; conversion to
GeoJSON [lon, lat] happens at the API boundary.
"""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

EARTH_RADIUS_MILES = 3958.7613

LatLon = tuple[float, float]

# Regular checkpoints closer than this to the destination are dropped so the
# destination is not duplicated (about 5 feet).
_DESTINATION_MERGE_MILES = 1e-3


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def cumulative_miles(points: Sequence[LatLon]) -> list[float]:
    """Distance from the first point to each vertex, in miles. cum[0] is 0."""
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    cum = [0.0]
    for (lat1, lon1), (lat2, lon2) in pairwise(points):
        cum.append(cum[-1] + haversine_miles(lat1, lon1, lat2, lon2))
    return cum


@dataclass(frozen=True)
class SampledPoint:
    index: int  # 0-based order along the route
    mile: float  # distance from the origin along the polyline
    lat: float
    lon: float
    vertex_index: int  # the point lies on segment [vertex_index, vertex_index + 1]
    vertex_fraction: float  # 0 at vertex_index, 1 at vertex_index + 1


def sample_along_route(
    points: Sequence[LatLon],
    interval_miles: float,
    cumulative: Sequence[float] | None = None,
) -> list[SampledPoint]:
    """
    Checkpoints at mile 0, interval, 2*interval, ... and always the destination.
    A zero-length route yields a single checkpoint at the origin.
    """
    if interval_miles <= 0:
        raise ValueError("interval_miles must be positive")
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    cum = list(cumulative) if cumulative is not None else cumulative_miles(points)
    if len(cum) != len(points):
        raise ValueError("cumulative must have one entry per point")

    total = cum[-1]
    if total <= 0:
        lat, lon = points[0]
        return [SampledPoint(index=0, mile=0.0, lat=lat, lon=lon, vertex_index=0, vertex_fraction=0.0)]

    target_miles: list[float] = []
    k = 0
    while True:
        mile = k * interval_miles
        if mile > total - _DESTINATION_MERGE_MILES:
            break
        target_miles.append(mile)
        k += 1
    target_miles.append(total)

    samples: list[SampledPoint] = []
    seg = 0
    last_seg = len(cum) - 2
    for index, mile in enumerate(target_miles):
        while seg < last_seg and cum[seg + 1] < mile:
            seg += 1
        seg_len = cum[seg + 1] - cum[seg]
        frac = 0.0 if seg_len <= 0 else min(max((mile - cum[seg]) / seg_len, 0.0), 1.0)
        (lat0, lon0), (lat1, lon1) = points[seg], points[seg + 1]
        samples.append(
            SampledPoint(
                index=index,
                mile=mile,
                lat=lat0 + (lat1 - lat0) * frac,
                lon=lon0 + (lon1 - lon0) * frac,
                vertex_index=seg,
                vertex_fraction=frac,
            )
        )
    return samples


@dataclass(frozen=True)
class ProgressEntry:
    """Travel time from the origin to a given vertex, as reported by the routing provider."""

    point_index: int
    seconds: float


def time_profile(progress: Sequence[ProgressEntry], cumulative: Sequence[float]) -> list[tuple[float, float]]:
    """
    (mile, seconds) pairs in increasing mile order, using this module's own
    cumulative mileage for the provider's point indices so that checkpoint
    miles and timing miles are measured the same way.
    """
    if len(progress) < 2:
        raise ValueError("a time profile needs at least two progress entries")
    profile: list[tuple[float, float]] = []
    for entry in sorted(progress, key=lambda e: e.point_index):
        if not 0 <= entry.point_index < len(cumulative):
            raise ValueError(f"progress point_index {entry.point_index} is outside the route")
        profile.append((cumulative[entry.point_index], float(entry.seconds)))
    for (mile0, sec0), (mile1, sec1) in pairwise(profile):
        if sec1 < sec0 or mile1 < mile0:
            raise ValueError("progress entries must be non-decreasing in distance and time")
    return profile


def seconds_at_mile(profile: Sequence[tuple[float, float]], mile: float) -> float:
    """Linear interpolation between profile entries; clamped at both ends."""
    if mile <= profile[0][0]:
        return profile[0][1]
    if mile >= profile[-1][0]:
        return profile[-1][1]
    miles = [m for m, _ in profile]
    i = bisect.bisect_right(miles, mile)  # profile[i-1].mile <= mile < profile[i].mile
    mile0, sec0 = profile[i - 1]
    mile1, sec1 = profile[i]
    if mile1 == mile0:
        return sec1
    return sec0 + (sec1 - sec0) * (mile - mile0) / (mile1 - mile0)


def simplify_polyline(points: Sequence[LatLon], tolerance_deg: float) -> list[LatLon]:
    """
    Douglas–Peucker in degree space (adequate for display). Endpoints are
    always kept. Iterative so very long routes do not hit recursion limits.
    """
    n = len(points)
    if n <= 2:
        return list(points)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        ay, ax = points[a]
        by, bx = points[b]
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        best, best_i = -1.0, -1
        for i in range(a + 1, b):
            py, px = points[i]
            if length_sq == 0:
                dist = math.hypot(px - ax, py - ay)
            else:
                t = ((px - ax) * dx + (py - ay) * dy) / length_sq
                t = min(max(t, 0.0), 1.0)
                dist = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
            if dist > best:
                best, best_i = dist, i
        if best > tolerance_deg:
            keep[best_i] = True
            stack.append((a, best_i))
            stack.append((best_i, b))
    return [p for p, k in zip(points, keep, strict=True) if k]
