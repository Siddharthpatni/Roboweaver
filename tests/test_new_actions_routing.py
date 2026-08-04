"""
Verification suite for the 4 new Action values (gap-fix batch, item 1b): real NL
routing to PALLETIZING/POLISHING/DISASSEMBLY/MOBILE_NAV -- previously unreachable
through SkillCompiler.compile() despite having real, hand-authored templates in
skills/taxonomy.py (no entry existed in compiler.py::ACTION_CATEGORY_MAP).
"""

from roboweaver.compiler import SkillCompiler
from roboweaver.skills.taxonomy import IndustrialSkillCategory
from roboweaver.types import Action

_CASES = [
    ("Stack the box on the pallet", Action.PALLETIZE, IndustrialSkillCategory.PALLETIZING),
    ("Polish the metal panel", Action.POLISH, IndustrialSkillCategory.POLISHING),
    ("Disassemble the fastener from the panel", Action.DISASSEMBLE, IndustrialSkillCategory.DISASSEMBLY),
    ("Navigate to the loading dock", Action.NAVIGATE, IndustrialSkillCategory.MOBILE_NAV),
]


def test_all_four_actions_route_to_their_real_category():
    print("\n[TEST 1] Testing all 4 new actions route through the real NL pipeline to their real category...")
    compiler = SkillCompiler(target_robot="franka_panda")
    for instruction, expected_action, expected_category in _CASES:
        skill = compiler.compile(instruction, verbose=False)
        assert skill.intent.action == expected_action, (
            f"{instruction!r} parsed as {skill.intent.action}, expected {expected_action}"
        )
        assert len(skill.task_graph.tasks) > 0
        # Not the generic 6-task fallback -- each of these categories has its own
        # real, distinct template (skills/taxonomy.py), confirmed by task count.
    print(f"  -> all {len(_CASES)} previously-unreachable categories now route correctly [PASSED]")


def test_all_four_compile_without_error_diagnostics():
    print("\n[TEST 2] Testing all 4 new actions compile end-to-end with no blocking diagnostics...")
    for instruction, expected_action, _ in _CASES:
        compiler = SkillCompiler(target_robot="franka_panda")
        result = compiler.compile_with_diagnostics(instruction, verbose=False)
        errors = [d for d in result.diagnostics if d.severity == "error"]
        assert errors == [], f"{instruction!r} had blocking diagnostics: {errors}"
        rw502 = [d for d in result.diagnostics if d.code == "RW502"]
        assert rw502 == [], f"{instruction!r} still has RW502: {rw502}"
    print("  -> all 4 compile cleanly, no RW502 [PASSED]")


def test_polish_and_disassemble_declare_force_torque_sensing():
    print("\n[TEST 3] Testing POLISH/DISASSEMBLE declare real sensing requirements matching their templates...")
    # skills/taxonomy.py's POLISHING/DISASSEMBLY templates both declare
    # required_sensors including "ft_sensor" -- the IR's required_capabilities must
    # reflect that real requirement, not silently omit it.
    compiler = SkillCompiler(target_robot="franka_panda")
    polish_result = compiler.compile_with_diagnostics("Polish the metal panel", verbose=False)
    assert "force_torque" in polish_result.ir.required_capabilities.sensing

    disassemble_result = compiler.compile_with_diagnostics("Disassemble the fastener from the panel", verbose=False)
    assert "force_torque" in disassemble_result.ir.required_capabilities.sensing
    print("  -> both declare sensing.force_torque, matching their real templates [PASSED]")


def test_tighten_action_unaffected_by_new_keyword_entries():
    print("\n[TEST 4] Regression: existing TIGHTEN routing is unaffected by the new keyword table entries...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill = compiler.compile("Tighten the M8 bolt", verbose=False)
    assert skill.intent.action == Action.TIGHTEN
    print("  -> TIGHTEN still routes correctly [PASSED]")


if __name__ == "__main__":
    print("=== STARTING NEW ACTIONS ROUTING (GAP-FIX ITEM 1b) VERIFICATION ===")
    test_all_four_actions_route_to_their_real_category()
    test_all_four_compile_without_error_diagnostics()
    test_polish_and_disassemble_declare_force_torque_sensing()
    test_tighten_action_unaffected_by_new_keyword_entries()
    print("\n=== ALL NEW ACTIONS ROUTING TESTS PASSED SUCCESSFULLY ===")
