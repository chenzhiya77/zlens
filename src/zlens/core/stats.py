"""Percentile math for the performance panel.

Linear interpolation between closest ranks (the common "inclusive" convention),
operating on pre-sorted samples.
"""

from zlens.sources.models import LatencyStats

_P50, _P90, _P99 = 50, 90, 99


def percentile(sorted_values: list[int], pct: int) -> float:
    if not sorted_values:
        raise ValueError("percentile of empty sample list")
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * pct / 100
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def latency_stats(sorted_values: list[int]) -> LatencyStats | None:
    if not sorted_values:
        return None
    return LatencyStats(
        sample_count=len(sorted_values),
        p50_ms=round(percentile(sorted_values, _P50), 1),
        p90_ms=round(percentile(sorted_values, _P90), 1),
        p99_ms=round(percentile(sorted_values, _P99), 1),
    )
