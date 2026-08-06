"""
Tests for the centralized Ollama Manager (nlu/ollama_manager.py).

Works without a running Ollama server — all HTTP interactions are mocked.
Tests: availability detection, model listing, per-feature config, generate(),
chat(), and to_status_dict() serialization.
"""

from __future__ import annotations

import json
import io
import os
import urllib.error
import unittest
from unittest.mock import patch, MagicMock
from http.client import HTTPResponse
from io import BytesIO
from urllib.error import URLError

from roboweaver.nlu.ollama_manager import (
    OllamaManager,
    OllamaResponse,
    OllamaStatus,
    OllamaModel,
    DEFAULT_HOST,
    DEFAULT_MODEL,
)


class FakeHTTPResponse:
    """Minimal stand-in for urllib's response object."""
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class TestOllamaManagerAvailability(unittest.TestCase):
    """is_available() probes — must report honestly."""

    def test_unreachable_host_reports_unavailable(self):
        mgr = OllamaManager(host="http://localhost:1")
        self.assertFalse(mgr.is_available())

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_reachable_host_reports_available(self, mock_urlopen):
        mock_urlopen.return_value = FakeHTTPResponse(b'{"models":[]}', 200)
        mgr = OllamaManager(host="http://localhost:11434")
        self.assertTrue(mgr.is_available())


class TestOllamaManagerModels(unittest.TestCase):
    """Model listing and per-feature config."""

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_list_models_parses_response(self, mock_urlopen):
        body = json.dumps({
            "models": [
                {
                    "name": "llama3.1:8b",
                    "size": 4_500_000_000,
                    "digest": "abc123",
                    "modified_at": "2024-01-01",
                    "details": {"parameter_size": "8B", "quantization_level": "Q4_0"},
                },
                {
                    "name": "codellama:7b",
                    "size": 3_800_000_000,
                    "digest": "def456",
                    "modified_at": "2024-01-02",
                    "details": {"parameter_size": "7B", "quantization_level": "Q5_1"},
                },
            ]
        }).encode()
        mock_urlopen.return_value = FakeHTTPResponse(body)

        mgr = OllamaManager()
        models = mgr.list_models()
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].name, "llama3.1:8b")
        self.assertEqual(models[0].parameter_size, "8B")
        self.assertEqual(models[1].name, "codellama:7b")

    def test_model_for_feature_uses_default(self):
        mgr = OllamaManager(default_model="mistral:7b")
        self.assertEqual(mgr.model_for_feature("parser"), "mistral:7b")

    @patch.dict(os.environ, {"ROBOWEAVER_MODEL_EXPLAINER": "codellama:13b"})
    def test_model_for_feature_uses_env_override(self):
        mgr = OllamaManager()
        self.assertEqual(mgr.model_for_feature("explainer"), "codellama:13b")
        # Non-overridden feature still uses default
        self.assertEqual(mgr.model_for_feature("parser"), DEFAULT_MODEL)

    def test_runtime_feature_selection_and_recommendation(self):
        mgr = OllamaManager()
        mgr.set_model_for_feature("chat", "mistral:7b")
        self.assertEqual(mgr.model_for_feature("chat"), "mistral:7b")
        self.assertEqual(
            mgr.recommend_model("codegen", ["llama3.1:8b", "codellama:7b"]),
            "codellama:7b",
        )
        with self.assertRaises(ValueError):
            mgr.set_model_for_feature("unknown", "model")


class TestOllamaManagerGenerate(unittest.TestCase):
    """generate() and chat() — mock the HTTP layer."""

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_generate_success(self, mock_urlopen):
        body = json.dumps({
            "response": "The robot should pick the cube.",
            "eval_count": 42,
        }).encode()
        mock_urlopen.return_value = FakeHTTPResponse(body)

        mgr = OllamaManager(host="http://localhost:11434")
        resp = mgr.generate("What does this skill do?", feature="explainer")

        self.assertIsNotNone(resp.text)
        self.assertEqual(resp.text, "The robot should pick the cube.")
        self.assertEqual(resp.token_count, 42)
        self.assertIsNone(resp.error)
        self.assertGreater(resp.latency_s, 0)

    def test_generate_unreachable_returns_error(self):
        mgr = OllamaManager(host="http://localhost:1")
        resp = mgr.generate("test prompt")
        self.assertIsNone(resp.text)
        self.assertIsNotNone(resp.error)
        self.assertIn("unreachable", resp.error.lower())

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_generate_http_error_is_not_misreported_as_offline(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "http://localhost:11434/api/generate", 404, "Not Found", {},
            io.BytesIO(b'{"error":"model not found"}'),
        )
        resp = OllamaManager().generate("test")
        self.assertIsNone(resp.text)
        self.assertIn("HTTP 404", resp.error)
        self.assertIn("model not found", resp.error)
        self.assertNotIn("unreachable", resp.error.lower())

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_chat_success(self, mock_urlopen):
        body = json.dumps({
            "message": {"role": "assistant", "content": "I can help with that."},
            "eval_count": 15,
        }).encode()
        mock_urlopen.return_value = FakeHTTPResponse(body)

        mgr = OllamaManager()
        resp = mgr.chat([
            {"role": "user", "content": "What is RoboIR?"}
        ])
        self.assertEqual(resp.text, "I can help with that.")
        self.assertIsNone(resp.error)

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_generate_stream_yields_tokens_and_final_metadata(self, mock_urlopen):
        class StreamingResponse(FakeHTTPResponse):
            def __iter__(self):
                return iter([
                    b'{"response":"Hello ","done":false}\n',
                    b'{"response":"robot","done":true,"eval_count":2}\n',
                ])

        mock_urlopen.return_value = StreamingResponse(b"")
        mgr = OllamaManager()
        chunks = list(mgr.generate_stream("Say hello"))
        self.assertEqual("".join(c.text for c in chunks), "Hello robot")
        self.assertTrue(chunks[-1].done)
        self.assertEqual(chunks[-1].token_count, 2)
        self.assertEqual(mgr.total_calls, 1)


class TestOllamaManagerStatus(unittest.TestCase):
    """to_status_dict() serialization."""

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_status_dict_shape(self, mock_urlopen):
        tags_body = json.dumps({"models": [{"name": "llama3.1:8b", "size": 4500000000, "digest": "x", "details": {}}]}).encode()
        version_body = json.dumps({"version": "0.3.0"}).encode()

        def side_effect(url, *args, **kwargs):
            if "/api/version" in url:
                return FakeHTTPResponse(version_body)
            return FakeHTTPResponse(tags_body)

        mock_urlopen.side_effect = side_effect

        mgr = OllamaManager()
        status = mgr.to_status_dict()

        self.assertTrue(status["available"])
        self.assertEqual(status["version"], "0.3.0")
        self.assertIn("models", status)
        self.assertIn("feature_models", status)
        self.assertEqual(status["total_calls"], 0)
        self.assertIsNone(status["avg_latency_s"])


class TestOllamaManagerMetrics(unittest.TestCase):
    """Latency tracking."""

    @patch("roboweaver.nlu.ollama_manager.urllib.request.urlopen")
    def test_latency_tracked(self, mock_urlopen):
        body = json.dumps({"response": "ok"}).encode()
        mock_urlopen.return_value = FakeHTTPResponse(body)

        mgr = OllamaManager()
        mgr.generate("test")
        mgr.generate("test2")

        self.assertEqual(mgr.total_calls, 2)
        self.assertIsNotNone(mgr.avg_latency_s)
        self.assertGreater(mgr.avg_latency_s, 0)


if __name__ == "__main__":
    unittest.main()
