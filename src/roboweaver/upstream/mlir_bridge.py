"""Native LLVM/MLIR bridge for RoboIR.

RoboWeaver owns its robotics dialect and textual exporter. When an upstream
``mlir-opt`` executable is available, this module executes canonicalization and
CSE against that emitted module and records reproducible evidence. It deliberately
does not claim to link LLVM libraries or produce machine code.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from roboweaver.ir.schema import RoboIR

_PASS_PIPELINE = ("canonicalize", "cse")
_CANDIDATES = (
    "mlir-opt", "mlir-opt-21", "mlir-opt-20", "mlir-opt-19", "mlir-opt-18",
    "mlir-opt-17", "mlir-opt-16",
)
_MAX_OUTPUT_BYTES = 512 * 1024


class MLIRBridgeError(RuntimeError):
    """Native MLIR was required but unavailable, invalid, or failed."""


@dataclass(frozen=True)
class NativeMLIREvidence:
    status: str
    executable: str | None
    version: str | None
    pass_pipeline: tuple[str, ...]
    input_sha256: str
    output_sha256: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "executable": self.executable,
            "version": self.version,
            "pass_pipeline": list(self.pass_pipeline),
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "detail": self.detail,
        }


def _mlir_string(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=True)


def emit_mlir(ir: RoboIR) -> str:
    """Serialize complete compiler evidence as a valid unregistered MLIR dialect."""

    lines = [
        "module {",
        "  \"roboweaver.skill\"() {"
        f"skill_id = {_mlir_string(ir.skill_id)}, action = {_mlir_string(ir.action)}, "
        f"ir_version = {_mlir_string(ir.ir_version)}}} : () -> ()",
    ]
    if ir.program is not None:
        for index, task in enumerate(ir.program.tasks):
            lines.append(
                "  \"roboweaver.task\"() {"
                f"index = {index} : i64, kind = {_mlir_string(task.type)}, "
                f"description = {_mlir_string(task.description)}}} : () -> ()"
            )
    if ir.lowering is not None:
        lines.append(
            "  \"roboweaver.target\"() {"
            f"robot = {_mlir_string(ir.lowering.robot_id)}, "
            f"motion_model = {_mlir_string(ir.lowering.motion_model)}}} : () -> ()"
        )
        for trajectory in ir.lowering.trajectories:
            lines.append(
                "  \"roboweaver.trajectory\"() {"
                f"task = {_mlir_string(trajectory.task_description)}, "
                f"duration_s = {trajectory.duration_s:.17g} : f64, "
                f"waypoints = {len(trajectory.waypoints)} : i64}} : () -> ()"
            )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _resolve_executable(configured: str | None) -> str | None:
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.is_absolute():
            return str(configured_path) if configured_path.is_file() else None
        return shutil.which(configured)
    return next((path for name in _CANDIDATES if (path := shutil.which(name))), None)


def _version(executable: str) -> str:
    try:
        process = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=5,
            check=False, env=_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    line = (process.stdout or process.stderr).splitlines()
    return line[0][:240] if line else "unknown"


def _subprocess_env() -> dict[str, str]:
    """Do not expose API tokens or unrelated process secrets to compiler tools."""

    return {
        key: value for key in ("PATH", "LANG", "LC_ALL")
        if (value := os.environ.get(key)) is not None
    }


def native_mlir_tool_status() -> dict[str, object]:
    """Return process-local availability without claiming a compile was executed."""

    mode = os.getenv("ROBOWEAVER_MLIR_MODE", "auto").strip().lower()
    executable = _resolve_executable(os.getenv("ROBOWEAVER_MLIR_OPT"))
    return {
        "mode": mode,
        "available": executable is not None,
        "executable": executable,
        "version": _version(executable) if executable else None,
    }


def run_native_mlir(ir: RoboIR, mode: str | None = None) -> NativeMLIREvidence:
    """Execute upstream ``mlir-opt`` in ``off``, ``auto`` or ``required`` mode."""

    selected_mode = (mode or os.getenv("ROBOWEAVER_MLIR_MODE", "auto")).strip().lower()
    if selected_mode not in {"off", "auto", "required"}:
        raise MLIRBridgeError("ROBOWEAVER_MLIR_MODE must be off, auto, or required")
    source = emit_mlir(ir)
    source_digest = hashlib.sha256(source.encode()).hexdigest()
    if selected_mode == "off":
        return NativeMLIREvidence(
            "disabled", None, None, _PASS_PIPELINE, source_digest,
            detail="Native MLIR execution was explicitly disabled.",
        )
    executable = _resolve_executable(os.getenv("ROBOWEAVER_MLIR_OPT"))
    if executable is None:
        if selected_mode == "required":
            raise MLIRBridgeError("mlir-opt is required but no supported executable was found")
        return NativeMLIREvidence(
            "unavailable", None, None, _PASS_PIPELINE, source_digest,
            detail="Install mlir-opt or set ROBOWEAVER_MLIR_OPT to enable native verification.",
        )
    try:
        process = subprocess.run(
            [
                executable,
                "--allow-unregistered-dialect",
                "--canonicalize",
                "--cse",
            ],
            input=source,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MLIRBridgeError(f"failed to execute mlir-opt: {exc}") from exc
    if process.returncode != 0:
        detail = process.stderr.strip()[:4000] or f"mlir-opt exited with {process.returncode}"
        raise MLIRBridgeError(detail)
    output = process.stdout.encode()
    if len(output) > _MAX_OUTPUT_BYTES:
        raise MLIRBridgeError("mlir-opt output exceeded the 512 KiB evidence bound")
    return NativeMLIREvidence(
        "succeeded",
        executable,
        _version(executable),
        _PASS_PIPELINE,
        source_digest,
        hashlib.sha256(output).hexdigest(),
        detail="Upstream mlir-opt accepted and transformed the emitted RoboWeaver dialect module.",
    )
