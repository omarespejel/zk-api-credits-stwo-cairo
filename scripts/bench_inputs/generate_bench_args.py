#!/usr/bin/env python3
"""Generate deterministic zk_api_credits witness/argument files for benches.

The generator reads canonical depth fixtures (default files are
`scripts/bench_inputs/depth_<d>.json`) and writes Cairo `--arguments-file`-ready
arrays. It is intentionally small and deterministic:

- keeps the merkle proof and root from fixtures;
- formats u256 fields as two field elements (`low`, `high`);
- supports per-run overrides for witness fields.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path


def parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    value = str(value).strip()
    if value.lower().startswith("0x"):
        return int(value, 16)
    if value.lower().startswith("0b"):
        return int(value, 2)
    return int(value, 10)


def split_u256(value: int) -> tuple[str, str]:
    value = value & ((1 << 256) - 1)
    low = value & ((1 << 128) - 1)
    high = value >> 128
    return hex(low), hex(high)


def parse_depths(raw: str) -> list[int]:
    return [int(item) for item in raw.split() if item.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate fixed-class zk_api_credits benchmark args.")
    parser.add_argument(
        "--base-dir",
        default="scripts/bench_inputs",
        help="Directory containing depth_<d>.json base fixtures.",
    )
    parser.add_argument(
        "--out-dir",
        default="scripts/bench_inputs",
        help="Directory where generated depth_<d>.json argument files should be written.",
    )
    parser.add_argument(
        "--depths",
        default="8 16 20 32",
        help="Space separated list of depths to materialize.",
    )
    parser.add_argument("--identity-secret", default=None, help="Override identity_secret (felt252).")
    parser.add_argument("--ticket-index", default=None, help="Override ticket_index (felt252).")
    parser.add_argument("--x", default=None, help="Override x (felt252).")
    parser.add_argument("--scope", default=None, help="Override scope (felt252).")
    parser.add_argument(
        "--user-message-limit",
        default=None,
        help="Override user_message_limit (u32 stored as felt).",
    )
    parser.add_argument("--deposit", default=None, help="Override deposit (u256) as decimal or hex.")
    parser.add_argument("--class-price", default=None, help="Override class_price (u256) as decimal or hex.")
    parser.add_argument(
        "--recompute-roots",
        action="store_true",
        help=(
            "Recompute merkle_root with the helper executable "
            "(useful after overriding user_message_limit)."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated files in output directory.",
    )
    return parser.parse_args()


def write_json(path: Path, payload: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(payload, f, indent=2)


def load_base_fixture(base_dir: Path, depth: int) -> list[str]:
    path = base_dir / f"depth_{depth}.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing base fixture: {path}")
    with path.open() as f:
        fixture = json.load(f)
    if not isinstance(fixture, list) or len(fixture) < 9:
        raise ValueError(f"Invalid fixture structure in {path}: expected list with >=9 entries.")
    return fixture


def compute_root(identity_secret: str, user_message_limit: str, proof: list[str], cwd: Path) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="derive_root_", dir=cwd, delete=False
    ) as tmp:
        tmp.write(json.dumps([identity_secret, user_message_limit, *proof]))
        tmp_path = Path(tmp.name)

    try:
        output = subprocess.check_output(
            [
                "scarb",
                "execute",
                "--executable-name",
                "derive_rate_commitment_root",
                "--arguments-file",
                str(tmp_path),
                "--print-program-output",
            ],
            cwd=str(cwd),
            text=True,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    m = re.search(r"Program output:\n([^\n]+)", output)
    if not m:
        raise RuntimeError(f"Could not parse root from scarb output: {output}")

    prime = (1 << 251) + (17 << 192) + 1
    root = int(m.group(1).strip(), 0) % prime
    return hex(root)


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir)
    out_dir = Path(args.out_dir)
    project_root = Path(__file__).resolve().parents[2]

    base_fields = parse_depths(args.depths)
    overrides = {
        "identity_secret": args.identity_secret,
        "ticket_index": args.ticket_index,
        "x": args.x,
        "scope": args.scope,
        "user_message_limit": args.user_message_limit,
        "deposit": args.deposit,
        "class_price": args.class_price,
    }

    for depth in base_fields:
        fixture = load_base_fixture(base_dir, depth)

        # Legacy format v0 (before scope):
        # [identity_secret, ticket_index, x, deposit_low, deposit_high, class_price_low, class_price_high, merkle_root, ...proof]
        #
        # Legacy format v1 (scope added):
        # [identity_secret, ticket_index, x, scope, deposit_low, deposit_high, class_price_low, class_price_high, merkle_root, ...proof]
        #
        # Current format v2 (scope + user_message_limit):
        # [identity_secret, ticket_index, x, scope, user_message_limit, deposit_low, deposit_high, class_price_low, class_price_high, merkle_root, ...proof]
        #
        # Detection relies on where the proof length appears.
        if len(fixture) >= 11 and parse_int(fixture[10]) <= 64 and parse_int(fixture[9]) > 64:
            # v2
            identity_secret = fixture[0]
            ticket_index = fixture[1]
            x = fixture[2]
            scope = fixture[3]
            user_message_limit = fixture[4]
            deposit_low = fixture[5]
            deposit_high = fixture[6]
            class_price_low = fixture[7]
            class_price_high = fixture[8]
            merkle_root = fixture[9]
            proof = fixture[10:]
        elif len(fixture) >= 10 and parse_int(fixture[9]) <= 64 and parse_int(fixture[8]) > 64:
            # v1
            identity_secret = fixture[0]
            ticket_index = fixture[1]
            x = fixture[2]
            scope = fixture[3]
            user_message_limit = "0x20"
            deposit_low = fixture[4]
            deposit_high = fixture[5]
            class_price_low = fixture[6]
            class_price_high = fixture[7]
            merkle_root = fixture[8]
            proof = fixture[9:]
        elif len(fixture) >= 9 and parse_int(fixture[8]) <= 64 and parse_int(fixture[7]) > 64:
            # v0
            identity_secret = fixture[0]
            ticket_index = fixture[1]
            x = fixture[2]
            scope = "0x20"
            user_message_limit = "0x20"
            deposit_low = fixture[3]
            deposit_high = fixture[4]
            class_price_low = fixture[5]
            class_price_high = fixture[6]
            merkle_root = fixture[7]
            proof = fixture[8:]
        else:
            raise ValueError(f"Unsupported fixture layout in {base_dir / f'depth_{depth}.json'}")

        if overrides["identity_secret"] is not None:
            identity_secret = hex(parse_int(overrides["identity_secret"]))
        if overrides["ticket_index"] is not None:
            ticket_index = hex(parse_int(overrides["ticket_index"]))
        if overrides["x"] is not None:
            x = hex(parse_int(overrides["x"]))
        if overrides["scope"] is not None:
            scope = hex(parse_int(overrides["scope"]))
        if overrides["user_message_limit"] is not None:
            user_message_limit = hex(parse_int(overrides["user_message_limit"]))
        if overrides["deposit"] is not None:
            deposit_low, deposit_high = split_u256(parse_int(overrides["deposit"]))
        if overrides["class_price"] is not None:
            class_price_low, class_price_high = split_u256(parse_int(overrides["class_price"]))

        if args.recompute_roots or overrides["user_message_limit"] is not None:
            merkle_root = compute_root(identity_secret, user_message_limit, proof, project_root)

        out = [
            identity_secret,
            ticket_index,
            x,
            scope,
            user_message_limit,
            deposit_low,
            deposit_high,
            class_price_low,
            class_price_high,
            merkle_root,
            *proof,
        ]

        out_path = out_dir / f"depth_{depth}.json"
        if out_path.exists() and not args.overwrite:
            print(f"skip: {out_path} (exists, use --overwrite to replace)")
            continue

        write_json(out_path, out)
        print(f"wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
