#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path


def parse_relation_uses(log_text: str):
    if "All relation uses" not in log_text:
        return None
    start = log_text.find("All relation uses")
    block = log_text[start:]
    block_lines = block.splitlines()
    in_block = False
    relation_counts = {}
    for line in block_lines:
        if '{' in line:
            in_block = True
            continue
        if not in_block:
            continue
        if '}' in line:
            break
        match = re.search(r'"([^"]+)"\s*:\s*([0-9]+)', line)
        if match:
            relation_counts[match.group(1)] = int(match.group(2))
    return relation_counts


def parse_log_path(path: Path):
    stem = path.stem
    m = re.match(r'depth_(\d+)_run(\d+)_verify', stem)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'depth_(\d+)_run(\d+)_.+_verify', stem)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r'depth_(\d+)_verify', stem)
    if m:
        return int(m.group(1)), 1
    return None, None


def gather_relation_rows(log_paths):
    rows = []
    all_keys = set()
    for path in log_paths:
        log_text = path.read_text()
        depth, iteration = parse_log_path(path)
        relations = parse_relation_uses(log_text) or {}
        all_keys.update(relations.keys())
        rows.append({
            "run_id": path.stem,
            "depth": "" if depth is None else str(depth),
            "iteration": "" if iteration is None else str(iteration),
            "verified": "yes" if "Verification successful" in log_text else "no",
            "verify_log": str(path),
            **{f"relation__{k}": str(v) for k, v in relations.items()},
        })
    return rows, sorted(all_keys)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract cairo-air verifier relation counts from cairo-prove verify logs."
    )
    parser.add_argument(
        "--verify-logs-dir",
        default="scripts/results/main_baseline",
        help="Directory containing *_verify.log files",
    )
    parser.add_argument(
        "--pattern",
        default="depth_*_verify.log",
        help="Glob pattern for verify logs relative to --verify-logs-dir",
    )
    parser.add_argument(
        "--out",
        default="scripts/results/main_baseline/relation_counts.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    logs_root = Path(args.verify_logs_dir)
    log_paths = sorted(logs_root.glob(args.pattern))
    if not log_paths:
        print(f"No verify logs found at {logs_root} with pattern {args.pattern}")
        return 1

    rows, relation_keys = gather_relation_rows(log_paths)
    if not rows:
        print("No parseable rows from verify logs")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["run_id", "depth", "iteration", "verified", "verify_log"]
    headers.extend([f"relation__{k}" for k in relation_keys])

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            normalized = {k: row.get(k, "") for k in headers}
            writer.writerow(normalized)

    print(f"Wrote {len(rows)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
