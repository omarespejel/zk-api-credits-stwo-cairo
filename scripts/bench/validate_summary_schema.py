#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__:
    from .schema_contract import read_rows, validate_summary_headers
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.bench.schema_contract import read_rows, validate_summary_headers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate benchmark summary CSV schema contract.")
    parser.add_argument("--summary", required=True, help="Path to summary CSV file.")
    parser.add_argument("--label", default=None, help="Human-readable label in errors.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise FileNotFoundError(f"summary file not found: {summary_path}")
    rows = read_rows(summary_path)
    label = args.label or str(summary_path)
    validate_summary_headers(rows, label)
    print(f"schema ok: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
