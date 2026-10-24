import asyncio
import json
import random

from app.agents.persona import HistoryEntry, PersonaResult
from app.agents.supervisor import Supervisor, fallback_bank, rule_violations, sanitize
from app.data.personas import load_personas
from app.llm import LLMClient, LLMResponse, MockLLMClient
from app.schemas import Emotion, PersonaOutput
from tests.test_persona import ctx

RAKA = load_personas()["raka"]


def result(text: str) -> PersonaResult:
    return PersonaResult(PersonaOutput(text=text, emotion=Emotion.HAPPY), raw=text, model="m", latency_ms=1, dialog_act=None, catchphrase=None)


def regen_with(*texts):
    queue = list(texts)
    calls = []

    async def regen(correction):
        calls.append(correction)
        return result(queue.pop(0))

    regen.calls = calls
    return regen


def sup(mode, llm=None, timeout_ms=5000):
    return Supervisor(llm or MockLLMClient(delay_sec=0), "m", mode, random.Random(0), timeout_ms=timeout_ms)


def test_sanitize_strips_markdown_emoji_and_stage_directions():
    text, hits = sanitize("**Wah** seru 😂 (tertawa) banget")
    assert text == "Wah seru banget"
    assert set(hits) == {"markdown", "emoji", "stage_direction"}


def test_rules_catch_banned_long_and_repeat():
    history = [HistoryEntry("salsa", "Salsa", "Oke lanjut.")]
    assert "banned:bangsat" in rule_violations("dasar bangsat lu", [])
    assert "too_long" in rule_violations("kata " * 100, [])
    assert "exact_repeat" in rule_violations("oke, lanjut!", history)
    assert rule_violations("Wah seru juga ya.", history) == []


async def test_off_forwards_raw_text():
    r = await sup("off").review(RAKA, result("**bangsat**"), ctx(), regen_with(), 1)
    assert r.text == "**bangsat**" and r.verdict.action == "forward"


async def test_rules_mode_sanitizes_and_forwards_without_llm():
    llm = MockLLMClient(delay_sec=0)
    r = await sup("rules", llm).review(RAKA, result("*Seru* banget 😂"), ctx(), regen_with(), 1)
    assert r.text == "Seru banget" and r.verdict.action == "forward" and llm.calls == 0


async def test_rules_violation_regenerates_with_correction():
    regen = regen_with("Wah seru juga ya.")
    r = await sup("rules").review(RAKA, result("dasar bangsat"), ctx(), regen, 1)
    assert r.verdict.action == "regenerate" and r.text == "Wah seru juga ya."
    assert "banned:bangsat" in regen.calls[0].persona_reminder


async def test_failed_regeneration_uses_fallback_bank():
    r = await sup("rules").review(RAKA, result("dasar bangsat"), ctx(), regen_with("tetap bangsat"), 1)
    assert r.verdict.action == "fallback" and r.text in fallback_bank()["raka"]
    assert r.verdict.regenerations == 1


async def test_full_mode_llm_violation_regenerates():
    regen = regen_with("Oke, balik ke topik ya.")
    r = await sup("full").review(RAKA, result("LANGGAR ini"), ctx(), regen, 1)
    assert r.verdict.checks["blocker"] == "violation" and r.verdict.action == "regenerate"
    assert regen.calls[0].persona_reminder == "jangan ulangi penanda uji"


class _ClaimJudge(LLMClient):
    def __init__(self, delay=0.0):
        self.delay = delay

    async def generate(self, prompt, *, model, system_instruction="", response_schema=None, temperature=1.0):
        await asyncio.sleep(self.delay)
        parsed = {"persona": "ok", "blocker": "ok", "safety": "ok", "evidence": "", "correction": "", "claims": ["Raka pernah ngekos di Dago"]}
        return LLMResponse(raw=json.dumps(parsed), parsed=parsed, model=model)


async def test_claims_go_to_ledger_and_next_prompt():
    s = sup("full", _ClaimJudge())
    await s.review(RAKA, result("Gue dulu ngekos di Dago."), ctx(), regen_with(), 4)
    assert s.ledger[0].claim == "Raka pernah ngekos di Dago" and s.ledger[0].turn == 4
    assert "Raka pernah ngekos di Dago (giliran 4)" in s.judgement_prompt(RAKA, "x", ctx())


async def test_first_check_timeout_forwards_and_flags():
    r = await sup("full", _ClaimJudge(delay=0.5), timeout_ms=50).review(RAKA, result("Seru *banget*"), ctx(), regen_with(), 1)
    assert r.verdict.timed_out and r.verdict.action == "forward" and r.text == "Seru banget"
