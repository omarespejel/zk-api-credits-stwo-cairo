# zk_api_credits

A small, self-contained proof-of-concept to answer one question from Davide’s “ZK API Usage Credits: LLMs and Beyond” post:

> Is the fixed-class RLN-style design practical on a real prover today, or is it just a diagram?

I implemented one concrete instance and measured it end-to-end.

## TL;DR

- Circuit implements:
  - Poseidon Merkle membership for `identity_secret` (leaf commitment).
  - RLN share `y = k + a * x`, where `a = Poseidon(identity_secret, ticket_index)`.
  - Nullifier `Poseidon(a)` for rate limiting.
  - Solvency floor `(ticket_index + 1) * class_price <= deposit` (fixed-class cost).
- Benchmarked on Apple M3 Pro with 10 runs per depth (`8, 16, 20, 32`):
  - **Prove p50:** ≈ 8.6–13.2s depending on depth.
  - **Verify p50:** ≈ 64–66ms for all depths.
  - **Proof size:** ≈ 14.0–14.5 MB.
- Interpretation:
  - Verification is cheap and effectively depth-independent in this setup.
  - Proving time is dominated by prover overhead, and is compatible with pre-generating proofs between user requests.

For this experiment I used Cairo and a STARK prover, but the circuit structure itself is stack-agnostic: it is intended as a concrete data point, not a stack-specific protocol argument.

## Why this repo exists

The post discusses a full protocol (membership, RLN rate limiting, solvency, refunds/variable costs). This repo focuses on the fixed-class branch:

- same cost per call,
- no in-circuit refunds,
- no homomorphic or replay-by-spending machinery,
- still includes membership, RLN share, nullifier, and solvency floor.

The goals were:

- validate the fixed-class branch end-to-end as a runnable circuit,
- collect proof/verification numbers from an actual prover,
- check whether those numbers align with usage patterns like human-paced LLM/API calls.

## How it relates to Davide’s post

In this repo, the covered layer is:

- Merkle membership for identity,
- RLN share construction,
- nullifier generation and slashing math,
- solvency floor enforcement.

I deliberately excluded:

- variable-cost routing,
- E(R) signatures/homomorphic refund paths,
- chain-side accounting or deployment code.

Concretely, this is equivalent to setting the refund/ER branch aside and testing whether the fixed-class case is operationally practical today.

## Snapshot benchmark results

Latest clean run (`2026-02-14T23:38:01Z` UTC), 10 iterations, Apple M3 Pro:

| depth | prove p50 (ms) | verify p50 (ms) | proof size (bytes) |
|---|---:|---:|---:|
| 8  | 12734 | 66 | 14048899 |
| 16 | 8589  | 66 | 14349849 |
| 20 | 10400 | 64 | 14436847 |
| 32 | 13169 | 64 | 14472551 |

More detailed stats are in:

- `scripts/results/bench_summary.csv`
- `scripts/results/bench_report.md`

## Scope and non-goals

What this repo includes:

- fixed-class circuit behavior,
- reproducible benchmark harness,
- spec-demo scripts for slashing/replay and pre-generation.

What it does not include:

- protocol deployment contracts,
- networking or chain-side accounting,
- refunds or class-transition logic,
- pairing primitives/BBS+.

## Versioning

- Cairo: `2.14.0`
- Scarb: `2.14.0`
- `openzeppelin_merkle_tree`: `2.0.0`

## Usage

```bash
cd zk-api-credits
scarb build
/path/to/cairo-prove prove target/release/zk_api_credits.executable.json ./proof.json \
  --arguments-file scripts/bench_inputs/template_depth_args.json
/path/to/cairo-prove verify ./proof.json
```

### Benchmark harness

- Regenerate depth fixtures:

```bash
./scripts/bench_inputs/generate_bench_args.py \
  --depths "8 16 20 32" \
  --out-dir scripts/bench_inputs
```

- Run benchmark (example):

```bash
CAIRO_PROVE=/path/to/cairo-prove BENCH_DEPTHS="8 16 20 32" BENCH_ITERATIONS=10 ./scripts/bench/run_depths.sh
```

- Generate report from CSVs:

```bash
./scripts/bench/generate_report.py \
  --summary scripts/results/bench_summary.csv \
  --relation-counts scripts/results/relation_counts.csv \
  --out scripts/results/bench_report.md
```

Outputs:

- `scripts/results/bench_runs.csv`
- `scripts/results/bench_summary.csv`
- `scripts/results/relation_counts.csv`
- `scripts/results/bench_report.md`

### Security/Spec demos

#### Slashing recovery (`scripts/slash.py`)

```bash
python3 scripts/slash.py share1.json share2.json
```

Recovers `identity_secret` via:

```text
a0 = (y1 * x2 - y2 * x1) / (x2 - x1)
```

#### Parallel pre-generation (`scripts/precompute_parallel.sh`)

```bash
DEPTH=8 COUNT=5 BASE_INDEX=0 X_START=1000 X_STEP=7 ./scripts/precompute_parallel.sh
```

#### Minimal API demo server (`scripts/mini_api_server.py`)

```bash
python3 scripts/mini_api_server.py --cairo-prove /path/to/cairo-prove
```

## Credits

- `openzeppelin_merkle_tree` crate for Poseidon Merkle primitives.
- `stwo-cairo` (`cairo-prove`) for STARK proof generation/verification in this benchmark.
- `dcrapis` (ethresear.ch) and the broader RLN/API-credits discussion for fixed-class framing:
  - https://ethresear.ch/t/zk-api-usage-credits-llms-and-beyond/24104
  - https://hackmd.io/3da7PaYmTqmNTTwqxVidRg
