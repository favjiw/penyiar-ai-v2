# Gerbang Tahap 2, sesi ulang 20 menit (24 Okt 2026, sore)

Konfigurasi produksi dari `.env` (key Gemini baru dengan kuota segar, ElevenLabs utama + Edge, cadangan persona `compat:gemini-3.8-flash`), `PIPELINE_DEPTH=2`, target 20 menit. Log `show_20261024_165455_8758`. Transkrip: [tahap2-gate-5-transkrip.md](tahap2-gate-5-transkrip.md).

**Hasil tidak mewakili sistem: jaringan laptop sedang sangat tidak stabil.**

| Metrik | Nilai |
|---|---|
| Durasi | 18,4 menit, 74 giliran, `completed` (dibawa ke Closing oleh pengaman persona) |
| Persona timeout | 30/74 (DNS `getaddrinfo failed`, permintaan menggantung >10 s) → 31 giliran kalimat aman |
| Supervisor timeout | 69/74 |
| TTS | 63 ElevenLabs, 6 Edge, 5 tanpa suara; 843 kredit |
| Jeda p50 / p95 | 9,9 s / 19,0 s |
| Topik | t1 4/4 dan t2 3/3 memakai jatah (±6–7 mnt); t3 dipotong pengaman setelah persona gagal ≥90 s |

Percobaan sebelumnya hari ini (`show_20261024_165234_71a1`) berhenti dalam 0,6 menit karena DNS gagal tepat di awal dan pengaman wrap-up terlalu agresif; diperbaiki (`PERSONA_FAILURE_WRAP_SEC`).

## Yang terbukti

- Semua jalur cadangan bekerja tanpa crash: TTS → Edge, Showrunner timeout → keputusan berbasis jatah waktu, persona gagal berkepanjangan → Closing dengan peringatan di konsol.
- Kuota harian tidak habis (key baru).

## Yang belum terbukti

Kualitas sesi 20 menit penuh dengan jaringan normal. Sesi 3 (jaringan baik, 8,6 menit) menunjukkan angka sistem sebenarnya: persona p50 1,4 s, Supervisor p50 1,2 s, jeda p50 0 s. **Disarankan menjalankan gerbang 20 menit dari jaringan yang stabil** (mis. jaringan lab/kampus): `python scripts/run_show.py --blocker <id>` dengan `SESSION_TARGET_MIN=20`, `MIN_TURNS_PER_TOPIC=8`, `MAX_TURNS_PER_TOPIC=60`, `PIPELINE_DEPTH=2`.
