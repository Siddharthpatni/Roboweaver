"""Safe identifiers for generated code, package names, and filesystem entries."""

from __future__ import annotations

import re
import unicodedata

_SAFE_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


def safe_identifier(value: object, *, default: str = "object", max_length: int = 80) -> str:
    """Convert untrusted display text to a stable lowercase ASCII identifier."""
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    identifier = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    if not identifier:
        identifier = default
    if identifier[0].isdigit():
        identifier = f"id_{identifier}"
    identifier = identifier[:max_length].rstrip("_")
    return identifier or default


def require_safe_identifier(value: object, *, field_name: str = "identifier") -> str:
    """Reject rather than rename identifiers that are persisted as public IDs."""
    if not isinstance(value, str) or not _SAFE_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must match {_SAFE_IDENTIFIER_RE.pattern} and be at most 80 characters."
        )
    return value


def safe_comment(value: object, *, max_length: int = 240) -> str:
    """Flatten untrusted text before embedding it in line-oriented source comments."""
    text = " ".join(str(value).split())
    return "".join(char for char in text if char.isprintable())[:max_length]
