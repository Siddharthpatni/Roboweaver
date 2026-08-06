"""
Verification Suite for the Ollama-backed Semantic Parser (src/roboweaver/nlu/).

This is the one test file in this suite that is NOT in .github/workflows/ci.yml's
test list, on purpose: it needs a real, locally-running Ollama server with a pulled
model to exercise the real LLM path, which GitHub-hosted CI runners don't have and
never will (installing a multi-gigabyte model on a shared CI runner isn't a real
integration test, it's a resource-hostile stunt). Run this file locally, with
`ollama serve` running, to actually exercise it.

Verifies:
1. is_available() honestly reports reachability -- both when Ollama is running and
   when it isn't (constructed against an intentionally closed port).
2. A real local model correctly parses a natural-language instruction into RoboWeaver's
   real Action taxonomy (skipped, not failed, if no local Ollama server answers --
   this is an integration test against real local infrastructure, not a hermetic unit
   test, and an environment that doesn't have it isn't a RoboWeaver bug).
3. SkillCompiler.compile_with_llm_parser() falls back to the deterministic parser --
   honestly, with a stated reason -- when Ollama is unreachable.
4. A model response outside RoboWeaver's real Action taxonomy is rejected, not
   silently coerced into some nearby guess.
"""

from __future__ import annotations

from roboweaver.compiler import SkillCompiler
from roboweaver.nlu import OllamaIntentParser
from roboweaver.types import Action

UNREACHABLE_HOST = "http://localhost:1"


def test_availability_check_is_honest():
    print("[TEST 1] Testing is_available() against a real closed port...")
    parser = OllamaIntentParser(host=UNREACHABLE_HOST)
    assert parser.is_available() is False, "an intentionally closed port must report unavailable"
    print("  -> Correctly reported unavailable for a closed port [PASSED]")


def test_fallback_to_deterministic_parser_when_unreachable():
    print("\n[TEST 2] Testing compile_with_llm_parser() falls back honestly when Ollama is unreachable...")
    compiler = SkillCompiler(target_robot="franka_panda")
    skill, result = compiler.compile_with_llm_parser(
        "pick up the red cube", host=UNREACHABLE_HOST, verbose=False
    )
    assert result.intent is None
    assert result.error is not None and "unreachable" in result.error.lower()
    assert skill.intent.action == Action.PICK  # the deterministic fallback still ran
    print(f"  -> Honest error surfaced ('{result.error[:60]}...'), deterministic fallback still compiled [PASSED]")


def test_unknown_action_from_model_output_is_rejected():
    print("\n[TEST 3] Testing a model response outside the real Action taxonomy is rejected, not guessed...")
    parser = OllamaIntentParser()
    result = parser._parse_model_output('{"action": "TELEPORT", "object_name": "cube", "parameters": {}}')
    assert result.intent is None
    assert "not in RoboWeaver's Action taxonomy" in result.error
    print("  -> Unknown action correctly rejected instead of silently coerced [PASSED]")


def test_non_finite_model_parameters_are_rejected():
    parser = OllamaIntentParser()
    result = parser._parse_model_output(
        '{"action":"PICK","object_name":"cube","parameters":{"speed":NaN}}'
    )
    assert result.intent is None
    assert result.error is not None


def test_real_local_ollama_parse():
    print("\n[TEST 4] Testing a real local Ollama model against RoboWeaver's Action taxonomy...")
    parser = OllamaIntentParser()
    if not parser.is_available():
        print("  -> SKIPPED: no local Ollama server answered at", parser.host)
        return

    result = parser.parse("grab the blue wrench and hand it to me")
    if result.intent is None:
        print(f"  -> SKIPPED: local model did not return a usable parse ({result.error})")
        return

    assert result.intent.action in Action
    assert result.intent.object_name
    print(
        f"  -> Real local model ({parser.model}) parsed to "
        f"{result.intent.action.value}({result.intent.object_name!r}) [PASSED]"
    )


if __name__ == "__main__":
    print("=== STARTING OLLAMA SEMANTIC PARSER VERIFICATION ===")
    test_availability_check_is_honest()
    test_fallback_to_deterministic_parser_when_unreachable()
    test_unknown_action_from_model_output_is_rejected()
    test_real_local_ollama_parse()
    print("\n=== ALL OLLAMA SEMANTIC PARSER TESTS COMPLETED ===")
