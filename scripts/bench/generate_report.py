#!/usr/bin/env python3
import argparse
import csv
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


def read_csv_rows(path: Path):
    with path.open() as f:
        return list(csv.DictReader(f))


def write_header(f):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    f.write("# zk_api_credits Benchmark Report\n\n")
    f.write(f"Generated: {now}\n\n")


def write_summary_table(f, summary_rows):
    f.write("## Summary by Depth\n\n")
    if not summary_rows:
        f.write("No summary rows available.\n\n")
        return

    headers = summary_rows[0].keys()
    f.write("| " + " | ".join(headers) + " |\n")
    f.write("|" + "|".join(["---"] * len(headers)) + "|\n")
    for row in summary_rows:
        f.write("| " + " | ".join(row[h] for h in headers) + " |\n")
    f.write("\n")


def write_relation_table(f, relation_rows):
    f.write("## Verifier Relation Counts (representative successful run per depth)\n\n")
    if not relation_rows:
        f.write("No relation rows available.\n\n")
        return

    rel_keys = [k for k in relation_rows[0].keys() if k.startswith("relation__")]
    by_depth = OrderedDict()
    for r in relation_rows:
        if r.get("verified") != "yes":
            continue
        if r.get("depth") not in by_depth:
            by_depth[r["depth"]] = r
        if len(by_depth) == 0:
            continue

    if not by_depth:
        f.write("No successful verifier rows available.\n\n")
        return

    f.write("| depth | " + " | ".join(k.replace("relation__", "") for k in rel_keys) + " |\n")
    f.write("|" + "|".join(["---"] * (len(rel_keys) + 1)) + "|\n")
    for depth in sorted(by_depth.keys(), key=int):
        row = by_depth[depth]
        values = [row.get(k, "") for k in rel_keys]
        f.write("| " + depth + " | " + " | ".join(values) + " |\n")
    f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a human-readable benchmark report.")
    parser.add_argument("--summary", default="scripts/results/main_baseline/bench_summary.csv")
    parser.add_argument("--relation-counts", default="scripts/results/main_baseline/relation_counts.csv")
    parser.add_argument("--out", default="scripts/results/main_baseline/bench_report.md")
    args = parser.parse_args()

    summary_path = Path(args.summary)
    relation_path = Path(args.relation_counts)
    out_path = Path(args.out)

    summary_rows = read_csv_rows(summary_path) if summary_path.exists() else []
    relation_rows = read_csv_rows(relation_path) if relation_path.exists() else []

    with out_path.open("w") as f:
        write_header(f)
        f.write("## Inputs\n\n")
        f.write(f"- summary: `{summary_path}`\n")
        f.write(f"- relation_counts: `{relation_path}`\n\n")

        write_summary_table(f, summary_rows)
        write_relation_table(f, relation_rows)

    print(f"Wrote report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
