#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${PROJECT_ROOT}"

BENCH_DEPTHS="${BENCH_DEPTHS:-8 16 20 32}"
BENCH_ITERATIONS="${BENCH_ITERATIONS:-5}"
RESULTS_DIR="${RESULTS_DIR:-${PROJECT_ROOT}/scripts/results/v2_kernel_only_$(date +%s)}"
SCARB_PROFILE="${SCARB_PROFILE:-release}"
RUN_TAG="run$(date +%s)"
PROVER_ENGINE="scarb-prove"
TARGET_NAME="zk_api_credits_v2_kernel"
MACHINE=$(python3 - <<'PY'
import platform
print(f"{platform.system()}-{platform.machine()}")
PY
)
mkdir -p "${RESULTS_DIR}"

if [[ "${BENCH_ITERATIONS}" -lt 1 ]]; then
  echo "BENCH_ITERATIONS must be >= 1" >&2
  exit 1
fi

if [[ "${SCARB_PROFILE}" == "release" ]]; then
  SCARB_GLOBAL_ARGS=(--release)
else
  SCARB_GLOBAL_ARGS=()
fi

echo "building once (${SCARB_PROFILE} profile) ..."
scarb ${SCARB_GLOBAL_ARGS[@]+"${SCARB_GLOBAL_ARGS[@]}"} build >/dev/null

RAW="${RESULTS_DIR}/runs.csv"
SUMMARY="${RESULTS_DIR}/summary.csv"
DELTA="${RESULTS_DIR}/v1_vs_v2_from_baseline.csv"
BASELINE_SUMMARY="${BASELINE_SUMMARY:-${PROJECT_ROOT}/scripts/results/main_baseline/bench_summary.csv}"

cat > "${RAW}" <<EOF
run_tag,prover_engine,profile,target,machine,depth,iteration,prove_wall_ms,verify_wall_ms,proof_size_bytes,proof_path
EOF

for depth in ${BENCH_DEPTHS}; do
  args_file="${PROJECT_ROOT}/scripts/bench_inputs/v2_kernel/depth_${depth}.json"
  if [[ ! -f "${args_file}" ]]; then
    echo "missing args file: ${args_file}" >&2
    exit 1
  fi

  for iteration in $(seq 1 "${BENCH_ITERATIONS}"); do
    prove_log="$(mktemp "${RESULTS_DIR}/.v2_d${depth}_i${iteration}_prove_XXXX.log")"
    start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    scarb ${SCARB_GLOBAL_ARGS[@]+"${SCARB_GLOBAL_ARGS[@]}"} prove --execute --no-build \
      --executable-name "${TARGET_NAME}" \
      --arguments-file "${args_file}" >"${prove_log}" 2>&1
    end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    prove_wall_ms=$((end_ms - start_ms))

    proof_path=$(python3 - "${prove_log}" <<'PY'
import re
import sys
text = open(sys.argv[1]).read()
m = re.search(r"Saving proof to: (.+)", text)
if not m:
    raise SystemExit("could not parse proof path")
print(m.group(1).strip())
PY
)
    rm -f "${prove_log}"

    verify_start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    scarb ${SCARB_GLOBAL_ARGS[@]+"${SCARB_GLOBAL_ARGS[@]}"} verify --proof-file "${proof_path}" >/dev/null 2>&1
    verify_end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    verify_wall_ms=$((verify_end_ms - verify_start_ms))
    proof_size_bytes=$(wc -c < "${proof_path}" | tr -d ' ')

    echo "${RUN_TAG},${PROVER_ENGINE},${SCARB_PROFILE},${TARGET_NAME},${MACHINE},${depth},${iteration},${prove_wall_ms},${verify_wall_ms},${proof_size_bytes},${proof_path}" >> "${RAW}"
    echo "depth=${depth} iter=${iteration} prove_ms=${prove_wall_ms} verify_ms=${verify_wall_ms} proof_bytes=${proof_size_bytes}"
  done
done

python3 - "${RAW}" "${SUMMARY}" "${RUN_TAG}" "${PROVER_ENGINE}" "${SCARB_PROFILE}" "${TARGET_NAME}" "${MACHINE}" <<'PY'
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median
import sys

raw_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
run_tag = sys.argv[3]
prover_engine = sys.argv[4]
profile = sys.argv[5]
target = sys.argv[6]
machine = sys.argv[7]

rows = list(csv.DictReader(raw_path.open()))
agg = defaultdict(lambda: {"prove": [], "verify": [], "size": []})

for row in rows:
    depth = int(row["depth"])
    agg[depth]["prove"].append(int(row["prove_wall_ms"]))
    agg[depth]["verify"].append(int(row["verify_wall_ms"]))
    agg[depth]["size"].append(int(row["proof_size_bytes"]))

with summary_path.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "run_tag",
        "prover_engine",
        "profile",
        "target",
        "machine",
        "depth",
        "samples",
        "prove_min_ms",
        "prove_p50_ms",
        "prove_max_ms",
        "verify_min_ms",
        "verify_p50_ms",
        "verify_max_ms",
        "size_min_bytes",
        "size_p50_bytes",
        "size_max_bytes",
    ])
    for depth in sorted(agg):
        prove = sorted(agg[depth]["prove"])
        verify = sorted(agg[depth]["verify"])
        size = sorted(agg[depth]["size"])
        w.writerow([
            run_tag,
            prover_engine,
            profile,
            target,
            machine,
            depth,
            len(prove),
            min(prove),
            int(median(prove)),
            max(prove),
            min(verify),
            int(median(verify)),
            max(verify),
            min(size),
            int(median(size)),
            max(size),
        ])
PY

if [[ -f "${BASELINE_SUMMARY}" ]]; then
  python3 - "${BASELINE_SUMMARY}" "${SUMMARY}" "${DELTA}" <<'PY'
import csv
import sys
from pathlib import Path

baseline = list(csv.DictReader(Path(sys.argv[1]).open()))
v2 = list(csv.DictReader(Path(sys.argv[2]).open()))
out = Path(sys.argv[3])

baseline_by_depth = {int(r["depth"]): r for r in baseline}
v2_by_depth = {int(r["depth"]): r for r in v2}

def read_p50(row, wall_key, compact_key):
    if wall_key in row:
        return float(row[wall_key])
    if compact_key in row:
        return float(row[compact_key])
    raise KeyError(f"missing expected key pair: {wall_key}/{compact_key}")

with out.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "depth",
        "v1_prove_p50_ms",
        "v2_prove_p50_ms",
        "prove_delta_pct",
        "v1_verify_p50_ms",
        "v2_verify_p50_ms",
        "verify_delta_pct",
        "v1_size_p50_bytes",
        "v2_size_p50_bytes",
        "size_delta_pct",
    ])
    for depth in sorted(set(baseline_by_depth) & set(v2_by_depth)):
        b = baseline_by_depth[depth]
        v = v2_by_depth[depth]
        v1_prove = read_p50(b, "prove_wall_ms_p50", "prove_p50_ms")
        v2_prove = read_p50(v, "prove_wall_ms_p50", "prove_p50_ms")
        v1_verify = read_p50(b, "verify_wall_ms_p50", "verify_p50_ms")
        v2_verify = read_p50(v, "verify_wall_ms_p50", "verify_p50_ms")
        v1_size = read_p50(b, "proof_size_bytes_p50", "size_p50_bytes")
        v2_size = read_p50(v, "proof_size_bytes_p50", "size_p50_bytes")

        prove_delta = ((v2_prove - v1_prove) / v1_prove) * 100 if v1_prove else 0.0
        verify_delta = ((v2_verify - v1_verify) / v1_verify) * 100 if v1_verify else 0.0
        size_delta = ((v2_size - v1_size) / v1_size) * 100 if v1_size else 0.0

        w.writerow([
            depth,
            int(v1_prove),
            int(v2_prove),
            round(prove_delta, 2),
            int(v1_verify),
            int(v2_verify),
            round(verify_delta, 2),
            int(v1_size),
            int(v2_size),
            round(size_delta, 2),
        ])
PY
fi

python3 - <<PY
import json
from datetime import datetime, timezone

meta = {
    "run_tag": "${RUN_TAG}",
    "prover_engine": "${PROVER_ENGINE}",
    "profile": "${SCARB_PROFILE}",
    "target": "${TARGET_NAME}",
    "machine": "${MACHINE}",
    "bench_depths": "${BENCH_DEPTHS}".split(),
    "iterations": int("${BENCH_ITERATIONS}"),
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
}
with open("${RESULTS_DIR}/bench_meta.json", "w") as f:
    json.dump(meta, f, indent=2)
PY

echo "raw runs: ${RAW}"
echo "summary : ${SUMMARY}"
if [[ -f "${DELTA}" ]]; then
  echo "delta   : ${DELTA}"
fi
