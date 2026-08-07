from __future__ import annotations
from unittest.mock import patch

import pytest

from roboweaver.codegen.ai_codegen import CodeReviewResult
from roboweaver.codegen.connection_gen import generate_connection_code


def test_connection_adapter_is_deterministic_and_keeps_endpoint_out_of_source():
    result = generate_connection_code(
        robot_id="ur5e",
        protocol="sim",
        uri="sim://192.168.10.20:30002",
    )
    assert result.filename == "connect_ur5e.py"
    assert "resolve_bridge_class" in result.code
    assert "send_trajectory" not in result.code
    assert "192.168.10.20" not in result.code
    assert result.environment == {"ROBOWEAVER_TARGET_URI": "sim://192.168.10.20:30002"}
    assert result.provider == "none"


@patch("roboweaver.codegen.connection_gen.AICodeReviewer.review_connection_python")
def test_openrouter_review_is_additive_and_never_replaces_source(mock_review):
    mock_review.return_value = CodeReviewResult(
        original_code="source",
        annotated_code="# cloud review\nsource",
        issues=["Confirm endpoint identity"],
        model="example/coder:free",
    )
    result = generate_connection_code(
        robot_id="franka_panda",
        protocol="ros2",
        uri="ros2://robot-controller.local",
        provider="openrouter",
        ai_review=True,
    )
    assert result.code.startswith("#!/usr/bin/env python3")
    assert result.annotated_code == "# cloud review\nsource"
    assert result.issues == ["Confirm endpoint identity"]
    assert result.provider == "openrouter"
    assert "robot-controller.local" not in mock_review.call_args.args[0]


@pytest.mark.parametrize(
    ("robot_id", "protocol", "uri"),
    [
        ("invented_robot", "sim", "sim://localhost:1234"),
        ("ur5e", "telnet", "telnet://localhost:23"),
        ("ur5e", "sim", "file:///tmp/socket"),
        ("ur5e", "ros2", "ros2://user:password@localhost"),
    ],
)


def test_connection_adapter_rejects_untrusted_inputs(robot_id, protocol, uri):
    with pytest.raises(ValueError):
        generate_connection_code(robot_id, protocol, uri)
