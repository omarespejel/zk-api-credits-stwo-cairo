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
from pathlib import Path


def parse_int(value: str) -> int:
    value = value.strip()
    if isinstance(value, int):
        return value
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
    parser.add_argument("--deposit", default=None, help="Override deposit (u256) as decimal or hex.")
    parser.add_argument("--class-price", default=None, help="Override class_price (u256) as decimal or hex.")
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
    if not isinstance(fixture, list) or len(fixture) < 8:
        raise ValueError(f"Invalid fixture structure in {path}: expected list with >=8 entries.")
    return fixture


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir)
    out_dir = Path(args.out_dir)

    base_fields = parse_depths(args.depths)
    overrides = {
        "identity_secret": args.identity_secret,
        "ticket_index": args.ticket_index,
        "x": args.x,
        "deposit": args.deposit,
        "class_price": args.class_price,
    }

    for depth in base_fields:
        fixture = load_base_fixture(base_dir, depth)

        identity_secret = fixture[0]
        ticket_index = fixture[1]
        x = fixture[2]
        deposit_low = fixture[3]
        deposit_high = fixture[4]
        class_price_low = fixture[5]
        class_price_high = fixture[6]
        merkle_root = fixture[7]

        if overrides["identity_secret"] is not None:
            identity_secret = hex(parse_int(overrides["identity_secret"]))
        if overrides["ticket_index"] is not None:
            ticket_index = hex(parse_int(overrides["ticket_index"]))
        if overrides["x"] is not None:
            x = hex(parse_int(overrides["x"]))
        if overrides["deposit"] is not None:
            deposit_low, deposit_high = split_u256(parse_int(overrides["deposit"]))
        if overrides["class_price"] is not None:
            class_price_low, class_price_high = split_u256(parse_int(overrides["class_price"]))

        out = [
            identity_secret,
            ticket_index,
            x,
            deposit_low,
            deposit_high,
            class_price_low,
            class_price_high,
            merkle_root,
            *fixture[8:],
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
