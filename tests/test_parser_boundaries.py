"""Adversarial boundaries for the deterministic taxonomy parser."""

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.ir import SkillCompilationError
from roboweaver.types import Action


@pytest.mark.parametrize("instruction", ["Unpack the shipment", "Refill coolant"])
def test_action_keywords_do_not_match_inside_unrelated_words(instruction):
    intent = SkillCompiler("universal")._parse_intent(instruction)
    assert intent.action is Action.PICK
    assert intent.confidence == 0.0
    assert any("fallback, not a parse" in warning for warning in intent.parse_warnings)


@pytest.mark.parametrize("instruction", ["Unpack the shipment", "Refill coolant"])
def test_unknown_actions_fail_closed_before_portable_ir_or_artifact_generation(instruction):
    with pytest.raises(SkillCompilationError) as exc_info:
        SkillCompiler("universal").compile_portable(instruction, verbose=False)

    assert [diagnostic.code for diagnostic in exc_info.value.diagnostics] == ["RW101"]
    assert "parser fallback" in exc_info.value.diagnostics[0].reason


@pytest.mark.parametrize(
    ("instruction", "expected"),
    [
        ("Pack the shipment", Action.PACKAGE),
        ("Fill the container", Action.POUR),
        ("Navigate to the loading dock", Action.NAVIGATE),
    ],
)
def test_complete_action_words_still_route_normally(instruction, expected):
    intent = SkillCompiler("universal")._parse_intent(instruction)
    assert intent.action is expected
    assert intent.confidence > 0.0
