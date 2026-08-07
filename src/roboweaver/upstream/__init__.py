"""Optional bridges to upstream compiler executables."""

from roboweaver.upstream.mlir_bridge import (
    MLIRBridgeError,
    NativeMLIREvidence,
    emit_mlir,
    native_mlir_tool_status,
    run_native_mlir,
)
from roboweaver.upstream.mlir_explainer import MLIRExplanation, explain_mlir

__all__ = [
    "MLIRBridgeError", "NativeMLIREvidence", "emit_mlir",
    "native_mlir_tool_status", "run_native_mlir",
    "MLIRExplanation", "explain_mlir",
]
