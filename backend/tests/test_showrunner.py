import json

from app.agents.persona import HistoryEntry
from app.agents.showrunner import Showrunner, TopicProgress
from app.llm import LLMClient, LLMError, LLMResponse, MockLLMClient
from tests.test_persona import make_blocker


class _Judge(LLMClient):
    def __init__(self, **answer):
        self.answer = {"points_covered": [], "saturation": 0.3, "decision": "continue", "steer_hint": "", "new_angle": "", "next_speaker": "", "reason": "r"} | answer
        self.prompts = []

    async def generate(self, prompt, *, model, system_instruction="", response_schema=None, temperature=1.0):
        self.prompts.append(prompt)
        return LLMResponse(raw=json.dumps(self.answer), parsed=self.answer, model=model)


class _Down(LLMClient):
    async def generate(self, *a, **kw):
        raise LLMError("429 kuota habis")


def progress(turns, last=False, covered=()):
    t = make_blocker().topics[0]
    return TopicProgress(topic=t, is_last=last, turns=turns, covered=set(covered), history=[HistoryEntry("raka", "Raka", "halo")])


def sr(llm, policy="llm", **kw):
    return Showrunner(llm, "m", policy, every_k=3, min_turns=6, max_turns=40, **kw)


def test_call_schedule():
    s = sr(MockLLMClient())
    assert [t for t in range(1, 13) if s.should_call(progress(t))] == [3, 6, 9, 12]
    assert sr(MockLLMClient(), "fixed_turns", fixed_turns=8).should_call(progress(8))


async def test_no_transition_before_min_turns():
    d = await sr(_Judge(decision="transition", points_covered=["t1p1"])).decide(progress(3), turn=10)
    assert d.decision == "steer" and d.steer_hint.startswith("bahas t1p2")


async def test_transition_after_min_and_close_on_last_topic():
    assert (await sr(_Judge(decision="transition")).decide(progress(6), 1)).decision == "transition"
    assert (await sr(_Judge(decision="transition")).decide(progress(6, last=True), 1)).decision == "close"
    assert (await sr(_Judge(decision="close")).decide(progress(6), 1)).decision == "transition"


async def test_coverage_is_monotonic_and_filters_unknown_ids():
    p = progress(6, covered=["t1p1"])
    d = await sr(_Judge(points_covered=["t1p2", "t9p9"])).decide(p, 1)
    assert d.points_covered == ["t1p1", "t1p2"]


async def test_hard_limit_forces_transition_without_llm():
    llm = _Judge()
    d = await sr(llm).decide(progress(40), 1)
    assert d.forced and d.decision == "transition" and llm.prompts == []


async def test_coverage_only_policy():
    s = sr(_Judge(points_covered=["t1p1", "t1p2", "t1p3"], decision="continue"), "coverage_only")
    assert (await s.decide(progress(6), 1)).decision == "transition"
    s2 = sr(_Judge(points_covered=["t1p1"], decision="transition"), "coverage_only")
    d = await s2.decide(progress(9), 1)
    assert d.decision == "steer" and "t1p2" in d.steer_hint


async def test_llm_failure_falls_back_to_fixed_turns():
    d = await sr(_Down(), fixed_turns=6).decide(progress(6), 1)
    assert d.policy == "fixed_turns" and d.decision == "transition" and "LLM gagal" in d.reason


async def test_next_speaker_validated():
    assert (await sr(_Judge(next_speaker="Salsa")).decide(progress(3), 1)).next_speaker == "salsa"
    assert (await sr(_Judge(next_speaker="budi")).decide(progress(3), 1)).next_speaker is None


def budgeted(turns, elapsed, budget=300, covered=("t1p1", "t1p2", "t1p3"), last=False):
    p = progress(turns, last=last, covered=covered)
    p.budget_s, p.elapsed_s = budget, elapsed
    return p


async def test_budget_left_turns_transition_into_new_angle():
    p = budgeted(9, elapsed=120)
    d = await sr(_Judge(decision="transition", points_covered=["t1p1", "t1p2", "t1p3"], new_angle="kebiasaan unik penghuni kos")).decide(p, 1)
    assert d.decision == "steer" and d.steer_hint == "sudut baru: kebiasaan unik penghuni kos"
    assert p.angles == ["kebiasaan unik penghuni kos"] and "jatah topik tersisa" in d.reason
    assert "kebiasaan unik penghuni kos" in sr(_Judge()).judgement_prompt(p)  # tidak diulang


async def test_budget_left_with_uncovered_points_steers_to_point():
    d = await sr(_Judge(decision="transition", points_covered=["t1p1"])).decide(budgeted(9, 60, covered=["t1p1"]), 1)
    assert d.decision == "steer" and d.steer_hint.startswith("bahas t1p2")


async def test_budget_spent_moves_on_once_coverage_is_enough():
    d = await sr(_Judge(decision="steer", steer_hint="lanjut")).decide(budgeted(12, elapsed=310), 1)
    assert d.decision == "transition" and "jatah waktu topik habis" in d.reason
    d_last = await sr(_Judge(decision="continue")).decide(budgeted(12, elapsed=310, last=True), 1)
    assert d_last.decision == "close"
    low = await sr(_Judge(decision="steer", steer_hint="x")).decide(budgeted(12, elapsed=310, covered=["t1p1"]), 1)
    assert low.decision == "steer"  # cakupan <60%: tetap bahas poin


async def test_budget_rule_only_for_llm_policy():
    d = await sr(_Judge(points_covered=["t1p1", "t1p2", "t1p3"]), "coverage_only").decide(budgeted(9, elapsed=10), 1)
    assert d.decision == "transition"



async def test_fallback_respects_topic_budget():
    s = sr(_Down(), fixed_turns=6)
    early = await s.decide(budgeted(26, elapsed=200), 1)
    assert early.decision == "continue" and early.policy == "budget" and "tersisa" in early.reason
    late = await s.decide(budgeted(26, elapsed=400), 1)
    assert late.decision == "transition" and "habis" in late.reason
    assert s.fallback_decision(budgeted(26, elapsed=200), 1, "timeout").decision == "continue"
