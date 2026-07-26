"""
Verification Suite for Prompt-to-System Multi-Robot Builder (PromptToWorkcellBuilder).

Verifies building complete multi-robot systems directly from natural language prompts,
such as ShopMate-R (connecting Temi, Pepper, and Franka Panda).
"""

import shutil
from pathlib import Path
from roboweaver.fleet import PromptToWorkcellBuilder, SystemPromptParser


def test_shopmate_r_prompt_parsing():
    """Verify parsing of the ShopMate-R retail assistant prompt."""
    prompt = "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"
    parsed = SystemPromptParser.parse(prompt)

    assert parsed.workcell_name == "ShopMate_R"
    assert set(parsed.robots) == {"temi", "pepper", "franka_panda"}
    assert len(parsed.tasks) >= 3
    print("  -> Verified ShopMate-R Prompt Parsing (Temi, Pepper, Franka Panda) [PASSED]")


def test_build_system_from_prompt():
    """Verify end-to-end multi-robot system compilation and ROS 2 package export from text prompt."""
    prompt = "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"
    out_dir = Path("/Users/siddharthpatni/.gemini/antigravity-ide/scratch/roboweaver/test_prompt_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        choreographer, pkg_path = PromptToWorkcellBuilder.build_from_prompt(
            prompt, output_dir=out_dir, verbose=False
        )
        assert pkg_path is not None
        assert pkg_path.exists()
        assert (pkg_path / "composite_workcell_bt.xml").exists()
        assert (pkg_path / "launch" / "workcell_orchestration.launch.py").exists()

        launch_txt = (pkg_path / "launch" / "workcell_orchestration.launch.py").read_text(encoding="utf-8")
        assert "namespace='/temi'" in launch_txt
        assert "namespace='/pepper'" in launch_txt
        assert "namespace='/franka_panda'" in launch_txt

        print(f"  -> Successfully compiled ShopMate-R Workcell & exported ROS 2 package: {pkg_path.name} [PASSED]")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=== STARTING ROBOWEAVER PROMPT-TO-SYSTEM BUILDER VERIFICATION ===")
    test_shopmate_r_prompt_parsing()
    test_build_system_from_prompt()
    print("\n=== ALL PROMPT-TO-SYSTEM BUILDER TESTS PASSED SUCCESSFULLY ===")
