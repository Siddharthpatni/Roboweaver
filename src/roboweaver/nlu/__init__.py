"""Optional, additive Natural Language Understanding backends for Stage 04 (Task
Understanding). The deterministic keyword parser in compiler.py stays the default --
see ollama_parser.py's module docstring for why.

AI-powered modules (all fully offline, Ollama-backed, additive):
  * ollama_manager.py   — centralized client for all AI features
  * skill_explainer.py  — human-readable compilation explanations
  * skill_composer.py   — complex instruction decomposition
  * ollama_parser.py    — LLM-backed intent parser (existing)
  * connection_advisor.py — LLM-backed connection advisor (existing)
"""

from roboweaver.nlu.ollama_parser import OllamaIntentParser, OllamaParseResult, DEFAULT_HOST, DEFAULT_MODEL
from roboweaver.nlu.ollama_manager import (
    OllamaManager, OllamaResponse, OllamaStatus, OllamaStreamChunk, get_manager,
)
from roboweaver.nlu.skill_explainer import SkillExplainer, SkillExplanation
from roboweaver.nlu.skill_composer import SkillComposer, SkillComposition

__all__ = [
    "OllamaIntentParser", "OllamaParseResult", "DEFAULT_HOST", "DEFAULT_MODEL",
    "OllamaManager", "OllamaResponse", "OllamaStatus", "OllamaStreamChunk", "get_manager",
    "SkillExplainer", "SkillExplanation",
    "SkillComposer", "SkillComposition",
]
