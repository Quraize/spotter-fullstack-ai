"""
Pick up to N genuinely different routes from a provider's alternatives.

Routing providers sometimes return alternatives that share most of their road
with the primary route. Overlap is measured as the share of a route's ~1 km
grid cells (0.01 degree) that another route also passes through. Routes are
considered in provider order (fastest first); one that overlaps an already
kept route by more than the threshold is dropped. With fill=True, if that
leaves fewer than N routes, the least-overlapping dropped routes are added
back so the driver still sees as many options as the provider could supply.
"""

from __future__ import annotations

from collections.abc import Sequence

from .sampling import LatLon

DEFAULT_CELL_DEG = 0.01
DEFAULT_OVERLAP_THRESHOLD = 0.8


def _cells(points: Sequence[LatLon], cell_deg: float) -> set[tuple[int, int]]:
    return {(round(lat / cell_deg), round(lon / cell_deg)) for lat, lon in points}


def path_overlap(a: Sequence[LatLon], b: Sequence[LatLon], cell_deg: float = DEFAULT_CELL_DEG) -> float:
    """Share of path a's cells that path b also visits, 0.0 to 1.0."""
    cells_a = _cells(a, cell_deg)
    if not cells_a:
        return 0.0
    return len(cells_a & _cells(b, cell_deg)) / len(cells_a)


def select_distinct_routes(
    paths: Sequence[Sequence[LatLon]],
    max_routes: int = 3,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
    cell_deg: float = DEFAULT_CELL_DEG,
    fill: bool = False,
) -> list[int]:
    """Indices into `paths` to keep, in ascending (provider) order."""
    cells = [_cells(p, cell_deg) for p in paths]

    def overlap(i: int, j: int) -> float:
        return len(cells[i] & cells[j]) / len(cells[i]) if cells[i] else 0.0

    chosen: list[int] = []
    for i in range(len(paths)):
        if len(chosen) >= max_routes:
            break
        if all(overlap(i, j) < overlap_threshold for j in chosen):
            chosen.append(i)

    if fill and len(chosen) < max_routes:
        dropped = [i for i in range(len(paths)) if i not in chosen]
        dropped.sort(key=lambda i: (max((overlap(i, j) for j in chosen), default=0.0), i))
        chosen.extend(dropped[: max_routes - len(chosen)])
        chosen.sort()
    return chosen
