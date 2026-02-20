# zk_api_credits

A small, self‑contained proof‑of‑concept to answer one question from Davide’s “ZK API Usage Credits: LLMs and Beyond” post:

> Is the fixed‑class RLN-style design actually practical today on a real prover, or is it just a nice diagram?

I implemented one concrete instance and measured it end‑to‑end.

## TL;DR

- Circuit implements:
  - Poseidon Merkle membership for `identity_secret` (leaf commitment).
  - RLN share `y = k + a * x` with `a = Poseidon(identity_secret, scope, ticket_index)`.
  - Nullifier `Poseidon(a)` for rate limiting.
  - Solvency floor `(ticket_index + 1) * class_price <= deposit` (fixed‑class cost).
- Benchmarked on an Apple M3 Pro (10 runs per depth: 8, 16, 20, 32):
  - **Prove p50:** ≈ 8.6–13.2s depending on depth.
  - **Verify p50:** ≈ 64–66ms for all depths.
  - **Proof size:** ≈ 14.0–14.5 MB.
- Interpretation:
  - Verification is cheap and essentially depth‑independent.
  - Proving time is dominated by prover overhead, not circuit size, but is compatible with **pre‑generating proofs** for human‑paced LLM/API usage.

For this experiment I used Cairo plus a STARK prover I know well, but the circuit structure is generic. Nothing in this repo assumes a specific chain or proving stack beyond “there is a zkVM and a STARK prover”; it’s meant as one concrete data point, not an argument for one stack over another.

## Why this repo exists

Davide’s write‑up explores a full ZK API credits protocol: Merkle‑gated identities, RLN‑style rate limiting, solvency, refunds, and slashing. The part I focused on here is the **fixed‑class branch** he mentions as a special case: every call costs the same, no refunds, just “do I still have credits left or not?”.

My goals were:

- Check that the fixed‑class variant can be implemented cleanly as a circuit.
- Get real prove/verify numbers on a modern STARK prover.
- See whether those numbers line up with the kind of LLM/API usage patterns in the post (e.g. pre‑generating proofs while the user reads responses).

This repo:

- Implements the fixed‑class circuit (membership, RLN share, nullifier, solvency floor).
- Wires it into a prover with a reproducible benchmarking harness.
- Adds small “spec demos” (slashing recovery and a tiny API server) to exercise both the honest path and the slashing path.

It is **not** a protocol proposal and **not** meant for production use. It’s an implementation artifact to test whether one branch of Davide’s design behaves well in practice.

## How it relates to Davide’s post

Very roughly, his post has two layers:

- A **core RLN layer**: identities in a Merkle tree, RLN shares, nullifiers, solvency, and slashing.
- A **refund / E(R) layer**: handling variable‑cost calls with signed refunds or a homomorphic commitment to total refunds.

This repo only targets the first layer, and within that, the fixed‑class case:

- Poseidon membership in a Merkle tree (identity leaf).
- RLN share construction `y = k + a * x` with `a = Poseidon(identity_secret, scope, ticket_index)`.
- Nullifier `Poseidon(a)` for rate limiting.
- Solvency floor `(ticket_index + 1) * class_price <= deposit`.

The refund / E(R) layer (in‑circuit signature verification, homomorphic updates to commitments) is deliberately left out. In Davide’s terms, you can think of this as answering:

> “If we temporarily set R = 0 and keep C_max constant, does the rest of the mechanism behave well on a real prover?”

The answer from this repo is: **for human‑paced LLM/API usage, yes.** Verification is ~65ms, proof sizes are ~14MB, and proving can be pushed into pre‑generation between user requests.

## Snapshot benchmark results

Latest clean run (2026-02-14T23:38:01Z UTC, 10 iterations, Apple M3 Pro):

| depth | prove p50 (ms) | verify p50 (ms) | proof size (bytes) |
|---|---:|---:|---:|
| 8  | 12734 | 66 | 14048899 |
| 16 |  8589 | 66 | 14349849 |
| 20 | 10400 | 64 | 14436847 |
| 32 | 13169 | 64 | 14472551 |

More detailed stats (min/p95/max, relation counts, etc.) are in `scripts/results/bench_report.md` and `scripts/results/bench_summary.csv`.

Tiny note on "proof size": the files in `scripts/results/*_proof.json` are pretty-printed JSON, so they look huge.
If you just want a quick "ok how big is this really" number, gzip is a decent proxy:

```bash
python3 scripts/proof_size.py scripts/results/depth_16_run1_proof.json
```

## Scope and non‑goals

What this repo includes:

- Fixed‑class circuit behavior.
- Benchmark and reproducibility harness.
- Protocol‑flow scripts for slashing/replay and pre‑generation.

What this repo does not include:

- Protocol deployment contracts.
- Networking or chain‑side accounting.
- Refund pathways or class‑transition logic.
- Pairing primitives or BBS+ components.

## Usage

```bash
cd zk-api-credits-stwo-cairo
scarb build

# one‑shot prove + verify with template arguments
/path/to/cairo-prove prove target/release/zk_api_credits.executable.json ./proof.json \
  --arguments-file scripts/bench_inputs/template_depth_args.json
/path/to/cairo-prove verify ./proof.json
```
