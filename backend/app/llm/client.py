"""Klien LLM: Gemini (live) dan Mock (LLM_MODE=mock).

Semua panggilan LLM lewat antarmuka ini sehingga beralih antara API dan mock
cukup lewat config. Diadaptasi dari repo lama (conversational-ai@v1-format-clock):
- structured output dari model Pydantic;
- rate limit per model dan backoff eksponensial pada 429/503;
- mock memakai responder per skema yang didaftarkan modul pemakainya,
  sehingga client tidak perlu tahu skema setiap agen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Type

from pydantic import BaseModel

from app.llm.rate_limiter import RateLimiterRegistry

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    raw: str = ""
    parsed: Any = field(default_factory=dict)
    model: str = ""
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    parse_error: str = ""


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        system_instruction: str = "",
        response_schema: Type[BaseModel] | None = None,
        temperature: float = 1.0,
    ) -> LLMResponse: ...


# ── Mock ─────────────────────────────────────────────────────────────────────

MockResponder = Callable[[str, int], Any]
_MOCK_RESPONDERS: dict[Type[BaseModel], MockResponder] = {}


def register_mock(schema: Type[BaseModel], responder: MockResponder) -> None:
    """Daftarkan jawaban mock untuk satu skema: responder(prompt, nomor_panggilan) -> dict."""
    _MOCK_RESPONDERS[schema] = responder


class MockLLMClient(LLMClient):
    """Deterministik, tanpa jaringan dan tanpa kuota."""

    def __init__(self, delay_sec: float = 0.05):
        self._delay = delay_sec
        self.calls = 0

    async def generate(self, prompt, *, model, system_instruction="", response_schema=None, temperature=1.0):
        self.calls += 1
        start = time.perf_counter()
        await asyncio.sleep(self._delay)
        responder = _MOCK_RESPONDERS.get(response_schema) if response_schema else None
        parsed = responder(prompt, self.calls) if responder else {"text": f"[mock {self.calls}]"}
        raw = json.dumps(parsed, ensure_ascii=False)
        return LLMResponse(
            raw=raw,
            parsed=parsed,
            model=model or "mock",
            latency_ms=int((time.perf_counter() - start) * 1000),
            input_tokens=len(prompt.split()),
            output_tokens=len(raw.split()),
        )


# ── Gemini ───────────────────────────────────────────────────────────────────


class GeminiLLMClient(LLMClient):
    MAX_RETRIES = 4
    BASE_BACKOFF_SEC = 2.0

    def __init__(self, api_key: str, limiters: RateLimiterRegistry, fail_inject: bool = False):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.limiters = limiters
        self._fail_inject = fail_inject

    async def generate(self, prompt, *, model, system_instruction="", response_schema=None, temperature=1.0):
        from google.genai import types

        if self._fail_inject:
            raise LLMError("FAIL_INJECT=llm: galat LLM simulasi")
        if not model:
            raise LLMError("Model ID kosong; isi GEMINI_MODEL_* di .env")

        config: dict[str, Any] = {"temperature": temperature}
        if system_instruction:
            config["system_instruction"] = system_instruction
        if response_schema:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_schema

        last_error: Exception | None = None
        for attempt in range(self.MAX_RETRIES):
            await self.limiters.get(model).acquire()
            try:
                start = time.perf_counter()
                resp = await self._client.aio.models.generate_content(
                    model=model, contents=prompt, config=types.GenerateContentConfig(**config)
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
                raw = resp.text or ""
                parsed: Any = {}
                parse_error = ""
                if response_schema:
                    try:
                        parsed = response_schema.model_validate_json(raw).model_dump(mode="json")
                    except Exception as e:  # pemanggil yang memutuskan ulang atau galat
                        parse_error = str(e)[:500]
                usage = getattr(resp, "usage_metadata", None)
                return LLMResponse(
                    raw=raw,
                    parsed=parsed,
                    model=model,
                    latency_ms=latency_ms,
                    input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                    parse_error=parse_error,
                )
            except Exception as e:
                last_error = e
                retryable = any(c in str(e) for c in ("429", "500", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))
                if not retryable or attempt == self.MAX_RETRIES - 1:
                    break
                backoff = self.BASE_BACKOFF_SEC * (2**attempt)
                logger.warning("Gemini %s galat (percobaan %d), ulang dalam %.0fs: %s", model, attempt + 1, backoff, e)
                await asyncio.sleep(backoff)
        raise LLMError(f"Panggilan LLM gagal: {last_error}") from last_error


def create_llm_client(settings) -> LLMClient:
    if settings.LLM_MODE == "mock":
        return MockLLMClient()
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY wajib bila LLM_MODE=live")
    limiters = RateLimiterRegistry(default_rpm=settings.GEMINI_RPM_DEFAULT)
    for role in ("blocker", "persona", "supervisor", "showrunner"):
        limiters.set_limit(settings.model_for(role), settings.rpm_for(role))
    return GeminiLLMClient(settings.GEMINI_API_KEY, limiters, fail_inject="llm" in settings.FAIL_INJECT)
