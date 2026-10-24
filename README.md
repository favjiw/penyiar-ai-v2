# penyiar-ai-v2

Penyiar AI co-host untuk live TikTok HITS Unikom Radio: obrolan ala podcast, mode manusia + AI (A) dan AI + AI (B).

Acuan tunggal kebutuhan, arsitektur, dan tahapan: [PRD.md](PRD.md). Status pengerjaan: PRD §16.

## Menjalankan

```bash
cp .env.example .env          # isi GEMINI_API_KEY, GEMINI_MODEL_BLOCKER, ELEVENLABS_API_KEY
pip install -r backend/requirements.txt
cd frontend && npm install
```

Backend (dari folder `backend/`):

```bash
python -m uvicorn app.main:app --port 8000
```

Frontend (dari folder `frontend/`), lalu buka http://localhost:5173:

```bash
npx vite --port 5173
```

Tanpa kuota API: set `LLM_MODE=mock` dan `TTS_MODE=mock` di `.env`. Konfigurasi preview Claude Code ada di `.claude/launch.json` (`backend`, `backend-mock`, `backend-edge`, `frontend`).

## Tes

```bash
cd backend && python -m pytest -q
cd frontend && npm run typecheck
```

## Isi repo

| Folder | Isi |
|---|---|
| `backend/app/` | FastAPI, config, skema, klien LLM, TTS, generator blocker, prompt (`prompts/*.md`), data persona |
| `backend/scripts/blocker_kt.py` | Uji kriteria terima FR-1 (10 tema) |
| `frontend/src/` | Konsol operator (React + Vite + TypeScript) |
| `tahap0/` | Alat dan hasil uji kelayakan Tahap 0 |
| `docs/` | Transkrip/analisis live HITS 20 Okt dan laporan KT |
