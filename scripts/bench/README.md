# Benchmarking

This folder contains scripts for running real STWO measurements for `zk_api_credits`.

## Prerequisites

- `cairo-prove` binary available (or set `CAIRO_PROVE`).
- project built with `scarb build`.
- depth-specific arguments in `scripts/bench_inputs/depth_<depth>.json`.

## Run

```bash
./scripts/bench/run_depths.sh
```

The runner supports multi-run benchmarks:

```bash
BENCH_DEPTHS="8 16 20 32" BENCH_ITERATIONS=10 ./scripts/bench/run_depths.sh
```

Set `COLLECT_RELATION_COUNTS=0` to skip relation parsing.

The script expects these files:
- `scripts/bench_inputs/depth_8.json`
- `scripts/bench_inputs/depth_16.json`
- `scripts/bench_inputs/depth_20.json`
- `scripts/bench_inputs/depth_32.json`

You can regenerate those files deterministically from committed fixtures with:

```bash
./scripts/bench_inputs/generate_bench_args.py \
  --depths "8 16 20 32" \
  --out-dir scripts/bench_inputs
```

The generator preserves proof arrays and merkle roots, and rewrites only witness fields.
Use `--overwrite` if you want to re-emit existing files.

If you prefer alternate inputs without copying files, point the harness at another directory:

```bash
BENCH_INPUTS_DIR=path/to/args ./scripts/bench/run_depths.sh
```

For each available depth file, it writes:
- `scripts/results/depth_<depth>_runN_proof.json`
- `scripts/results/depth_<depth>_runN_prove.log`
- `scripts/results/depth_<depth>_runN_verify.log`
- `scripts/results/bench_runs.csv` (raw runs)
- `scripts/results/bench_summary.csv` (aggregated metrics)
- `scripts/results/relation_counts.csv` (relation usage, if enabled)

The `scripts/bench_inputs/template_depth_args.json` file documents argument ordering and includes placeholders for `MERKLE_ROOT_PLACEHOLDER` and proof array elements.

Relation counts can also be extracted from existing logs:

```bash
./scripts/bench/extract_relation_counts.py \
  --verify-logs-dir scripts/results \
  --out scripts/results/relation_counts.csv
```

Generate a compact shareable report:

```bash
./scripts/bench/generate_report.py \
  --summary scripts/results/bench_summary.csv \
  --relation-counts scripts/results/relation_counts.csv \
  --out scripts/results/bench_report.md
```

Note: `cairo-prove` currently does not expose constraint counts in a single CLI field; relation counts are the closest stable complexity signal.
