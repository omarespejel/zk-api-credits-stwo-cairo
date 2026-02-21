#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


DEFAULTS = {
    "refund_commitment_prev": "0x7b",
    "refund_amount": "0x1",
    "refund_commitment_next_expected": "0x3639abd57ba0779f4fdd845168e3815a72834c875ee135981660ebedaa68770",
    "remask_nonce": "0x9",
    "server_pubkey": "0x3fcb8c6e0c6062cac02df9ff0f3775b2263874a4cbf42643fc26713e5a8ceb6",
    "signature_r": "0x1ef15c18599971b7beced415a40f0c7deacfd9b0d1819e03d723d8bc943cfca",
    "signature_s": "0x67075b978a9f74ca9d515e59bef04b9db63216b02f159a1bd77ec0cb88b0e6",
}


def parse_depths(raw: str) -> list[int]:
    return [int(item) for item in raw.split() if item.strip()]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate v2-kernel args from depth fixtures.")
    p.add_argument("--base-dir", default="scripts/bench_inputs")
    p.add_argument("--out-dir", default="scripts/bench_inputs/v2_kernel")
    p.add_argument("--depths", default="8 16 20 32")
    p.add_argument("--overwrite", action="store_true")
    for key in DEFAULTS:
        p.add_argument(f"--{key.replace('_', '-')}", default=None)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(args.base_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    extras = {
        k: getattr(args, k) if getattr(args, k) is not None else v
        for k, v in DEFAULTS.items()
    }

    for depth in parse_depths(args.depths):
        src = base_dir / f"depth_{depth}.json"
        if not src.exists():
            raise FileNotFoundError(f"missing {src}")
        data = json.loads(src.read_text())
        out_path = out_dir / f"depth_{depth}.json"
        if out_path.exists() and not args.overwrite:
            print(f"skip: {out_path}")
            continue

        payload = [
            *data,
            extras["refund_commitment_prev"],
            extras["refund_amount"],
            extras["refund_commitment_next_expected"],
            extras["remask_nonce"],
            extras["server_pubkey"],
            extras["signature_r"],
            extras["signature_s"],
        ]
        out_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
