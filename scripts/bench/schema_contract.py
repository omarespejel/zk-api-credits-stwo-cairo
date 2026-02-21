#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path

COMMON_SUMMARY_COLUMNS = (
    "run_tag",
    "prover_engine",
    "profile",
    "depth",
    "samples",
)

P50_ALIASES: dict[str, tuple[str, str]] = {
    "prove": ("prove_wall_ms_p50", "prove_p50_ms"),
    "verify": ("verify_wall_ms_p50", "verify_p50_ms"),
    "size": ("proof_size_bytes_p50", "size_p50_bytes"),
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def require_non_empty(rows: list[dict[str, str]], label: str) -> None:
    if not rows:
        raise RuntimeError(f"{label} has no rows")


def _find_metric_key(row: dict[str, str], metric: str) -> str:
    if metric not in P50_ALIASES:
        raise KeyError(f"unknown metric: {metric}")
    for candidate in P50_ALIASES[metric]:
        if candidate in row:
            return candidate
    raise KeyError(
        f"missing p50 metric columns for '{metric}'; expected one of {P50_ALIASES[metric]}"
    )


def read_p50(row: dict[str, str], metric: str) -> float:
    key = _find_metric_key(row, metric)
    return float(row[key])


def validate_summary_headers(rows: list[dict[str, str]], label: str) -> None:
    require_non_empty(rows, label)
    sample = rows[0]
    missing_common = [key for key in COMMON_SUMMARY_COLUMNS if key not in sample]
    if missing_common:
        raise RuntimeError(f"{label} missing common summary keys: {missing_common}")
    for metric in ("prove", "verify", "size"):
        _find_metric_key(sample, metric)

