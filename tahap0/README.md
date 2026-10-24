# Tahap 0: Uji kelayakan

Skrip dan halaman uji untuk gerbang Tahap 0 (PRD §13). Hasil mentah ditulis ke `tahap0/out/` (tidak di-commit); ringkasan dan keputusan ditulis ke [`HASIL.md`](HASIL.md) lalu ke PRD §15.

## Persiapan

```bash
python -m venv .venv
.venv/Scripts/pip install -r tahap0/requirements.txt
cp .env.example .env   # isi GEMINI_API_KEY dan GEMINI_MODEL_TTS
```

## Checklist

| Uji | Alat | Status |
|---|---|---|
| Kuota free tier | `quota.md` + `quota_calc.py` | Sebagian: 500 RPD/model terukur dari 429 |
| TTS Gemini vs Edge vs ElevenLabs | `tts_bench.py`, `el_audition.py`, `audio_judge.py` | Selesai: suara disetujui Favian |
| STT Web Speech vs faster-whisper | `stt_webspeech.html`, `stt_bench.py` + `data/stt_sentences.txt` | Belum |
| Avatar T1 crossfade | `crossfade_test.html` | Belum |
| Avatar T2 RTF | `t2_rtf.py` | Belum |
| Keputusan gerbang | `HASIL.md` → PRD §15 | Belum |

## Menjalankan halaman uji

```bash
python -m http.server -d tahap0 8800
```

Lalu buka `http://localhost:8800/stt_webspeech.html` atau `http://localhost:8800/crossfade_test.html` di Chrome.
