"""Behavioral proof for upstream-inspired and native compiler integration."""

from __future__ import annotations

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.compiler_core import (
    CompilerPhase,
    CompilerPluginManifest,
    CompilerPluginRegistry,
    ConversionError,
    ConversionPattern,
    ConversionTarget,
    Operation,
    apply_full_conversion,
)
from roboweaver.ir import AnalysisManager, PassContext, PreservedAnalyses
from roboweaver.upstream import MLIRBridgeError, emit_mlir, run_native_mlir


def test_full_conversion_rewrites_every_illegal_operation():
    result = apply_full_conversion(
        [Operation("portable.move"), Operation("portable.grasp")],
        ConversionTarget(frozenset({"robot.move", "robot.grasp"})),
        [
            ConversionPattern("portable.move", lambda _: Operation("robot.move"), "LowerMove"),
            ConversionPattern("portable.grasp", lambda _: Operation("robot.grasp"), "LowerGrasp"),
        ],
    )
    assert [operation.name for operation in result.operations] == ["robot.move", "robot.grasp"]
    assert len(result.trace) == 2


def test_full_conversion_fails_when_one_operation_has_no_pattern():
    with pytest.raises(ConversionError, match="portable.unknown"):
        apply_full_conversion(
            [Operation("portable.unknown")],
            ConversionTarget(frozenset({"robot.known"})),
            [],
        )


def test_phase_plugin_registry_resolves_higher_priority_external_provider():
    registry = CompilerPluginRegistry("test.roboweaver.plugins")
    builtin = object()
    external = object()
    registry.register(CompilerPluginManifest(
        "builtin", "1", CompilerPhase.TRANSFORMATION, "serial_arm", builtin,
    ))
    manifest = CompilerPluginManifest(
        "external", "2", CompilerPhase.TRANSFORMATION, "serial_arm", external,
        priority=10, source="test-entry-point",
    )

    class FakeEntryPoint:
        name = "serial_arm"

        @staticmethod
        def load():
            return manifest

    assert registry.discover([FakeEntryPoint()]) == 1
    assert registry.resolve(CompilerPhase.TRANSFORMATION, "serial_arm").provider is external


def test_analysis_manager_caches_and_invalidates_unpreserved_results():
    compiler = SkillCompiler("franka_panda")
    result = compiler.compile_with_diagnostics("Pick up the cube", verbose=False)
    manager = AnalysisManager()
    manager.register("skill", lambda ctx: ctx.ir.skill_id)
    context = PassContext(result.ir, result.skill, compiler.robot_spec, analyses=manager)
    assert manager.get("skill", context) == result.ir.skill_id
    assert manager.get("skill", context) == result.ir.skill_id
    assert manager.snapshot() == (1, 1, 0)
    manager.invalidate(result.ir, PreservedAnalyses.none())
    assert manager.snapshot() == (1, 1, 1)


def test_real_motion_lowering_records_full_conversion_trace():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the cube", verbose=False,
    )
    trace = result.ir.lowering.legalization_trace
    assert trace
    assert any("portable.action.PICK -> target.serial_arm.action.PICK" in item for item in trace)
    assert all("portable." in item and "target.serial_arm." in item for item in trace)


def test_mlir_export_contains_program_and_target_operations():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the cube", verbose=False,
    )
    source = emit_mlir(result.ir)
    assert source.startswith("module {\n")
    assert '"roboweaver.skill"' in source
    assert '"roboweaver.task"' in source
    assert '"roboweaver.target"' in source
    assert '"roboweaver.trajectory"' in source


def test_required_native_mlir_fails_closed_when_executable_is_absent(monkeypatch):
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the cube", verbose=False,
    )
    monkeypatch.setenv("ROBOWEAVER_MLIR_OPT", "/definitely/missing/mlir-opt")
    with pytest.raises(MLIRBridgeError, match="required"):
        run_native_mlir(result.ir, mode="required")


def test_pipeline_reports_real_analysis_cache_reuse():
    result = SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the cube", verbose=False,
    )
    assert result.pipeline.records[0].metrics["analysis_cache_misses"] == 1.0
    assert result.pipeline.records[1].metrics["analysis_cache_hits"] == 1.0
    assert result.pipeline.records[2].metrics["analysis_cache_hits"] == 1.0
