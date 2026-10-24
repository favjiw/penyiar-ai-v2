from pydantic import BaseModel

from app.config import Settings
from app.llm import LLMResponse, MockLLMClient, RateLimiter, RateLimiterRegistry, create_llm_client, register_mock


class _Echo(BaseModel):
    text: str


async def test_mock_generic_response():
    client = MockLLMClient(delay_sec=0)
    resp = await client.generate("Halo", model="m")
    assert isinstance(resp, LLMResponse)
    assert resp.parsed["text"].startswith("[mock")
    assert resp.model == "m"


async def test_mock_uses_registered_responder():
    register_mock(_Echo, lambda prompt, n: {"text": f"{prompt}-{n}"})
    client = MockLLMClient(delay_sec=0)
    resp = await client.generate("x", model="m", response_schema=_Echo)
    assert resp.parsed == {"text": "x-1"}


async def test_rate_limiter_first_call_is_free():
    assert await RateLimiter(60, "t").acquire() == 0.0


def test_registry_keeps_strictest_limit_per_model():
    reg = RateLimiterRegistry(default_rpm=5)
    reg.set_limit("flash", 10)
    reg.set_limit("flash", 4)
    reg.set_limit("", 9)  # model kosong diabaikan
    assert reg.get("flash").rate == 4
    assert reg.get("other").rate == 5


def test_factory_returns_mock_in_mock_mode():
    assert isinstance(create_llm_client(Settings(LLM_MODE="mock", _env_file=None)), MockLLMClient)
