"""Tabel ucapan untuk deteksi niat pindah topik (mode A). Salah pindah lebih buruk daripada terlewat."""

import pytest

from app.show.intent import detect_topic_switch

NEXT = "Dompet tipis anak zodiak boros"
TRANS = "Kalau urusan hati udah, sekarang kita intip urusan dompet mereka."


@pytest.mark.parametrize(
    "text,rule",
    [
        ("oke kita lanjut ke topik berikutnya ya", "frasa"),
        ("yuk pindah ke topik selanjutnya", "frasa"),
        ("sekarang kita masuk ke bahasan berikutnya", "frasa"),
        ("kita ke obrolan selanjutnya aja", "frasa"),
        ("oke next topik", "frasa"),
        ("kalau urusan hati udah sekarang kita intip urusan dompet mereka", "transisi"),
        ("nah sekarang kita ngomongin dompet tipis anak zodiak yang boros", "judul"),
        ("yuk kita bahas anak zodiak boros yang dompetnya tipis", "judul"),
        ("ayo pindah ke topik berikutnya", "frasa"),
    ],
)
def test_switch_detected(text, rule):
    assert detect_topic_switch(text, segment="topic", next_title=NEXT, transition=TRANS) == rule


@pytest.mark.parametrize(
    "text",
    [
        "lanjut cerita dong Sal",
        "oke lanjut",
        "next",
        "topik ini seru banget sih",
        "gue mau pindah kos bulan depan",
        "menurut lo topik selanjutnya bakal seru nggak",  # tanpa kata kerja pindah
        "dompet gue tipis banget akhir bulan",  # judul hanya sebagian, tanpa ajakan pindah
        "hati gue sih udah capek",
        "eh masuk akal juga ya",
        "gue sih sekarang ngerasa urusan hati itu ribet banget",
        "lo juga gitu kan, urusan hati sekarang bikin pusing",
        "lo mau lanjut ke bahasan lain nggak Sal?",
        "gue ke obrolan baru banget deh minggu ini",
        "eh lanjut dong, zodiak yang boros dompet tipis itu gimana sih",
    ],
)
def test_ordinary_talk_is_not_a_switch(text):
    assert detect_topic_switch(text, segment="topic", next_title=NEXT, transition=TRANS) is None


def test_closing_only_when_next_step_is_closing():
    said = "oke saatnya kita rangkum obrolan hari ini"
    assert detect_topic_switch(said, segment="topic", next_title=None, transition="", next_is_closing=True) == "penutup"
    assert detect_topic_switch(said, segment="topic", next_title=NEXT, transition=TRANS) is None


def test_opening_start_and_closing_has_no_next():
    assert detect_topic_switch("yuk kita mulai topik pertama", segment="opening", next_title="First date gagal") == "mulai"
    assert detect_topic_switch("kita lanjut ke topik berikutnya", segment="closing", next_title=None) is None
