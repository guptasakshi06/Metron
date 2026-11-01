"""Injective, typed, length-framed content encoding (distinct from S03 sketches)."""

from __future__ import annotations

import math
import struct
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from data_optimizer.readers.stream import ProfileError


def frame(tag: bytes, payload: bytes) -> bytes:
    return tag + str(len(payload)).encode("ascii") + b":" + payload


def encode(value: Any) -> bytes:
    if value is None:
        return frame(b"n", b"")
    if isinstance(value, bool):
        return frame(b"b", b"1" if value else b"0")
    if isinstance(value, int):
        return frame(b"i", str(value).encode("ascii"))
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ProfileError("nonfinite_number_unsupported")
        # as_tuple preserves exact precision, trailing fractional zeros and signed zero.
        parts = value.as_tuple()
        payload = f"{parts.sign}:{''.join(str(d) for d in parts.digits)}:{parts.exponent}"
        return frame(b"d", payload.encode("ascii"))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProfileError("nonfinite_number_unsupported")
        return frame(b"f", struct.pack(">d", value))
    if isinstance(value, datetime):
        aware = value.utcoffset() is not None
        instant = value.astimezone(UTC) if aware else value
        return frame(b"z" if aware else b"t", instant.isoformat(timespec="microseconds").encode())
    if isinstance(value, date):
        return frame(b"D", value.isoformat().encode())
    if isinstance(value, str):
        return frame(b"s", value.encode("utf-8"))
    if isinstance(value, bytes):
        return frame(b"B", value)
    if isinstance(value, dict):
        if any(not isinstance(k, str) for k in value):
            raise ProfileError("object_keys_must_be_strings")
        return frame(b"o", b"".join(encode(k) + encode(value[k]) for k in sorted(value)))
    if isinstance(value, (list, tuple)):
        return frame(b"a", b"".join(encode(v) for v in value))
    raise ProfileError("unsupported_logical_type")
