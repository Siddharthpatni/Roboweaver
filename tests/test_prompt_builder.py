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


def test_card_scanner_turtlebot_prompt():
    """Verify parsing and system generation for TurtleBot 4 Card Scanner (card_scannner_ws)."""
    prompt = "Build a visitor card scanner system with TurtleBot4 to scan security ID badges and navigate to reception desk"
    parsed = SystemPromptParser.parse(prompt)
    assert "turtlebot4" in parsed.robots
    assert any(t["action"] == "MOBILE_NAV" for t in parsed.tasks)

    out_dir = Path("local_test_prompt_out")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        choreographer, pkg_path = PromptToWorkcellBuilder.build_from_prompt(
            prompt, output_dir=out_dir, verbose=False
        )
        assert pkg_path is not None
        assert pkg_path.exists()
        launch_txt = (pkg_path / "launch" / "workcell_orchestration.launch.py").read_text(encoding="utf-8")
        assert "namespace='/turtlebot4'" in launch_txt
        print("  -> Verified TurtleBot 4 Card Scanner Prompt Parsing & ROS 2 Package Generation [PASSED]")
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def test_build_system_from_prompt():
    """Verify end-to-end multi-robot system compilation and ROS 2 package export from text prompt."""
    prompt = "Build ShopMate-R retail assistant with Temi for navigation, Pepper for customer interaction, and Franka arm for restocking"
    out_dir = Path("local_test_prompt_out")
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
    test_card_scanner_turtlebot_prompt()
    test_build_system_from_prompt()
    print("\n=== ALL PROMPT-TO-SYSTEM BUILDER TESTS PASSED SUCCESSFULLY ===")
