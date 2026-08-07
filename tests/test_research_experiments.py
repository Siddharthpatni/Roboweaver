import json
from xml.etree import ElementTree as ET

import pytest

from roboweaver.research.experiments import (
    ExperimentPlanner,
    parse_experiment_spec,
    validate_generated_python,
)


def test_climbing_monkey_fallback_emits_valid_bounded_artifacts():
    result = ExperimentPlanner().plan("Make a climbing monkey robot", use_ai=False)

    assert result.spec.name == "climbing_monkey"
    assert len(result.spec.links) == 9
    assert len(result.spec.joints) == 8
    assert result.provider == "deterministic_fallback"
    assert result.safety["model_authored_code_executed"] is False
    assert result.sandbox["network"] == "none"
    ET.fromstring(result.artifacts["model.urdf"])
    validate_generated_python(result.artifacts["brain_train.py"])
    compile(result.artifacts["brain_train.py"], "brain_train.py", "exec")
    assert set(result.artifact_sha256) == {"experiment.json", "model.urdf", "brain_train.py"}


def test_experiment_schema_rejects_disconnected_or_unsafe_content():
    result = ExperimentPlanner().plan("generic research robot", use_ai=False)
    payload = json.loads(result.artifacts["experiment.json"])
    payload["links"].append({"name": "orphan", "shape": "box", "size_m": [0.1] * 3, "mass_kg": 1})
    with pytest.raises(ValueError, match="connected"):
        parse_experiment_spec(payload)

    with pytest.raises(ValueError, match="blocked"):
        validate_generated_python("import subprocess\nsubprocess.run(['whoami'])")
