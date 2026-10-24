# Gerbang Tahap 2, sesi 3 (24 Okt 2026)

Blocker sama (`blk_20261024_kos-kosan_ca3a`), ElevenLabs utama + Edge failover. Perubahan dari sesi 2: Supervisor di `gemini-3.5-flash-lite` dengan prompt `supervisor-v3`, kalimat aman per segmen. Showrunner tetap `gemini-3.1-flash-lite`. Transkrip: [tahap2-gate-3-transkrip.md](tahap2-gate-3-transkrip.md).

| Kriteria | Sesi 1 | Sesi 2 | **Sesi 3** | Target |
|---|---|---|---|---|
| Selesai tanpa crash / intervensi | ✓ | ✓ | ✓ | ✓ |
| Durasi | 16,4 mnt* | 8,8 mnt | 8,6 mnt (7,5 mnt audio) | 20 mnt |
| Giliran | 40 | 43 | 52 | |
| Jeda p50 | 0,44 s | 0 s | 0 s | ≤1,5 s |
| Jeda p95 | 60 s | 9,8 s | 8,5 s | ≤4 s |
| Supervisor p50 | 5,0 s | 5,0 s | **1,18 s** | ≤1,5 s (FR-5) |
| Supervisor timeout | 23/40 | 23/43 | 2/52 | |
| TTS | Edge, 11 gagal | 43/43 ElevenLabs | 52/52 ElevenLabs | |
| Kredit ElevenLabs | 0 | 1.406 | 1.619 | |
| Cakupan poin | 4/4, 3/3, 3/4 | 4/4, 3/3, 4/4 | 4/4, 3/3, 4/4 | ≥60% |

\* sebagian besar menunggu jaringan yang putus-sambung.

## Jeda p95

6 dari 51 jeda di atas 4 s, semuanya di giliran 32–37: satu menit ketika persona (3,6–8,2 s), Supervisor (4–5 s), dan TTS (3,8 s) melambat bersamaan, plus satu persona timeout. Di luar jendela itu semua jeda ≤4 s. Usulan [C]: `PIPELINE_DEPTH=2` (dua giliran disiapkan di depan) dan filler pendek saat antrean kosong (bank filler direncanakan di Tahap 4).

## KT lain yang terukur

- FR-3: 0 markdown/emoji/keterangan panggung di 135 giliran (KT meminta 200). Panjang giliran p50 25 kata, p90 48, maks 65.
- FR-4: tidak ada topik yang berhenti sebelum 60% poin tercakup; tidak ada `forced` (3 dari 10 sesi uji).
- FR-2: tombol operator (pause/lanjut/stop) merespons ±23 ms di konsol.
