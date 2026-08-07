from datetime import datetime, timedelta, timezone

import pytest

from roboweaver.compiler import SkillCompiler
from roboweaver.perception import PerceptionError, PoseObservation, StaticObservationProvider


def observation(**changes):
    values = {
        "object_id": "red_cube",
        "object_class": "cube",
        "position_m": (0.32, 0.02, 0.15),
        "frame_id": "robot_base",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.96,
        "provider_id": "camera_detector_1",
        "calibration_id": "calibration_2026_08",
    }
    values.update(changes)
    return PoseObservation(**values)


def test_measured_pose_provenance_reaches_roboir_and_removes_missing_perception_warning():
    provider = StaticObservationProvider([observation()])
    result = SkillCompiler("franka_panda", perception_provider=provider).compile_with_diagnostics(
        "Pick up the red cube", verbose=False,
    )
    obj = result.ir.objects[0]
    assert obj.pose_source == "perception"
    assert obj.observation["provider_id"] == "camera_detector_1"
    assert obj.observation["calibration_id"] == "calibration_2026_08"
    assert not any(item.code == "RW201" for item in result.diagnostics)


@pytest.mark.parametrize(
    "item",
    [
        observation(confidence=0.5),
        observation(frame_id="camera_optical"),
        observation(observed_at=(datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()),
    ],
)
def test_perception_policy_rejects_untrusted_observations(item):
    with pytest.raises(PerceptionError):
        SkillCompiler(
            "franka_panda", perception_provider=StaticObservationProvider([item]),
        ).compile_portable("Pick up the red cube", verbose=False)
