"""Optional cascade-backed AI explanation of the real native MLIR/LLVM bridge
output. Strictly a read-only summarizer: it re-derives the exact deterministic
MLIR text `run_native_mlir` already hashed and describes the real recorded
evidence. It cannot alter compilation, cannot run without an explicit opt-in
query parameter, and is never required for a compile to succeed -- the same
"AI is an optional sidecar" boundary as every other RoboWeaver AI feature.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from roboweaver.ir.schema import RoboIR
from roboweaver.nlu.cascade import CascadeManager
from roboweaver.upstream.mlir_bridge import NativeMLIREvidence, emit_mlir

_SYSTEM_PROMPT = """You are a compiler engineer explaining real LLVM/MLIR bridge \
output to a robotics developer. You are given the exact recorded evidence from \
an actual mlir-opt invocation attempt (or its stated unavailable status) and the \
exact emitted RoboIR MLIR module text. In 3-5 plain-language sentences, explain \
what the module represents, what the canonicalize+CSE pipeline did or would do to \
it, and one concrete thing worth verifying. Describe only what is present in the \
supplied evidence and text -- never invent pass names, hardware, benchmarks, or a \
result that was not shown to you. If the tool status is unavailable, say so plainly \
instead of describing an execution that did not happen."""


@dataclass(frozen=True)
class MLIRExplanation:
    text: str | None
    provider: str
    model: str
    error: str | None
    cache_hit: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "error": self.error,
            "cache_hit": self.cache_hit,
        }


def explain_mlir(
    ir: RoboIR,
    evidence: NativeMLIREvidence,
    cascade: CascadeManager | None = None,
) -> MLIRExplanation:
    """Regenerate the exact deterministic MLIR text `evidence` was computed
    from (a pure function of `ir`, not a re-run of the optional mlir-opt
    subprocess) and ask the provider cascade to summarize the real evidence."""
    mlir_text = emit_mlir(ir)
    prompt = (
        f"Native tool status: {evidence.status}\n"
        f"Executable: {evidence.executable or 'none'}\n"
        f"Version: {evidence.version or 'none'}\n"
        f"Pass pipeline: {', '.join(evidence.pass_pipeline) or 'none'}\n"
        f"Detail: {evidence.detail or 'none'}\n\n"
        f"Emitted MLIR module:\n{mlir_text[:4000]}"
    )
    manager = cascade or CascadeManager()
    response = manager.generate(
        prompt=prompt, feature="mlir_explain", system=_SYSTEM_PROMPT, temperature=0.2,
    )
    return MLIRExplanation(
        text=response.text,
        provider=response.provider,
        model=response.model,
        error=response.error,
        cache_hit=response.cache_hit,
    )
