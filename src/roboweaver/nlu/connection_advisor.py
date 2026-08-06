"""
LLM-assisted connection advisor -- suggests how to bind a discovered network
endpoint to a real robot in ROBOT_REGISTRY.

Discovery can only ever say "port 30002 answered". Turning that into "this is a
UR arm, drive it with the ros2 bridge at ros2://192.168.1.40" is an inference,
and one an LLM is genuinely good at when given the real evidence (banner text,
reverse-DNS name, port, latency).

Two providers, both opt-in and never automatic:

  * OllamaBackend    -- a locally-hosted model. Fully offline, nothing leaves
                        the machine. This is the default and the one that
                        matches RoboWeaver's stated posture.
  * OpenRouterBackend -- a cloud API. Requires OPENROUTER_API_KEY in the backend
                        environment. Using it means sending the endpoint facts
                        (IP addresses, banners, hostnames of your network) to a
                        third party, so it is never selected implicitly.

Whatever the provider, the model's answer is validated against the real registry
before it is returned: a hallucinated robot id or an unsupported protocol is
rejected with a stated reason rather than handed to the driver layer. The
advisor recommends -- it never opens a connection itself.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# A no-cost model, so the default path costs nothing. OpenRouter's free lineup
# is churned regularly (the previous default here started returning 404), so if
# this id stops resolving, list the current ones with:
#   curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
#        https://openrouter.ai/api/v1/models | jq -r '.data[]|select(.pricing.prompt=="0").id'
OPENROUTER_DEFAULT_MODEL = "openai/gpt-oss-20b:free"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Cheapest model in the Claude family -- this advisor emits ~100 tokens of JSON,
# so there is no reason to pay for a larger one.
ANTHROPIC_DEFAULT_MODEL = "claude-haiku-4-5-20251001"

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

# Hard ceiling on generated tokens for every paid provider. The advisor's reply
# is a single small JSON object, so this caps the worst-case cost per call at a
# fraction of a cent and makes a runaway bill structurally impossible.
#
# Not smaller than this: reasoning-style models emit chain-of-thought *before*
# the answer and bill it as output. At 300 they hit the cap mid-thought and
# return finish_reason="length" with content=null -- an empty answer that still
# costs money. 800 leaves room for the reply to actually land.
MAX_OUTPUT_TOKENS = 800


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

    Providers without a native JSON mode (Anthropic has no `response_format`)
    routinely answer with ```json ... ``` fences, and some models add a
    sentence either side. The payload is still perfectly good -- discarding it
    over formatting would be throwing away a correct answer.
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


def _extract_chat_content(envelope: dict[str, Any], provider: str, model: str) -> tuple[str, str | None]:
    """Pull the assistant text out of an OpenAI-shaped chat response.

    `content` is not reliably a string: reasoning-style models routinely return
    it as null and put their output in `reasoning` instead, which crashed the
    JSON parse downstream. Anything that is not usable text becomes a stated
    error here rather than a None leaking into json.loads().
    """
    try:
        choice = envelope["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        return "", f"{provider} response had no message for model '{model}'."

    if choice.get("finish_reason") == "length" and not message.get("content"):
        return "", (
            f"{provider} model '{model}' hit the {MAX_OUTPUT_TOKENS}-token cap before "
            "producing an answer (it spent the budget on reasoning). Use a "
            "non-reasoning model such as openai/gpt-oss-20b:free."
        )

    content = message.get("content")
    if isinstance(content, list):
        # Some providers return content as a list of typed blocks.
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        # Reasoning models sometimes leave the answer only in `reasoning`.
        fallback = message.get("reasoning")
        if isinstance(fallback, str) and fallback.strip():
            return fallback, None
        return "", (
            f"{provider} model '{model}' returned no text content "
            "(likely a reasoning-only response). Try a different model."
        )
    return content, None


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


class OpenRouterBackend(_Backend):
    """Cloud API. Opt-in only.

    The key is read from the environment and never logged, echoed, or returned
    in any response. Note that using this sends the endpoint facts -- including
    internal IP addresses and service banners from your network -- to a third
    party.
    """

    name = "openrouter"

    def __init__(self, model: str = OPENROUTER_DEFAULT_MODEL, api_key: str | None = None, timeout: float = 45.0):
        self.model = model
        self.timeout = timeout
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str) -> tuple[str, str | None]:
        if not self._api_key:
            return "", (
                "OPENROUTER_API_KEY is not set in the backend environment. Export it "
                "for the dashboard process (never in frontend/.env -- Next.js inlines "
                "NEXT_PUBLIC_* variables into the browser bundle)."
            )

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": MAX_OUTPUT_TOKENS,
                # Keep the token budget for the answer rather than the
                # chain-of-thought; ignored by non-reasoning models.
                "reasoning": {"effort": "low"},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "HTTP-Referer": "https://github.com/roboweaver",
                "X-Title": "RoboWeaver",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                envelope = loads_strict(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Surface the status but never the request headers, which carry the key.
            return "", f"OpenRouter returned HTTP {exc.code} for model '{self.model}'."
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return "", f"OpenRouter unreachable: {exc}"
        except json.JSONDecodeError as exc:
            return "", f"OpenRouter's response envelope wasn't valid JSON: {exc}"

        return _extract_chat_content(envelope, "OpenRouter", self.model)


class AnthropicBackend(_Backend):
    """Anthropic Messages API. Opt-in, key from ANTHROPIC_API_KEY.

    Capped at MAX_OUTPUT_TOKENS; the advisor's reply is one small JSON object.
    """

    name = "anthropic"

    def __init__(self, model: str = ANTHROPIC_DEFAULT_MODEL, api_key: str | None = None, timeout: float = 45.0):
        self.model = model
        self.timeout = timeout
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str) -> tuple[str, str | None]:
        if not self._api_key:
            return "", "ANTHROPIC_API_KEY is not set in the backend environment."

        payload = json.dumps(
            {
                "model": self.model,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            ANTHROPIC_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                envelope = loads_strict(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return "", f"Anthropic API returned HTTP {exc.code} for model '{self.model}'."
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return "", f"Anthropic API unreachable: {exc}"
        except json.JSONDecodeError as exc:
            return "", f"Anthropic's response envelope wasn't valid JSON: {exc}"

        try:
            # content is a list of blocks; the text block holds the JSON reply.
            for block in envelope.get("content", []):
                if block.get("type") == "text":
                    return block.get("text", ""), None
            return "", "Anthropic response contained no text block."
        except (AttributeError, TypeError):
            return "", "Anthropic response had an unexpected shape."


class OpenAIBackend(_Backend):
    """OpenAI Chat Completions. Opt-in, key from OPENAI_API_KEY."""

    name = "openai"

    def __init__(self, model: str = OPENAI_DEFAULT_MODEL, api_key: str | None = None, timeout: float = 45.0):
        self.model = model
        self.timeout = timeout
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def complete(self, prompt: str) -> tuple[str, str | None]:
        if not self._api_key:
            return "", "OPENAI_API_KEY is not set in the backend environment."

        payload = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": MAX_OUTPUT_TOKENS,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            OPENAI_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # nosec B310
                envelope = loads_strict(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return "", f"OpenAI API returned HTTP {exc.code} for model '{self.model}'."
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return "", f"OpenAI API unreachable: {exc}"
        except json.JSONDecodeError as exc:
            return "", f"OpenAI's response envelope wasn't valid JSON: {exc}"

        return _extract_chat_content(envelope, "OpenAI", self.model)


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
    """Factory for the dashboard API.

    Defaults to Ollama: it is local, offline, and free, so it is the right
    choice unless a caller deliberately asks for a paid provider.
    """
    if provider == "openrouter":
        return ConnectionAdvisor(OpenRouterBackend(model=model or OPENROUTER_DEFAULT_MODEL))
    if provider == "anthropic":
        return ConnectionAdvisor(AnthropicBackend(model=model or ANTHROPIC_DEFAULT_MODEL))
    if provider == "openai":
        return ConnectionAdvisor(OpenAIBackend(model=model or OPENAI_DEFAULT_MODEL))
    return ConnectionAdvisor(OllamaBackend(model=model))


def advisor_status() -> dict[str, Any]:
    """What is actually usable right now -- probed, not assumed."""
    ollama = OllamaBackend()
    ollama_up = ollama.manager.is_available(timeout=3.0)

    return {
        "ollama_available": ollama_up,
        "ollama_host": ollama.host,
        "ollama_model": ollama.model,
        # Reports only whether a key is present -- never the key itself.
        "openrouter_configured": bool(os.environ.get("OPENROUTER_API_KEY")),
        "openrouter_model": OPENROUTER_DEFAULT_MODEL,
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "anthropic_model": ANTHROPIC_DEFAULT_MODEL,
        "openai_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "openai_model": OPENAI_DEFAULT_MODEL,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        # Ollama is local and free; the rest bill per call. The UI uses this to
        # mark paid providers so a click never costs money unexpectedly.
        "free_providers": ["ollama", "openrouter"],
        "supported_protocols": list(SUPPORTED_PROTOCOLS),
    }
