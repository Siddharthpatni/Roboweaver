"""Strict JSON decoding shared by every untrusted JSON boundary."""

from __future__ import annotations

import json
from typing import Any


def _reject_non_finite(constant: str) -> None:
    raise json.JSONDecodeError(f"Non-finite number '{constant}' is not valid JSON", constant, 0)


def loads_strict(value: str | bytes | bytearray) -> Any:
    """Decode RFC-compliant JSON and reject Python's NaN/Infinity extensions."""
    return json.loads(value, parse_constant=_reject_non_finite)
