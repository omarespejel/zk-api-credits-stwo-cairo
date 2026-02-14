# Fixed-Class RLN-Style API Credits in Cairo + STWO

## 1) What we built

This repo contains a runnable proof-of-concept Cairo program and benchmark harness for a fixed-class, membership-gated RLN-style API-credits flow.

- Identity commitment and inclusion proof against a Poseidon Merkle root.
- RLN-style share:
  - `a1 = Poseidon(identity_secret, ticket_index)`
  - `y = identity_secret + a1 * x`
- Public nullifier:
  - `nullifier = Poseidon(a1)`
- Solvency floor:
  - `(ticket_index + 1) * class_price <= deposit`

No refunds, no homomorphic encryption, and no signatures are implemented in this PoC.

## 2) Why this artifact exists

This replaces abstract discussion in the spec with measured STWO behavior for a concrete variant:

- `scarb build`
- `cairo-prove prove`
- `cairo-prove verify`
- Wall-clock benchmark numbers for proof generation and verification
- Relation/constraint-usage signals from verifier logs

The stack uses in-circuit Poseidon and the `cairo-prove` toolchain.
No pairing-based dependencies are introduced in this variant.

## 2.1) Benchmark environment

- CPU: Apple M3 Pro (12 cores)
- RAM: 18 GB
- OS: macOS 14.7 (arm64)
- Toolchain: `scarb 2.14.0`, Cairo compiler `2.14.0`
- Python: `3.13.5`
- Prover: `cairo-prove`
- Run timestamp: `2026-02-14T22:49:22Z`
- Iterations: `BENCH_ITERATIONS=5`

## 2.2) Caveat on non-monotonic depth behavior

Depth-16 timing appears below depth-8 in this run (`26,243ms` vs `17,688ms` p50).
Relation counts still increase with depth (notably `RangeCheck_19`), so this is treated as a trace/padding effect in this environment, not a functional circuit failure.

## 3) Circuit contract

Executable entrypoint order in Cairo:

1. `identity_secret: felt252`
2. `ticket_index: felt252`
3. `x: felt252`
4. `deposit: u256` (felt252 low, felt252 high)
5. `class_price: u256` (felt252 low, felt252 high)
6. `merkle_root: felt252`
7. `merkle_proof: Array<felt252>`

Public outputs:
- `nullifier`
- `x`
- `y`
- `merkle_root`

### Why witness `u256` is split

`deposit` and `class_price` are 256-bit values for monotonic numeric comparison.
In Cairo argument files, each `u256` is represented as two felt terms: `low`, `high`.

## 4) Reproducible benchmark workflow

### Generate deterministic argument files

```bash
./scripts/bench_inputs/generate_bench_args.py \
  --depths "8 16 20 32" \
  --out-dir scripts/bench_inputs
```

This copies committed Merkle roots/proofs from fixtures and rewrites witness fields when requested.

### Run benchmark suite

```bash
CAIRO_PROVE=/path/to/cairo-prove \
BENCH_DEPTHS="8 16 20 32" \
BENCH_ITERATIONS=5 \
./scripts/bench/run_depths.sh
```

Artifacts:
- `scripts/results/bench_runs.csv`
- `scripts/results/bench_summary.csv`
- `scripts/results/relation_counts.csv`
- `scripts/results/bench_report.md`

## 5) Current empirical baseline

Latest 5-run aggregate (`RUST_LOG=info`, single machine):

| depth | prove_wall_ms_min | prove_wall_ms_p50 | prove_wall_ms_p95 | prove_wall_ms_max | verify_wall_ms_min | verify_wall_ms_p95 | verify_wall_ms_max | proof_size_bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 8 | 19934 | 26243 | 33383 | 33383 | 81 | 104 | 104 | 14,048,899 |
| 16 | 15951 | 17688 | 43066 | 43066 | 119 | 458 | 458 | 14,349,849 |
| 20 | 14968 | 16245 | 27244 | 27244 | 71 | 116 | 116 | 14,436,847 |
| 32 | 15659 | 19466 | 21843 | 21843 | 63 | 99 | 99 | 14,472,551 |

Each value is from `BENCH_ITERATIONS=5` prove/verify runs.

## 6) Repo-level demos

- `scripts/slash.py` recovers `identity_secret` from two shares with identical `(nullifier, ticket_index)` and different `x`.
- `scripts/precompute_parallel.sh` produces consecutive tickets in parallel and measures batch wall-clock.
- `scripts/mini_api_server.py` offers a minimal `/submit` flow for proof verification, replay checks, and slash payload emission when nullifier reuse is detected with different `x`.

State in the API demo is in-memory and non-persistent.

## 7) Repository status

- Circuit and tests are in `src/lib.cairo` (9 passing tests)
- Benchmark orchestration and report tooling in `scripts/bench`
- Deterministic argument generation in `scripts/bench_inputs/generate_bench_args.py`
- Protocol flow demos in `scripts/` and `scripts/bench/`

## 8) What this demonstrates

This is a build/run/measure baseline for the fixed-class variant:
- witness checks are implemented and tested
- benchmarks and relation logs are reproducible locally
- protocol-flow artifacts (slashing, replay tracking, parallel generation) are included in a runnable demo stack
