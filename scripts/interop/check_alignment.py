#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}) in {cwd}: {' '.join(cmd)}\n{completed.stdout}"
        )
    return completed.stdout or ""


def parse_program_output(text: str) -> list[int]:
    lines = text.splitlines()
    values: list[int] = []
    in_output = False
    for line in lines:
        stripped = line.strip()
        if stripped == "Program output:":
            in_output = True
            continue
        if not in_output:
            continue
        if not stripped:
            continue
        if stripped.startswith("Saving output to:"):
            break
        values.append(int(stripped))
    if not values:
        raise ValueError(f"could not parse program output from:\n{text}")
    return values


def to_args(values: list[int]) -> str:
    return ",".join(str(v) for v in values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check interop between zk-api-credits and cairo-circuits.")
    parser.add_argument(
        "--vector",
        default="scripts/interop/vectors/shared_vector_01.json",
        help="Path to interop vector json.",
    )
    parser.add_argument(
        "--our-repo",
        default=".",
        help="Path to zk-api-credits repo.",
    )
    parser.add_argument(
        "--vivian-repo",
        default="../cairo-circuits",
        help="Path to cairo-circuits repo.",
    )
    parser.add_argument(
        "--scarb-our",
        default="scarb",
        help="Scarb binary/path for zk-api-credits repo.",
    )
    parser.add_argument(
        "--scarb-vivian",
        default="scarb",
        help="Scarb binary/path for cairo-circuits repo.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip build step and run only execute checks.",
    )
    return parser.parse_args()


def derive_root(our_repo: Path, scarb_our: str, secret: int, limit: int) -> int:
    output = run(
        [
            scarb_our,
            "--release",
            "execute",
            "--executable-name",
            "derive_rate_commitment_root",
            "--arguments",
            to_args([secret, limit, 0]),
            "--print-program-output",
        ],
        cwd=our_repo,
    )
    values = parse_program_output(output)
    if len(values) != 1:
        raise ValueError(f"expected single root output, got {values}")
    return values[0]


def run_our_main(our_repo: Path, scarb_our: str, vector: dict, root: int) -> dict[str, int]:
    args = [
        int(vector["identity_secret"]),
        int(vector["ticket_index"]),
        int(vector["x"]),
        int(vector["scope"]),
        int(vector["user_message_limit"]),
        int(vector["deposit_low"]),
        int(vector["deposit_high"]),
        int(vector["class_price_low"]),
        int(vector["class_price_high"]),
        root,
        0,
    ]
    output = run(
        [
            scarb_our,
            "--release",
            "execute",
            "--executable-name",
            "zk_api_credits",
            "--arguments",
            to_args(args),
            "--print-program-output",
        ],
        cwd=our_repo,
    )
    values = parse_program_output(output)
    if len(values) != 4:
        raise ValueError(f"expected 4 outputs from zk_api_credits, got {values}")
    return {
        "nullifier": values[0],
        "x": values[1],
        "y": values[2],
        "root": values[3],
    }


def run_vivian_main(vivian_repo: Path, scarb_vivian: str, vector: dict, root: int) -> dict[str, int]:
    # cairo_circuits CLI args: [secret, limit, ticket, reserved0] +
    # 10 sibling slots + 10 path-index slots (zero-padded in this shared vector) +
    # [expected_root, x, scope]
    args = [
        int(vector["identity_secret"]),
        int(vector["user_message_limit"]),
        int(vector["ticket_index"]),
        0,
    ]
    args.extend([0] * 10)
    args.extend([0] * 10)
    args.extend([root, int(vector["x"]), int(vector["scope"])])

    output = run(
        [
            scarb_vivian,
            "execute",
            "-p",
            "cairo_circuits",
            "--arguments",
            to_args(args),
            "--print-program-output",
        ],
        cwd=vivian_repo,
    )
    values = parse_program_output(output)
    if len(values) != 5:
        raise ValueError(f"expected 5 outputs from cairo_circuits, got {values}")
    return {
        "x": values[0],
        "scope": values[1],
        "y": values[2],
        "root": values[3],
        "nullifier": values[4],
    }


def check_alignment(our_out: dict[str, int], vivian_out: dict[str, int], root: int) -> None:
    mismatches: list[str] = []
    if our_out["nullifier"] != vivian_out["nullifier"]:
        mismatches.append(
            f"nullifier mismatch: ours={our_out['nullifier']} vivian={vivian_out['nullifier']}"
        )
    if our_out["y"] != vivian_out["y"]:
        mismatches.append(f"y mismatch: ours={our_out['y']} vivian={vivian_out['y']}")
    if our_out["root"] != root:
        mismatches.append(f"our output root mismatch: out={our_out['root']} expected={root}")
    if vivian_out["root"] != root:
        mismatches.append(
            f"vivian output root mismatch: out={vivian_out['root']} expected={root}"
        )
    if mismatches:
        raise AssertionError("alignment check failed:\n" + "\n".join(mismatches))


def main() -> int:
    args = parse_args()
    our_repo = Path(args.our_repo).resolve()
    vivian_repo = Path(args.vivian_repo).resolve()
    vector_path = (our_repo / args.vector).resolve() if not Path(args.vector).is_absolute() else Path(args.vector)

    if not vector_path.exists():
        raise FileNotFoundError(f"vector file not found: {vector_path}")

    vector = json.loads(vector_path.read_text())

    if not args.skip_build:
        run([args.scarb_our, "--release", "build"], cwd=our_repo)
        run([args.scarb_vivian, "build"], cwd=vivian_repo)

    secret = int(vector["identity_secret"])
    limit = int(vector["user_message_limit"])

    root = derive_root(our_repo, args.scarb_our, secret, limit)
    our_out = run_our_main(our_repo, args.scarb_our, vector, root)
    vivian_out = run_vivian_main(vivian_repo, args.scarb_vivian, vector, root)

    check_alignment(our_out, vivian_out, root)

    report = {
        "vector": vector.get("name", str(vector_path)),
        "root": root,
        "our": our_out,
        "vivian": vivian_out,
        "status": "ok",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"interop check failed: {exc}", file=sys.stderr)
        raise
