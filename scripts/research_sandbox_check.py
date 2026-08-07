"""Fixed entry point for the networkless research sandbox image."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from roboweaver.research.experiments import ExperimentPlanner, validate_generated_python
from roboweaver.research.mujoco_adapter import run_physics_rollout


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a bounded research embodiment.")
    parser.add_argument("--objective", default="Design a climbing monkey robot")
    parser.add_argument("--physics-steps", type=int, default=600)
    args = parser.parse_args()
    if os.environ.get("ROBOWEAVER_RESEARCH_SANDBOX") != "1":
        print(json.dumps({"status": "refused", "reason": "sandbox marker missing"}))
        return 2
    result = ExperimentPlanner().plan(args.objective, use_ai=False)
    ET.fromstring(result.artifacts["model.urdf"])
    validate_generated_python(result.artifacts["brain_train.py"])
    compile(result.artifacts["brain_train.py"], "brain_train.py", "exec")
    physics = run_physics_rollout(result.spec, max_steps=args.physics_steps)
    output_dir = Path("/output")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, content in result.artifacts.items():
        target = output_dir / name
        target.write_text(content, encoding="utf-8")
    report = {
        "status": "validated",
        "experiment": result.spec.name,
        "links": len(result.spec.links),
        "joints": len(result.spec.joints),
        "artifacts": result.artifact_sha256,
        "network_policy": "none",
        "hardware_policy": "no devices mounted",
        "physics_execution": physics.to_dict(),
    }
    (output_dir / "sandbox-report.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
