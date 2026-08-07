"""
Tests for the AI Skill Explanation Engine (nlu/skill_explainer.py).

Works without a running Ollama server — mocks the OllamaManager.generate() call.
Tests: explain_compilation(), explain_diagnostic(), explain_safety(), explain_diff().
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from roboweaver.nlu.ollama_manager import OllamaManager, OllamaResponse
from roboweaver.nlu.skill_explainer import SkillExplainer, SkillExplanation


def _mock_manager(response_text: str | None = "This is an AI explanation.", error: str | None = None) -> OllamaManager:
    mgr = MagicMock(spec=OllamaManager)
    mgr.generate.return_value = OllamaResponse(
        text=response_text,
        model="llama3.1:8b",
        latency_s=0.5,
        error=error,
    )
    return mgr


def _sample_compilation_result() -> dict:
    return {
        "instruction": "Pick up the red cube",
        "robot": "franka_panda",
        "intent": {
            "action": "PICK",
            "object_name": "red cube",
            "parameters": {"confidence": 0.95},
        },
        "tasks": [
            {"type": "PERCEIVE", "description": "Detect red cube"},
            {"type": "PLAN_MOTION", "description": "Plan approach trajectory"},
            {"type": "GRASP", "description": "Close gripper on red cube"},
        ],
        "ir": {
            "execution": {"robot_id": "franka_panda", "dof": 7},
            "required_capabilities": {
                "perception": ["object_detection"],
                "manipulation": ["grasp"],
                "sensing": [],
            },
            "verification": {
                "safety_checks": ["joint_limits", "collision"],
                "collision_check": True,
                "simulation_required": False,
            },
        },
        "diagnostics": [
            {"severity": "warning", "code": "RW301", "message": "Assumed default pose"},
        ],
    }


class TestSkillExplainer(unittest.TestCase):

    def test_explain_compilation_success(self):
        explainer = SkillExplainer(manager=_mock_manager())
        result = explainer.explain_compilation(
            _sample_compilation_result(),
            {"gripper_type": "parallel", "payload_capacity_kg": 3, "max_reach_m": 0.855},
        )
        self.assertIsInstance(result, SkillExplanation)
        self.assertIsNotNone(result.text)
        self.assertEqual(result.model, "llama3.1:8b")
        self.assertIsNone(result.error)

    def test_explain_compilation_ollama_offline(self):
        explainer = SkillExplainer(manager=_mock_manager(
            response_text=None,
            error="Ollama unreachable at http://localhost:1",
        ))
        result = explainer.explain_compilation(_sample_compilation_result())
        self.assertIsNone(result.text)
        self.assertIn("unreachable", result.error)

    def test_explain_diagnostic(self):
        explainer = SkillExplainer(manager=_mock_manager())
        diag = {
            "code": "RW301",
            "severity": "warning",
            "message": "Object pose assumed — no perception system configured",
            "reason": "No camera specified for this robot",
            "required_capability": "object_detection",
            "fixes": ["Add a depth camera", "Specify coordinates manually"],
        }
        result = explainer.explain_diagnostic(diag, robot_id="franka_panda")
        self.assertIsNotNone(result.text)
        self.assertIsNone(result.error)

    def test_explain_safety(self):
        explainer = SkillExplainer(manager=_mock_manager())
        result = explainer.explain_safety(
            _sample_compilation_result(),
            {"payload_capacity_kg": 3, "max_reach_m": 0.855},
        )
        self.assertIsNotNone(result.text)

    def test_explain_diff(self):
        explainer = SkillExplainer(manager=_mock_manager())
        diff = {
            "instruction": "Pick up the red cube",
            "from_robot": "franka_panda",
            "to_robot": "ur5e",
            "field_changes": {"execution.dof": [7, 6], "execution.robot_id": ["franka_panda", "ur5e"]},
            "objects_added": [],
            "objects_removed": [],
            "objects_changed": [],
        }
        result = explainer.explain_diff(diff)
        self.assertIsNotNone(result.text)

    def test_prompt_includes_instruction(self):
        mgr = _mock_manager()
        explainer = SkillExplainer(manager=mgr)
        explainer.explain_compilation(_sample_compilation_result())
        call_args = mgr.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[1].get("prompt") or call_args[0][0]
        self.assertIn("Pick up the red cube", prompt)


if __name__ == "__main__":
    unittest.main()
