#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PROJECT_ROOT}"

CAIRO_PROVE="${CAIRO_PROVE:-$(command -v cairo-prove || true)}"
CAIRO_RUST_LOG="${CAIRO_RUST_LOG:-info}"
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
if [[ -z "${CAIRO_PROVE}" ]]; then
  echo "cairo-prove binary not found. Set CAIRO_PROVE." >&2
  exit 1
fi

DEPTH="${DEPTH:-8}"
COUNT="${COUNT:-5}"
BASE_INDEX="${BASE_INDEX:-0}"
X_START="${X_START:-1000}"
X_STEP="${X_STEP:-7}"
VERIFY_AFTER="${VERIFY_AFTER:-0}"
OUT_DIR="${OUT_DIR:-scripts/results/parallel_batch_$(date +%s)}"
TARGET="${PROJECT_ROOT}/target/release/zk_api_credits.executable.json"
ARGS_BASE="scripts/bench_inputs/depth_${DEPTH}.json"

if [[ ! -f "${ARGS_BASE}" ]]; then
  echo "Arguments template not found: ${ARGS_BASE}" >&2
  exit 1
fi
if [[ ! -f "${TARGET}" ]]; then
  echo "Executable not found: ${TARGET}. Run scarb build." >&2
  exit 1
fi

if (( COUNT <= 0 )); then
  echo "COUNT must be >= 1" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

echo "Spawning ${COUNT} parallel proofs at depth ${DEPTH} in ${OUT_DIR}"
run_start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)

job_meta=()
pids=()

for i in $(seq 0 $((COUNT - 1))); do
  ticket_index=$((BASE_INDEX + i))
  x=$((X_START + i * X_STEP))
  args_file="${OUT_DIR}/depth_${DEPTH}_ticket_${ticket_index}_x_${x}_args.json"
  proof_file="${OUT_DIR}/depth_${DEPTH}_ticket_${ticket_index}_x_${x}_proof.json"
  log_file="${OUT_DIR}/depth_${DEPTH}_ticket_${ticket_index}_x_${x}_prove.log"
  meta_file="${OUT_DIR}/depth_${DEPTH}_ticket_${ticket_index}_x_${x}_meta.txt"

  python3 - "$ARGS_BASE" "$ticket_index" "$x" "$args_file" <<'PY'
import json
import sys
base_path, ticket_index, x, out_path = sys.argv[1:5]
ticket = int(ticket_index)
x_value = int(x)
with open(base_path) as f:
    args = json.load(f)
args[1] = hex(ticket)
args[2] = hex(x_value)
with open(out_path, "w") as f:
    json.dump(args, f, separators=(",", ":"), sort_keys=False)
PY

  (
    start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    if RUST_LOG="${CAIRO_RUST_LOG}" "${CAIRO_PROVE}" prove \
      "${TARGET}" \
      "${proof_file}" \
      --arguments-file "${args_file}" \
      >"${log_file}" \
      2>&1; then
      prove_status=0
    else
      prove_status=$?
    fi
    end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
    wall_ms=$((end_ms - start_ms))
    printf "%s|%s|%s|%s\n" \
      "${ticket_index}" "${x}" "${prove_status}" "${wall_ms}" > "${meta_file}"
  ) &
  pid=$!
  pids+=("${pid}")
  job_meta+=("${ticket_index}:${x}:${proof_file}:${log_file}:${meta_file}")
  echo "started pid=${pid} ticket=${ticket_index} x=${x}"
done

echo
echo "Waiting for ${#pids[@]} proofs..."
for pid in "${pids[@]}"; do
  wait "${pid}" || true
done

run_end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
elapsed_ms=$((run_end_ms - run_start_ms))
elapsed_s=$(python3 - <<PY
import math
print(round(${elapsed_ms} / 1000, 2))
PY
)

success_count=0
failed_count=0
echo
echo "Proof summary:"
for item in "${job_meta[@]}"; do
  IFS=":" read -r ticket_index x proof_file log_file meta_file <<< "${item}"

  if [[ ! -f "${meta_file}" ]]; then
    status="missing-meta"
    wall_ms_display="n/a"
    proof_status="1"
    failed_count=$((failed_count + 1))
  else
    IFS="|" read -r _ _ proof_status wall_ms < "${meta_file}"
    wall_ms_display="${wall_ms}ms"
    if [[ "${proof_status}" == "0" && -s "${proof_file}" ]]; then
      status="proved"
      success_count=$((success_count + 1))
    else
      status="failed"
      failed_count=$((failed_count + 1))
    fi
  fi

  if [[ "${VERIFY_AFTER}" == "1" && "${proof_status}" == "0" ]]; then
    if RUST_LOG="${CAIRO_RUST_LOG}" "${CAIRO_PROVE}" verify "${proof_file}" >/dev/null 2>&1; then
      status="verified"
    else
      status="prove_invalid"
    fi
  fi

  proof_bytes=0
  if [[ -f "${proof_file}" ]]; then
    proof_bytes=$(wc -c < "${proof_file}" | tr -d ' ')
  fi

  echo "ticket=${ticket_index} x=${x} proof=${proof_file} status=${status} wall_ms=${wall_ms_display} proof_bytes=${proof_bytes}"
done

echo
echo "parallel wall-clock: ${elapsed_ms}ms (${elapsed_s}s)"
echo "jobs started: ${#pids[@]}  output directory: ${OUT_DIR}"
echo "proved jobs: ${success_count}"
echo "failed jobs: ${failed_count}"
