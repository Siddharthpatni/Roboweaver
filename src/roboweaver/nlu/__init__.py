"""Optional, additive Natural Language Understanding backends for Stage 04 (Task
Understanding). The deterministic keyword parser in compiler.py stays the default --
see ollama_parser.py's module docstring for why."""

from roboweaver.nlu.ollama_parser import OllamaIntentParser, OllamaParseResult, DEFAULT_HOST, DEFAULT_MODEL

__all__ = ["OllamaIntentParser", "OllamaParseResult", "DEFAULT_HOST", "DEFAULT_MODEL"]
