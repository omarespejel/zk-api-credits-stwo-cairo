#!/usr/bin/env python3
"""Sequential V2 kernel state demo.

Chain fixture schema: each step must have step, ticket_index, scope,
refund_commitment_prev, refund_amount, refund_commitment_next_expected,
server_pubkey, signature_r, signature_s. Genesis step (step=0) must have
refund_commitment_prev equal to GENESIS_REFUND_COMMITMENT_PREV. Steps must be
monotonic and gap-free (0, 1, 2, ...).
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

V2_FIXED_PREFIX_LEN = 11
GENESIS_REFUND_COMMITMENT_PREV = 0x7B  # expected refund_commitment_prev for step=0
V2_PROOF_LEN_IDX = 10
V2_TAIL_LEN = 7
V2_REMASK_NONCE_OFFSET = 3  # relative offset within the tail (0 = refund_commitment_prev)
V2_TICKET_INDEX_IDX = 1    # absolute index within the fixed prefix
V2_SCOPE_IDX = 3            # absolute index within the fixed prefix (coincidentally == REMASK_NONCE_OFFSET)


def parse_int(value: str | int) -> int:
    """Convert a hex/decimal string or int to int, auto-detecting base."""
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def to_hex(value: int) -> str:
    """Format an integer as a 0x-prefixed hex string."""
    return hex(value)


def to_args(values: list[int]) -> str:
    """Join a list of ints into a comma-separated hex string for scarb CLI."""
    return ",".join(to_hex(v) for v in values)


DEFAULT_SUBPROCESS_TIMEOUT_S = 600
ENV_TIMEOUT = "V2_SEQUENTIAL_DEMO_TIMEOUT_S"


def _timeout_seconds(args: argparse.Namespace) -> int:
    """Resolve timeout: --timeout flag > env var > default (600s)."""
    if getattr(args, "timeout", None) is not None:
        return args.timeout
    raw = os.environ.get(ENV_TIMEOUT)
    if raw:
        return int(raw)
    return DEFAULT_SUBPROCESS_TIMEOUT_S


def run(cmd: list[str], cwd: Path, timeout_s: int = DEFAULT_SUBPROCESS_TIMEOUT_S) -> tuple[str, int]:
    """Run a subprocess, returning (stdout, elapsed_ms). Raises on failure or timeout."""
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        partial = exc.output or ""
        raise RuntimeError(
            f"command timed out after {timeout_s}s ({elapsed_ms}ms elapsed): "
            f"{' '.join(cmd)}\n{partial}"
        ) from exc
    elapsed_ms = int((time.monotonic() - start) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc.stdout, elapsed_ms


def parse_proof_path(prove_output: str) -> str:
    """Extract the proof file path from scarb prove stdout."""
    for line in prove_output.splitlines():
        marker = "Saving proof to:"
        if marker in line:
            return line.split(marker, 1)[1].strip()
    raise ValueError(f"could not parse proof path from output:\n{prove_output}")


def extract_prefix_and_remask(base_args: list[int]) -> tuple[list[int], int]:
    """Split base v2 args into (fixed prefix, remask_nonce) by parsing the proof length field."""
    # v2_kernel args (0-indexed):
    # 0..9   fixed public/private prefix ending at merkle_root
    # 10     merkle_proof length
    # 11..   merkle_proof elements
    # tail   [refund_commitment_prev, refund_amount, refund_commitment_next_expected,
    #         remask_nonce, server_pubkey, signature_r, signature_s]
    if len(base_args) < V2_FIXED_PREFIX_LEN + 1:
        raise ValueError("base v2 args too short")
    proof_len = parse_int(base_args[V2_PROOF_LEN_IDX])
    prefix_len = V2_FIXED_PREFIX_LEN + proof_len
    if len(base_args) < prefix_len + V2_TAIL_LEN:
        raise ValueError("base v2 args malformed: expected v2 extras tail")
    remask_nonce = parse_int(base_args[prefix_len + V2_REMASK_NONCE_OFFSET])
    return [parse_int(v) for v in base_args[:prefix_len]], remask_nonce


def build_v2_args(prefix: list[int], remask_nonce: int, step: dict) -> list[int]:
    """Construct v2_kernel CLI args from the fixed prefix and a chain step dict."""
    args = list(prefix)
    args[V2_TICKET_INDEX_IDX] = parse_int(step["ticket_index"])
    args[V2_SCOPE_IDX] = parse_int(step["scope"])
    args.extend(
        [
            parse_int(step["refund_commitment_prev"]),
            parse_int(step["refund_amount"]),
            parse_int(step["refund_commitment_next_expected"]),
            remask_nonce,
            parse_int(step["server_pubkey"]),
            parse_int(step["signature_r"]),
            parse_int(step["signature_s"]),
        ]
    )
    return args


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the sequential v2 demo."""
    p = argparse.ArgumentParser(description="Sequential V2 kernel state demo (no parallel branches).")
    p.add_argument("--repo", default=".")
    p.add_argument("--depth", type=int, default=8)
    p.add_argument("--steps", type=int, default=3)
    p.add_argument("--skip-build", action="store_true")
    p.add_argument("--skip-verify", action="store_true")
    p.add_argument("--chain-file", default="scripts/v2_fixtures/sequential_chain.json")
    p.add_argument("--scarb", default="scarb")
    p.add_argument(
        "--timeout",
        type=int,
        default=None,
        metavar="SECONDS",
        help=f"subprocess timeout (default: {DEFAULT_SUBPROCESS_TIMEOUT_S} or {ENV_TIMEOUT})",
    )
    return p.parse_args()


def main() -> int:
    """Run a sequential chain of v2 proofs and report results as JSON."""
    args = parse_args()
    repo = Path(args.repo).resolve()
    base_args_path = repo / f"scripts/bench_inputs/v2_kernel/depth_{args.depth}.json"
    chain_path = repo / args.chain_file

    if not base_args_path.exists():
        raise FileNotFoundError(f"missing base args file: {base_args_path}")
    if not chain_path.exists():
        raise FileNotFoundError(f"missing chain file: {chain_path}")

    base_args = json.loads(base_args_path.read_text())
    chain = json.loads(chain_path.read_text())
    if args.steps < 1:
        raise ValueError("--steps must be >= 1")
    if args.steps > len(chain):
        raise ValueError(f"--steps={args.steps} exceeds available chain length={len(chain)}")

    prefix, remask_nonce = extract_prefix_and_remask(base_args)
    steps = chain[: args.steps]

    timeout_s = _timeout_seconds(args)
    if not args.skip_build:
        run([args.scarb, "--release", "build"], cwd=repo, timeout_s=timeout_s)

    REQUIRED_STEP_KEYS = {
        "step",
        "ticket_index",
        "scope",
        "refund_commitment_prev",
        "refund_amount",
        "refund_commitment_next_expected",
        "server_pubkey",
        "signature_r",
        "signature_s",
    }
    for i, s in enumerate(chain):
        missing = REQUIRED_STEP_KEYS - s.keys()
        if missing:
            raise ValueError(
                f"chain entry {i} is missing required fields: {', '.join(sorted(missing))}"
            )
        step_no = parse_int(s["step"])
        if step_no != i:
            raise ValueError(
                f"chain entry {i} has step={step_no}; expected {i} "
                "(monotonic contiguous sequence starting at 0)"
            )

    local_state = parse_int(chain[0]["refund_commitment_prev"])
    if local_state == 0:
        raise ValueError("chain fixture has zero initial refund_commitment_prev; likely invalid")
    if local_state != GENESIS_REFUND_COMMITMENT_PREV:
        raise ValueError(
            f"chain fixture genesis refund_commitment_prev={to_hex(local_state)} "
            f"does not match expected {to_hex(GENESIS_REFUND_COMMITMENT_PREV)}"
        )
    runs = []

    for step in steps:
        prev = parse_int(step["refund_commitment_prev"])
        nxt = parse_int(step["refund_commitment_next_expected"])
        if prev != local_state:
            raise RuntimeError(
                f"state mismatch before prove at step={step['step']}: local={to_hex(local_state)} prev={to_hex(prev)}"
            )

        v2_args = build_v2_args(prefix, remask_nonce, step)
        prove_out, prove_ms = run(
            [
                args.scarb,
                "--release",
                "prove",
                "--execute",
                "--no-build",
                "--executable-name",
                "zk_api_credits_v2_kernel",
                "--arguments",
                to_args(v2_args),
            ],
            cwd=repo,
            timeout_s=timeout_s,
        )
        proof_path = parse_proof_path(prove_out)

        verify_ms = None
        if not args.skip_verify:
            _, verify_ms = run(
                [args.scarb, "--release", "verify", "--proof-file", proof_path],
                cwd=repo,
                timeout_s=timeout_s,
            )

        local_state = nxt
        runs.append(
            {
                "step": step["step"],
                "ticket_index": step["ticket_index"],
                "proof_path": proof_path,
                "prove_ms": prove_ms,
                "verify_ms": verify_ms,
                "state_next": to_hex(local_state),
            }
        )

    # NOTE: The following are Python-level state comparisons only.
    # They verify that fixture refund_commitment_prev no longer matches the
    # advanced local state; they do NOT invoke the circuit (scarb prove).
    stale = chain[0]
    stale_prev = parse_int(stale["refund_commitment_prev"])
    stale_rejected = stale_prev != local_state

    if len(chain) > 1 and args.steps >= 2:
        branch = chain[1]
        branch_prev = parse_int(branch["refund_commitment_prev"])
        branch_rejected = branch_prev != local_state
    else:
        branch_rejected = None

    report = {
        "depth": args.depth,
        "steps_requested": args.steps,
        "steps_executed": len(runs),
        "final_state": to_hex(local_state),
        "stale_replay_rejected": stale_rejected,
        "branch_attempt_rejected": branch_rejected,
        "runs": runs,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
