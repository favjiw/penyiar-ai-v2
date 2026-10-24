# Tahap 0: Uji kelayakan

Skrip dan halaman uji untuk gerbang Tahap 0 (PRD §13). Hasil mentah ditulis ke `tahap0/out/` (tidak di-commit); ringkasan dan keputusan ditulis ke `tahap0/HASIL.md` lalu ke PRD §15.

## Persiapan

```bash
python -m venv .venv
.venv/Scripts/pip install -r tahap0/requirements.txt
cp .env.example .env   # isi GEMINI_API_KEY dan GEMINI_MODEL_TTS
```

## Checklist

| Uji | Alat | Status |
|---|---|---|
| Kuota free tier | `quota.md` + `quota_calc.py` | Belum |
| TTS Gemini vs Edge | `tts_bench.py` + `data/tts_sentences.txt` | Belum |
| STT Web Speech vs faster-whisper | `stt_webspeech.html`, `stt_bench.py` + `data/stt_sentences.txt` | Belum |
| Avatar T1 crossfade | `crossfade_test.html` | Belum |
| Avatar T2 RTF | `t2_rtf.py` | Belum |
| Keputusan gerbang | `HASIL.md` → PRD §15 | Belum |
