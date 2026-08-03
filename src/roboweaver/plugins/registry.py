"""
A small, generic, name-keyed plugin registry. See package docstring for motivation.
"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """Maps a plugin name (e.g. a protocol or backend id) to an implementation.
    Deliberately minimal: no auto-discovery, no entry-point scanning -- just a
    dict with clear errors, since that's all any current consumer needs."""

    def __init__(self, kind: str = "plugin"):
        self._kind = kind
        self._entries: dict[str, T] = {}

    def register(self, name: str, *, allow_override: bool = False):
        """Decorator/callable form: `registry.register("foo")(SomeClass)`, or use
        directly as `@registry.register("foo")` above a class/function definition."""
        def decorator(impl: T) -> T:
            key = name.lower()
            if not allow_override and key in self._entries:
                raise ValueError(
                    f"{self._kind} '{name}' is already registered "
                    f"(existing: {self._entries[key]!r}) -- pass allow_override=True "
                    f"to replace it deliberately."
                )
            self._entries[key] = impl
            return impl
        return decorator

    def get(self, name: str) -> T:
        key = name.lower()
        if key not in self._entries:
            raise KeyError(
                f"No {self._kind} registered under {name!r}. "
                f"Registered: {sorted(self._entries.keys())}"
            )
        return self._entries[key]

    def names(self) -> list[str]:
        return sorted(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name.lower() in self._entries
