# zk_api_credits

A runnable fixed-class STWO/Cairo proof-of-concept for RLN-style API credits.

## Why this repo exists

This repo was created to validate one concrete branch of the API-credits discussion with measurements instead of assumptions:

a) membership-gated requests via Poseidon Merkle proofs,

b) RLN-style nullifier/share derivation,

c) simple solvency enforcement, and

d) a full prove+verify path with real STWO artifacts.

The aim is to provide an implementation artifact for discussion, not a production protocol implementation.

## Scope and non-goals

What this repo includes:
- fixed-class circuit behavior,
- benchmark and reproducibility harness,
- protocol-flow scripts for slashing/replay and pre-generation.

What this repo does not include:
- protocol deployment contracts,
- networking or chain-side accounting,
- refund pathways or class-transition logic,
- pairing primitives or BBS+ components.

## TL;DR findings

- End-to-end fixed-class STWO/Cairo implementation is working in this workspace.
- Benchmarked 5 runs per depth (`8, 16, 20, 32`) with wall-clock prove/verify results and relation traces.
- In the latest run (`2026-02-14T22:49:22Z` UTC), verification remained sub-500ms and proof sizes were around 14.0–14.4MB.
- Depth-16 timing non-monotonicity appears in this run and is being treated as a trace/padding effect, not a circuit-functional regression.

## What this proves

- Poseidon-based membership in a Merkle tree (`identity_secret` leaf commitment)
- RLN Shamir share `y = k + a1 * x`, where `a1 = Poseidon(identity_secret, ticket_index)`
- Nullifier `Poseidon(a1)` for rate limiting
- Solvency floor constraint `(ticket_index + 1) * class_price <= deposit`

## Public/Private boundary

Inputs are passed as function arguments in the Cairo executable model.
The circuit does:

1. Verify Merkle inclusion
2. Derive share and nullifier
3. Enforce solvency inequality
4. Return `(nullifier, x, y, merkle_root)`

## Versioning

- Cairo: `2.14.0`
- Scarb: `2.14.0`
- `openzeppelin_merkle_tree`: `2.0.0`

## Usage

```bash
cd zk-api-credits
scarb build
/path/to/cairo-prove prove target/release/zk_api_credits.executable.json ./proof.json --arguments-file scripts/bench_inputs/template_depth_args.json
/path/to/cairo-prove verify ./proof.json
```

## Proof CLI notes

- `cairo-prove` logs do not include constraint counts in default output.
- Bench artifacts in this repo include:
  - wall-clock prove timing
  - wall-clock verify timing
  - proof file size
  - prover internal timing from logs when `RUST_LOG=info` is enabled

## Benchmarks

- Build once with `scarb build`
- Regenerate depth fixtures from canonical fixtures:

```bash
./scripts/bench_inputs/generate_bench_args.py \
  --depths "8 16 20 32" \
  --out-dir scripts/bench_inputs
```

The command keeps Merkle proof/root values from base fixtures and rewrites witness fields (`deposit`, `class_price`) as `u256` low/high limbs.

- Run multi-depth harness:

```bash
CAIRO_PROVE=/path/to/cairo-prove BENCH_DEPTHS="8 16 20 32" BENCH_ITERATIONS=5 ./scripts/bench/run_depths.sh
```

- Generate a shareable markdown report:

```bash
./scripts/bench/generate_report.py \
  --summary scripts/results/bench_summary.csv \
  --relation-counts scripts/results/relation_counts.csv \
  --out scripts/results/bench_report.md
```

Harness outputs:

- `scripts/results/bench_runs.csv`
- `scripts/results/bench_summary.csv`
- `scripts/results/relation_counts.csv`
- `scripts/results/bench_report.md`

`bench_summary.csv` includes min/p50/p95/max/average for wall-clock prove/verify and prover-internal timing, plus proof size.

## Latest snapshot context

- Run timestamp: `2026-02-14T22:49:22Z` UTC
- Environment: Apple M3 Pro (12 cores), 18 GB RAM, macOS 14.7.6 (arm64)
- Tooling: `scarb` + `cairo` `2.14.0`, Python `3.13.5`, `cairo-prove`
- Iterations: `BENCH_ITERATIONS=5`

## Security/Spec demos

### Slashing recovery (`scripts/slash.py`)

Build two `(nullifier, ticket_index, x, y)` share objects and run:

```bash
python3 scripts/slash.py share1.json share2.json
```

The script recovers `identity_secret` via:

```
a0 = (y1 * x2 - y2 * x1) / (x2 - x1)
```

Optional check:

```bash
python3 scripts/slash.py share1.json share2.json --expected-identity-secret 0x2a
```

### Parallel pre-generation (`scripts/precompute_parallel.sh`)

Generate multiple tickets in parallel for latency experiments:

```bash
DEPTH=8 COUNT=5 BASE_INDEX=0 X_START=1000 X_STEP=7 ./scripts/precompute_parallel.sh
```

Output:
- one proof + log per ticket in `OUT_DIR` (default `scripts/results/parallel_batch_<ts>`)
- per-ticket wall time from proof logs
- total wall-clock for the batch

### Minimal API demo server (`scripts/mini_api_server.py`)

Starts a tiny in-memory API server that verifies proofs and tracks nullifier replay:

```bash
python3 scripts/mini_api_server.py --cairo-prove /path/to/cairo-prove
```

Endpoints:
- `GET /healthz`
- `POST /submit` with:
  - `proof_b64` (base64 proof json, preferred) or `proof_path`
  - `nullifier`, `ticket_index`, `x`, `y`
- `GET /state`

The demo stores state in-memory; no persistence/on-chain accounting.

## Files

- `src/lib.cairo` — circuit and tests
- `scripts/bench_inputs/template_depth_args.json` — argument order template
- `scripts/bench/run_depths.sh` — multi-depth benchmark runner
- `scripts/prove_example.sh` — one-shot prove + verify
- `scripts/precompute_parallel.sh` — parallel proof generation
- `scripts/slash.py` / `scripts/mini_api_server.py` — protocol demos

## Credits

- `openzeppelin_merkle_tree` crate for Poseidon Merkle primitives.
- `stwo-cairo` (`cairo-prove`) for STWO-backed proof generation and verification workflow.
- Existing RLN and community discussions as prior art for Shamir-share/slashing formulas and API-credits framing.
