# Hasil Tahap 0

Ringkasan per uji. Angka mentah ada di `tahap0/out/` (lokal, tidak di-commit).

## TTS

### Edge TTS (24 Okt 2026, laptop MX250, jaringan rumah)

10 kalimat `data/tts_sentences.txt`, satu kali jalan.

| Suara | Latensi total p50 | Maks | Chunk pertama p50 | Durasi audio |
|---|---|---|---|---|
| `id-ID-ArdiNeural` (pria) | 0,93 s | 3,27 s | 0,45 s | 4,5–5,5 s |
| `id-ID-GadisNeural` (wanita) | 2,33 s | 3,88 s | 1,85 s | 5,7–7,3 s |

- Semua 20 kalimat berhasil setelah `aiohttp` dipaksa memakai resolver DNS sistem. Tanpa itu sebagian besar request menggantung (aiodns timeout); perbaikan ini wajib ikut ke `tts/provider.py` di Tahap 1.
- Skor "robot atau tidak": belum dinilai.

### Gemini TTS (24 Okt 2026, `gemini-3.8-flash-tts`, key free tier dari repo lama)

Suara pria `Puck`. Suara wanita (`Kore`) belum sempat dibuat.

| Hasil | Angka |
|---|---|
| Berhasil | 7 dari 7 request pertama (pria 01–07) |
| Latensi | 3,7 / 3,7 / 4,7 / 12,7 / 17,4 / 27,1 / 28,0 s (p50 12,7 s) |
| Durasi audio | 3,9–5,8 s, RTF p50 2,35 (lebih lambat dari waktu nyata) |
| Batas kuota | **3 RPM per model** (`GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, quotaValue 3). Request ke-8 langsung 429. |
| Percobaan ulang dengan laju 2,8 RPM | 9 request berturut-turut timeout di 40 s, tanpa audio |

Kesimpulan sementara [C]:
- Gemini TTS free tier **tidak layak sebagai TTS utama live**. Mode B butuh sekitar 6,7 request TTS per menit (lebih dari 2× batas), dan latensinya sering di atas batas jeda p95 ≤4 s.
- Usulan: **Edge TTS sebagai utama**. Gemini TTS dipakai offline untuk bank filler dan klip yang di-cache, bila kualitasnya dinilai jauh lebih baik.
- Masih perlu: penilaian "robot atau tidak" atas `gemini_male_01..07.wav` dibanding `edge_male_01..07.mp3`, serta pengecekan RPD di AI Studio.

### ElevenLabs (24 Okt 2026, key dari Favian)

Key uji hanya punya izin TTS (tanpa `user_read`, `models_read`, `voices_read`), jadi sisa kredit dan tier akun tidak bisa dibaca dan Voice Library tidak bisa dicari lewat API. Kandidat suara Indonesia diambil dari katalog publik [json2video](https://json2video.com/ai-voices/languages/indonesian/indonesia/) (96 suara), lalu diverifikasi langsung lewat API: 12 dari 12 kandidat bisa dipakai.

**Audisi** (`el_audition.py`, model `eleven_flash_v2_5`, 2 kalimat per suara). Kriteria pilihan [C]: transkrip setia (tanpa kata disisipkan/diulang), tempo cepat ala siaran, deskripsi "young".

| Persona | Pilihan | voice_id | Cadangan | Alasan |
|---|---|---|---|---|
| Raka | Pratama (young; clear, confident, warm) | `q8qwd1jY2jS3AWOBeq25` | Ginanjar `JjCMg2oeB7ExbMJUJHSK` | WER 0 di kedua kalimat, tempo cepat |
| Salsa | Aita (young; youthful, expressive, friendly) | `ffTJE9l3Kt2ipEM32UOc` | Kira `gmnazjXOFoOcWA59sd5m` | WER terendah, tempo tercepat |

Dakocan, Senandika, Tri Nugraha, dan Honeypie menyisipkan/mengulang kata ("pernah kayak, pernah kayak"); tidak dipilih. Sampel semua kandidat: `out/el_audition/` — **pilihan ini perlu didengar ulang oleh Favian**.

**Benchmark** (10 kalimat × 2 suara pilihan, endpoint streaming, mp3 128 kbps):

| Model | Suara | Latensi total p50 | Maks | Byte pertama p50 | Kata/detik | WER transkrip rata-rata |
|---|---|---|---|---|---|---|
| `eleven_flash_v2_5` | Pratama | 0,57 s | 1,08 s | 0,46 s | 3,3 | 0,078 |
| `eleven_flash_v2_5` | Aita | 0,55 s | 0,58 s | 0,44 s | 3,0 | 0,064 |
| `eleven_multilingual_v2` | Pratama | 1,35 s | 1,85 s | 1,30 s | 3,1 | 0,112 |
| `eleven_multilingual_v2` | Aita | 1,43 s | 1,61 s | 1,37 s | 1,9 (lambat) | 0,052 |
| `eleven_v3` (uji 2 kalimat) | Pratama | 2,4–2,8 s | | | | |

- Sisa WER hanya variasi ejaan transkripsi (lo/lu, gue/gua, abis/habis); tidak ada kata yang hilang atau disisipkan.
- **Cold start:** request pertama ke suara library kadang 15–20 s; berikutnya ±0,5 s. Perlu warm-up per suara saat cek pra-live.
- `eleven_v3` menerima tag `[laughs]` (sampel `out/tts/v3_laugh.mp3`), tapi 4–5× lebih lambat dari flash.
- **Biaya:** header `character-cost` mencatat 16 kredit untuk kalimat 79 karakter di flash (±0,2/karakter) dan 29–31 di v3. Perkiraan kasar mode B (giliran ±150 karakter, 6,7 giliran/menit): ±4 rb kredit per 20 menit, ±12 rb per 60 menit di flash. Kuota bulanan akun belum diketahui (key tanpa `user_read`).

**Catatan validitas juri audio:** `audio_judge.py` (Gemini `gemini-3.5-flash-lite`) memberi skor 5/5 di semua aspek untuk semua klip, **termasuk Edge TTS dan Gemini TTS**. Skor kealamian dari LLM-judge audio ini tidak bisa dipakai; hanya transkripsinya (WER) yang berguna. Penilaian "robot atau tidak" tetap harus oleh manusia (KT FR-6).

**Keputusan:** Favian memilih ElevenLabs flash sebagai TTS utama; PRD diperbarui ke v2.2 (pengecualian Rp0 khusus TTS).

**Penilaian dengar (24 Okt 2026):** Favian mendengar sampel Pratama (Raka) dan Aita (Salsa) beserta pembanding (Ginanjar, Kira, Edge) dan menyatakan suara sudah oke [F]. KT FR-6 lengkap (5 penilai, skor ≥3,5) masih menunggu penilai lain.

## STT

Belum. Web Speech: `stt_webspeech.html`. faster-whisper: `stt_bench.py` di PC lab dengan rekaman dari halaman yang sama.

## Kuota

Diukur dari error 429 saat uji (24 Okt 2026), bukan dari dasbor AI Studio; angka RPM teks belum terlihat.

| Model | Batas terukur | Catatan |
|---|---|---|
| `gemini-3.8-flash-tts` | 3 RPM | Tidak dipakai di live |
| `gemini-3.5-flash-lite` | **500 RPD** | `gemini-flash-lite-latest` alias model ini (kuota bersama) |
| `gemini-3.1-flash-lite` | (RPD belum kena) | Sering 503 "high demand" |

Kebutuhan terukur dari sesi mode B 20 menit (Tahap 2): ±100 giliran → ±100 request persona, ±100 Supervisor (`full`), ±35 Showrunner. Bila persona dan Supervisor di model yang sama: ±240 request/sesi, jadi **±2 sesi 20 menit per hari per model**, atau 1 sesi 60 menit tidak muat sama sekali.

Konsekuensi untuk live 60 menit dan eksperimen FR-14:
- pisahkan peran ke model berbeda (masing-masing 500 RPD), dan isi `GEMINI_MODEL_PERSONA_FALLBACK`;
- Supervisor `rules` (tanpa LLM) menghemat ±100 request per 20 menit;
- eksperimen offline mode B perlu dijadwalkan lintas hari atau memakai beberapa model.

Masih perlu: cek dasbor AI Studio untuk RPM/RPD resmi semua model, isi `quota.md`.

## Avatar T1

Belum: perlu klip Flow (idle, listen, talk per karakter). Uji di `crossfade_test.html`.

## Avatar T2

Belum: perlu PC lab. Ukur dengan `t2_rtf.py`. Catatan: di laptop MX250, `nvidia-smi` tidak melaporkan memory.used, jadi VRAM puncak terbaca 0; cek ulang di GTX 1080.

## Keputusan gerbang

| Keputusan | Pilihan | Alasan |
|---|---|---|
| STT | | |
| TTS utama | **ElevenLabs `eleven_flash_v2_5`** (Pratama = Raka, Aita = Salsa), Edge failover [F, 24 Okt 2026]; suara disetujui Favian setelah didengar | Flash p50 0,55 s dan setia teks; Gemini free tier 3 RPM, p50 12,7 s. PRD v2.2 |
| T2 | | |
| `PIPELINE_DEPTH` | | |
