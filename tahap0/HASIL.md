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

## STT

Belum. Web Speech: `stt_webspeech.html`. faster-whisper: `stt_bench.py` di PC lab dengan rekaman dari halaman yang sama.

## Kuota

Belum. Isi `quota.md`. Perkiraan kebutuhan mode B dengan asumsi default (giliran 8 s + jeda 1 s, Showrunner tiap 3 giliran, 10% regenerasi):

| Peran | req/menit | 20 menit | 60 menit |
|---|---|---|---|
| persona | 7,3 | 147 | 441 |
| supervisor (full) | 7,3 | 147 | 441 |
| showrunner | 2,2 | 45 | 134 |
| tts | 6,7 | 134 | 400 |

## Avatar T1

Belum: perlu klip Flow (idle, listen, talk per karakter). Uji di `crossfade_test.html`.

## Avatar T2

Belum: perlu PC lab. Ukur dengan `t2_rtf.py`. Catatan: di laptop MX250, `nvidia-smi` tidak melaporkan memory.used, jadi VRAM puncak terbaca 0; cek ulang di GTX 1080.

## Keputusan gerbang

| Keputusan | Pilihan | Alasan |
|---|---|---|
| STT | | |
| TTS utama | Usulan: Edge (Gemini untuk cache offline) | Gemini free tier 3 RPM, latensi p50 12,7 s; menunggu penilaian kualitas dan keputusan Favian |
| T2 | | |
| `PIPELINE_DEPTH` | | |
