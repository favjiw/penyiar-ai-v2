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

### Gemini TTS

Belum: perlu `GEMINI_API_KEY` dan `GEMINI_MODEL_TTS` di `.env`.

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
| TTS utama | | |
| T2 | | |
| `PIPELINE_DEPTH` | | |
