"""Tests for the cascade-backed, read-only MLIR explanation (upstream/mlir_explainer.py).

Works without a running provider -- exercises the real cascade against a fake
manager, matching tests/test_model_cascade.py's pattern, rather than mocking a
single provider directly.
"""

from __future__ import annotations

from roboweaver.compiler import SkillCompiler
from roboweaver.nlu.cascade import CascadeCandidate, CascadeManager
from roboweaver.nlu.ollama_manager import OllamaResponse
from roboweaver.upstream import NativeMLIREvidence, run_native_mlir
from roboweaver.upstream.mlir_explainer import explain_mlir


class _FakeManager:
    def __init__(self, provider, response):
        self.provider = provider
        self.response = response
        self.prompts: list[str] = []

    def model_for_feature(self, feature):
        return f"{self.provider}-{feature}"

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.response


def _real_ir():
    return SkillCompiler("franka_panda").compile_with_diagnostics(
        "Pick up the cube", verbose=False,
    ).ir


def test_explain_mlir_summarizes_the_real_evidence_and_module_text():
    fake = _FakeManager("ollama", OllamaResponse(
        "The module represents a PICK skill for franka_panda.", None, "llama3.1:8b", 0.4,
    ))
    cascade = CascadeManager([CascadeCandidate(fake)])
    ir = _real_ir()
    evidence = run_native_mlir(ir)  # unavailable on a machine without mlir-opt

    result = explain_mlir(ir, evidence, cascade=cascade)

    assert result.text == "The module represents a PICK skill for franka_panda."
    assert result.provider == "ollama"
    assert result.error is None
    # The prompt must be grounded in the real evidence and real emitted text,
    # not a description the model has to invent.
    assert len(fake.prompts) == 1
    assert evidence.status in fake.prompts[0]
    assert '"roboweaver.skill"' in fake.prompts[0]


def test_explain_mlir_reports_provider_error_without_fabricating_text():
    fake = _FakeManager("ollama", OllamaResponse(None, "Ollama is not configured.", "llama3.1:8b", 0.0))
    cascade = CascadeManager([CascadeCandidate(fake)])
    ir = _real_ir()
    evidence = NativeMLIREvidence(
        status="unavailable", executable=None, version=None,
        pass_pipeline=("canonicalize", "cse"), input_sha256="a" * 64, detail="no mlir-opt found",
    )

    result = explain_mlir(ir, evidence, cascade=cascade)

    assert result.text is None
    assert result.error == "ollama: Ollama is not configured."
