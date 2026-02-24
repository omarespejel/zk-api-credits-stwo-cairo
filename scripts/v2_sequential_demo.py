#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
from pathlib import Path

V2_FIXED_PREFIX_LEN = 11
V2_PROOF_LEN_IDX = 10
V2_TAIL_LEN = 7
V2_REMASK_NONCE_OFFSET = 3
V2_TICKET_INDEX_IDX = 1
V2_SCOPE_IDX = 3


def parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def to_hex(value: int) -> str:
    return hex(value)


def to_args(values: list[int]) -> str:
    return ",".join(to_hex(v) for v in values)


SUBPROCESS_TIMEOUT_S = 600

def run(cmd: list[str], cwd: Path) -> tuple[str, int]:
    start = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=SUBPROCESS_TIMEOUT_S,
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc.stdout, elapsed_ms


def parse_proof_path(prove_output: str) -> str:
    for line in prove_output.splitlines():
        marker = "Saving proof to:"
        if marker in line:
            return line.split(marker, 1)[1].strip()
    raise ValueError(f"could not parse proof path from output:\n{prove_output}")


def extract_prefix_and_remask(base_args: list[int]) -> tuple[list[int], int]:
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
    p = argparse.ArgumentParser(description="Sequential V2 kernel state demo (no parallel branches).")
    p.add_argument("--repo", default=".")
    p.add_argument("--depth", type=int, default=8)
    p.add_argument("--steps", type=int, default=3)
    p.add_argument("--skip-build", action="store_true")
    p.add_argument("--skip-verify", action="store_true")
    p.add_argument("--chain-file", default="scripts/v2_fixtures/sequential_chain.json")
    p.add_argument("--scarb", default="scarb")
    return p.parse_args()


def main() -> int:
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

    if not args.skip_build:
        run([args.scarb, "--release", "build"], cwd=repo)

    local_state = parse_int(steps[0]["refund_commitment_prev"])
    if local_state == 0:
        raise ValueError("chain fixture has zero initial refund_commitment_prev; likely invalid")
    first_step_idx = steps[0].get("step", 0)
    if first_step_idx != 0:
        raise ValueError(f"chain fixture starts at step={first_step_idx}; expected genesis step=0")
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
        )
        proof_path = parse_proof_path(prove_out)

        verify_ms = None
        if not args.skip_verify:
            _, verify_ms = run(
                [args.scarb, "--release", "verify", "--proof-file", proof_path],
                cwd=repo,
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
