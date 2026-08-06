"""
Tests for the AI Recovery Advisor (runtime/ai_recovery.py).

Works without a running Ollama server — mocks the OllamaManager.generate() call.
Tests: successful advice, offline fallback, response parsing.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from roboweaver.nlu.ollama_manager import OllamaManager, OllamaResponse
from roboweaver.runtime.ai_recovery import AIRecoveryAdvisor, AIRecoveryAdvice


def _mock_manager(text: str | None = None, error: str | None = None) -> OllamaManager:
    mgr = MagicMock(spec=OllamaManager)
    if text is None and error is None:
        text = (
            "**Root Cause**: The grasp force threshold was not met due to misalignment.\n"
            "**Recovery Guidance**:\n"
            "- Retry with a wider approach vector\n"
            "- Increase pre-grasp height by 15mm\n"
            "**Parameter Adjustments**: approach_height: 0.12 → 0.135\n"
            "**Prevention**: Add a depth camera for real-time pose estimation."
        )
    mgr.generate.return_value = OllamaResponse(
        text=text, model="llama3.1:8b", latency_s=1.2, error=error,
    )
    return mgr


class TestAIRecoveryAdvisor(unittest.TestCase):

    def test_advise_success(self):
        advisor = AIRecoveryAdvisor(manager=_mock_manager())
        advice = advisor.advise(
            failure_mode="GRASP_FAILED",
            rule_based_action="RETRY_GRASP",
            rule_based_reason="Grasp force threshold not met.",
            robot_id="franka_panda",
            robot_spec={"dof": 7, "gripper_type": "parallel"},
            skill_context={"action": "PICK", "object_name": "red cube"},
        )

        self.assertIsInstance(advice, AIRecoveryAdvice)
        self.assertEqual(advice.rule_based_action, "RETRY_GRASP")
        self.assertIsNotNone(advice.ai_explanation)
        self.assertIsNone(advice.error)
        self.assertEqual(advice.model, "llama3.1:8b")

    def test_advise_ollama_offline(self):
        advisor = AIRecoveryAdvisor(manager=_mock_manager(
            text=None, error="Ollama unreachable",
        ))
        advice = advisor.advise(
            failure_mode="GRASP_FAILED",
            rule_based_action="RETRY_GRASP",
            rule_based_reason="Test reason.",
        )

        # Rule-based result is always present
        self.assertEqual(advice.rule_based_action, "RETRY_GRASP")
        self.assertEqual(advice.rule_based_reason, "Test reason.")
        # AI is absent with stated error
        self.assertIsNone(advice.ai_explanation)
        self.assertIn("unreachable", advice.error.lower())

    def test_advise_passes_context(self):
        mgr = _mock_manager()
        advisor = AIRecoveryAdvisor(manager=mgr)
        advisor.advise(
            failure_mode="COLLISION_DETECTED",
            rule_based_action="EMERGENCY_STOP",
            rule_based_reason="Collision.",
            robot_id="ur5e",
            skill_context={"action": "PLACE", "error_message": "Joint 3 collision"},
        )
        call_args = mgr.generate.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[0][0]
        self.assertIn("COLLISION_DETECTED", prompt)
        self.assertIn("ur5e", prompt)

    def test_root_cause_extraction(self):
        advisor = AIRecoveryAdvisor(manager=_mock_manager())
        advice = advisor.advise(
            failure_mode="GRASP_FAILED",
            rule_based_action="RETRY_GRASP",
            rule_based_reason="Test.",
        )
        # The mock response contains a Root Cause section
        self.assertIsNotNone(advice.ai_root_cause)
        self.assertEqual(
            advice.ai_suggested_params["changes"]["approach_height"],
            {"from": 0.12, "to": 0.135},
        )


if __name__ == "__main__":
    unittest.main()
