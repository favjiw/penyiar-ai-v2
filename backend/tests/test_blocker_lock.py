import pytest

from app.blocker import BlockerInvalid, BlockerStore
from app.schemas import BlockerPoint
from tests.test_persona import make_blocker


@pytest.fixture
def draft(tmp_path):
    store = BlockerStore(tmp_path)
    b = make_blocker(2)
    b.locked = False
    return store, store.save(b)


def test_lock_accepts_three_to_five_points(draft):
    store, b = draft
    assert store.lock(b.id).locked


@pytest.mark.parametrize("count", [1, 2, 6])
def test_lock_rejects_points_out_of_range(draft, count):
    store, b = draft
    edited = b.model_copy(deep=True)
    edited.topics[1].poin = [BlockerPoint(text=f"poin {i}") for i in range(count)]
    store.update(b.id, edited)  # draf boleh belum rapi
    with pytest.raises(BlockerInvalid, match=rf"Topik 2.*{count} poin"):
        store.lock(b.id)
    assert not store.get(b.id).locked


def test_lock_rejects_empty_fields_and_lists_every_problem(draft):
    store, b = draft
    edited = b.model_copy(deep=True)
    edited.opening.hook = " "
    edited.topics[0].transisi = ""
    edited.closing.ajakan = ""
    store.update(b.id, edited)
    with pytest.raises(BlockerInvalid) as err:
        store.lock(b.id)
    msg = str(err.value)
    assert "hook kosong" in msg and "kalimat transisi kosong" in msg and "ajakan kosong" in msg
