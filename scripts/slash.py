#!/usr/bin/env python3
"""Slash recovery demo for two RLN shares.

Usage:
  python3 scripts/slash.py path_or_json1 path_or_json2 [--expected-identity-secret V]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rln_math import Share, derive_a1, parse_share, recover_identity_secret, to_felt_hex


def load_share(path_or_json: str) -> dict:
    candidate = Path(path_or_json)
    if candidate.exists():
        return json.loads(candidate.read_text())
    return json.loads(path_or_json)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("share1", help="Path to JSON share file or raw JSON string.")
    parser.add_argument("share2", help="Path to JSON share file or raw JSON string.")
    parser.add_argument(
        "--expected-identity-secret",
        help="Optional expected identity_secret to verify against recovered value.",
    )
    args = parser.parse_args()

    s1 = parse_share(load_share(args.share1))
    s2 = parse_share(load_share(args.share2))

    if s1.nullifier != s2.nullifier:
        raise SystemExit("Error: nullifiers do not match.")
    if s1.ticket_index != s2.ticket_index:
        raise SystemExit("Error: ticket_index does not match.")
    if s1.x == s2.x:
        raise SystemExit("Error: x values must be different to recover secret.")

    identity_secret = recover_identity_secret(s1.x, s1.y, s2.x, s2.y)
    a1_s1 = derive_a1(identity_secret, s1.x, s1.y)

    result = {
        "nullifier": to_felt_hex(s1.nullifier),
        "ticket_index": to_felt_hex(s1.ticket_index),
        "share1": {"x": to_felt_hex(s1.x), "y": to_felt_hex(s1.y)},
        "share2": {"x": to_felt_hex(s2.x), "y": to_felt_hex(s2.y)},
        "recovered_identity_secret": to_felt_hex(identity_secret),
        "derived_a1": to_felt_hex(a1_s1),
        "slash": True,
    }

    if args.expected_identity_secret is not None:
        expected = to_felt_hex(args.expected_identity_secret)
        result["expected_identity_secret"] = expected
        result["identity_match"] = expected == to_felt_hex(identity_secret)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
