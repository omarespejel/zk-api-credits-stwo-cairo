#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from schema_contract import read_p50, read_rows, validate_summary_headers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build v1 vs v2 delta table from summary CSV files.")
    parser.add_argument("--baseline-summary", required=True)
    parser.add_argument("--v2-summary", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline_path = Path(args.baseline_summary)
    v2_path = Path(args.v2_summary)
    out_path = Path(args.out)

    baseline_rows = read_rows(baseline_path)
    v2_rows = read_rows(v2_path)
    validate_summary_headers(baseline_rows, f"baseline summary ({baseline_path})")
    validate_summary_headers(v2_rows, f"v2 summary ({v2_path})")

    baseline_by_depth = {int(r["depth"]): r for r in baseline_rows}
    v2_by_depth = {int(r["depth"]): r for r in v2_rows}
    shared_depths = sorted(set(baseline_by_depth) & set(v2_by_depth))

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

            prove_delta = ((v2_prove - v1_prove) / v1_prove) * 100 if v1_prove else 0.0
            verify_delta = ((v2_verify - v1_verify) / v1_verify) * 100 if v1_verify else 0.0
            size_delta = ((v2_size - v1_size) / v1_size) * 100 if v1_size else 0.0

            w.writerow([
                depth,
                int(v1_prove),
                int(v2_prove),
                round(prove_delta, 2),
                int(v1_verify),
                int(v2_verify),
                round(verify_delta, 2),
                int(v1_size),
                int(v2_size),
                round(size_delta, 2),
            ])

    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
