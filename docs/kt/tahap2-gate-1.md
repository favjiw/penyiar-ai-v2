# Gerbang Tahap 2, sesi 1 (24 Okt 2026)

Sesi mode B headless (`scripts/run_show.py`), tanpa intervensi operator. Log: `backend/logs/show_20261024_144451_5dc7.jsonl` (lokal). Transkrip: [tahap2-gate-1-transkrip.md](tahap2-gate-1-transkrip.md).

| Konfigurasi | Nilai |
|---|---|
| Blocker | "Kos-kosan" · Drama fasilitas kos (3 topik, 3–4 poin), dibuat dan dikunci otomatis |
| LLM | persona `gemini-3.5-flash-lite`; Supervisor `full` + Showrunner `llm` di `gemini-3.1-flash-lite` |
| TTS | Edge saja (tanpa cadangan), supaya uji panjang tidak memakai kredit ElevenLabs |
| Showrunner | `SESSION_TARGET_MIN=20`, `MIN_TURNS_PER_TOPIC=8`, `MAX_TURNS_PER_TOPIC=60` |

## Hasil

| Kriteria | Hasil | Catatan |
|---|---|---|
| Berjalan tanpa crash dan tanpa intervensi | ✓ | Opening → 3 topik → Closing, `session_end: completed` |
| Durasi 20 menit | ✗ (16,4 menit, hanya 6,9 menit audio) | Sisanya waktu tunggu karena gangguan jaringan |
| Log lengkap | ✓ | `report.py` merekonstruksi transkrip dan keputusan |
| Jeda antargiliran p50 ≤1,5 s | ✓ 0,44 s | |
| Jeda p95 ≤4 s | ✗ 60 s (maks 267 s) | DNS laptop gagal (`getaddrinfo failed`), Edge timeout, Gemini 503 |
| Cakupan poin | 4/4, 3/3, 3/4 | Showrunner: 9 steer, 2 transition, 1 close, 0 forced |

## Temuan dan tindakan

1. **Jaringan laptop putus-sambung selama uji**: 11 dari 40 giliran tanpa suara (Edge gagal, breaker terbuka, tidak ada cadangan), 2 giliran persona jatuh ke kalimat aman. Siaran tetap jalan.
2. **Panggilan LLM persona dan Showrunner tidak dibatasi waktu**: saat DNS macet, retry + backoff menghasilkan siaran hening sampai 4,5 menit. **Diperbaiki**: `PERSONA_TIMEOUT_MS` (kalimat aman) dan `SHOWRUNNER_TIMEOUT_MS` (fixed_turns).
3. **Supervisor `full` timeout di 23/40 giliran** (batas 5 s), sebagian besar karena `gemini-3.1-flash-lite` 503 "high demand" lalu retry. Ucapan tetap lolos aturan cepat dan ditandai `timed_out`.
4. **Supervisor menandai pembukaan sebagai keluar topik** (1 regenerasi tidak perlu). **Diperbaiki** di prompt `supervisor-v2`.
5. **Blocker 3 topik × 3–5 poin habis sekitar 7–8 menit audio**. Showrunner memindahkan topik setelah poin habis dan obrolan mulai berulang (jenuh 0,7), keputusan yang wajar secara editorial. Untuk sesi 20 menit, materinya perlu lebih banyak: ini keputusan Favian (lihat PRD §16).
6. Giliran persona cenderung panjang di awal (40–54 kata) dan pembuka kadang mirip ("Aduh, bener banget tuh kata ...").
