import random

from app.data.personas import load_personas
from app.tts import FailoverTTS, MockTTSProvider
from app.tts.filler import FillerBank


async def test_prepare_and_pick_without_immediate_repeat(tmp_path):
    bank = FillerBank(FailoverTTS(MockTTSProvider(delay_sec=0)), tmp_path, random.Random(1))
    salsa = load_personas()["salsa"]
    n = await bank.prepare(salsa)
    assert 15 <= n <= 25
    picks = [bank.pick("salsa") for _ in range(20)]
    assert all(p.url.startswith("/audio/filler_salsa_") for p in picks)
    assert all(a.text != b.text for a, b in zip(picks, picks[1:]))
    assert (tmp_path / picks[0].url.split("/")[-1]).exists()
    assert bank.pick("raka") is None  # belum disiapkan


def test_every_persona_has_filler_phrases():
    phrases = FillerBank.phrases()
    for pid in load_personas():
        assert 15 <= len(phrases[pid]) <= 25
        assert all(len(p.split()) <= 6 for p in phrases[pid])
