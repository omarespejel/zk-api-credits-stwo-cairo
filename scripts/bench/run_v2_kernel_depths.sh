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
MACHINE_CACHE="${PROJECT_ROOT}/.bench_machine_cache"
SCARB_VERSION="$(scarb --version 2>/dev/null || echo unknown)"
CACHE_KEY="${SCARB_VERSION}"
if [[ -f "${MACHINE_CACHE}" ]] && head -1 "${MACHINE_CACHE}" | grep -qF "${CACHE_KEY}"; then
  MACHINE=$(tail -1 "${MACHINE_CACHE}")
else
  MACHINE=$(python3 - <<'PY'
import platform
print(f"{platform.system()}-{platform.machine()}")
PY
)
  printf '%s\n%s\n' "${CACHE_KEY}" "${MACHINE}" > "${MACHINE_CACHE}"
fi
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

ms_now() {
  python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
}

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
    start_ms=$(ms_now)
    scarb ${SCARB_GLOBAL_ARGS[@]+"${SCARB_GLOBAL_ARGS[@]}"} prove --execute --no-build \
      --executable-name "${TARGET_NAME}" \
      --arguments-file "${args_file}" >"${prove_log}" 2>&1
    end_ms=$(ms_now)
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

    verify_start_ms=$(ms_now)
    scarb ${SCARB_GLOBAL_ARGS[@]+"${SCARB_GLOBAL_ARGS[@]}"} verify --proof-file "${proof_path}" >/dev/null 2>&1
    verify_end_ms=$(ms_now)
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
  python3 -m scripts.bench.build_v1_v2_delta \
    --baseline-summary "${BASELINE_SUMMARY}" \
    --v2-summary "${SUMMARY}" \
    --out "${DELTA}"
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
