"""Plan open-ended embodiments without executing model-authored source code."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any
from xml.etree import ElementTree as ET

from roboweaver.json_utils import loads_strict
from roboweaver.nlu.cascade import CascadeManager, CascadeResponse


_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,47}$")
_SHAPES = {"box", "cylinder", "sphere", "capsule"}
_JOINT_TYPES = {"fixed", "revolute", "continuous", "prismatic"}
_SENSORS = {"joint_position", "joint_velocity", "contact", "imu", "camera", "force_torque"}
_ALGORITHMS = {"PPO", "SAC", "TD3", "behavior_cloning"}
_FORBIDDEN_IMPORTS = {"os", "pathlib", "socket", "subprocess", "requests", "urllib", "shutil"}
_FORBIDDEN_CALLS = {"eval", "exec", "compile", "open", "__import__", "input"}


@dataclass(frozen=True)
class LinkSpec:
    name: str
    shape: str
    size_m: tuple[float, float, float]
    mass_kg: float


@dataclass(frozen=True)
class JointSpec:
    name: str
    parent: str
    child: str
    joint_type: str
    axis: tuple[float, float, float]
    lower: float
    upper: float
    effort: float
    velocity: float


@dataclass(frozen=True)
class TrainingSpec:
    algorithm: str
    observation_terms: tuple[str, ...]
    reward_terms: tuple[str, ...]
    termination_terms: tuple[str, ...]
    max_steps: int


@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    objective: str
    embodiment_class: str
    links: tuple[LinkSpec, ...]
    joints: tuple[JointSpec, ...]
    sensors: tuple[str, ...]
    training: TrainingSpec

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentResult:
    spec: ExperimentSpec
    provider: str
    model: str
    attempts: int
    cache_hit: bool
    ai_error: str | None
    artifacts: dict[str, str]
    artifact_sha256: dict[str, str]
    safety: dict[str, Any]
    sandbox: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "provider": self.provider,
            "model": self.model,
            "attempts": self.attempts,
            "cache_hit": self.cache_hit,
            "ai_error": self.ai_error,
            "artifacts": self.artifacts,
            "artifact_sha256": self.artifact_sha256,
            "safety": self.safety,
            "sandbox": self.sandbox,
        }


def _finite_number(value: Any, field: str, low: float, high: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number.")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{field} must be between {low} and {high}.")
    return number


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _NAME_RE.fullmatch(value):
        raise ValueError(f"{field} must be lower_snake_case and at most 48 characters.")
    return value


def _text(value: Any, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{field} must contain 1-{max_length} characters.")
    return value.strip()


def _string_list(value: Any, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ValueError(f"{field} must contain 1-{maximum} strings.")
    result = tuple(_text(item, field, 80) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} must not contain duplicates.")
    return result


def _parse_links(links_raw: Any) -> tuple[LinkSpec, ...]:
    if not isinstance(links_raw, list) or not 1 <= len(links_raw) <= 24:
        raise ValueError("links must contain 1-24 entries.")
    links: list[LinkSpec] = []
    for index, item in enumerate(links_raw):
        if not isinstance(item, dict):
            raise ValueError(f"links[{index}] must be an object.")
        shape = item.get("shape")
        if shape not in _SHAPES:
            raise ValueError(f"links[{index}].shape must be one of {sorted(_SHAPES)}.")
        size = item.get("size_m")
        if not isinstance(size, list) or len(size) != 3:
            raise ValueError(f"links[{index}].size_m must have three values.")
        links.append(LinkSpec(
            _name(item.get("name"), f"links[{index}].name"),
            shape,
            tuple(_finite_number(v, f"links[{index}].size_m", 0.01, 3.0) for v in size),
            _finite_number(item.get("mass_kg"), f"links[{index}].mass_kg", 0.01, 500.0),
        ))
    link_names = {link.name for link in links}
    if len(link_names) != len(links):
        raise ValueError("Link names must be unique.")
    return tuple(links)


def _parse_joint(item: Any, index: int, link_names: set[str], children: set[str]) -> JointSpec:
    if not isinstance(item, dict):
        raise ValueError(f"joints[{index}] must be an object.")
    parent = _name(item.get("parent"), f"joints[{index}].parent")
    child = _name(item.get("child"), f"joints[{index}].child")
    joint_type = item.get("joint_type")
    axis = item.get("axis")
    if parent not in link_names or child not in link_names or parent == child:
        raise ValueError(f"joints[{index}] must connect two different declared links.")
    if child in children:
        raise ValueError(f"Link '{child}' has multiple parents.")
    if joint_type not in _JOINT_TYPES:
        raise ValueError(f"joints[{index}].joint_type is unsupported.")
    if not isinstance(axis, list) or len(axis) != 3:
        raise ValueError(f"joints[{index}].axis must have three values.")
    lower = _finite_number(item.get("lower", 0.0), f"joints[{index}].lower", -6.3, 6.3)
    upper = _finite_number(item.get("upper", 0.0), f"joints[{index}].upper", -6.3, 6.3)
    if joint_type not in {"fixed", "continuous"} and lower >= upper:
        raise ValueError(f"joints[{index}] lower limit must be below upper limit.")
    children.add(child)
    return JointSpec(
        _name(item.get("name"), f"joints[{index}].name"),
        parent,
        child,
        joint_type,
        tuple(_finite_number(v, f"joints[{index}].axis", -1.0, 1.0) for v in axis),
        lower,
        upper,
        _finite_number(item.get("effort", 1.0), f"joints[{index}].effort", 0.01, 1000.0),
        _finite_number(item.get("velocity", 1.0), f"joints[{index}].velocity", 0.01, 100.0),
    )


def _parse_joints(joints_raw: Any, links: tuple[LinkSpec, ...]) -> tuple[JointSpec, ...]:
    if not isinstance(joints_raw, list) or len(joints_raw) > 32:
        raise ValueError("joints must contain at most 32 entries.")
    link_names = {link.name for link in links}
    joints: list[JointSpec] = []
    children: set[str] = set()
    for index, item in enumerate(joints_raw):
        joints.append(_parse_joint(item, index, link_names, children))
    if len({joint.name for joint in joints}) != len(joints):
        raise ValueError("Joint names must be unique.")
    if joints and len(joints) != len(links) - 1:
        raise ValueError("The morphology must be one connected acyclic link tree.")
    roots = link_names - children
    if len(roots) != 1:
        raise ValueError("The morphology must have exactly one root link.")
    reachable = set(roots)
    for _ in links:
        reachable.update(joint.child for joint in joints if joint.parent in reachable)
    if reachable != link_names:
        raise ValueError("The morphology contains a cycle or disconnected link.")
    return tuple(joints)


def _parse_training(training_raw: Any) -> TrainingSpec:
    if not isinstance(training_raw, dict):
        raise ValueError("training must be an object.")
    algorithm = training_raw.get("algorithm")
    if algorithm not in _ALGORITHMS:
        raise ValueError(f"training.algorithm must be one of {sorted(_ALGORITHMS)}.")
    return TrainingSpec(
        algorithm,
        _string_list(training_raw.get("observation_terms"), "observation_terms", 16),
        _string_list(training_raw.get("reward_terms"), "reward_terms", 16),
        _string_list(training_raw.get("termination_terms"), "termination_terms", 12),
        int(_finite_number(training_raw.get("max_steps", 1000), "training.max_steps", 10, 1_000_000)),
    )


def parse_experiment_spec(raw: str | dict[str, Any]) -> ExperimentSpec:
    data = loads_strict(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        raise ValueError("Experiment output must be one JSON object.")
    links = _parse_links(data.get("links"))
    joints = _parse_joints(data.get("joints"), links)
    sensors = _string_list(data.get("sensors"), "sensors", 12)
    if not set(sensors) <= _SENSORS:
        raise ValueError(f"sensors must be selected from {sorted(_SENSORS)}.")
    return ExperimentSpec(
        _name(data.get("name"), "name"),
        _text(data.get("objective"), "objective", 400),
        _text(data.get("embodiment_class"), "embodiment_class", 80),
        links,
        joints,
        sensors,
        _parse_training(data.get("training")),
    )


def validate_generated_python(source: str) -> None:
    if len(source) > 50_000:
        raise ValueError("Generated scaffold exceeds 50,000 characters.")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Generated scaffold is invalid Python: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[0] for alias in node.names}
            if names & _FORBIDDEN_IMPORTS:
                raise ValueError("Generated scaffold imports a blocked host-access module.")
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in _FORBIDDEN_IMPORTS:
            raise ValueError("Generated scaffold imports a blocked host-access module.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_CALLS:
            raise ValueError(f"Generated scaffold calls blocked function '{node.func.id}'.")


def _geometry(parent: ET.Element, link: LinkSpec) -> None:
    geometry = ET.SubElement(parent, "geometry")
    x, y, z = link.size_m
    if link.shape == "box":
        ET.SubElement(geometry, "box", {"size": f"{x:.4f} {y:.4f} {z:.4f}"})
    elif link.shape == "sphere":
        ET.SubElement(geometry, "sphere", {"radius": f"{x / 2:.4f}"})
    else:
        ET.SubElement(geometry, "cylinder", {"radius": f"{x / 2:.4f}", "length": f"{z:.4f}"})


def generate_urdf(spec: ExperimentSpec) -> str:
    robot = ET.Element("robot", {"name": spec.name})
    for item in spec.links:
        link = ET.SubElement(robot, "link", {"name": item.name})
        inertial = ET.SubElement(link, "inertial")
        ET.SubElement(inertial, "mass", {"value": f"{item.mass_kg:.4f}"})
        ET.SubElement(inertial, "inertia", {
            "ixx": "0.01", "ixy": "0", "ixz": "0", "iyy": "0.01", "iyz": "0", "izz": "0.01"
        })
        for element_name in ("visual", "collision"):
            element = ET.SubElement(link, element_name)
            _geometry(element, item)
    for item in spec.joints:
        joint = ET.SubElement(robot, "joint", {"name": item.name, "type": item.joint_type})
        ET.SubElement(joint, "parent", {"link": item.parent})
        ET.SubElement(joint, "child", {"link": item.child})
        ET.SubElement(joint, "origin", {"xyz": "0 0 0.15", "rpy": "0 0 0"})
        ET.SubElement(joint, "axis", {"xyz": " ".join(f"{value:.4f}" for value in item.axis)})
        if item.joint_type not in {"fixed", "continuous"}:
            ET.SubElement(joint, "limit", {
                "lower": f"{item.lower:.4f}", "upper": f"{item.upper:.4f}",
                "effort": f"{item.effort:.4f}", "velocity": f"{item.velocity:.4f}",
            })
    ET.indent(robot, space="  ")
    return ET.tostring(robot, encoding="unicode", xml_declaration=True) + "\n"


def generate_training_scaffold(spec: ExperimentSpec) -> str:
    config = json.dumps(spec.to_dict(), sort_keys=True, indent=2)
    return f'''"""RoboWeaver research-only training scaffold for {spec.name}.

This file does not connect to ROS, a network, or physical hardware. Implement the
SimulatorAdapter protocol inside the isolated research image before training.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

EXPERIMENT = json.loads({config!r})


class SimulatorAdapter(Protocol):
    def reset(self) -> list[float]: ...
    def step(self, action: list[float]) -> tuple[list[float], dict[str, float], bool]: ...


@dataclass(frozen=True)
class RewardWeights:
    progress: float = 2.0
    contact: float = 0.5
    energy: float = -0.02
    fall: float = -5.0


def reward(metrics: dict[str, float], weights: RewardWeights = RewardWeights()) -> float:
    return (
        weights.progress * metrics.get("vertical_progress", 0.0)
        + weights.contact * metrics.get("stable_contacts", 0.0)
        + weights.energy * metrics.get("energy", 0.0)
        + weights.fall * metrics.get("fell", 0.0)
    )


def train(adapter: SimulatorAdapter, policy) -> dict[str, float]:
    """Bounded rollout hook; policy/update implementation is intentionally injected."""
    observations = adapter.reset()
    total_reward = 0.0
    steps = 0
    for steps in range(EXPERIMENT["training"]["max_steps"]):
        action = list(policy.act(observations))
        observations, metrics, done = adapter.step(action)
        value = reward(metrics)
        policy.observe(value, done)
        total_reward += value
        if done:
            break
    return {{"steps": float(steps + 1), "total_reward": total_reward}}


if __name__ == "__main__":
    print(json.dumps({{"status": "adapter_required", "experiment": EXPERIMENT["name"]}}))
'''


def _climbing_monkey_spec(objective: str) -> ExperimentSpec:
    links = [
        LinkSpec("torso", "box", (0.28, 0.18, 0.42), 8.0),
        LinkSpec("left_upper_arm", "capsule", (0.08, 0.08, 0.32), 1.2),
        LinkSpec("left_forearm", "capsule", (0.07, 0.07, 0.34), 0.9),
        LinkSpec("right_upper_arm", "capsule", (0.08, 0.08, 0.32), 1.2),
        LinkSpec("right_forearm", "capsule", (0.07, 0.07, 0.34), 0.9),
        LinkSpec("left_thigh", "capsule", (0.10, 0.10, 0.34), 2.0),
        LinkSpec("left_shin", "capsule", (0.09, 0.09, 0.32), 1.4),
        LinkSpec("right_thigh", "capsule", (0.10, 0.10, 0.34), 2.0),
        LinkSpec("right_shin", "capsule", (0.09, 0.09, 0.32), 1.4),
    ]
    edges = [
        ("left_shoulder", "torso", "left_upper_arm"), ("left_elbow", "left_upper_arm", "left_forearm"),
        ("right_shoulder", "torso", "right_upper_arm"), ("right_elbow", "right_upper_arm", "right_forearm"),
        ("left_hip", "torso", "left_thigh"), ("left_knee", "left_thigh", "left_shin"),
        ("right_hip", "torso", "right_thigh"), ("right_knee", "right_thigh", "right_shin"),
    ]
    joints = tuple(JointSpec(name, parent, child, "revolute", (0.0, 1.0, 0.0), -2.4, 2.4, 60.0, 4.0)
                   for name, parent, child in edges)
    return ExperimentSpec(
        "climbing_monkey", objective[:400], "branched_climbing_quadruped", tuple(links), joints,
        ("joint_position", "joint_velocity", "contact", "imu", "camera"),
        TrainingSpec(
            "PPO", ("joint_state", "body_orientation", "contact_state", "target_direction"),
            ("vertical_progress", "stable_contacts", "energy_penalty", "fall_penalty"),
            ("fell", "reached_height", "time_limit"), 4096,
        ),
    )


def _generic_spec(objective: str) -> ExperimentSpec:
    links = (
        LinkSpec("base", "box", (0.35, 0.25, 0.15), 5.0),
        LinkSpec("body", "box", (0.22, 0.18, 0.35), 3.0),
        LinkSpec("tool", "capsule", (0.08, 0.08, 0.30), 0.8),
    )
    joints = (
        JointSpec("body_joint", "base", "body", "revolute", (0.0, 1.0, 0.0), -1.5, 1.5, 30.0, 2.0),
        JointSpec("tool_joint", "body", "tool", "revolute", (1.0, 0.0, 0.0), -2.0, 2.0, 15.0, 3.0),
    )
    return ExperimentSpec(
        "generated_robot", objective[:400], "articulated_research_robot", links, joints,
        ("joint_position", "joint_velocity", "imu"),
        TrainingSpec("PPO", ("joint_state", "target_direction"), ("task_progress", "energy_penalty"),
                     ("task_complete", "time_limit"), 2048),
    )


_SYSTEM_PROMPT = """You design bounded research-only robot embodiments. Return JSON only.
Required keys: name, objective, embodiment_class, links, joints, sensors, training.
links: 1-24 objects with lower_snake_case name, shape box/cylinder/sphere/capsule,
size_m as 3 positive values, mass_kg. joints: one connected tree with name, parent,
child, joint_type fixed/revolute/continuous/prismatic, axis[3], lower, upper, effort,
velocity. sensors: joint_position/joint_velocity/contact/imu/camera/force_torque.
training: algorithm PPO/SAC/TD3/behavior_cloning plus non-empty observation_terms,
reward_terms, termination_terms and max_steps. Do not emit code, paths, URLs, plugins,
commands, or physical-hardware instructions."""


class ExperimentPlanner:
    def __init__(self, cascade: CascadeManager | None = None) -> None:
        self.cascade = cascade

    def plan(self, objective: str, use_ai: bool = True) -> ExperimentResult:
        clean = _text(objective, "objective", 1000)
        response: CascadeResponse | None = None
        spec: ExperimentSpec | None = None
        ai_error: str | None = None
        if use_ai:
            cascade = self.cascade or CascadeManager()
            response = cascade.generate(
                prompt=clean,
                feature="experiment",
                system=_SYSTEM_PROMPT,
                json_mode=True,
                temperature=0.1,
                validate=lambda text: parse_experiment_spec(text),
            )
            if response.text is not None:
                spec = parse_experiment_spec(response.text)
            else:
                ai_error = response.error
        if spec is None:
            spec = _climbing_monkey_spec(clean) if any(word in clean.lower() for word in ("climb", "monkey", "ape")) else _generic_spec(clean)
        artifacts = {
            "experiment.json": json.dumps(spec.to_dict(), sort_keys=True, indent=2) + "\n",
            "model.urdf": generate_urdf(spec),
            "brain_train.py": generate_training_scaffold(spec),
        }
        validate_generated_python(artifacts["brain_train.py"])
        digests = {name: hashlib.sha256(value.encode("utf-8")).hexdigest() for name, value in artifacts.items()}
        provider = response.provider if response and response.text is not None else "deterministic_fallback"
        model = response.model if response and response.text is not None else "roboweaver/bounded-template-v1"
        return ExperimentResult(
            spec,
            provider,
            model,
            response.attempts if response else 0,
            response.cache_hit if response else False,
            ai_error,
            artifacts,
            digests,
            {
                "schema_validated": True,
                "python_ast_validated": True,
                "model_authored_code_executed": False,
                "physical_hardware_allowed": False,
                "external_network_allowed": False,
                "limitations": [
                    "URDF geometry is a generated research approximation, not a manufacturable design.",
                    "A simulator adapter and physics validation are required before training.",
                    "No result authorizes physical deployment.",
                ],
            },
            {
                "runner": "docker-compose research profile",
                "network": "none",
                "root_filesystem": "read_only",
                "capabilities": "all_dropped",
                "devices": "none",
                "pids_limit": 64,
                "memory_limit": "1g",
                "cpu_limit": 2.0,
                "command": "docker compose --profile research run --rm experiment-sandbox",
                "status": "artifact_ready_not_executed",
                "physics_adapter": "mujoco (runs only inside the sandbox container above, not this API call)",
            },
        )
