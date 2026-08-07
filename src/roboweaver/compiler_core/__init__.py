"""Reusable compiler infrastructure adapted from established compiler designs."""

from roboweaver.compiler_core.conversion import (
    ConversionError,
    ConversionPattern,
    ConversionTarget,
    Operation,
    apply_full_conversion,
)
from roboweaver.compiler_core.plugins import (
    CompilerPhase,
    CompilerPluginManifest,
    CompilerPluginRegistry,
)

__all__ = [
    "CompilerPhase",
    "CompilerPluginManifest",
    "CompilerPluginRegistry",
    "ConversionError",
    "ConversionPattern",
    "ConversionTarget",
    "Operation",
    "apply_full_conversion",
]
