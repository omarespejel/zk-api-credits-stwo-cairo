#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def write_table(f, headers: list[str], rows: list[dict[str, str]]) -> None:
    f.write("| " + " | ".join(headers) + " |\n")
    f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
    for row in rows:
        f.write("| " + " | ".join(row.get(h, "") for h in headers) + " |\n")
    f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a single shareable table pack with engine/profile guardrails."
    )
    parser.add_argument("--main-summary", required=True, help="Path to baseline bench_summary.csv")
    parser.add_argument("--delta-summary", required=True, help="Path to v1_v2 delta summary.csv")
    parser.add_argument("--delta-table", required=True, help="Path to v1_vs_v2_delta.csv")
    parser.add_argument("--out", required=True, help="Output markdown file")
    parser.add_argument(
        "--allow-mixed",
        action="store_true",
        help="Allow mixed engine/profile inputs and inject automatic caveat text.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    main_summary_path = Path(args.main_summary)
    delta_summary_path = Path(args.delta_summary)
    delta_table_path = Path(args.delta_table)
    out_path = Path(args.out)

    main_rows = read_rows(main_summary_path)
    delta_rows = read_rows(delta_summary_path)
    delta_table_rows = read_rows(delta_table_path)

    if not main_rows:
        raise RuntimeError(f"no rows in {main_summary_path}")
    if not delta_rows:
        raise RuntimeError(f"no rows in {delta_summary_path}")

    main_meta = main_rows[0]
    delta_meta = delta_rows[0]
    main_engine = main_meta.get("prover_engine", "unknown")
    delta_engine = delta_meta.get("prover_engine", "unknown")
    main_profile = main_meta.get("profile", "unknown")
    delta_profile = delta_meta.get("profile", "unknown")

    caveat = None
    if (main_engine != delta_engine) or (main_profile != delta_profile):
        caveat = (
            "Mixed benchmark families detected: "
            f"baseline=({main_engine},{main_profile}) vs delta=({delta_engine},{delta_profile})."
        )
        if not args.allow_mixed:
            raise RuntimeError(
                caveat + " Re-run with matching engine/profile or pass --allow-mixed."
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        f.write("# Combined Benchmark Pack\n\n")
        if caveat:
            f.write(f"> Caveat: {caveat}\n\n")
        else:
            f.write(
                f"> Engine/profile match confirmed: `{main_engine}` + `{main_profile}`.\n\n"
            )

        f.write("## Baseline Summary\n\n")
        baseline_headers = [
            "run_tag",
            "prover_engine",
            "profile",
            "machine",
            "target",
            "depth",
            "samples",
            "prove_wall_ms_p50",
            "verify_wall_ms_p50",
            "proof_size_bytes_p50",
        ]
        write_table(f, baseline_headers, main_rows)

        f.write("## V1 vs V2-kernel Summary\n\n")
        delta_headers = [
            "run_tag",
            "prover_engine",
            "profile",
            "machine",
            "variant",
            "target",
            "depth",
            "samples",
            "prove_p50_ms",
            "verify_p50_ms",
            "size_p50_bytes",
        ]
        write_table(f, delta_headers, delta_rows)

        f.write("## V1 vs V2-kernel Delta Table\n\n")
        if delta_table_rows:
            write_table(f, list(delta_table_rows[0].keys()), delta_table_rows)
        else:
            f.write("No rows in delta table.\n")

    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
