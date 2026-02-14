# Fixed-Class RLN API-Credits PoC (Cairo + STWO)

I implemented the fixed-class variant end-to-end in Cairo + `cairo-prove` and collected reproducible proof/verify measurements.
The current implementation excludes E(R), refunds, signatures, and pairing assumptions.

## What was implemented

Circuit (`src/lib.cairo`) enforces:

1. **Membership:** `identity_secret` is committed as `Poseidon(identity_secret)` and verified against a Poseidon Merkle root.
2. **Shamir share (RLN-style):**
   - `a1 = Poseidon(identity_secret, ticket_index)`
   - `y = identity_secret + a1 * x`
3. **Nullifier:** `nullifier = Poseidon(a1)` (public)
4. **Solvency floor check:**
   - `(ticket_index + 1) * class_price <= deposit`

Public outputs: `(nullifier, x, y, merkle_root)`.

## Scope of this run

This artifact is a runnable fixed-class PoC for the question:
**“Can we build and measure a practical API-credits proving path with STWO/Cairo?”**

It includes:

- Poseidon-native Cairo hashing
- STWO Cairo prover (`cairo-prove`)
- End-to-end wall-clock proof generation and verification
- Public artifacts and relation-usage traces
- No pairing-based dependencies

## Benchmark environment

- CPU: Apple M3 Pro (12 cores)
- RAM: 18 GB
- OS: macOS 14.7.6 (arm64)
- Toolchain: `scarb 2.14.0`, Cairo compiler `2.14.0`
- Prover: `cairo-prove`
- Python: `3.13.5`
- Run timestamp: `2026-02-14T22:49:22Z` UTC
- `BENCH_DEPTHS="8 16 20 32"`
- `BENCH_ITERATIONS=5`
- `RUST_LOG=info` for internal prover timing extraction

## Depth-16 behavior caveat

A non-monotonic timing result appears in this run (`depth-16` faster than `depth-8` in some aggregate points).
This is consistent with STWO trace quantization/padding effects at proof-layout boundaries and does not change circuit semantics.

## How to reproduce

From repository root:

```bash
cd zk-api-credits
scarb build

./scripts/bench_inputs/generate_bench_args.py \
  --depths "8 16 20 32" \
  --out-dir scripts/bench_inputs

CAIRO_PROVE=/path/to/cairo-prove \
BENCH_DEPTHS="8 16 20 32" \
BENCH_ITERATIONS=5 \
./scripts/bench/run_depths.sh

./scripts/bench/generate_report.py \
  --summary scripts/results/bench_summary.csv \
  --relation-counts scripts/results/relation_counts.csv \
  --out scripts/results/bench_report.md
```

Artifacts produced:

- `scripts/results/bench_runs.csv`
- `scripts/results/bench_summary.csv`
- `scripts/results/relation_counts.csv`
- `scripts/results/bench_report.md`

## Current results (latest 5-run aggregate)

| depth | prove p50 (ms) | prove p95 (ms) | prove max (ms) | verify p95 (ms) | verify max (ms) | proof size (bytes) |
|---|---:|---:|---:|---:|---:|---:|
| 8  | 26,243 | 33,383 | 33,383 | 104 | 104 | 14,048,899 |
| 16 | 17,688 | 43,066 | 43,066 | 458 | 458 | 14,349,849 |
| 20 | 16,245 | 27,244 | 27,244 | 116 | 116 | 14,436,847 |
| 32 | 19,466 | 21,843 | 21,843 | 99 | 99 | 14,472,551 |

Each value is from `BENCH_ITERATIONS=5` prove+verify runs. Verifier timings are sampled from each verify call.

### Timing interpretation

At roughly 1 request/minute, proof generation can be overlapped with client-side waiting windows for many interactive API flows.
Verification remains sub-500ms in this dataset.

### Protocol-level demos in this repo

- `scripts/slash.py` recovers `identity_secret` from two shares with same `nullifier` and `ticket_index`:
  `a0 = (y1*x2 - y2*x1) / (x2 - x1)`.
- `scripts/precompute_parallel.sh` generates consecutive tickets in parallel and reports total wall-clock.
- `scripts/mini_api_server.py` accepts `proof_path` or base64 proof, verifies with `cairo-prove`, tracks in-memory spent nullifiers, and returns a slash payload when a nullifier reappears with a different `x`.

Repo status:

- Artifact is a runnable implementation for fixed-class fixed-parameters flow.
- Next work is protocol hardening and API integration layers.
