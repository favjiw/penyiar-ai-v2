# Gerbang Tahap 2, sesi 20 menit (24 Okt 2026)

Keputusan Favian sebelum sesi ini: blocker tetap 3–5 poin; Showrunner boleh mengarahkan ke sudut baru di luar poin sampai jatah waktu topik habis. Jatah topik = sisa target `SESSION_TARGET_MIN=20` (dikurangi cadangan Closing) dibagi sisa topik.

Blocker sama dengan sesi sebelumnya (`blk_20261024_kos-kosan_ca3a`, 3 topik). ElevenLabs utama + Edge failover. Persona dan Supervisor `gemini-3.5-flash-lite`, Showrunner `gemini-flash-lite-latest`, `MIN_TURNS_PER_TOPIC=8`, `MAX_TURNS_PER_TOPIC=60`. Log `show_20261024_154501_eacf`. Transkrip: [tahap2-gate-4-transkrip.md](tahap2-gate-4-transkrip.md).

(Percobaan sebelumnya, `show_20261024_153743_56bc`, dihentikan: jalur cadangan Showrunner saat timeout memakai `fixed_turns` dan mengabaikan jatah, sehingga topik pindah terlalu cepat. Sudah diperbaiki sebelum sesi ini.)

## Hasil

| Kriteria | Hasil |
|---|---|
| Durasi | **21,4 menit** ✓, 97 giliran, `completed` |
| Tanpa crash dan tanpa intervensi | ✓ |
| Log lengkap | ✓ |
| Topik 1 | 6,5 mnt, 34 giliran, 4/4 poin, 9 sudut baru (mis. "resep darurat anak kos", "mitos hantu dapur kos") |
| Topik 2 | 6,4 mnt, 37 giliran, 3/3 poin, 9 sudut baru (mis. "numpang mandi di toilet fakultas") |
| Topik 3 | 5,8 mnt, 22 giliran, **rusak**: 33 persona timeout → kalimat aman berulang, audio total 32 s |
| Kredit ElevenLabs | 1.585 |
| Jeda p50 / p95 | 5,9 s / 19,7 s (terpengaruh topik 3) |

## Penyebab topik 3 rusak: kuota harian Gemini habis

Mulai 15:55 semua panggilan ke `gemini-3.5-flash-lite` mendapat 429 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, **batas 500 request per hari per model**. `gemini-flash-lite-latest` ternyata alias model yang sama (kuota ikut habis). Sesi ini adalah sesi live ke-5 hari itu; satu sesi 20 menit memakai ±240 request di model persona/Supervisor. Kuota pulih ±22 jam kemudian.

Engine tetap jalan sesuai desain, tapi hasilnya bukan siaran yang layak. **Perbaikan** (commit "Live survives an exhausted daily Gemini quota"):
- error kuota harian langsung gagal, tanpa retry;
- persona pindah ke `GEMINI_MODEL_PERSONA_FALLBACK`; Supervisor turun ke `rules` sampai akhir sesi (PRD §8);
- persona gagal 3× beruntun → siaran dibawa ke Closing; konsol menampilkan peringatan.

## Catatan kualitas

- Sudut baru beragam dan nyambung ke topik, tetapi Showrunner mencatat kejenuhan 0,85 di beberapa titik topik 1 ("mulai berputar-putar"). Perlu dinilai Favian dari transkrip apakah 6 menit per topik masih enak didengar.
- Supervisor timeout 46/97, sebagian besar di topik 3 (kuota).
