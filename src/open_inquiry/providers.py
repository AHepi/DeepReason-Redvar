"""Replaceable model transport and explicit token-accounting capabilities.

The controller owns permission to use an estimated route. Fixtures count UTF-8
bytes in canonical message JSON as synthetic units, never as production tokens.
Ollama has no preflight tokenizer here: its byte-based heuristic is only an
estimate and cannot enforce an exact input or financial ceiling.

Official adapter references checked 2026-09-07:
https://docs.ollama.com/api/chat
https://docs.ollama.com/api/usage
https://docs.ollama.com/api/authentication
https://docs.ollama.com/capabilities/thinking
https://docs.ollama.com/modelfile

prompt_eval_count is total input, including the prompt_eval_cached_count subset.
eval_count is the provider's aggregate generated-output observation. No separate
reasoning counter is documented; we do not invent one or add a text-derived
reasoning estimate. The endpoint/model still determines what it actually counts
and honours. Aggregate counters remain observations; unverified reasoning
inclusion keeps accounting_complete false and preserves the conservative ledger
charge. num_predict requests a generation limit; this adapter does not
certify every endpoint/model's enforcement or its internal reasoning accounting.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import os
import queue
import threading
import time
from typing import Protocol
from urllib import error, parse, request


class ProviderError(RuntimeError):
    """A transport failure with a credential-free, bounded public description."""


@dataclass
class ProviderResult:
    text: str
    usage: dict | None = None
    metadata: dict = field(default_factory=dict)


class Provider(Protocol):
    name: str
    count_kind: str

    def count(self, messages: list[dict]) -> int: ...

    def generate(self, messages: list[dict], *, max_tokens: int, timeout: float) -> ProviderResult: ...


def _serialise(messages: list[dict]) -> bytes:
    return json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _limits(max_tokens: int, timeout: float) -> None:
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ProviderError("max_tokens must be a positive integer")
    if type(timeout) not in {int, float} or not math.isfinite(timeout) or timeout <= 0:
        raise ProviderError("timeout must be a positive finite duration")


class ScriptedProvider:
    """A deterministic local fixture; supplied text is not a semantic classifier.

    Strings are bounded to max_tokens synthetic UTF-8 bytes. ProviderResult
    inputs retain their explicit usage, enabling missing-usage/overrun tests.
    Exhaustion is an explicit error, rather than an unrecorded repeated sample.
    """

    name = "scripted"
    count_kind = "fixture"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self._cursor = 0

    def count(self, messages: list[dict]) -> int:
        return len(_serialise(messages))

    def generate(self, messages: list[dict], *, max_tokens: int, timeout: float) -> ProviderResult:
        _limits(max_tokens, timeout)
        self.calls.append({"messages": deepcopy(messages), "max_tokens": max_tokens, "timeout": timeout})
        if self._cursor >= len(self.responses):
            raise ProviderError("scripted fixture has no remaining response")
        response = self.responses[self._cursor]
        self._cursor += 1
        if isinstance(response, Exception):
            raise ProviderError("scripted fixture simulated a provider failure") from None
        if isinstance(response, ProviderResult):
            return deepcopy(response)
        if not isinstance(response, str):
            raise ProviderError("scripted responses must be prose or ProviderResult values")
        text = response.encode("utf-8")[:max_tokens].decode("utf-8", errors="ignore")
        return ProviderResult(text, {
            "input_tokens": self.count(messages), "output_tokens": len(text.encode("utf-8")),
            "cached_input_tokens": 0, "reasoning_tokens": 0, "reasoning_included": True,
        }, {"provider": self.name, "count_kind": self.count_kind,
            "accounting": "fixture UTF-8 byte units; not production model tokens",
            "generation_truncated": text != response})


class DemoProvider(ScriptedProvider):
    """Unlimited deterministic fixture rounds for learning the CLI without keys."""

    name = "demo"

    def __init__(self):
        super().__init__([])

    def generate(self, messages: list[dict], *, max_tokens: int, timeout: float) -> ProviderResult:
        self.responses.append(
            f"Demo contribution {self._cursor + 1}. This is a local transport fixture. "
            "The current question remains open; inspect the supplied source passages and "
            "the assumptions connecting them before deciding what to examine next."
        )
        return super().generate(messages, max_tokens=max_tokens, timeout=timeout)


class _NoRedirect(request.HTTPRedirectHandler):
    """The operator selected one endpoint; redirect text cannot grant another."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Ollama endpoint redirected; choose the intended endpoint explicitly")


class OllamaProvider:
    """One non-streaming HTTP request per dispatch, with no automatic retry.

    Timeout bounds how long generate waits, not remote computation. A daemon
    worker may finish network cleanup afterward; a timed-out instance is retired
    so no later call can overlap that uncertain request through this instance.
    The ledger must settle any dispatched failure as unknown consumption.
    """

    name = "ollama"
    count_kind = "estimated"

    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 api_key_env: str = "OLLAMA_API_KEY", think=None, *,
                 context_window: int | None = None, max_response_bytes: int = 8 * 1024 * 1024):
        if not isinstance(model, str) or not model.strip():
            raise ProviderError("an Ollama model name is required")
        try:
            parsed = parse.urlsplit(base_url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and parsed.username is None and parsed.password is None
                     and not parsed.query and not parsed.fragment)
            parsed.port
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ProviderError("base_url must be an HTTP(S) endpoint without embedded credentials, query, or fragment")
        if think is not None and type(think) is not bool and not (
                isinstance(think, str) and think in {"low", "medium", "high", "max"}):
            raise ProviderError("think must be a supported boolean or level; check the selected model documentation")
        if context_window is not None and (type(context_window) is not int or context_window <= 0):
            raise ProviderError("context_window must be a positive integer")
        if type(max_response_bytes) is not int or max_response_bytes <= 0:
            raise ProviderError("max_response_bytes must be a positive integer")
        if not isinstance(api_key_env, str) or not api_key_env:
            raise ProviderError("api_key_env must name an environment variable")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.think = think
        self.context_window = context_window
        self.max_response_bytes = max_response_bytes
        self._parsed = parsed
        self._retired = False
        self._opener = request.build_opener(_NoRedirect())

    def count(self, messages: list[dict]) -> int:
        """Heuristic estimate, including serialised host message structure.

        Four bytes per estimated unit plus eight units per message and sixteen
        fixed units are implementation choices, with no conservativeness claim.
        Actual provider templates and model tokenisation are not visible here.
        """
        return (len(_serialise(messages)) + 3) // 4 + 8 * len(messages) + 16

    def _request(self, req: request.Request, timeout: float) -> bytes:
        deadline = time.monotonic() + timeout
        with self._opener.open(req, timeout=timeout) as response:
            chunks = []
            size = 0
            while True:
                if time.monotonic() >= deadline:
                    raise ProviderError("Ollama request timed out; consumption is unknown")
                read = getattr(response, "read1", response.read)
                chunk = read(min(65536, self.max_response_bytes + 1 - size))
                size += len(chunk)
                if size > self.max_response_bytes:
                    raise ProviderError("Ollama response exceeded the configured byte limit; consumption is unknown")
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)

    def generate(self, messages: list[dict], *, max_tokens: int, timeout: float) -> ProviderResult:
        _limits(max_tokens, timeout)
        if self._retired:
            raise ProviderError("this Ollama adapter was retired after an uncertain timeout; resume explicitly with a new adapter")
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "options": {"num_predict": max_tokens}}
        if self.think is not None:
            payload["think"] = self.think
        if self.context_window is not None:
            payload["options"]["num_ctx"] = self.context_window
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        key = os.environ.get(self.api_key_env)
        local = self._parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if key and not local:
            if self._parsed.scheme != "https":
                raise ProviderError("authenticated remote Ollama requests require HTTPS")
            if "\r" in key or "\n" in key:
                raise ProviderError("the Ollama API key environment variable has an invalid format")
            headers["Authorization"] = "Bearer " + key
        if self._parsed.hostname == "ollama.com" and not key:
            raise ProviderError("direct Ollama Cloud access requires the configured API key environment variable")
        endpoint = self.base_url + ("/chat" if self.base_url.endswith("/api") else "/api/chat")
        req = request.Request(endpoint, json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers, method="POST")
        results: queue.Queue = queue.Queue(maxsize=1)

        def perform():
            try:
                results.put((True, self._request(req, timeout)))
            except Exception as exc:
                # Never propagate provider bodies, exception strings, URLs or headers.
                if isinstance(exc, ProviderError):
                    safe_errors = {
                        "Ollama endpoint redirected; choose the intended endpoint explicitly",
                        "Ollama request timed out; consumption is unknown",
                        "Ollama response exceeded the configured byte limit; consumption is unknown",
                    }
                    public = str(exc) if str(exc) in safe_errors else "Ollama transport failed; consumption is unknown"
                elif isinstance(exc, error.HTTPError):
                    public = f"Ollama request failed with HTTP status {exc.code}; consumption is unknown"
                elif isinstance(exc, (TimeoutError, error.URLError)):
                    public = "Ollama connection failed or timed out; consumption is unknown"
                else:
                    public = "Ollama transport failed; consumption is unknown"
                results.put((False, public))

        threading.Thread(target=perform, daemon=True, name="open-inquiry-ollama").start()
        try:
            ok, outcome = results.get(timeout=timeout)
        except queue.Empty:
            self._retired = True
            raise ProviderError("Ollama request timed out; consumption is unknown") from None
        if not ok:
            raise ProviderError(outcome) from None
        try:
            response = json.loads(outcome)
            if not isinstance(response, dict) or response.get("error"):
                raise ValueError
            message = response["message"]
            text = message["content"]
            if not isinstance(text, str):
                raise ValueError
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ProviderError("Ollama returned an invalid chat response; consumption is unknown") from None

        def metric(key):
            value = response.get(key)
            return value if type(value) is int and value >= 0 else None

        usage = {"input_tokens": metric("prompt_eval_count"), "output_tokens": metric("eval_count"),
                 "cached_input_tokens": metric("prompt_eval_cached_count"),
                 "reasoning_tokens": None, "reasoning_included": None,
                 "accounting_complete": False}
        metadata = {
            "provider": self.name, "model": self.model, "count_kind": self.count_kind,
            "accounting": "provider prompt_eval_count plus aggregate eval_count; cached input is a subset",
            "reasoning_accounting": "no separate reasoning counter; endpoint/model inclusion is not independently verified",
            "accounting_uncertainty": "hidden-generation inclusion is unverified; retain conservative reservation charge",
            "thinking_retained": False, "thinking_present": bool(message.get("thinking")),
            "generation_limit_verified": False, "requested_options": payload["options"],
            "requested_think": self.think,
            "done": response.get("done") is True,
            "timing_nanoseconds": {name: metric(name) for name in (
                "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")},
        }
        if not metadata["done"]:
            # Partial counters do not prove that the remote request consumed no more.
            usage["output_tokens"] = None
            metadata["accounting_uncertainty"] = "response did not report completion"
        return ProviderResult(text, usage, metadata)
