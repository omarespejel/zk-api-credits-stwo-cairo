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

For each available depth file, it writes (default directory: `scripts/results/main_baseline`):
- `scripts/results/main_baseline/depth_<depth>_runN_<run_tag>_proof.json`
- `scripts/results/main_baseline/depth_<depth>_runN_<run_tag>_prove.log`
- `scripts/results/main_baseline/depth_<depth>_runN_<run_tag>_verify.log`
- `scripts/results/main_baseline/bench_runs.csv` (raw runs)
- `scripts/results/main_baseline/bench_summary.csv` (aggregated metrics)
- `scripts/results/main_baseline/relation_counts.csv` (relation usage, if enabled)
- `scripts/results/main_baseline/bench_meta.json` (engine/profile/target/machine metadata)

The `scripts/bench_inputs/template_depth_args.json` file documents argument ordering and includes placeholders for `MERKLE_ROOT_PLACEHOLDER` and proof array elements.

Raw benchmark rows include self-describing provenance columns by default:
- `prover_engine`
- `profile`
- `target`
- `run_tag`
- `machine`

Relation counts can also be extracted from existing logs:

```bash
./scripts/bench/extract_relation_counts.py \
  --verify-logs-dir scripts/results/main_baseline \
  --out scripts/results/main_baseline/relation_counts.csv
```

Generate a compact shareable report:

```bash
./scripts/bench/generate_report.py \
  --summary scripts/results/main_baseline/bench_summary.csv \
  --relation-counts scripts/results/main_baseline/relation_counts.csv \
  --out scripts/results/main_baseline/bench_report.md
```

Note: `cairo-prove` currently does not expose constraint counts in a single CLI field; relation counts are the closest stable complexity signal.

## V1 vs V2-kernel delta run

To compare fixed-class v1 against the minimal v2 kernel shape (adds ECDSA + Pedersen path), run:

```bash
BENCH_ITERATIONS=10 ./scripts/bench/run_v1_v2_delta.sh
```

Outputs are written to a timestamped folder:
- `scripts/results/v1_v2_delta_<ts>/runs.csv`
- `scripts/results/v1_v2_delta_<ts>/summary.csv`
- `scripts/results/v1_v2_delta_<ts>/v1_vs_v2_delta.csv`
- `scripts/results/v1_v2_delta_<ts>/bench_meta.json`

Notes:
- This script uses `scarb prove/verify` and defaults to release profile (`SCARB_PROFILE=release`).
- Inputs for v2 live under `scripts/bench_inputs/v2_kernel`.
- In this repo's current environment, `v2_kernel` is not executable via raw `cairo-prove` directly; use this `scarb prove/verify` path for the delta runs.

## V2-kernel depth sweep only

To benchmark only `v2_kernel` across depths:

```bash
BENCH_ITERATIONS=10 ./scripts/bench/run_v2_kernel_depths.sh
```

Outputs are written to:
- `scripts/results/v2_kernel_only_<ts>/runs.csv`
- `scripts/results/v2_kernel_only_<ts>/summary.csv`
- `scripts/results/v2_kernel_only_<ts>/bench_meta.json`

If `scripts/results/main_baseline/bench_summary.csv` exists, the script also emits:
- `scripts/results/v2_kernel_only_<ts>/v1_vs_v2_from_baseline.csv`

This gives a one-file depth-by-depth V1-vs-V2 table using the committed baseline family.

## Combined report guardrail

If you need one shareable table pack that mixes families, use:

```bash
python3 scripts/bench/combine_tables.py \
  --main-summary scripts/results/main_baseline/bench_summary.csv \
  --delta-summary scripts/results/v1_v2_delta_<ts>/summary.csv \
  --delta-table scripts/results/v1_v2_delta_<ts>/v1_vs_v2_delta.csv \
  --out scripts/results/combined_report.md
```

This script fails on engine/profile mismatch unless `--allow-mixed` is set. With `--allow-mixed`, it auto-injects a caveat banner.
