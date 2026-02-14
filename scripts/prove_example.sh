#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAIRO_PROVE=${CAIRO_PROVE:-$(command -v cairo-prove || true)}
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
ARGS_FILE=${1:-"${PROJECT_ROOT}/scripts/bench_inputs/template_depth_args.json"}

if [[ -z "${CAIRO_PROVE}" ]]; then
  echo "cairo-prove binary not found. Set CAIRO_PROVE explicitly." >&2
  exit 1
fi

if [[ ! -f "${ARGS_FILE}" ]]; then
  echo "Arguments file not found: ${ARGS_FILE}" >&2
  exit 1
fi

cd "${PROJECT_ROOT}"
scarb --release build

echo "Proving with arguments from: ${ARGS_FILE}"
${CAIRO_PROVE} prove "${PROJECT_ROOT}/target/release/zk_api_credits.executable.json" "${PROJECT_ROOT}/proof.json" --arguments-file "${ARGS_FILE}"
${CAIRO_PROVE} verify "${PROJECT_ROOT}/proof.json"

proof_size=$(wc -c < "${PROJECT_ROOT}/proof.json")
echo "proof_size_bytes=${proof_size}"
