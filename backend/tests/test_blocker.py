import json

import pytest

from app.blocker import (
    BlockerGenerationError,
    BlockerGenerator,
    BlockerInvalid,
    BlockerLocked,
    BlockerStore,
)
from app.blocker.generator import _mock_drafts
from app.llm import LLMClient, LLMResponse, MockLLMClient
from app.schemas import BlockerPoint, GenerateBlockerRequest


class _Scripted(LLMClient):
    """Mengembalikan jawaban berurutan; dict = JSON valid, str = galat parsing."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def generate(self, prompt, *, model, system_instruction="", response_schema=None, temperature=1.0):
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, str):
            return LLMResponse(raw=answer, model=model, parse_error=answer)
        return LLMResponse(raw=json.dumps(answer), parsed=answer, model=model)


def _good(tema="Kopi", topik=3, varian=3):
    return _mock_drafts(f"TEMA: {tema}\nJUMLAH_TOPIK: {topik}\nJUMLAH_VARIAN: {varian}", 1)


@pytest.fixture
def store(tmp_path):
    return BlockerStore(tmp_path)


async def test_generate_mock_returns_distinct_valid_variants(store):
    gen = BlockerGenerator(MockLLMClient(delay_sec=0), "mock", store)
    blockers, meta = await gen.generate(GenerateBlockerRequest(tema="Zodiak", jumlah_topik=2, jumlah_varian=3))
    assert len(blockers) == 3
    assert len({b.variant_label for b in blockers}) == 3
    assert len({b.generation_id for b in blockers}) == 1
    b = blockers[0]
    assert [t.id for t in b.topics] == ["t1", "t2"]
    assert b.topics[1].poin[0].id == "t2p1"
    assert not b.locked and b.versi == 1 and b.id.startswith("blk_") and "zodiak" in b.id
    assert meta.prompt_version == "blocker-v3" and meta.attempts == 1
    assert store.get(b.id) == b


async def test_retry_once_after_parse_error_then_succeeds(store):
    llm = _Scripted("bukan json", _good())
    blockers, meta = await BlockerGenerator(llm, "m", store).generate(GenerateBlockerRequest(tema="Kopi"))
    assert meta.attempts == 2 and len(blockers) == 3
    assert "ditolak" in llm.prompts[1]


async def test_retries_up_to_twice_then_succeeds(store):
    llm = _Scripted("bukan json", _good(topik=1), _good())
    blockers, meta = await BlockerGenerator(llm, "m", store).generate(GenerateBlockerRequest(tema="Kopi"))
    assert meta.attempts == 3 and len(blockers) == 3 and not llm.answers
    assert "JSON tidak sesuai skema" in llm.prompts[1] and "diminta 3" in llm.prompts[2]  # tiap ulang memuat alasan penolakan terbaru
    assert meta.issues_first_attempt


async def test_fails_after_three_bad_answers(store):
    too_few_topics = _good(topik=1)
    llm = _Scripted(too_few_topics, too_few_topics, too_few_topics)
    with pytest.raises(BlockerGenerationError) as err:
        await BlockerGenerator(llm, "m", store).generate(GenerateBlockerRequest(tema="Kopi", jumlah_topik=3))
    assert any("diminta 3" in i for i in err.value.issues)
    assert "3 percobaan" in str(err.value) and not llm.answers  # tepat 3 panggilan, tidak lebih


async def test_duplicate_labels_rejected(store):
    dup = _good()
    for v in dup["variants"]:
        v["variant_label"] = "Sama"
    with pytest.raises(BlockerGenerationError):
        await BlockerGenerator(_Scripted(dup, dup, dup), "m", store).generate(GenerateBlockerRequest(tema="Kopi"))


async def test_extra_points_trimmed_and_digits_flagged(store):
    answer = _good(topik=1, varian=2)
    topic = answer["variants"][0]["topics"][0]
    topic["poin"] = [{"text": f"poin {chr(97 + i)}", "perlu_cek": False} for i in range(7)]
    topic["poin"][0]["text"] = "harga kopi naik 20 persen tahun ini"
    blockers, _ = await BlockerGenerator(_Scripted(answer), "m", store).generate(
        GenerateBlockerRequest(tema="Kopi", jumlah_topik=1, jumlah_varian=2)
    )
    poin = blockers[0].topics[0].poin
    assert len(poin) == 5
    assert poin[0].perlu_cek and not poin[1].perlu_cek


async def test_regenerate_variant_avoids_old_label(store):
    gen = BlockerGenerator(MockLLMClient(delay_sec=0), "mock", store)
    blockers, _ = await gen.generate(GenerateBlockerRequest(tema="Hujan", jumlah_topik=1, jumlah_varian=2))
    labels = [b.variant_label for b in blockers]
    new, _ = await gen.regenerate_variant(blockers[0].id, labels[1:])
    assert new.variant_label not in labels
    assert new.generation_id == blockers[0].generation_id and len(new.topics) == 1


async def test_edit_lock_and_new_version(store):
    gen = BlockerGenerator(MockLLMClient(delay_sec=0), "mock", store)
    (b, *_), _ = await gen.generate(GenerateBlockerRequest(tema="Kos-kosan", jumlah_topik=2, jumlah_varian=2))

    edited = b.model_copy(deep=True)
    edited.topics[0].poin.insert(0, BlockerPoint(text="poin baru tanpa id"))
    edited.topics.reverse()
    edited.locked = True  # klien tidak bisa mengunci lewat edit
    saved = store.update(b.id, edited)
    assert not saved.locked
    assert saved.topics[1].poin[0].text == "poin baru tanpa id" and saved.topics[1].poin[0].id == "t2p1"

    locked = store.lock(b.id)
    assert locked.locked
    with pytest.raises(BlockerLocked):
        store.update(b.id, locked)

    v2 = store.new_version(b.id)
    assert v2.versi == 2 and v2.parent_id == b.id and not v2.locked
    assert v2.topics == locked.topics


async def test_edit_rejects_empty_structure(store):
    gen = BlockerGenerator(MockLLMClient(delay_sec=0), "mock", store)
    (b, *_), _ = await gen.generate(GenerateBlockerRequest(tema="Mudik", jumlah_topik=1, jumlah_varian=2))
    empty = b.model_copy(deep=True)
    empty.topics = []
    with pytest.raises(BlockerInvalid):
        store.update(b.id, empty)
    with pytest.raises(BlockerInvalid):
        store.new_version(b.id)  # draf belum dikunci
