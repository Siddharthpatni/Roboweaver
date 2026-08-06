"""
LLM-assisted connection advisor -- suggests how to bind a discovered network
endpoint to a real robot in ROBOT_REGISTRY.

Discovery can only ever say "port 30002 answered". Turning that into "this is a
UR arm, drive it with the ros2 bridge at ros2://192.168.1.40" is an inference,
and one an LLM is genuinely good at when given the real evidence (banner text,
reverse-DNS name, port, latency).

The advisor uses Ollama, hosted on an operator-controlled HTTP origin. Endpoint
facts such as IP addresses, banners, and hostnames are never routed through a
cloud-model API by RoboWeaver.

Whatever the provider, the model's answer is validated against the real registry
before it is returned: a hallucinated robot id or an unsupported protocol is
rejected with a stated reason rather than handed to the driver layer. The
advisor recommends -- it never opens a connection itself.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from roboweaver.hardware.registry_robots import ROBOT_REGISTRY
from roboweaver.json_utils import loads_strict
from roboweaver.nlu.ollama_manager import OllamaManager, get_manager

# The only protocols UniversalRobotDriver actually implements a bridge for.
# "sim" performs a genuine TCP reachability probe; "ros2" attempts a real
# rclpy/DDS connection. Anything else would silently fall through to ros2.
SUPPORTED_PROTOCOLS = ("ros2", "sim")

OLLAMA_DEFAULT_HOST = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "llama3.1:8b"

@dataclass
class ConnectionAdvice:
    """`robot_id` is None whenever the advice could not be trusted -- provider
    unreachable, malformed JSON, or a value outside the real registry. `error`
    always states which, so callers never mistake a failure for a suggestion."""

    robot_id: str | None
    protocol: str | None
    uri: str | None
    reasoning: str = ""
    confidence: float = 0.0
    provider: str = ""
    model: str = ""
    error: str | None = None
    raw_response: str = ""


def _build_prompt(endpoint: dict[str, Any]) -> str:
    """Only real, observed evidence goes into the prompt -- never a guess the
    model could then launder back to us as its own conclusion."""
    registry_ids = ", ".join(sorted(ROBOT_REGISTRY))
    banner = endpoint.get("banner") or "(the service sent no banner)"
    hostname = endpoint.get("hostname") or "(no reverse-DNS name)"

    return f"""You are helping bind a discovered network endpoint to a robot driver.

Observed evidence (all of it measured, none assumed):
- host: {endpoint.get('host')}
- port: {endpoint.get('port')}
- reverse-DNS hostname: {hostname}
- TCP banner: {banner}
- port-convention guess: {endpoint.get('robot_type_guess') or 'unknown'}
- connect latency: {endpoint.get('latency_ms')} ms

Choose the best matching robot id from EXACTLY this list:
{registry_ids}

Choose a protocol from EXACTLY this list: {', '.join(SUPPORTED_PROTOCOLS)}
  - "ros2" only if the evidence suggests a ROS 2 / DDS endpoint.
  - "sim" for a simulator or a raw TCP controller port.

Reply with ONLY JSON, no prose and no markdown fences:
{{"robot_id": "<id from the list>", "protocol": "<ros2|sim>", "confidence": <0.0-1.0>, "reasoning": "<one short sentence citing the evidence>"}}

If the evidence does not actually indicate a robot, set confidence below 0.3 and
say so in reasoning. Do not invent an id that is not in the list."""


def _coerce_json_text(raw: str) -> str:
    """Recover the JSON object from a model reply that wrapped it in prose.

    Smaller local models sometimes answer with ```json ... ``` fences or add a
    sentence either side. The payload is still usable once its JSON is isolated.
    """
    text = raw.strip()

    # Strip a leading ```json / ``` fence and its closing counterpart.
    fence = re.match(r"^```[a-zA-Z]*\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    if text.startswith("{"):
        return text

    # Otherwise take the outermost {...} span, if there is one.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


class _Backend:
    name = ""

    def complete(self, prompt: str) -> tuple[str, str | None]:
        """Return (raw_text, error). Exactly one is meaningful."""
        raise NotImplementedError


class OllamaBackend(_Backend):
    """Local, offline model. Nothing leaves the machine."""

    name = "ollama"

    def __init__(
        self, model: str | None = None, host: str | None = None,
        timeout: float = 30.0, manager: OllamaManager | None = None,
    ):
        self.timeout = timeout
        self.manager = manager or (
            OllamaManager(host=host, default_model=model) if host is not None else get_manager()
        )
        self.model = model or self.manager.model_for_feature("advisor")
        self.host = self.manager.host

    def complete(self, prompt: str) -> tuple[str, str | None]:
        response = self.manager.generate(
            prompt,
            feature="advisor",
            model=self.model,
            json_mode=True,
            timeout=self.timeout,
            temperature=0.0,
        )
        return response.text or "", response.error


class ConnectionAdvisor:
    """Recommends a driver binding for a discovered endpoint. Never connects."""

    def __init__(self, backend: _Backend | None = None):
        self.backend = backend or OllamaBackend()

    def advise(self, endpoint: dict[str, Any]) -> ConnectionAdvice:
        prompt = _build_prompt(endpoint)
        raw, error = self.backend.complete(prompt)

        model = getattr(self.backend, "model", "")
        if error:
            return ConnectionAdvice(
                robot_id=None, protocol=None, uri=None,
                provider=self.backend.name, model=model, error=error,
            )

        return self._validate(raw, endpoint, model)

    def _validate(self, raw: str, endpoint: dict[str, Any], model: str) -> ConnectionAdvice:
        """Reject anything the model invented. The registry and the protocol
        list are the authority here, not the model's output."""
        base = {"provider": self.backend.name, "model": model, "raw_response": raw or ""}

        if not isinstance(raw, str) or not raw.strip():
            return ConnectionAdvice(
                robot_id=None, protocol=None, uri=None,
                error="Provider returned an empty response.", **base,
            )

        try:
            parsed = loads_strict(_coerce_json_text(raw))
        except TypeError as exc:
            return ConnectionAdvice(
                robot_id=None, protocol=None, uri=None,
                error=f"Provider response was not decodable text: {exc}", **base,
            )
        except json.JSONDecodeError as exc:
            return ConnectionAdvice(
                robot_id=None, protocol=None, uri=None,
                error=f"Model output was not valid JSON: {exc}", **base,
            )

        robot_id = str(parsed.get("robot_id", "")).strip()
        if robot_id not in ROBOT_REGISTRY:
            return ConnectionAdvice(
                robot_id=None, protocol=None, uri=None,
                error=(
                    f"Model suggested robot_id '{robot_id}', which is not in ROBOT_REGISTRY. "
                    "Refusing to pass an unknown id to the driver layer."
                ),
                **base,
            )

        protocol = str(parsed.get("protocol", "")).strip().lower()
        if protocol not in SUPPORTED_PROTOCOLS:
            return ConnectionAdvice(
                robot_id=None, protocol=None, uri=None,
                error=(
                    f"Model suggested protocol '{protocol}', but only "
                    f"{SUPPORTED_PROTOCOLS} have real bridges implemented."
                ),
                **base,
            )

        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        host = endpoint.get("host", "localhost")
        port = endpoint.get("port")
        uri = f"{protocol}://{host}:{port}" if port else f"{protocol}://{host}"

        return ConnectionAdvice(
            robot_id=robot_id,
            protocol=protocol,
            uri=uri,
            reasoning=str(parsed.get("reasoning", "")).strip()[:400],
            confidence=confidence,
            **base,
        )


def build_advisor(provider: str, model: str | None = None) -> ConnectionAdvisor:
    """Build the local advisor and reject unsupported egress paths."""
    if provider != "ollama":
        raise ValueError("provider must be 'ollama'; cloud model providers are not supported")
    return ConnectionAdvisor(OllamaBackend(model=model))


def advisor_status() -> dict[str, Any]:
    """What is actually usable right now -- probed, not assumed."""
    ollama = OllamaBackend()
    ollama_up = ollama.manager.is_available(timeout=3.0)

    return {
        "ollama_available": ollama_up,
        "ollama_host": ollama.host,
        "ollama_model": ollama.model,
        "providers": ["ollama"],
        "supported_protocols": list(SUPPORTED_PROTOCOLS),
    }
