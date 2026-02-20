#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CAIRO_PROVE="${CAIRO_PROVE:-}"
if [[ -z "${CAIRO_PROVE}" ]]; then
  CAIRO_PROVE="$(command -v cairo-prove || true)"
fi
if [[ -z "${CAIRO_PROVE}" ]]; then
  for candidate in \
    "${PROJECT_ROOT}/../stwo-cairo-src/cairo-prove/target/release/cairo-prove" \
    "${PROJECT_ROOT}/../stwo-cairo/cairo-prove/target/release/cairo-prove"; do
    if [[ -x "${candidate}" ]]; then
      CAIRO_PROVE="${candidate}"
      break
    fi
  done
fi
CIRCUIT_BINARY="${PROJECT_ROOT}/target/release/zk_api_credits.executable.json"
RESULTS_DIR="${RESULTS_DIR:-${PROJECT_ROOT}/scripts/results/main_baseline}"

BENCH_DEPTHS=${BENCH_DEPTHS:-"8 16 20 32"}
ITERATIONS=${BENCH_ITERATIONS:-5}
COLLECT_RELATION_COUNTS=${COLLECT_RELATION_COUNTS:-1}
BENCH_INPUTS_DIR=${BENCH_INPUTS_DIR:-"${PROJECT_ROOT}/scripts/bench_inputs"}
PROVER_ENGINE="cairo-prove"
PROFILE="release"
TARGET_NAME="zk_api_credits"
MACHINE=$(python3 - <<'PY'
import platform
print(f"{platform.system()}-{platform.machine()}")
PY
)

if [[ ! -x "${CAIRO_PROVE}" ]]; then
  echo "cairo-prove binary not found at ${CAIRO_PROVE}" >&2
  echo "Set CAIRO_PROVE to your installed cairo-prove binary." >&2
  exit 1
fi

if [[ ! -d "${BENCH_INPUTS_DIR}" ]]; then
  echo "Benchmark inputs directory not found: ${BENCH_INPUTS_DIR}" >&2
  exit 1
fi

if [[ ! -f "${CIRCUIT_BINARY}" ]]; then
  echo "Executable artifact not found: ${CIRCUIT_BINARY}" >&2
  echo "Run: scarb --release build" >&2
  exit 1
fi

if [[ ${ITERATIONS} -lt 1 ]]; then
  echo "BENCH_ITERATIONS must be >= 1" >&2
  exit 1
fi

mkdir -p "${RESULTS_DIR}"
RUN_TAG="run$(date +%s)"

RAW_RESULTS_FILE="${RESULTS_DIR}/bench_runs.csv"
SUMMARY_FILE="${RESULTS_DIR}/bench_summary.csv"

cat > "${RAW_RESULTS_FILE}" <<EOF
run_tag,prover_engine,profile,target,machine,run_id,depth,iteration,prove_wall_ms,prove_log_ms,verify_wall_ms,proof_size_bytes,proof_path,prove_log_path,verify_log_path
EOF

run_id=0
for depth in ${BENCH_DEPTHS}; do
  args_file="${BENCH_INPUTS_DIR}/depth_${depth}.json"
  if [[ ! -f "${args_file}" ]]; then
    echo "Missing benchmark args: ${args_file}; skip depth=${depth}." >&2
    continue
  fi

  for iteration in $(seq 1 "${ITERATIONS}"); do
    run_id=$((run_id + 1))
    proof_file="${RESULTS_DIR}/depth_${depth}_run${iteration}_${RUN_TAG}_proof.json"
    prove_log="${RESULTS_DIR}/depth_${depth}_run${iteration}_${RUN_TAG}_prove.log"
    verify_log="${RESULTS_DIR}/depth_${depth}_run${iteration}_${RUN_TAG}_verify.log"

    start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    RUST_LOG=info ${CAIRO_PROVE} prove "${CIRCUIT_BINARY}" "${proof_file}" --arguments-file "${args_file}" >"${prove_log}" 2>&1
    end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    prove_wall_ms=$((end_ms - start_ms))
    proof_size_bytes=$(wc -c < "${proof_file}" | tr -d ' ')

    prove_log_ms=$(python3 - "${prove_log}" <<'PY'
import re
import sys
log_path = sys.argv[1]
text = open(log_path).read()
m = re.search(r"Proof generation completed in ([0-9.]+)s", text)
print(m.group(1) if m else "")
PY
)
    if [[ -n "${prove_log_ms}" ]]; then
      prove_log_ms=$(python3 - <<PY
import decimal
val = decimal.Decimal("${prove_log_ms}")
print(int(val * 1000))
PY
)
    fi

    verify_start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    RUST_LOG=info ${CAIRO_PROVE} verify "${proof_file}" >"${verify_log}" 2>&1
    verify_end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    verify_wall_ms=$((verify_end_ms - verify_start_ms))

    echo "${RUN_TAG},${PROVER_ENGINE},${PROFILE},${TARGET_NAME},${MACHINE},${run_id},${depth},${iteration},${prove_wall_ms},${prove_log_ms},${verify_wall_ms},${proof_size_bytes},${proof_file},${prove_log},${verify_log}" >> "${RAW_RESULTS_FILE}"

    echo "depth=${depth},iter=${iteration},prove_wall_ms=${prove_wall_ms},prove_log_ms=${prove_log_ms},verify_ms=${verify_wall_ms},proof_bytes=${proof_size_bytes}"
  done
done

python3 - "${RAW_RESULTS_FILE}" "${SUMMARY_FILE}" "${RUN_TAG}" "${PROVER_ENGINE}" "${PROFILE}" "${TARGET_NAME}" "${MACHINE}" <<'PY'
import csv
import math
from collections import defaultdict
from statistics import median
from pathlib import Path
import sys


def quantile(data, q):
    if not data:
        return ""
    data = sorted(data)
    index = int(math.ceil((len(data) * q)) - 1)
    if index < 0:
        index = 0
    if index >= len(data):
        index = len(data) - 1
    return data[index]


raw_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
run_tag = sys.argv[3]
prover_engine = sys.argv[4]
profile = sys.argv[5]
target = sys.argv[6]
machine = sys.argv[7]
rows = list(csv.DictReader(open(raw_path)))

agg = defaultdict(lambda: {
    "prove_wall_ms": [],
    "prove_log_ms": [],
    "verify_wall_ms": [],
    "proof_size_bytes": [],
})

for row in rows:
    d = int(row["depth"])
    agg[d]["prove_wall_ms"].append(int(row["prove_wall_ms"]))
    if row["prove_log_ms"]:
        agg[d]["prove_log_ms"].append(int(row["prove_log_ms"]))
    agg[d]["verify_wall_ms"].append(int(row["verify_wall_ms"]))
    agg[d]["proof_size_bytes"].append(int(row["proof_size_bytes"]))

with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "run_tag",
        "prover_engine",
        "profile",
        "target",
        "machine",
        "depth",
        "samples",
        "prove_wall_ms_min",
        "prove_wall_ms_p50",
        "prove_wall_ms_p95",
        "prove_wall_ms_max",
        "prove_wall_ms_avg",
        "prove_log_ms_min",
        "prove_log_ms_p50",
        "prove_log_ms_p95",
        "prove_log_ms_max",
        "prove_log_ms_avg",
        "verify_wall_ms_min",
        "verify_wall_ms_p50",
        "verify_wall_ms_p95",
        "verify_wall_ms_max",
        "verify_wall_ms_avg",
        "proof_size_bytes_min",
        "proof_size_bytes_p50",
        "proof_size_bytes_max",
    ])

    for depth in sorted(agg.keys()):
        data = agg[depth]
        pw = data["prove_wall_ms"]
        pl = data["prove_log_ms"]
        vw = data["verify_wall_ms"]
        ps = data["proof_size_bytes"]

        w.writerow([
            run_tag,
            prover_engine,
            profile,
            target,
            machine,
            depth,
            len(pw),
            min(pw),
            int(median(pw)),
            quantile(pw, 0.95),
            max(pw),
            int(sum(pw) / len(pw)),
            min(pl) if pl else "",
            int(median(pl)) if pl else "",
            quantile(pl, 0.95) if pl else "",
            max(pl) if pl else "",
            int(sum(pl) / len(pl)) if pl else "",
            min(vw),
            int(median(vw)),
            quantile(vw, 0.95),
            max(vw),
            int(sum(vw) / len(vw)),
            min(ps),
            int(median(ps)),
            max(ps),
        ])
PY

if [[ "${COLLECT_RELATION_COUNTS}" -eq 1 ]]; then
  "${PROJECT_ROOT}/scripts/bench/extract_relation_counts.py" \
    --verify-logs-dir "${RESULTS_DIR}" \
    --pattern "depth_*_${RUN_TAG}_verify.log" \
    --out "${RESULTS_DIR}/relation_counts.csv"
fi

python3 - <<PY
import json
from datetime import datetime, timezone

meta = {
    "run_tag": "${RUN_TAG}",
    "prover_engine": "${PROVER_ENGINE}",
    "profile": "${PROFILE}",
    "target": "${TARGET_NAME}",
    "machine": "${MACHINE}",
    "bench_depths": "${BENCH_DEPTHS}".split(),
    "iterations": int("${ITERATIONS}"),
    "cairo_prove": "${CAIRO_PROVE}",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
}
with open("${RESULTS_DIR}/bench_meta.json", "w") as f:
    json.dump(meta, f, indent=2)
PY

echo "Wrote raw runs: ${RAW_RESULTS_FILE}"
echo "Wrote summary: ${SUMMARY_FILE}"
if [[ "${COLLECT_RELATION_COUNTS}" -eq 1 ]]; then
  echo "Wrote relation counts: ${RESULTS_DIR}/relation_counts.csv"
fi
