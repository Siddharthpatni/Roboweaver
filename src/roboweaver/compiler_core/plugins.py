"""Phase-aware compiler plugin registry.

RoboticsLanguage composes language plugins through Input, Transformation and
Output phases.  RoboWeaver uses that core model here while retaining its own IR
and safety contracts. External distributions can publish entry points without
editing a central hard-coded dispatcher.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from importlib import metadata
from typing import Any, Iterable


class CompilerPhase(Enum):
    INPUT = "Input"
    TRANSFORMATION = "Transformation"
    OUTPUT = "Output"


@dataclass(frozen=True)
class CompilerPluginManifest:
    name: str
    version: str
    phase: CompilerPhase
    capability: str
    provider: Any
    priority: int = 0
    source: str = "builtin"


class CompilerPluginRegistry:
    """Deterministic registry with optional Python entry-point discovery."""

    def __init__(self, entry_point_group: str):
        self.entry_point_group = entry_point_group
        self._plugins: dict[tuple[CompilerPhase, str], CompilerPluginManifest] = {}

    def register(self, manifest: CompilerPluginManifest) -> None:
        key = (manifest.phase, manifest.capability)
        current = self._plugins.get(key)
        if current is not None and current.priority == manifest.priority:
            raise ValueError(
                f"duplicate compiler plugin for {manifest.phase.value}/{manifest.capability}: "
                f"{current.name!r} and {manifest.name!r} have equal priority"
            )
        if current is None or manifest.priority > current.priority:
            self._plugins[key] = manifest

    def discover(self, entry_points: Iterable[Any] | None = None) -> int:
        candidates = entry_points
        if candidates is None:
            selected = metadata.entry_points()
            candidates = (
                selected.select(group=self.entry_point_group)
                if hasattr(selected, "select")
                else selected.get(self.entry_point_group, ())
            )
        count = 0
        for entry_point in candidates:
            loaded = entry_point.load()
            manifest = loaded() if callable(loaded) and not isinstance(loaded, type) else loaded
            if isinstance(manifest, CompilerPluginManifest):
                self.register(manifest)
            else:
                self.register(CompilerPluginManifest(
                    name=entry_point.name,
                    version="external",
                    phase=CompilerPhase.TRANSFORMATION,
                    capability=entry_point.name,
                    provider=manifest,
                    priority=10,
                    source=f"entry-point:{self.entry_point_group}",
                ))
            count += 1
        return count

    def resolve(self, phase: CompilerPhase, capability: str) -> CompilerPluginManifest:
        try:
            return self._plugins[(phase, capability)]
        except KeyError as exc:
            raise LookupError(f"no {phase.value} compiler plugin provides {capability!r}") from exc

    def manifests(self) -> tuple[CompilerPluginManifest, ...]:
        return tuple(sorted(
            self._plugins.values(),
            key=lambda item: (item.phase.value, item.capability, -item.priority, item.name),
        ))
