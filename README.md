# zk-api-credits-stwo-cairo

Fixed-class RLN-style API credits PoC in Cairo, with STARK proving, benchmark harnesses, and protocol-flow demos.

This repo exists to answer a practical question from the Ethereum discussion around "ZK API Usage Credits":

> Is the fixed-class RLN path implementable and measurable now, or only a design sketch?

## Current status

- Fixed-class core path is implemented and tested.
- End-to-end prove/verify works for `zk_api_credits` on raw `cairo-prove`.
- A minimal `v2_kernel` executable exists for overhead exploration (signature + commitment-update path), measured via `scarb prove/verify`.
- CI and local preflight are matrix-driven so unsupported paths are explicit.

## TL;DR

Circuit constraints implemented:
- Merkle membership over RLN `rate_commitment = Poseidon(Poseidon(identity_secret), user_message_limit)`.
- RLN share `y = identity_secret + a1 * x` with `a1 = Poseidon(identity_secret, scope, ticket_index)`.
- Nullifier `Poseidon(a1)`.
- Ticket bound `ticket_index < user_message_limit`.
- Fixed-class solvency floor `(ticket_index + 1) * class_price <= deposit`.

Headline baseline snapshot (historical 10-run result used in the working-group discussion, Apple M3 Pro):

| Depth | Prove p50 (ms) | Verify p50 (ms) | Proof size (bytes) |
|---|---:|---:|---:|
| 8  | 12734 | 66 | 14048899 |
| 16 |  8589 | 66 | 14349849 |
| 20 | 10400 | 64 | 14436847 |
| 32 | 13169 | 64 | 14472551 |

Committed reproducible smoke baseline in this repo (`scripts/results/main_baseline/bench_summary.csv`, run_tag `run1771628208`, iterations=1):

| Depth | Prove (ms) | Verify (ms) | Proof size (bytes) |
|---|---:|---:|---:|
| 8  | 9106 | 47 | 13928872 |
| 16 | 8258 | 48 | 14376734 |
| 20 | 8515 | 50 | 14285650 |
| 32 | 6407 | 46 | 14282230 |

Interpretation:
- Verification is cheap and mostly depth-insensitive.
- Proving is the dominant cost and can be amortized with pre-generation for human-paced interactions.

## Protocol scope in this repo

What is included:
- Fixed-class RLN statement and constraints (`src/lib.cairo` -> `main`).
- Merkle proof utilities for rate commitment membership.
- Slashing math demo (`scripts/slash.py`).
- Parallel pre-generation demo (`scripts/precompute_parallel.sh`).
- Minimal API flow demo (`scripts/mini_api_server.py`).
- Benchmark harnesses with run metadata and guardrails.

What is intentionally out of scope:
- Production contract deployment and settlement infrastructure.
- Full variable-cost refund protocol.
- Pairing-based primitives (BBS+ path).

## Repo map

Core files:
- `src/lib.cairo`: fixed-class circuit + `v2_kernel` + tests.
- `Scarb.toml`: executable targets (`zk_api_credits`, `zk_api_credits_v2_kernel`, `derive_rate_commitment_root`).
- `compat_matrix.json`: full local support contract.
- `compat_matrix_ci.json`: CI-safe scarb-only subset.

Ops and benchmarking:
- `scripts/ci/preflight.py`: matrix-driven smoke/negative checks.
- `scripts/bench/run_depths.sh`: baseline depth benchmarking.
- `scripts/bench/run_v1_v2_delta.sh`: v1 vs v2-kernel comparison.
- `scripts/bench/combine_tables.py`: mixed-family guardrail report generation.
- `scripts/proof_size.py`: pretty/minified/gzip proof-size measurement.

## Quickstart

### 1) Requirements

- Scarb `2.14.0` for this repo's pinned Cairo deps.
- `cairo-prove` binary for raw-path runs.
- macOS/Linux shell tooling.

### 2) Build and test

```bash
scarb test
scarb --release build
```

### 3) Prove/verify fixed-class path with raw `cairo-prove`

```bash
/path/to/cairo-prove prove \
  target/release/zk_api_credits.executable.json \
  ./proof.json \
  --arguments-file scripts/bench_inputs/depth_8.json

/path/to/cairo-prove verify ./proof.json
```

### 4) Prove/verify v2-kernel path with scarb

```bash
scarb --release prove --execute --no-build \
  --executable-name zk_api_credits_v2_kernel \
  --arguments-file scripts/bench_inputs/v2_kernel/depth_8.json

# use proof path printed by scarb prove
scarb --release verify --proof-file <proof-file>
```

### 5) Measure proof artifact size correctly

`cairo-prove` proof files are pretty-printed JSON by default.
Use the helper to compare realistic sizes:

```bash
python3 scripts/proof_size.py scripts/results/main_baseline/depth_16_run1_run1771628208_proof.json
```

Current output for that artifact:
- pretty JSON: `14376734` bytes
- minified JSON: `3550433` bytes
- gzip: `1517215` bytes

## Benchmarking workflow

Baseline depth sweep (`cairo-prove` path):

```bash
BENCH_DEPTHS="8 16 20 32" BENCH_ITERATIONS=10 ./scripts/bench/run_depths.sh
```

Artifacts land in `scripts/results/main_baseline`:
- `bench_runs.csv`
- `bench_summary.csv`
- `bench_meta.json`
- logs and proofs per depth/run

Generate report:

```bash
python3 scripts/bench/generate_report.py \
  --summary scripts/results/main_baseline/bench_summary.csv \
  --relation-counts scripts/results/main_baseline/relation_counts.csv \
  --out scripts/results/main_baseline/bench_report.md
```

v1 vs v2-kernel delta (`scarb prove/verify` path):

```bash
BENCH_ITERATIONS=10 ./scripts/bench/run_v1_v2_delta.sh
```

Outputs are timestamped under `scripts/results/v1_v2_delta_<ts>`.

Combined table pack with guardrails:

```bash
python3 scripts/bench/combine_tables.py \
  --main-summary scripts/results/main_baseline/bench_summary.csv \
  --delta-summary scripts/results/v1_v2_delta_<ts>/summary.csv \
  --delta-table scripts/results/v1_v2_delta_<ts>/v1_vs_v2_delta.csv \
  --out scripts/results/combined_report.md
```

This command fails on engine/profile mismatch unless `--allow-mixed` is set.

## Support matrix and preflight contract

Matrix schema version is enforced by preflight (`MATRIX_SCHEMA_VERSION = 1`) to fail fast on drift.

Run full local preflight (includes unsupported-path negative check):

```bash
python3 scripts/ci/preflight.py
```

Run CI-equivalent preflight (scarb-only subset):

```bash
python3 scripts/ci/preflight.py --matrix compat_matrix_ci.json
```

Matrix meaning:
- `main_cairo_prove`: supported (`zk_api_credits` via raw `cairo-prove`).
- `v2_kernel_scarb_prove`: supported (`zk_api_credits_v2_kernel` via `scarb prove/verify`).
- `v2_kernel_cairo_prove`: intentionally unsupported today; expected error substring is tracked in `compat_matrix.json`.

## Known caveats

- CI intentionally uses `compat_matrix_ci.json` and does not run the raw `cairo-prove` negative-path test.
- `zk_api_credits_v2_kernel` on raw `cairo-prove` is currently unsupported in this environment.
- Proof size reporting is format-sensitive; always report pretty/minified/gzip (or binary format if/when added).

## Publish checklist

Use `PUBLISH_CHECKLIST.md` before sharing numbers externally.

## Credits and references

- Davide Crapis + EF dAI working group discussion that motivated this PoC.
- RLN work in Circom/Noir and broader RLN community designs.
- StarkWare/STWO + Cairo tooling used for implementation and measurement.

Reference discussion:
- https://ethresear.ch/t/zk-api-usage-credits-llms-and-beyond/24104
