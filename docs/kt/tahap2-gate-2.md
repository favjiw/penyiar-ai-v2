# Gerbang Tahap 2, sesi 2 (24 Okt 2026)

Blocker sama dengan sesi 1 (`blk_20261024_kos-kosan_ca3a`), konfigurasi produksi TTS: **ElevenLabs `eleven_flash_v2_5` utama** (Pratama/Aita), Edge failover. Batas waktu persona dan Showrunner sudah aktif. LLM: persona `gemini-3.5-flash-lite`; Supervisor `full` + Showrunner di `gemini-3.1-flash-lite`. Transkrip: [tahap2-gate-2-transkrip.md](tahap2-gate-2-transkrip.md).

| Kriteria | Hasil |
|---|---|
| Tanpa crash dan intervensi | ✓ `completed`, 43 giliran |
| Durasi | 8,8 menit (6,6 menit audio) |
| Jeda p50 / p95 / maks | 0 ms / 9,8 s / 16,9 s (target p95 ≤4 s: ✗) |
| Latensi p50 persona / Supervisor / TTS | 1,5 s / **5,0 s** / 0,7 s |
| TTS | 43/43 ElevenLabs, 1.406 kredit (±160 kredit/menit audio+jeda) |
| Cakupan poin | 4/4, 3/3, 4/4; Showrunner 7 steer, 5 continue, 2 transition, 1 close, 0 forced |
| Galat | 1 persona timeout di giliran pertama (jaringan) → kalimat aman |

## Penyebab jeda p95

Supervisor menyentuh batas 5 s di 23/43 giliran: `gemini-3.1-flash-lite` sering 503 "high demand" lalu retry. Uji langsung 5 kasus buatan tangan:

| Model | Latensi | Benar (prompt v3) |
|---|---|---|
| `gemini-3.5-flash-lite` | 1,2–1,6 s | 5/5 |
| `gemini-3.1-flash-lite` | 1,6–17,8 s | 5/5 |

Semua model di prompt v2 juga menandai anekdot pribadi kecil sebagai "fakta karangan" (false positive). **Tindakan:** Supervisor pindah ke `gemini-3.5-flash-lite`, prompt `supervisor-v3` memperjelas bahwa anekdot pribadi bukan pelanggaran, dan kalimat aman dibedakan per segmen (giliran pertama sesi ini berbunyi "Nah, menarik tuh." karena persona timeout).
