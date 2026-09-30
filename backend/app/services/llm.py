"""LLM provider abstraction.

LLMProvider
├── OpenAICompatibleProvider  (openai, deepseek, any OpenAI-compatible base_url)
└── MockProvider              (no network; callers fall back to extractive logic)

Callers must always handle `available == False` and `LLMError` — the product
degrades to extractive, retrieval-only answers rather than failing.
"""
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from contextvars import ContextVar
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger("ipsakti.llm")


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str = "base"
    available: bool = False
    last_latency_ms: int = 0
    last_usage: dict = {"prompt_tokens": 0, "completion_tokens": 0}

    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: Optional[int] = None) -> str:
        ...

    def complete_json(self, system: str, user: str, *, max_tokens: Optional[int] = None) -> Any:
        raw = self.complete(system, user, json_mode=True, max_tokens=max_tokens)
        return parse_json(raw)


def parse_json(raw: str) -> Any:
    raw = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fenced:
        raw = fenced.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = min([i for i in (raw.find("{"), raw.find("[")) if i >= 0], default=-1)
        if start >= 0:
            try:
                return json.loads(raw[start : raw.rfind("}" if raw[start] == "{" else "]") + 1])
            except json.JSONDecodeError:
                pass
    raise LLMError("The language model returned malformed JSON.")


class MockProvider(LLMProvider):
    name = "mock"
    available = False

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: Optional[int] = None) -> str:
        raise LLMError("No LLM configured (LLM_PROVIDER=mock).")


# OpenAI-compatible endpoints. Model names change over time — override with LLM_MODEL.
PRESET_URLS = {
    "deepseek": "https://api.deepseek.com",
    "grok": "https://api.x.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://localhost:11434/v1",
}
PROVIDERS = ("openai", *PRESET_URLS)
KEYLESS = ("ollama",)


class OpenAICompatibleProvider(LLMProvider):
    available = True

    def __init__(self, provider: str, api_key: str, model: str, base_url: Optional[str]):
        from openai import OpenAI

        if not base_url:
            base_url = PRESET_URLS.get(provider)
        self.name = f"{provider}:{model}"
        self._model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=settings.LLM_TIMEOUT_SECONDS)

    def complete(self, system: str, user: str, *, json_mode: bool = False, max_tokens: Optional[int] = None) -> str:
        started = time.monotonic()
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        def call(extra: dict):
            return self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
                **extra,
            )

        try:
            try:
                resp = call(kwargs)
            except Exception as exc:
                # Some OpenAI-compatible providers/models reject response_format; retry once without it.
                if kwargs and getattr(exc, "status_code", None) == 400:
                    resp = call({})
                else:
                    raise
        except Exception as exc:  # network, auth, quota, timeout
            logger.warning("LLM call failed provider=%s error=%s", self.name, type(exc).__name__)
            raise LLMError(f"LLM provider error: {type(exc).__name__}") from exc
        finally:
            self.last_latency_ms = int((time.monotonic() - started) * 1000)
        u = getattr(resp, "usage", None)
        self.last_usage = {
            "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
        }
        meter = current_meter.get()
        if meter is not None:
            meter.add(self)
        return resp.choices[0].message.content or ""


class UsageMeter:
    """Accumulates token usage across the LLM calls made for one request."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0

    def add(self, llm: LLMProvider) -> None:
        self.prompt_tokens += llm.last_usage.get("prompt_tokens", 0)
        self.completion_tokens += llm.last_usage.get("completion_tokens", 0)
        self.calls += 1

    def to_dict(self) -> dict:
        cost = (self.prompt_tokens * settings.LLM_PRICE_INPUT_PER_M + self.completion_tokens * settings.LLM_PRICE_OUTPUT_PER_M) / 1_000_000
        return {"calls": self.calls, "prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens,
                "estimated_cost_usd": round(cost, 6)}


current_meter: ContextVar[Optional["UsageMeter"]] = ContextVar("llm_usage_meter", default=None)


DATA_HANDLING = {
    "mock": "No language model is called. Nothing leaves this server.",
    "openai": "Question text and the retrieved source passages (plus a short innovation summary when an innovation is selected) "
              "are sent to the OpenAI API. Per OpenAI's API data-usage policy, API data is not used for training by default "
              "and may be retained up to 30 days for abuse monitoring. Verify the current policy before production use.",
    "ollama": "Runs locally on this machine via Ollama. Questions, passages and innovation details never leave the server — "
              "the recommended option for confidential formulations.",
    "gemini": "Question text and retrieved passages are sent to the Google Gemini API. On the free tier Google may use prompts "
              "and responses to improve its products — do not send confidential formulations on the free tier.",
    "groq": "Question text and retrieved passages are sent to the Groq API (hosted open models). Review Groq's data policy "
            "before sending confidential formulations.",
    "grok": "Question text and the retrieved source passages (plus a short innovation summary when an innovation is selected) "
            "are sent to the xAI API (Grok). Review xAI's current API data-usage and retention policy before sending confidential "
            "formulations; switch to a self-hosted model via LLM_BASE_URL if required.",
    "deepseek": "Question text and the retrieved source passages (plus a short innovation summary when an innovation is selected) "
                "are sent to the DeepSeek API (servers operated by DeepSeek). Review DeepSeek's current privacy policy and data "
                "location before sending confidential formulations; switch to a self-hosted model via LLM_BASE_URL if required.",
}


def data_handling() -> dict:
    p = settings.LLM_PROVIDER.lower() if get_llm().available else "mock"
    return {"provider": get_llm().name, "policy": DATA_HANDLING.get(p, DATA_HANDLING["openai"]),
            "self_hosted_option": "Any OpenAI-compatible server (vLLM, Ollama, LM Studio) can be used via LLM_BASE_URL."}


_provider: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    global _provider
    if _provider is None:
        p = settings.LLM_PROVIDER.lower()
        if p in PROVIDERS and (settings.LLM_API_KEY or p in KEYLESS):
            _provider = OpenAICompatibleProvider(p, settings.LLM_API_KEY or "local", settings.llm_model, settings.LLM_BASE_URL)
        else:
            _provider = MockProvider()
        logger.info("LLM provider: %s", _provider.name)
    return _provider


def llm_health() -> dict:
    llm = get_llm()
    if not llm.available:
        detail = "No API key configured; answers are extractive."
        if settings.LLM_PROVIDER.lower() in PROVIDERS:
            detail = f"LLM_PROVIDER={settings.LLM_PROVIDER} but LLM_API_KEY is empty; answers are extractive."
        return {"llm": "mock", "mode": "extractive", "detail": detail}
    try:
        llm.complete("Reply with the single word: ok", "ping", max_tokens=3)
        return {"llm": "ok", "provider": llm.name, "latency_ms": llm.last_latency_ms}
    except LLMError as exc:
        return {"llm": "error", "provider": llm.name, "detail": str(exc)}
