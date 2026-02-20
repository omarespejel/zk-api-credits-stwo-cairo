#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def is_valid_cairo_prove(binary_path: Path) -> bool:
    """Best-effort sanity check to avoid picking dummy `cairo-prove` binaries."""
    if not (binary_path.exists() and binary_path.is_file()):
        return False
    try:
        completed = subprocess.run(
            [str(binary_path), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError:
        return False
    output = completed.stdout or ""
    return "Usage: cairo-prove" in output and "prove" in output and "verify" in output


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for preflight checks."""
    parser = argparse.ArgumentParser(description="Matrix-driven preflight smoke checks.")
    parser.add_argument(
        "--matrix",
        default="compat_matrix.json",
        help="Path to support-matrix contract JSON.",
    )
    parser.add_argument(
        "--skip-negative",
        action="store_true",
        help="Skip unsupported-path checks (not recommended).",
    )
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip scarb test (useful for fast local reruns).",
    )
    return parser.parse_args()


def run(
    cmd: list[str],
    cwd: Path,
    expect_success: bool = True,
    expected_substring: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and assert expected success/failure semantics."""
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = completed.stdout or ""

    if expect_success and completed.returncode != 0:
        print(output)
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(cmd)}")

    if not expect_success and completed.returncode == 0:
        print(output)
        raise RuntimeError(f"command unexpectedly succeeded: {' '.join(cmd)}")

    if expected_substring is not None and expected_substring not in output:
        print(output)
        raise RuntimeError(
            "command output did not include expected substring "
            f"'{expected_substring}': {' '.join(cmd)}"
        )
    return completed


def resolve_cairo_prove(project_root: Path) -> str | None:
    """Resolve cairo-prove from env, PATH, or known local fallback paths."""
    env_value = os.environ.get("CAIRO_PROVE")

    if env_value:
        candidate = Path(env_value)
        if is_valid_cairo_prove(candidate):
            return str(candidate)

    for fallback in [
        project_root / "../stwo-cairo-src/cairo-prove/target/release/cairo-prove",
        project_root / "../stwo-cairo/cairo-prove/target/release/cairo-prove",
    ]:
        if is_valid_cairo_prove(fallback):
            return str(fallback)

    which = shutil.which("cairo-prove")
    if which and is_valid_cairo_prove(Path(which)):
        return which
    return None


def parse_proof_path_from_scarb_output(output: str) -> str:
    """Extract emitted proof path from scarb prove output."""
    match = re.search(r"Saving proof to:\s*(.+)", output)
    if not match:
        raise RuntimeError("could not parse proof path from scarb output")
    return match.group(1).strip()


def main() -> int:
    """Execute matrix-driven smoke checks across supported and unsupported paths."""
    args = parse_args()
    project_root = Path(__file__).resolve().parents[2]
    matrix_path = (project_root / args.matrix).resolve()

    if not matrix_path.exists():
        raise FileNotFoundError(f"matrix file not found: {matrix_path}")

    matrix = json.loads(matrix_path.read_text())
    contracts = matrix.get("contracts", [])
    if not contracts:
        raise RuntimeError("compat matrix has no contracts")

    needs_cairo_prove = any(c.get("engine") == "cairo-prove" for c in contracts)
    cairo_prove = resolve_cairo_prove(project_root) if needs_cairo_prove else None
    if needs_cairo_prove and not cairo_prove:
        raise RuntimeError(
            "cairo-prove not found; set CAIRO_PROVE or install cairo-prove for matrix checks"
        )

    if not args.no_tests:
        run(["scarb", "test"], cwd=project_root, expect_success=True)
    run(["scarb", "--release", "build"], cwd=project_root, expect_success=True)

    with tempfile.TemporaryDirectory(prefix="zk_preflight_") as tmp:
        tmp_dir = Path(tmp)
        required_keys = {"id", "engine", "target", "status", "arguments_file"}
        for idx, contract in enumerate(contracts):
            missing = sorted(required_keys - set(contract.keys()))
            if missing:
                raise ValueError(
                    f"compat matrix contract[{idx}] missing required keys: {missing}; "
                    f"entry={contract}"
                )

            contract_id = contract["id"]
            engine = contract["engine"]
            target = contract["target"]
            status = contract["status"]
            arguments_file = project_root / contract["arguments_file"]
            if not arguments_file.exists():
                raise FileNotFoundError(f"[{contract_id}] args file missing: {arguments_file}")

            print(
                f"\n[preflight] id={contract_id} target={target} engine={engine} status={status}"
            )

            if status == "supported":
                if engine == "cairo-prove":
                    binary = project_root / contract["binary"]
                    if not binary.exists():
                        raise FileNotFoundError(
                            f"[{contract_id}] binary missing, run release build: {binary}"
                        )
                    proof_path = tmp_dir / f"{contract_id}_proof.json"
                    run(
                        [
                            str(cairo_prove),
                            "prove",
                            str(binary),
                            str(proof_path),
                            "--arguments-file",
                            str(arguments_file),
                        ],
                        cwd=project_root,
                        expect_success=True,
                    )
                    if contract.get("verify", False):
                        run(
                            [str(cairo_prove), "verify", str(proof_path)],
                            cwd=project_root,
                            expect_success=True,
                        )
                elif engine == "scarb-prove":
                    prove = run(
                        [
                            "scarb",
                            "--release",
                            "prove",
                            "--execute",
                            "--no-build",
                            "--executable-name",
                            target,
                            "--arguments-file",
                            str(arguments_file),
                        ],
                        cwd=project_root,
                        expect_success=True,
                    )
                    if contract.get("verify", False):
                        proof_path = parse_proof_path_from_scarb_output(prove.stdout)
                        run(
                            ["scarb", "--release", "verify", "--proof-file", proof_path],
                            cwd=project_root,
                            expect_success=True,
                        )
                else:
                    raise RuntimeError(f"[{contract_id}] unsupported engine: {engine}")

            elif status == "unsupported":
                if args.skip_negative:
                    if os.environ.get("CI"):
                        raise RuntimeError(
                            f"[preflight] --skip-negative cannot be used in CI "
                            f"(contract={contract_id})"
                        )
                    print(
                        f"[preflight][warning] skipped unsupported-path check for "
                        f"{contract_id}; do not use this in CI"
                    )
                    continue

                expected = contract.get("expected_error_substring")
                if expected is None:
                    raise ValueError(
                        f"[{contract_id}] unsupported contract must declare "
                        "expected_error_substring"
                    )
                if engine == "cairo-prove":
                    binary = project_root / contract["binary"]
                    if not binary.exists():
                        raise FileNotFoundError(
                            f"[{contract_id}] binary missing, run release build: {binary}"
                        )
                    proof_path = tmp_dir / f"{contract_id}_unexpected_proof.json"
                    run(
                        [
                            str(cairo_prove),
                            "prove",
                            str(binary),
                            str(proof_path),
                            "--arguments-file",
                            str(arguments_file),
                        ],
                        cwd=project_root,
                        expect_success=False,
                        expected_substring=expected,
                    )
                elif engine == "scarb-prove":
                    run(
                        [
                            "scarb",
                            "--release",
                            "prove",
                            "--execute",
                            "--no-build",
                            "--executable-name",
                            target,
                            "--arguments-file",
                            str(arguments_file),
                        ],
                        cwd=project_root,
                        expect_success=False,
                        expected_substring=expected,
                    )
                else:
                    raise RuntimeError(f"[{contract_id}] unsupported engine: {engine}")
            else:
                raise RuntimeError(f"[{contract_id}] invalid status: {status}")

    print("\npreflight: all matrix checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
