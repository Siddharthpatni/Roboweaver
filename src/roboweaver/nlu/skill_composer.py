"""
Natural Language Skill Composer — uses a local Ollama model to decompose
complex, multi-step instructions into sequences of atomic RoboWeaver-compilable
skills.

\"Set up an assembly line for phone cases\" is not a single compilable instruction —
it's a high-level goal that requires decomposition into pick, place, inspect, etc.
This module bridges that gap:

  * Takes a complex, vague, or multi-step instruction
  * Decomposes it into ordered atomic instructions RoboWeaver's compiler understands
  * Suggests robot assignments from the real ROBOT_REGISTRY
  * Generates the multi-robot choreography prompt for the WorkcellBuilder

Additive: if Ollama is unavailable, returns a stated error — the caller can still
use the compiler's own keyword parser for single-instruction tasks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.nlu.ollama_manager import OllamaManager, get_manager
from roboweaver.types import Action


_VALID_ACTIONS = sorted(a.value for a in Action)

_COMPOSER_SYSTEM = """You are a robotics skill decomposition expert working with RoboWeaver, \
an LLVM-like compiler for robotics. You break down complex tasks into sequences of atomic \
robot skills.

RoboWeaver understands these action verbs: """ + ", ".join(_VALID_ACTIONS) + """

Rules:
- Each atomic step must use ONE action verb from the list above.
- Steps must be ordered by execution dependency (prerequisites first).
- Each step must specify a single, clear target object.
- If multiple robots are needed, assign the best-fit robot from the registry.
- Never invent robot IDs — only use IDs from the provided registry.
- Output ONLY valid JSON, no prose.
"""


@dataclass
class ComposedStep:
    """One atomic instruction in a composed skill sequence."""
    step_id: str
    instruction: str
    action: str
    target_object: str
    suggested_robot: str | None = None
    depends_on: list[str] = field(default_factory=list)
    reasoning: str = ""


@dataclass
class SkillComposition:
    """Full decomposition of a complex instruction into atomic steps.
    `steps` is empty and `error` is set when the LLM couldn't decompose."""
    original_instruction: str
    steps: list[ComposedStep] = field(default_factory=list)
    suggested_robots: list[str] = field(default_factory=list)
    choreography_prompt: str = ""
    model: str = ""
    latency_s: float = 0.0
    error: str | None = None


_COMPOSE_TEMPLATE = """Decompose this complex robot task into a sequence of atomic steps.

**Complex Instruction:** "{instruction}"

**Available Robots:**
{robot_list}

**Valid Actions:** {actions}

Output a JSON array of steps, each with this shape:
[
  {{
    "step_id": "step_1",
    "instruction": "<single atomic instruction using one action verb>",
    "action": "<ACTION from the valid list>",
    "target_object": "<the object this step acts on>",
    "suggested_robot": "<robot_id from the available list or null>",
    "depends_on": ["<step_ids this step depends on>"],
    "reasoning": "<why this step is needed and why this robot>"
  }}
]

Decompose into 2-8 atomic steps. Each instruction must be a single sentence \
starting with an action verb that RoboWeaver's compiler can parse."""


class SkillComposer:
    """Decomposes complex instructions into compilable atomic skill sequences."""

    def __init__(self, manager: OllamaManager | None = None):
        self.manager = manager or get_manager()

    def compose(self, instruction: str) -> SkillComposition:
        """Decompose a complex instruction into atomic, compilable steps."""
        robot_lines = []
        for rid, spec in sorted(ROBOT_REGISTRY.items()):
            robot_lines.append(
                f"  - {rid}: {spec.name} ({spec.dof}-DOF, "
                f"{spec.gripper_type} gripper, "
                f"{spec.payload_capacity_kg}kg payload, "
                f"{spec.max_reach_m}m reach)"
            )
        robot_list = "\n".join(robot_lines) or "  (no robots registered)"

        prompt = _COMPOSE_TEMPLATE.format(
            instruction=instruction,
            robot_list=robot_list,
            actions=", ".join(_VALID_ACTIONS),
        )

        resp = self.manager.generate(
            prompt=prompt,
            feature="composer",
            system=_COMPOSER_SYSTEM,
            json_mode=True,
            temperature=0.3,
        )

        if resp.text is None:
            return SkillComposition(
                original_instruction=instruction,
                error=resp.error,
                model=resp.model,
                latency_s=resp.latency_s,
            )

        return self._parse_composition(instruction, resp)

    def _parse_composition(self, instruction: str, resp: Any) -> SkillComposition:
        """Parse the LLM's JSON array into structured ComposedSteps."""
        raw = resp.text or ""

        # Try to extract JSON array from the response
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Try to find a JSON array in the response
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return SkillComposition(
                        original_instruction=instruction,
                        error=f"Model output was not valid JSON: {raw[:200]}",
                        model=resp.model,
                        latency_s=resp.latency_s,
                    )
            else:
                return SkillComposition(
                    original_instruction=instruction,
                    error=f"Model output contained no JSON array: {raw[:200]}",
                    model=resp.model,
                    latency_s=resp.latency_s,
                )

        # Handle both list and dict-with-steps responses
        if isinstance(parsed, dict):
            parsed = parsed.get("steps", parsed.get("tasks", []))
        if not isinstance(parsed, list):
            return SkillComposition(
                original_instruction=instruction,
                error="Model output was not a JSON array of steps.",
                model=resp.model,
                latency_s=resp.latency_s,
            )

        steps = []
        robots_used = set()
        valid_robot_ids = set(ROBOT_REGISTRY.keys())

        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue

            step_id = str(item.get("step_id", f"step_{i+1}"))
            raw_action = str(item.get("action", "PICK")).strip().upper()
            action = raw_action
            suggested_robot = item.get("suggested_robot")
            reasoning = str(item.get("reasoning", ""))

            # Validate action against the real taxonomy
            if action not in {a.value for a in Action}:
                action = "PICK"
                reasoning = (
                    f"RoboWeaver replaced unsupported action '{raw_action}' with PICK. "
                    + reasoning
                ).strip()

            # Validate robot ID against the real registry
            if suggested_robot and suggested_robot not in valid_robot_ids:
                reasoning = (
                    f"RoboWeaver rejected unknown robot id '{suggested_robot}'. "
                    + reasoning
                ).strip()
                suggested_robot = None

            if suggested_robot:
                robots_used.add(suggested_robot)

            depends = item.get("depends_on", [])
            if isinstance(depends, str):
                depends = [depends] if depends else []

            steps.append(ComposedStep(
                step_id=step_id,
                instruction=str(item.get("instruction", f"Pick object_{i+1}")),
                action=action,
                target_object=str(item.get("target_object", "object")),
                suggested_robot=suggested_robot,
                depends_on=depends,
                reasoning=reasoning,
            ))

        if not steps:
            return SkillComposition(
                original_instruction=instruction,
                error="Model returned an empty step list.",
                model=resp.model,
                latency_s=resp.latency_s,
            )

        # Generate choreography prompt for the WorkcellBuilder
        choreography = self._build_choreography_prompt(instruction, steps)

        return SkillComposition(
            original_instruction=instruction,
            steps=steps,
            suggested_robots=sorted(robots_used),
            choreography_prompt=choreography,
            model=resp.model,
            latency_s=resp.latency_s,
        )

    def _build_choreography_prompt(self, instruction: str, steps: list[ComposedStep]) -> str:
        """Generate the natural-language prompt that the WorkcellBuilder's
        SystemPromptParser.parse() can consume directly."""
        parts = [f"Build a workcell for: {instruction}"]

        # Collect unique robots
        robots = {s.suggested_robot for s in steps if s.suggested_robot}
        if robots:
            robot_descs = []
            for rid in sorted(robots):
                spec = ROBOT_REGISTRY.get(rid)
                if spec:
                    robot_descs.append(f"{spec.name} ({rid})")
            if robot_descs:
                parts.append(f"Using: {', '.join(robot_descs)}")

        for step in steps:
            robot_note = f" with {step.suggested_robot}" if step.suggested_robot else ""
            dep_note = f" (after {', '.join(step.depends_on)})" if step.depends_on else ""
            parts.append(f"Step {step.step_id}: {step.instruction}{robot_note}{dep_note}")

        return "\n".join(parts)
