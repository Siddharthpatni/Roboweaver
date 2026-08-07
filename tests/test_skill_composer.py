"""
Tests for the Natural Language Skill Composer (nlu/skill_composer.py).

Works without a running Ollama server — mocks the OllamaManager.generate() call.
Tests: successful decomposition, malformed output handling, robot validation.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from roboweaver.nlu.ollama_manager import OllamaManager, OllamaResponse
from roboweaver.nlu.skill_composer import SkillComposer, SkillComposition


def _mock_manager(text: str | None = None, error: str | None = None) -> OllamaManager:
    mgr = MagicMock(spec=OllamaManager)
    if text is None and error is None:
        text = json.dumps([
            {
                "step_id": "step_1",
                "instruction": "Pick up the phone case from the conveyor belt",
                "action": "PICK",
                "target_object": "phone case",
                "suggested_robot": "franka_panda",
                "depends_on": [],
                "reasoning": "Franka Panda has precision gripper for small parts.",
            },
            {
                "step_id": "step_2",
                "instruction": "Place the phone case into the assembly jig",
                "action": "PLACE",
                "target_object": "phone case",
                "suggested_robot": "franka_panda",
                "depends_on": ["step_1"],
                "reasoning": "Same robot, sequential operation.",
            },
            {
                "step_id": "step_3",
                "instruction": "Inspect the assembled phone case for defects",
                "action": "INSPECT",
                "target_object": "phone case",
                "suggested_robot": "ur5e",
                "depends_on": ["step_2"],
                "reasoning": "UR5e has mounted camera for inspection.",
            },
        ])
    mgr.generate.return_value = OllamaResponse(
        text=text, model="llama3.1:8b", latency_s=2.1, error=error,
    )
    return mgr


class TestSkillComposer(unittest.TestCase):

    def test_compose_success(self):
        composer = SkillComposer(manager=_mock_manager())
        result = composer.compose("Set up a phone case assembly line")

        self.assertIsInstance(result, SkillComposition)
        self.assertEqual(len(result.steps), 3)
        self.assertEqual(result.steps[0].action, "PICK")
        self.assertEqual(result.steps[0].suggested_robot, "franka_panda")
        self.assertEqual(result.steps[1].depends_on, ["step_1"])
        self.assertIn("franka_panda", result.suggested_robots)
        self.assertGreater(len(result.choreography_prompt), 0)
        self.assertIsNone(result.error)

    def test_compose_ollama_offline(self):
        composer = SkillComposer(manager=_mock_manager(
            text=None, error="Ollama unreachable",
        ))
        result = composer.compose("Build a workcell")

        self.assertEqual(len(result.steps), 0)
        self.assertIsNotNone(result.error)
        self.assertIn("unreachable", result.error.lower())

    def test_compose_malformed_json(self):
        composer = SkillComposer(manager=_mock_manager(text="This is not JSON at all."))
        result = composer.compose("Build something")

        self.assertEqual(len(result.steps), 0)
        self.assertIsNotNone(result.error)
        self.assertIn("JSON", result.error)

    def test_compose_invalid_robot_id_rejected(self):
        steps = json.dumps([{
            "step_id": "step_1",
            "instruction": "Pick the part",
            "action": "PICK",
            "target_object": "part",
            "suggested_robot": "fake_robot_9000",  # Not in ROBOT_REGISTRY
            "depends_on": [],
            "reasoning": "Test",
        }])
        composer = SkillComposer(manager=_mock_manager(text=steps))
        result = composer.compose("Test")

        # Step is still created, but robot is None (rejected against registry)
        self.assertEqual(len(result.steps), 1)
        self.assertIsNone(result.steps[0].suggested_robot)

    def test_compose_invalid_action_falls_back(self):
        steps = json.dumps([{
            "step_id": "step_1",
            "instruction": "Teleport the cube",
            "action": "TELEPORT",  # Not in Action enum
            "target_object": "cube",
            "depends_on": [],
        }])
        composer = SkillComposer(manager=_mock_manager(text=steps))
        result = composer.compose("Test")

        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].action, "PICK")  # Fallback

    def test_choreography_prompt_format(self):
        composer = SkillComposer(manager=_mock_manager())
        result = composer.compose("Phone case assembly")

        self.assertIn("Build a workcell for:", result.choreography_prompt)
        self.assertIn("Step step_1:", result.choreography_prompt)

    def test_compose_handles_dict_response(self):
        """Some models wrap the array in a dict with a 'steps' key."""
        wrapped = json.dumps({
            "steps": [
                {
                    "step_id": "step_1",
                    "instruction": "Pick the item",
                    "action": "PICK",
                    "target_object": "item",
                    "depends_on": [],
                },
            ]
        })
        composer = SkillComposer(manager=_mock_manager(text=wrapped))
        result = composer.compose("Test")
        self.assertEqual(len(result.steps), 1)


if __name__ == "__main__":
    unittest.main()
