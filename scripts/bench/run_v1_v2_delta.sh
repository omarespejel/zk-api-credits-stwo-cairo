#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${PROJECT_ROOT}"

BENCH_DEPTHS="${BENCH_DEPTHS:-8 16 20 32}"
BENCH_ITERATIONS="${BENCH_ITERATIONS:-5}"
RESULTS_DIR="${RESULTS_DIR:-${PROJECT_ROOT}/scripts/results/v1_v2_delta_$(date +%s)}"
SCARB_PROFILE="${SCARB_PROFILE:-release}"
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
scarb "${SCARB_GLOBAL_ARGS[@]}" build >/dev/null

RAW="${RESULTS_DIR}/runs.csv"
SUMMARY="${RESULTS_DIR}/summary.csv"
DELTA="${RESULTS_DIR}/v1_vs_v2_delta.csv"

cat > "${RAW}" <<EOF
variant,depth,iteration,prove_wall_ms,verify_wall_ms,proof_size_bytes,proof_path
EOF

run_variant() {
  local variant="$1"
  local executable_name="$2"
  local args_dir="$3"

  for depth in ${BENCH_DEPTHS}; do
    local args_file="${args_dir}/depth_${depth}.json"
    if [[ ! -f "${args_file}" ]]; then
      echo "missing args file: ${args_file}" >&2
      exit 1
    fi

    for iteration in $(seq 1 "${BENCH_ITERATIONS}"); do
      local start_ms end_ms prove_wall_ms
      local prove_log
      prove_log="$(mktemp "${RESULTS_DIR}/.${variant}_d${depth}_i${iteration}_prove_XXXX.log")"
      start_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
      scarb "${SCARB_GLOBAL_ARGS[@]}" prove --execute --no-build \
        --executable-name "${executable_name}" \
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
      scarb "${SCARB_GLOBAL_ARGS[@]}" verify --proof-file "${proof_path}" >/dev/null 2>&1
      verify_end_ms=$(python3 - <<'PY'
import time
print(int(time.time() * 1000))
PY
)
      verify_wall_ms=$((verify_end_ms - verify_start_ms))

      proof_size_bytes=$(wc -c < "${proof_path}" | tr -d ' ')
      echo "${variant},${depth},${iteration},${prove_wall_ms},${verify_wall_ms},${proof_size_bytes},${proof_path}" >> "${RAW}"
      echo "${variant} depth=${depth} iter=${iteration} prove_ms=${prove_wall_ms} verify_ms=${verify_wall_ms} proof_bytes=${proof_size_bytes}"
    done
  done
}

run_variant "v1" "zk_api_credits" "${PROJECT_ROOT}/scripts/bench_inputs"
run_variant "v2_kernel" "zk_api_credits_v2_kernel" "${PROJECT_ROOT}/scripts/bench_inputs/v2_kernel"

python3 - "${RAW}" "${SUMMARY}" "${DELTA}" <<'PY'
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median
import sys

raw_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
delta_path = Path(sys.argv[3])

rows = list(csv.DictReader(raw_path.open()))

agg = defaultdict(lambda: {"prove": [], "verify": [], "size": []})
for row in rows:
    key = (row["variant"], int(row["depth"]))
    agg[key]["prove"].append(int(row["prove_wall_ms"]))
    agg[key]["verify"].append(int(row["verify_wall_ms"]))
    agg[key]["size"].append(int(row["proof_size_bytes"]))

with summary_path.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "variant",
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
    for (variant, depth) in sorted(agg.keys()):
        prove = sorted(agg[(variant, depth)]["prove"])
        verify = sorted(agg[(variant, depth)]["verify"])
        size = sorted(agg[(variant, depth)]["size"])
        w.writerow([
            variant,
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

table = {}
for (variant, depth), vals in agg.items():
    table[(variant, depth)] = {
        "prove": int(median(sorted(vals["prove"]))),
        "verify": int(median(sorted(vals["verify"]))),
        "size": int(median(sorted(vals["size"]))),
    }

depths = sorted({depth for _, depth in table.keys()})
with delta_path.open("w", newline="") as f:
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
    for depth in depths:
        v1 = table.get(("v1", depth))
        v2 = table.get(("v2_kernel", depth))
        if v1 is None or v2 is None:
            continue
        prove_delta_pct = ((v2["prove"] - v1["prove"]) / v1["prove"]) * 100 if v1["prove"] else 0.0
        verify_delta_pct = ((v2["verify"] - v1["verify"]) / v1["verify"]) * 100 if v1["verify"] else 0.0
        size_delta_pct = ((v2["size"] - v1["size"]) / v1["size"]) * 100 if v1["size"] else 0.0
        w.writerow([
            depth,
            v1["prove"],
            v2["prove"],
            round(prove_delta_pct, 2),
            v1["verify"],
            v2["verify"],
            round(verify_delta_pct, 2),
            v1["size"],
            v2["size"],
            round(size_delta_pct, 2),
        ])

print(f"wrote {summary_path}")
print(f"wrote {delta_path}")
PY

echo "raw runs: ${RAW}"
echo "summary : ${SUMMARY}"
echo "delta   : ${DELTA}"
