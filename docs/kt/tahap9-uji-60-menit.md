# Uji siaran 60 menit (HANDOFF §3 langkah 10, PRD v2.7 Tahap 9)

Tanggal: 8 Nov 2026. Branch `feat/desain-ui-hits`.

## 1. Simulasi mock dipercepat (`backend/scripts/sim_60min.py`)

LLM dan TTS mock (TTS mock ±60 ms/karakter), tanpa kuota. Materi dibuat generator mock dengan `durasi_menit=60`
(6 topik × 9 menit). Dua seed (7, 11).

```
cd backend && LLM_MODE=mock TTS_MODE=mock .venv/bin/python scripts/sim_60min.py --seed 7 --json hasil.json
```

### Mode B (AI + AI)

| Kebijakan Showrunner | Menit audio | Giliran | Penutupan poin | Per topik | Opening / Closing | Galat |
|---|---|---|---|---|---|---|
| `fixed_turns` (hanya batas waktu) | 53,0 | 857 | 24× timer | 8,3–8,4 mnt (rencana 9) | 1,1 / 1,5 mnt | 0 |
| `llm` (Showrunner **mock**) | 6,1 | 100 | 24× early | 1,0 mnt | 0,1 / 0,1 mnt | 0 |

- Batas per poin dari menit topik bekerja: 9 mnt × 60 ÷ 4 poin = 135 dtk; poin ditutup sedikit sebelum batas
  (giliran penutup saat sisa ≤ `POINT_WRAP_S`), jadi topik ±8,4 mnt.
- Opening/Closing materi berdurasi kini diisi berbasis waktu (±3 menit audio, maks. 24 giliran). Di mock satu giliran
  hanya ±3,6 dtk sehingga batas 24 giliran tercapai lebih dulu (1,1–1,5 mnt). Dengan LLM nyata (±8 dtk audio per
  giliran, lihat §2) 24 giliran ≈ 3 menit. Dengan giliran nyata, total mode B diperkirakan mendekati 57–60 menit
  (topik ±50 mnt + Opening/Closing ±6 mnt) selama Showrunner tidak menutup poin terlalu dini.
- Showrunner mock **selalu** menilai obrolan jenuh, sehingga semua poin ditutup dini setelah `POINT_MIN_TURNS`.
  Ini artefak mock, bukan perilaku LLM; lihat §2.

### Mode A (penyiar + AI), jam tiruan

Penyiar skrip bicara terus sampai menit topik lewat dengan lewat waktu acak (0–200 dtk), lalu membaca kalimat pindah
topik dari materi (atau frasa eksplisit bila tidak terdeteksi).

| Seed | Menit siaran | Pertukaran | Pindah lewat ucapan | Kode halus | Galat |
|---|---|---|---|---|---|
| 7 | 79,1 | 615 | 7/7 (mulai, 5× frasa, penutup) | 6 (semua topik lewat ≥150 dtk) | 0 |
| 11 | 70,4 | 547 | 7/7 | 3 (tepat topik yang lewat ≥120 dtk) | 0 |

- Tidak ada pindah otomatis: topik hanya berganti lewat ucapan penyiar (diperiksa tiap topik di skrip).
- Kode halus muncul sekali per topik, saat lewat 122–129 dtk (ambang 120), tidak pada topik yang lewat <120 dtk.
- Total >60 menit karena penyiar skrip sengaja melewati waktu; ini menguji kode halus, bukan disiplin waktu.

## 2. Uji singkat LLM nyata, mode B (3 menit)

`scripts/run_show.py --tema "Zodiak" --topik 6 --time-scale 0 --tts-mock --max-minutes 3`, `gemini-3.5-flash-lite`.

- 22 giliran dalam 3 menit waktu nyata; audio rata-rata 8,2 dtk/giliran (TTS mock sebagai pendekatan); persona p50 1,7 dtk.
- Poin pertama ditutup dini oleh Showrunner LLM pada 144 dari 180 dtk (16 giliran, jenuh 0,85): penutupan dini LLM
  nyata tidak sependek mock.
- 2 dari 22 giliran persona melewati `PERSONA_TIMEOUT_MS` (20 dtk) → kalimat aman. Jaringan/Gemini; sudah tercatat
  sebagai risiko di PRD §15.

## 3. Yang belum diuji

- Siaran 60 menit penuh real time dengan LLM, TTS nyata, layar OBS, dan prompter. Kuota: mode B ±7 giliran/menit ⇒
  ±600 permintaan per jam bila persona + Showrunner + ringkasan satu model, melebihi 500 RPD free tier. Cek kesiapan
  akan menunjukkan ini; siaran 60 menit perlu cadangan `compat:` atau model per peran.
- Mode A dengan penyiar sungguhan: mic hands-free, deteksi pindah topik dari transkrip Web Speech asli, dan
  "tanpa satu klik pun".
- Dua popup (layar OBS + prompter) dari satu klik Mulai di Chrome.
