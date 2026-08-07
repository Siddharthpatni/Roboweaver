"""A small, deterministic full-conversion engine.

The design follows MLIR dialect conversion's useful semantics: a target declares
legal and illegal operations, ordered patterns rewrite operations, and a *full*
conversion succeeds only when no illegal operation remains.  This implementation
is native RoboWeaver code; the optional native bridge separately invokes
``mlir-opt`` when that upstream executable is installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


class ConversionError(ValueError):
    """An operation could not be legalized or a rewrite failed to converge."""


@dataclass(frozen=True)
class Operation:
    """One portable or target-dialect operation."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)


Rewrite = Callable[[Operation], Operation | Iterable[Operation] | None]


@dataclass(frozen=True)
class ConversionPattern:
    """A named rewrite for one operation, ordered by descending benefit."""

    source_operation: str
    rewrite: Rewrite
    name: str
    benefit: int = 1

    def apply(self, operation: Operation) -> tuple[Operation, ...] | None:
        if operation.name != self.source_operation:
            return None
        rewritten = self.rewrite(operation)
        if rewritten is None:
            return None
        if isinstance(rewritten, Operation):
            return (rewritten,)
        return tuple(rewritten)


@dataclass(frozen=True)
class ConversionTarget:
    """Legal/illegal operation contract for a target dialect."""

    legal_operations: frozenset[str]
    illegal_operations: frozenset[str] = frozenset()
    legal_prefixes: tuple[str, ...] = ()
    illegal_prefixes: tuple[str, ...] = ("portable.",)

    def is_legal(self, operation: Operation) -> bool:
        if operation.name in self.illegal_operations:
            return False
        if any(operation.name.startswith(prefix) for prefix in self.illegal_prefixes):
            return False
        return operation.name in self.legal_operations or any(
            operation.name.startswith(prefix) for prefix in self.legal_prefixes
        )


@dataclass(frozen=True)
class ConversionResult:
    operations: tuple[Operation, ...]
    trace: tuple[str, ...]


def apply_full_conversion(
    operations: Iterable[Operation],
    target: ConversionTarget,
    patterns: Iterable[ConversionPattern],
    *,
    max_rewrites: int = 256,
) -> ConversionResult:
    """Rewrite every illegal operation or fail with exact unresolved names."""

    ordered = sorted(patterns, key=lambda item: (-item.benefit, item.name))
    pending = list(operations)
    trace: list[str] = []
    rewrites = 0

    while True:
        illegal_index = next(
            (index for index, operation in enumerate(pending) if not target.is_legal(operation)),
            None,
        )
        if illegal_index is None:
            return ConversionResult(tuple(pending), tuple(trace))
        operation = pending[illegal_index]
        match = next(
            (
                (pattern, replacement)
                for pattern in ordered
                if (replacement := pattern.apply(operation)) is not None
            ),
            None,
        )
        if match is None:
            unresolved = sorted({item.name for item in pending if not target.is_legal(item)})
            raise ConversionError(f"full conversion left illegal operations: {', '.join(unresolved)}")
        pattern, replacement = match
        rewrites += 1
        if rewrites > max_rewrites:
            raise ConversionError(f"conversion exceeded the {max_rewrites}-rewrite convergence bound")
        pending[illegal_index:illegal_index + 1] = replacement
        produced = ", ".join(item.name for item in replacement) or "<erased>"
        trace.append(f"{pattern.name}: {operation.name} -> {produced}")
