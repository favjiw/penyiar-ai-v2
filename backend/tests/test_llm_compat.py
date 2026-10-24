import json

import httpx
import pytest

from app.config import Settings
from app.llm import LLMError, RateLimiterRegistry, create_llm_client
from app.llm.client import OpenAICompatLLMClient, RouterLLMClient
from app.schemas import PersonaOutput


def compat(handler, **kw):
    c = OpenAICompatLLMClient("https://x.test/v1", "k", RateLimiterRegistry(600), transport=httpx.MockTransport(handler), **kw)
    c.BASE_BACKOFF_SEC = 0
    return c


def reply(content, cost=0.00001):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost}})


async def test_sends_schema_and_reasoning_and_parses_fenced_json():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(json.loads(req.content))
        seen["auth"] = req.headers["authorization"]
        return reply('```json\n{"text": "Halo Sobat Hits", "emotion": "happy"}\n```')

    c = compat(handler)
    r = await c.generate("p", model="gemini-3.8-flash", system_instruction="sys", response_schema=PersonaOutput, temperature=0.5)
    assert r.parsed == {"text": "Halo Sobat Hits", "emotion": "happy"} and r.model == "compat:gemini-3.8-flash"
    assert seen["auth"] == "Bearer k" and seen["reasoning_effort"] == "none"
    assert seen["response_format"]["json_schema"]["name"] == "PersonaOutput"
    assert seen["messages"][0] == {"role": "system", "content": "sys"}
    assert c.cost_usd == pytest.approx(0.00001)


async def test_retries_on_5xx_then_fails_on_4xx():
    calls = []

    def flaky(req):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else reply('{"text": "ok", "emotion": "neutral"}')

    assert (await compat(flaky).generate("p", model="m", response_schema=PersonaOutput)).parsed["text"] == "ok"

    def bad_request(req):
        return httpx.Response(400, json={"error": "nope"})

    with pytest.raises(LLMError):
        await compat(bad_request).generate("p", model="m")


async def test_router_dispatches_by_prefix():
    class Fake:
        def __init__(self, name):
            self.name, self.models = name, []

        async def generate(self, prompt, *, model, **kw):
            self.models.append(model)
            return self.name

    g, c = Fake("gemini"), Fake("compat")
    router = RouterLLMClient(g, c, RateLimiterRegistry())
    assert await router.generate("p", model="gemini-3.5-flash-lite") == "gemini"
    assert await router.generate("p", model="compat:gemini-3.8-flash") == "compat"
    assert c.models == ["gemini-3.8-flash"]
    with pytest.raises(LLMError):
        await RouterLLMClient(g, None, RateLimiterRegistry()).generate("p", model="compat:x")


def test_factory_builds_router_from_settings():
    s = Settings(LLM_MODE="live", OPENAI_COMPAT_BASE_URL="https://x.test/v1", OPENAI_COMPAT_API_KEY="k", _env_file=None)
    assert isinstance(create_llm_client(s), RouterLLMClient)
    with pytest.raises(ValueError):
        create_llm_client(Settings(LLM_MODE="live", _env_file=None))
