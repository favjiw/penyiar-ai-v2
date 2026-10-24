from app.agents.hits_style import GREETING_HINT, OPENING_HINT, style_extras
from app.data.personas import load_personas


def test_personas_load_with_voices_and_assets():
    personas = load_personas()
    assert set(personas) == {"raka", "salsa"}
    assert personas["raka"].gender == "male" and personas["salsa"].gender == "female"
    for p in personas.values():
        assert p.voices["elevenlabs"] and p.voices["edge"].startswith("id-ID-")
        assert p.clips.endswith("manifest.json")
        assert not any("lagu" in d for d in p.do_not)


def test_style_extras_positions():
    assert OPENING_HINT in style_extras(0, closing=False)
    assert GREETING_HINT in style_extras(2, closing=False)
    assert style_extras(3, closing=False) == style_extras(1, closing=False)
