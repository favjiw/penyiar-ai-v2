import json
import random

from app.agents.persona import HistoryEntry, PersonaAgent, TurnContext, repetition_triggered
from app.data.personas import load_personas
from app.llm import LLMClient, LLMResponse, MockLLMClient
from app.schemas import Blocker, BlockerClosing, BlockerOpening, BlockerPoint, BlockerTopic, CorrectionMemory


def make_blocker(n_topics: int = 2) -> Blocker:
    topics = [
        BlockerTopic(
            id=f"t{i}",
            judul=f"Topik {i}",
            sudut_pandang="sudut",
            poin=[BlockerPoint(id=f"t{i}p{j}", text=f"poin {i}.{j}") for j in range(1, 4)],
            pertanyaan_penonton="Kalau lo gimana?",
            transisi="Nah, lanjut ya.",
        )
        for i in range(1, n_topics + 1)
    ]
    return Blocker(
        id="blk_test",
        tema="Kopi",
        created_at="2026-10-24T10:00:00+07:00",
        variant_label="Kopi dan kampus",
        opening=BlockerOpening(hook="Sobat Hits, tim kopi mana?", poin=["sapa penonton"]),
        topics=topics,
        closing=BlockerClosing(rangkuman="kopi itu soal selera", ajakan="tulis kopi favorit lo"),
        locked=True,
    )


class _Echo(LLMClient):
    """Mengembalikan teks tetap; mencatat prompt yang diterima."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.prompts = []

    async def generate(self, prompt, *, model, system_instruction="", response_schema=None, temperature=1.0):
        self.prompts.append((system_instruction, prompt))
        parsed = {"text": self.texts.pop(0), "emotion": "happy"}
        return LLMResponse(raw=json.dumps(parsed), parsed=parsed, model=model)


def ctx(**kw) -> TurnContext:
    b = make_blocker()
    base = dict(blocker=b, segment="topic", topic=b.topics[0], uncovered_points=["poin 1.2"], history=[], partner_name="Salsa", turn_in_segment=1)
    base.update(kw)
    return TurnContext(**base)


async def test_prompt_contains_blocker_context_and_correction():
    raka = load_personas()["raka"]
    llm = _Echo(["Wah seru juga ya."])
    agent = PersonaAgent(llm, "m", random.Random(1))
    res = await agent.generate(raka, ctx(steer_hint="bahas poin 1.2"), CorrectionMemory(persona_reminder="Raka tim kopi hitam"))
    system, prompt = llm.prompts[0]
    assert "Kamu adalah Raka" in system and "kopi hitam" in system and "{name}" not in system
    assert 'Topik "Topik 1"' in prompt and "poin 1.2" in prompt
    assert "Arahan produser: bahas poin 1.2" in prompt
    assert "KOREKSI" in prompt and "Raka tim kopi hitam" in prompt
    assert res.output.text == "Wah seru juga ya."


async def test_opening_discloses_ai_and_transition_uses_blocker_bridge():
    agent = PersonaAgent(_Echo(["a b c d", "e f g h"]), "m", random.Random(1))
    raka = load_personas()["raka"]
    b = make_blocker()
    await agent.generate(raka, ctx(segment="opening", topic=None, turn_in_segment=0))
    await agent.generate(raka, ctx(transition_to=b.topics[1]))
    opening_prompt, transition_prompt = agent._llm.prompts[0][1], agent._llm.prompts[1][1]
    assert "penyiar AI" in opening_prompt
    assert '"Topik 2"' in transition_prompt and "Nah, lanjut ya." in transition_prompt


def test_repetition_guard_detects_same_opener():
    history = [HistoryEntry("salsa", "Salsa", "Wah seru banget itu, gue suka.")]
    assert repetition_triggered("Wah seru banget kalau gitu.", history)
    assert not repetition_triggered("Eh tapi gue beda pendapat nih.", history)


async def test_guard_regenerates_once():
    history = [HistoryEntry("salsa", "Salsa", "Wah seru banget itu.")]
    llm = _Echo(["Wah seru banget lagi.", "Eh beda dong."])
    res = await PersonaAgent(llm, "m", random.Random(1)).generate(load_personas()["raka"], ctx(history=history))
    assert res.guard_regenerations == 1 and res.output.text == "Eh beda dong."


async def test_mode_a_prompt_is_short_and_names_human():
    llm = _Echo(["Iya kak."])
    await PersonaAgent(llm, "m", random.Random(1)).generate(load_personas()["salsa"], ctx(mode="A", human_name="Amar"))
    assert "Amar penyiar manusia yang memandu" in llm.prompts[0][1] and "1 sampai 3 kalimat" in llm.prompts[0][1]


async def test_mock_persona_has_no_markdown():
    agent = PersonaAgent(MockLLMClient(delay_sec=0), "mock", random.Random(1))
    for _ in range(10):
        res = await agent.generate(load_personas()["salsa"], ctx())
        assert not any(ch in res.output.text for ch in "*#_`")
