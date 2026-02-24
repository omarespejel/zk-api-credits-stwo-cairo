# zk-api-credits-stwo-cairo

this repo is a practical PoC for the fixed-class branch of zk api credits.
not a full protocol, not production, just trying to answer: "does this prove fast enough to be real?"

## what we implemented

core fixed-class circuit (`src/lib.cairo`, executable `zk_api_credits`):
- merkle membership for RLN rate commitment
- RLN share:
  - `a1 = Poseidon(identity_secret, scope, ticket_index)`
  - `y = identity_secret + a1 * x`
- nullifier:
  - `nullifier = Poseidon(a1)`
- bounds:
  - `ticket_index < user_message_limit`
- solvency floor:
  - `(ticket_index + 1) * class_price <= deposit`

also in repo:
- `v2_kernel` executable (minimal overhead probe, not full v2 protocol)
- slashing demo script
- mini api demo script
- benchmark harness + report scripts
- preflight matrix checks

## what this is not

- not deployment contracts
- not full refund / E(R) flow
- not pairing / bbs+ path
- not mobile-optimized proof transport

## quick numbers

historical 10-run snapshot used in working-group discussion (apple m3 pro):

| depth | prove p50 (ms) | verify p50 (ms) | proof size (bytes) |
|---|---:|---:|---:|
| 8  | 12734 | 66 | 14048899 |
| 16 |  8589 | 66 | 14349849 |
| 20 | 10400 | 64 | 14436847 |
| 32 | 13169 | 64 | 14472551 |

latest committed smoke baseline in this repo (`scripts/results/main_baseline/bench_summary.csv`, run `run1771628208`, 1 iter):

| depth | prove (ms) | verify (ms) | proof size (bytes) |
|---|---:|---:|---:|
| 8  | 9106 | 47 | 13928872 |
| 16 | 8258 | 48 | 14376734 |
| 20 | 8515 | 50 | 14285650 |
| 32 | 6407 | 46 | 14282230 |

rough reading:
- verify is cheap
- prove is the heavy part
- pre-generation is the intended UX model

## proof size note (important)

the raw proof file is pretty json, so size looks worse than wire reality.
if you just ran step 2, use `./proof.json`.
the numbers below are from a committed baseline artifact for reproducibility:
`scripts/results/main_baseline/depth_16_run1_run1771628208_proof.json`

- pretty: `14376734` bytes
- minified: `3550433` bytes
- gzip: `1517215` bytes

check it yourself:

```bash
# from step 2 output:
# python3 scripts/proof_size.py ./proof.json
#
# reproducible committed artifact:
python3 scripts/proof_size.py scripts/results/main_baseline/depth_16_run1_run1771628208_proof.json
```

## repo map

- `src/lib.cairo`: fixed-class circuit + `v2_kernel` + tests
- `Scarb.toml`: executable targets
- `scripts/ci/preflight.py`: matrix smoke/negative checks
- `scripts/bench/run_depths.sh`: baseline benchmark
- `scripts/bench/run_v1_v2_delta.sh`: v1 vs v2-kernel delta
- `scripts/bench/run_v2_kernel_depths.sh`: v2-kernel-only depth benchmark
- `scripts/bench/combine_tables.py`: guardrails for mixed benchmark families
- `scripts/v2_sequential_demo.py`: sequential state demo for v2-kernel
- `scripts/proof_size.py`: proof size formats

## support matrix (contract)

full local matrix in `compat_matrix.json`:
- `main_cairo_prove` -> supported
- `v2_kernel_scarb_prove` -> supported
- `v2_kernel_cairo_prove` -> intentionally unsupported (expected error tracked)

ci matrix in `compat_matrix_ci.json`:
- scarb-only supported smoke paths
- intentionally does **not** run raw `cairo-prove` unsupported-path negative check

preflight enforces matrix schema version and fails hard on drift.

## quickstart

### 1) build + tests

```bash
scarb test
scarb --release build
```

### 2) fixed-class prove/verify (raw cairo-prove)

```bash
/path/to/cairo-prove prove \
  target/release/zk_api_credits.executable.json \
  ./proof.json \
  --arguments-file scripts/bench_inputs/depth_8.json

/path/to/cairo-prove verify ./proof.json
```

### 3) v2-kernel probe path (scarb prove/verify)

```bash
scarb --release prove --execute --no-build \
  --executable-name zk_api_credits_v2_kernel \
  --arguments-file scripts/bench_inputs/v2_kernel/depth_8.json

# scarb prints: "Saving proof to: <proof-file>"
# (usually under target/execute/.../proof/proof.json)
scarb --release verify --proof-file <proof-file-from-line-above>
```

### 4) v2 sequential state demo (no parallel branches)

```bash
python3 scripts/v2_sequential_demo.py --depth 8 --steps 3
```

typical prove times per depth (Apple M-series, release profile):

| depth | prove time | recommended `--timeout` |
|-------|-----------|------------------------|
| 8     | ~3s       | 600 (default)          |
| 16    | ~5s       | 600 (default)          |
| 20    | ~8s       | 600 (default)          |
| 32    | ~15s      | 600 (default)          |

for slower machines or CI runners, set a higher timeout via
`--timeout 1200` or `V2_SEQUENTIAL_DEMO_TIMEOUT_S=1200`.

## cross-repo interop check

there is now a shared-vector alignment check against Vivian's Cairo RLN repo.
it verifies both implementations produce identical `nullifier` and `y` for the same input vector.

default vector:
- `scripts/interop/vectors/shared_vector_01.json`

run it:

```bash
python3 scripts/interop/check_alignment.py \
  --our-repo . \
  --vivian-repo ../cairo-circuits \
  --scarb-our scarb \
  --scarb-vivian ~/.asdf/installs/scarb/2.17.0-rc.1/bin/scarb
```

notes:
- this check computes a shared root first using `derive_rate_commitment_root`.
- it then executes both repos with aligned inputs and enforces output equality on `nullifier` and `y`.

## benchmark commands

baseline depths:

```bash
# defaults if unset:
# BENCH_DEPTHS="8 16 20 32", BENCH_ITERATIONS=5
# output dir default: scripts/results/main_baseline/
BENCH_DEPTHS="8 16 20 32" BENCH_ITERATIONS=10 ./scripts/bench/run_depths.sh
```

v1 vs v2-kernel:

```bash
# defaults if unset:
# BENCH_DEPTHS="8 16 20 32", BENCH_ITERATIONS=5, SCARB_PROFILE=release
# output dir pattern: scripts/results/v1_v2_delta_<unix_timestamp>/
BENCH_ITERATIONS=10 ./scripts/bench/run_v1_v2_delta.sh
```

v2-kernel depths only:

```bash
# defaults if unset:
# BENCH_DEPTHS="8 16 20 32", BENCH_ITERATIONS=5, SCARB_PROFILE=release
# output dir pattern: scripts/results/v2_kernel_only_<unix_timestamp>/
# if scripts/results/main_baseline/bench_summary.csv exists and engine/profile
# matches (or ALLOW_MIXED_BASELINE=1), also writes:
# scripts/results/v2_kernel_only_<unix_timestamp>/v1_vs_v2_from_baseline.csv
BENCH_ITERATIONS=10 ./scripts/bench/run_v2_kernel_depths.sh
```

combined report (with guardrail):

```bash
# replace <ts> with the unix timestamp suffix from your delta run dir
# ex: scripts/results/v1_v2_delta_1771699999/ -> <ts> is 1771699999
python3 scripts/bench/combine_tables.py \
  --main-summary scripts/results/main_baseline/bench_summary.csv \
  --delta-summary scripts/results/v1_v2_delta_<ts>/summary.csv \
  --delta-table scripts/results/v1_v2_delta_<ts>/v1_vs_v2_delta.csv \
  --out scripts/results/combined_report.md
```

## preflight

full local preflight:

```bash
python3 scripts/ci/preflight.py
```

ci-equivalent preflight:

```bash
python3 scripts/ci/preflight.py --matrix compat_matrix_ci.json
```

## ai review policy

- CodeRabbit + Greptile are advisory review bots in this repo.
- Greptile `fixWithAI` is enabled for suggestion quality, but it does **not** auto-commit code.
- all code changes still go through PR review + required checks before merge.
- bot noise is limited with `excludeAuthors` in `greptile.json` (dependency/update bots).

## caveats (current)

- `v2_kernel` on raw `cairo-prove` is still unsupported in this env
- ci does scarb-only smoke coverage
- proof size depends a lot on serialization format

## publish hygiene

before posting numbers, use:
- `PUBLISH_CHECKLIST.md`

## references

- main thread: https://ethresear.ch/t/zk-api-usage-credits-llms-and-beyond/24104
