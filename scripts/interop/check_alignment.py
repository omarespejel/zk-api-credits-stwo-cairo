#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_INT_KEYS = (
    "identity_secret",
    "user_message_limit",
    "ticket_index",
    "x",
    "scope",
    "deposit_low",
    "deposit_high",
    "class_price_low",
    "class_price_high",
)
VIVIAN_REQUIRED_INT_KEYS = (
    "vivian_merkle_proof_length",
    "vivian_expected_root",
)
VIVIAN_REQUIRED_ARRAY_KEYS = (
    "vivian_merkle_proof_indices",
    "vivian_merkle_proof_siblings",
)

RUN_TIMEOUT_SEC = 300
EMPTY_MERKLE_PROOF_LEN = 0
VIVIAN_RESERVED_LEAF_IDX = 0
MERKLE_TREE_MAX_DEPTH = 10
MERKLE_PROOF_SLOT_COUNT = MERKLE_TREE_MAX_DEPTH


def parse_strict_int(key: str, value: object, vector_path: Path) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"vector key '{key}' must be an integer value, got bool {value!r} in {vector_path}"
        )
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(
            f"vector key '{key}' must be an integer value, got float {value!r} in {vector_path}"
        )
    if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
        return int(value)
    raise ValueError(
        f"vector key '{key}' must be an integer value, got {value!r} in {vector_path}"
    )


def run(cmd: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=RUN_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"command timed out after {RUN_TIMEOUT_SEC}s in {cwd}: {' '.join(cmd)}"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}) in {cwd}: {' '.join(cmd)}\n{completed.stdout}"
        )
    return completed.stdout or ""


def parse_program_output(text: str) -> list[int]:
    lines = text.splitlines()
    values: list[int] = []
    in_output = False
    for line_no, line in enumerate(lines, start=1):
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
        try:
            values.append(int(stripped))
        except ValueError as exc:
            raise ValueError(
                f"non-integer program output line at {line_no}: {stripped!r}"
            ) from exc
    if not values:
        raise ValueError(f"could not parse program output from:\n{text}")
    return values


def to_args(values: list[int]) -> str:
    return ",".join(str(v) for v in values)


def validate_vector(vector_raw: object, vector_path: Path) -> dict[str, int | str | list[int]]:
    if not isinstance(vector_raw, dict):
        raise ValueError(f"vector must be a JSON object: {vector_path}")

    vector: dict[str, int | str | list[int]] = {}
    for key in REQUIRED_INT_KEYS:
        if key not in vector_raw:
            raise ValueError(f"vector missing required key '{key}' in {vector_path}")
        vector[key] = parse_strict_int(key, vector_raw[key], vector_path)

    if "name" in vector_raw:
        vector["name"] = str(vector_raw["name"])

    # Optional Vivian RLN strict inputs. If one is present, require all.
    has_any_vivian_key = any(
        key in vector_raw for key in (*VIVIAN_REQUIRED_INT_KEYS, *VIVIAN_REQUIRED_ARRAY_KEYS)
    )
    if has_any_vivian_key:
        for key in VIVIAN_REQUIRED_INT_KEYS:
            if key not in vector_raw:
                raise ValueError(f"vector missing required key '{key}' in {vector_path}")
            parsed = parse_strict_int(key, vector_raw[key], vector_path)
            if key == "vivian_merkle_proof_length" and not (0 <= parsed <= MERKLE_PROOF_SLOT_COUNT):
                raise ValueError(
                    f"vector key '{key}' must be between 0 and {MERKLE_PROOF_SLOT_COUNT} "
                    f"in {vector_path}"
                )
            vector[key] = parsed
        for key in VIVIAN_REQUIRED_ARRAY_KEYS:
            if key not in vector_raw:
                raise ValueError(f"vector missing required key '{key}' in {vector_path}")
            raw = vector_raw[key]
            if not isinstance(raw, list):
                raise ValueError(f"vector key '{key}' must be a JSON array in {vector_path}")
            if len(raw) != MERKLE_PROOF_SLOT_COUNT:
                raise ValueError(
                    f"vector key '{key}' must have {MERKLE_PROOF_SLOT_COUNT} entries "
                    f"in {vector_path}"
                )
            vector[key] = [parse_strict_int(f"{key}[{i}]", value, vector_path) for i, value in enumerate(raw)]

    return vector


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


def load_vector(vector_path: Path) -> dict[str, int | str | list[int]]:
    try:
        vector_raw = json.loads(vector_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json in vector file {vector_path}: {exc}") from exc
    return validate_vector(vector_raw, vector_path)


def ensure_repo_dir(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} repo path not found: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"{label} repo path is not a directory: {path}")


def derive_root(our_repo: Path, scarb_our: str, secret: int, limit: int) -> int:
    # derive_rate_commitment_root executable arg order:
    # [identity_secret, user_message_limit, merkle_proof_length]
    output = run(
        [
            scarb_our,
            "--release",
            "execute",
            "--executable-name",
            "derive_rate_commitment_root",
            "--arguments",
            to_args([secret, limit, EMPTY_MERKLE_PROOF_LEN]),
            "--print-program-output",
        ],
        cwd=our_repo,
    )
    values = parse_program_output(output)
    if len(values) != 1:
        raise ValueError(f"expected single root output, got {values}")
    return values[0]


def run_our_main(our_repo: Path, scarb_our: str, vector: dict, root: int) -> dict[str, int]:
    # zk_api_credits executable arg order:
    # [identity_secret, ticket_index, x, scope, user_message_limit,
    #  deposit_low, deposit_high, class_price_low, class_price_high, root, proof_len]
    args = [
        vector["identity_secret"],
        vector["ticket_index"],
        vector["x"],
        vector["scope"],
        vector["user_message_limit"],
        vector["deposit_low"],
        vector["deposit_high"],
        vector["class_price_low"],
        vector["class_price_high"],
        root,
        EMPTY_MERKLE_PROOF_LEN,
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


def resolve_vivian_project_root(vivian_repo: Path) -> Path:
    # New repo layout has per-circuit subdirs (e.g. rln/Scarb.toml).
    rln_root = vivian_repo / "rln"
    if (rln_root / "Scarb.toml").exists():
        return rln_root
    return vivian_repo


def run_vivian_main(vivian_repo: Path, scarb_vivian: str, vector: dict) -> dict[str, int]:
    # -p cairo_circuits: the RLN package is named cairo_circuits in both the
    # old flat layout and the new rln/ subdirectory (see rln/Scarb.toml).
    project_root = resolve_vivian_project_root(vivian_repo)
    strict_mode = "vivian_merkle_proof_length" in vector

    if strict_mode:
        # Current rln executable arg order:
        # [secret, limit, message_id, merkle_proof_length] +
        # [indices(10)] + [siblings(10)] + [expected_root, x, scope]
        args = [
            vector["identity_secret"],
            vector["user_message_limit"],
            vector["ticket_index"],
            vector["vivian_merkle_proof_length"],
        ]
        args.extend(vector["vivian_merkle_proof_indices"])
        args.extend(vector["vivian_merkle_proof_siblings"])
        args.extend([vector["vivian_expected_root"], vector["x"], vector["scope"]])
    else:
        # Legacy shape.
        args = [
            vector["identity_secret"],
            vector["user_message_limit"],
            vector["ticket_index"],
            VIVIAN_RESERVED_LEAF_IDX,
        ]
        args.extend([0] * MERKLE_PROOF_SLOT_COUNT)
        args.extend([0] * MERKLE_PROOF_SLOT_COUNT)
        args.extend([0, vector["x"], vector["scope"]])

    output = run(
        [
            scarb_vivian,
            "--release",
            "execute",
            "-p",
            "cairo_circuits",
            "--arguments",
            to_args(args),
            "--print-program-output",
        ],
        cwd=project_root,
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


def check_alignment(
    our_out: dict[str, int],
    vivian_out: dict[str, int],
    our_root: int,
    vivian_root_expected: int | None,
) -> None:
    mismatches: list[str] = []
    if our_out["nullifier"] != vivian_out["nullifier"]:
        mismatches.append(
            f"nullifier mismatch: ours={our_out['nullifier']} vivian={vivian_out['nullifier']}"
        )
    if our_out["y"] != vivian_out["y"]:
        mismatches.append(f"y mismatch: ours={our_out['y']} vivian={vivian_out['y']}")
    if our_out["root"] != our_root:
        mismatches.append(
            f"our output root mismatch: out={our_out['root']} expected={our_root}"
        )
    if vivian_root_expected is not None and vivian_out["root"] != vivian_root_expected:
        mismatches.append(
            f"vivian output root mismatch: out={vivian_out['root']} "
            f"expected={vivian_root_expected}"
        )
    if mismatches:
        raise AssertionError("alignment check failed:\n" + "\n".join(mismatches))


def main() -> int:
    args = parse_args()
    our_repo = Path(args.our_repo).resolve()
    vivian_repo = Path(args.vivian_repo).resolve()
    ensure_repo_dir(our_repo, "our")
    ensure_repo_dir(vivian_repo, "vivian")
    arg_vector_path = Path(args.vector)
    vector_path = arg_vector_path if arg_vector_path.is_absolute() else (our_repo / arg_vector_path)
    vector_path = vector_path.resolve()

    if not vector_path.exists():
        raise FileNotFoundError(f"vector file not found: {vector_path}")

    vector = load_vector(vector_path)

    if not args.skip_build:
        run([args.scarb_our, "--release", "build"], cwd=our_repo)
        run(
            [args.scarb_vivian, "--release", "build"],
            cwd=resolve_vivian_project_root(vivian_repo),
        )

    secret = vector["identity_secret"]
    limit = vector["user_message_limit"]

    our_root = derive_root(our_repo, args.scarb_our, secret, limit)
    our_out = run_our_main(our_repo, args.scarb_our, vector, our_root)
    vivian_out = run_vivian_main(vivian_repo, args.scarb_vivian, vector)
    vivian_root_expected = (
        vector["vivian_expected_root"] if "vivian_expected_root" in vector else None
    )

    check_alignment(our_out, vivian_out, our_root, vivian_root_expected)

    report = {
        "vector": vector.get("name", str(vector_path)),
        "our_root": our_root,
        "vivian_root_expected": vivian_root_expected,
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
