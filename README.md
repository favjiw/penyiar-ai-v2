# penyiar-ai-v2

Penyiar AI co-host untuk program HITS Unikom Radio: obrolan ala podcast (Opening, maksimal 3 topik, Closing) dengan mode manusia + AI (A) dan AI + AI (B). Fokus saat ini: kualitas percakapan; avatar, komentar, dan live TikTok ditunda (arsip: branch `archive/avatar-dan-komentar`).

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

Live mode B dari konsol: kunci blocker di tab **Blocker**, buka tab **Live**, klik **Cek pra-live**, lalu **Mulai mode B**. Pintasan: `P` pause/lanjut, `N` next topik, `S` stop. Audio diputar di tab konsol.

Mode A (penyiar + AI): di tab **Live** pilih *Mode A*, persona AI, dan nama penyiar, lalu **Mulai**. Penyiar memakai **Prompter** (`/prompter`, Chrome): tahan `Spasi` untuk bicara, `Esc` batal, `N` next topik.

Sesi tanpa browser (uji/eksperimen) dan ringkasannya:

```bash
cd backend
python scripts/run_show.py --tema "Kos-kosan" --topik 3        # real time, audio tidak diputar
python scripts/report.py logs/show_<id>.jsonl --transcript transkrip.md
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
| `backend/app/agents/` | Persona, Supervisor, Showrunner |
| `backend/app/show/` | Show Engine (mode B) dan API live + WebSocket |
| `backend/scripts/` | `blocker_kt.py` (KT FR-1), `run_show.py` (sesi headless), `report.py` (ringkasan log), `mode_a_probe.py` (latensi mode A) |
| `frontend/src/` | Konsol operator dan prompter penyiar (React + Vite + TypeScript) |
| `tahap0/` | Alat dan hasil uji kelayakan Tahap 0 |
| `docs/` | Transkrip/analisis live HITS 20 Okt dan laporan KT |
