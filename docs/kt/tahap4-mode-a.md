# Tahap 4: Mode A (penyiar + AI), catatan uji (25 Okt 2026)

## Yang dibangun

- `ModeAEngine` (`backend/app/show/mode_a.py`): ucapan penyiar (transkrip PTT) → filler langsung → persona menjawab 1–3 kalimat → Supervisor (batas 2,5 s) → TTS per kalimat (kalimat pertama dikirim begitu siap, sisanya `audio_part`). Penyiar boleh memotong AI. Showrunner hanya memberi saran dan `steer_hint`. Next topik oleh penyiar.
- Bank filler 18 kalimat per persona (`backend/app/data/filler.json`), di-TTS sekali lalu di-cache.
- Prompter `/prompter`: topik besar, poin dengan centang Showrunner, pertanyaan penonton, saran Showrunner, PTT (tahan Spasi / tombol; Esc batal; mode tekan-tekan), Next topik (`N`), transkrip singkat. Web Speech `id-ID`; kolom ketik bila browser tidak mendukung.
- Konsol: pilih mode A, persona AI, nama penyiar; transkrip memuat baris penyiar dan STT sementara.
- Stage mode A: panel atas transparan untuk kamera studio (source OBS), panel bawah avatar AI.

Keputusan terbuka PRD §15.2 diisi default [C], bisa diubah: nama penyiar diisi operator saat Mulai (#2); AI ikut di Opening dan Closing, penyiar yang memandu (#3).

## Uji

- 9 tes mode A (engine + API) lulus; uji browser dengan backend mock: konsol → mode A → prompter menampilkan topik dan poin → PTT → filler → jawaban AI → stage memutar klip `listen`/`talk` di panel bawah.
- `scripts/mode_a_probe.py` (live Gemini + ElevenLabs, 25 Okt 02:11): filler 0 ms setelah transkrip diterima; jawaban utama p50 11,8 s. **Tidak mewakili**: pada jam itu satu panggilan Gemini paling sederhana pun 4–6 s (kemarin ±1,4 s), dan Supervisor menyentuh batas 2,5 s di semua giliran. Perbaikan dari uji ini: kalimat aman dari bank tidak lagi diperiksa Supervisor.

Perkiraan di kondisi API normal (angka Tahap 2): persona ±1,4 s + Supervisor ±1,2 s + TTS kalimat pertama ±0,6 s ≈ 3,2 s, ditambah waktu STT. Target KT p50 ≤4 s mepet; bila perlu, opsi [C]: Supervisor `rules` di mode A, atau TTS kalimat pertama dijalankan bersamaan dengan pemeriksaan Supervisor.

## Belum

- Uji STT nyata (rekaman 20 kalimat Tahap 0) dan latensi lepas tombol → filler di browser.
- Pengukuran ulang `mode_a_probe.py` di jam API normal.
- Gerbang: sesi 15 menit bersama penyiar sungguhan.
