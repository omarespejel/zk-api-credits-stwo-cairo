#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

if __package__:
    from .schema_contract import read_p50, read_rows, validate_summary_headers
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.bench.schema_contract import (
        read_p50,
        read_rows,
        validate_summary_headers,
    )


class BuildDeltaError(RuntimeError):
    """Base exception for delta-build validation errors."""


class DuplicateDepthError(BuildDeltaError):
    """Raised when a summary CSV contains duplicate depth rows."""


class DepthMismatchError(BuildDeltaError):
    """Raised when baseline and v2 summaries use different depth sets."""


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the v1-vs-v2 delta builder."""
    parser = argparse.ArgumentParser(description="Build v1 vs v2 delta table from summary CSV files.")
    parser.add_argument("--baseline-summary", required=True)
    parser.add_argument("--v2-summary", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    """Read baseline and v2 summaries, compute percentage deltas, write CSV."""
    args = parse_args()
    baseline_path = Path(args.baseline_summary)
    v2_path = Path(args.v2_summary)
    out_path = Path(args.out)

    baseline_rows = read_rows(baseline_path)
    v2_rows = read_rows(v2_path)
    validate_summary_headers(baseline_rows, f"baseline summary ({baseline_path})")
    validate_summary_headers(v2_rows, f"v2 summary ({v2_path})")

    def _index_by_depth(rows: list[dict[str, str]], label: str) -> dict[int, dict[str, str]]:
        """Build depth->row index, raising on duplicates."""
        by_depth: dict[int, dict[str, str]] = {}
        for row in rows:
            depth = int(row["depth"])
            if depth in by_depth:
                raise DuplicateDepthError(f"{label} has duplicate depth={depth}")
            by_depth[depth] = row
        return by_depth

    baseline_by_depth = _index_by_depth(baseline_rows, "baseline")
    v2_by_depth = _index_by_depth(v2_rows, "v2")
    missing_in_v2 = sorted(set(baseline_by_depth) - set(v2_by_depth))
    missing_in_baseline = sorted(set(v2_by_depth) - set(baseline_by_depth))
    if missing_in_v2 or missing_in_baseline:
        raise DepthMismatchError(
            f"depth mismatch: missing in v2={missing_in_v2}, "
            f"missing in baseline={missing_in_baseline}"
        )
    shared_depths = sorted(baseline_by_depth)

    def delta_or_nan(metric: str, depth: int, baseline_value: float, v2_value: float) -> float:
        """Return percentage change, or NaN with a warning when baseline is zero."""
        if baseline_value == 0:
            print(
                f"[warn] baseline {metric} is zero at depth={depth}; "
                f"v2={v2_value}; writing NaN delta",
                file=sys.stderr,
            )
            return math.nan
        if baseline_value < 0:
            print(
                f"[warn] baseline {metric} is negative at depth={depth}; "
                f"baseline={baseline_value}, v2={v2_value}; check input data integrity",
                file=sys.stderr,
            )
        return ((v2_value - baseline_value) / baseline_value) * 100

    def csv_delta_value(value: float) -> str | float:
        """Return canonical CSV delta representation."""
        return "NaN" if math.isnan(value) else round(value, 2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "depth",
            "v1_prove_p50_ms",
            "v2_prove_p50_ms",
            "prove_delta_pct",
            "v1_verify_p50_ms",
            "v2_verify_p50_ms",
            "verify_delta_pct",
            "v1_size_p50_bytes",
            "v2_size_p50_bytes",
            "size_delta_pct",
        ])
        for depth in shared_depths:
            baseline = baseline_by_depth[depth]
            v2 = v2_by_depth[depth]
            v1_prove = read_p50(baseline, "prove")
            v2_prove = read_p50(v2, "prove")
            v1_verify = read_p50(baseline, "verify")
            v2_verify = read_p50(v2, "verify")
            v1_size = read_p50(baseline, "size")
            v2_size = read_p50(v2, "size")

            prove_delta = delta_or_nan("prove", depth, v1_prove, v2_prove)
            verify_delta = delta_or_nan("verify", depth, v1_verify, v2_verify)
            size_delta = delta_or_nan("size", depth, v1_size, v2_size)

            w.writerow([
                depth,
                int(v1_prove),
                int(v2_prove),
                csv_delta_value(prove_delta),
                int(v1_verify),
                int(v2_verify),
                csv_delta_value(verify_delta),
                int(v1_size),
                int(v2_size),
                csv_delta_value(size_delta),
            ])

    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
