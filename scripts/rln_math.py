#!/usr/bin/env python3
"""RLN field math helpers for the fixed-class demo.

This file contains the minimal finite-field operations needed for share recovery and
optional consistency checks in the slashing path.
"""

from __future__ import annotations

from dataclasses import dataclass


CAIRO_FIELD_PRIME = (1 << 251) + (17 << 192) + 1


def to_felt(value: int | str) -> int:
    """Parse a Rust/Cairo-style felt literal and normalize into the Cairo field.

    Accepts decimals or hex (`0x`-prefixed) strings and integers.
    """
    if isinstance(value, int):
        n = value
    else:
        n = int(str(value), 0)
    return n % CAIRO_FIELD_PRIME


def to_felt_hex(value: int | str) -> str:
    """Return a canonical hex felt representation."""
    return hex(to_felt(value))


def field_inv(value: int | str) -> int:
    """Modular inverse in the Cairo base field."""
    n = to_felt(value)
    if n == 0:
        raise ValueError("inverse does not exist for 0 in field")
    return pow(n, CAIRO_FIELD_PRIME - 2, CAIRO_FIELD_PRIME)


def recover_identity_secret(x1: int | str, y1: int | str, x2: int | str, y2: int | str) -> int:
    """Recover identity_secret (a0) from two RLN shares with same ticket index.

    Using:
      y1 = a0 + a1 * x1
      y2 = a0 + a1 * x2
      a0 = (y1 * x2 - y2 * x1) / (x2 - x1)
    """
    x1 = to_felt(x1)
    y1 = to_felt(y1)
    x2 = to_felt(x2)
    y2 = to_felt(y2)

    if x1 == x2:
        raise ValueError("x1 and x2 are equal; a0 recovery requires two distinct messages")

    num = (y1 * x2 - y2 * x1) % CAIRO_FIELD_PRIME
    den = field_inv(x2 - x1)
    return (num * den) % CAIRO_FIELD_PRIME


def derive_a1(a0: int | str, x: int | str, y: int | str) -> int:
    """Recover a1 from one share (non-zero x)."""
    x = to_felt(x)
    if x == 0:
        raise ValueError("cannot derive a1 when x == 0")
    a0 = to_felt(a0)
    y = to_felt(y)
    return ((y - a0) * field_inv(x)) % CAIRO_FIELD_PRIME


@dataclass(frozen=True)
class Share:
    nullifier: int
    ticket_index: int
    x: int
    y: int


def parse_share(raw: dict) -> Share:
    """Parse untrusted share payloads into normalized field elements."""
    required = ["nullifier", "ticket_index", "x", "y"]
    missing = [k for k in required if k not in raw]
    if missing:
        raise KeyError(f"missing share keys: {', '.join(missing)}")

    return Share(
        nullifier=to_felt(raw["nullifier"]),
        ticket_index=to_felt(raw["ticket_index"]),
        x=to_felt(raw["x"]),
        y=to_felt(raw["y"]),
    )
