# Catatan progres: fokus topik dan percakapan

Branch kerja: `feat/topik-percakapan`. Kondisi sebelum penghapusan: branch `archive/avatar-dan-komentar`, tag `pre-strip`. Acuan keputusan: PRD v2.5 §1.3.1.

## Fase 1: hapus avatar, stage, dan komentar (selesai, 30 Okt 2026)

**Dihapus**
- Halaman `/stage`, pemutar klip Flow (`VideoAvatar`), zona aman TikTok, popup OBS.
- Lip-sync MuseTalk: `avatar-worker/`, `backend/app/avatar/`, field `video_url` dan `avatar_render`, tes T2.
- Aset dan alat avatar: `assets/`, `tahap0/t2_rtf.py`, `tahap0/crossfade_test.html`, dokumen OBS, prompt Flow, laporan MuseTalk.
- Setelan `AVATAR_*`, `COMMENTS_ENABLED`, `TIKTOK_USERNAME`; field `clips` di kartu persona.
- Role WebSocket `stage`. Konsol sekarang satu-satunya pemilik audio.

**Tidak ada yang perlu dihapus (sudah tidak ada di repo ini):** fitur komentar (FR-13 belum pernah dibuat), three.js/VRM, format clock, jingle, PSA, musik.

**Diubah:** kata "tulis di komentar" di prompt Blocker, persona, dan bank kalimat aman diganti netral (prompt Blocker jadi `blocker-v3`). Larangan mengarang isi komentar tetap. Nama field `pertanyaan_penonton` tidak berubah.

**Dipertahankan:** Supervisor dan Showrunner (default Supervisor akan `off`, lihat Fase 4), ElevenLabs + Edge, ASR push-to-talk di prompter, bank filler.

## Fase 2: orb giliran bicara (selesai, 30 Okt 2026)

- Tab **Live** konsol punya panel "Giliran bicara": satu orb per penyiar AI (mode A: 1, mode B dan C: 2) dengan nama dan label state, dan indikator mikrofon kecil untuk penyiar manusia (mode A dan C). Daftar peserta berupa list.
- State orb: `idle` (redup), `listening` (bernapas pelan), `thinking` (kilau berputar), `speaking` (skala dan kecerahan mengikuti amplitudo audio).
  - Mode B: yang giliran berikutnya `thinking`, yang lain `listening`.
  - Mode A dan C: `thinking` dari ucapan penyiar diterima sampai jawaban AI mulai; selain itu `listening`.
- Audio diputar lewat Web Audio (`AudioContext` + `AnalyserNode`), amplitudo dihaluskan (naik cepat, turun pelan) dan ditulis ke variabel CSS `--lvl` per frame tanpa render React. `AudioContext` yang masih suspended diperlakukan sebagai audio diblokir (tombol "Aktifkan audio"), bukan diam-diam bisu.
- Warna lewat variabel CSS `--orb-raka-1/2`, `--orb-salsa-1/2`, `--orb-default-1/2` di `frontend/src/console/orb.css`.
- `prefers-reduced-motion`: tanpa skala dan animasi; state dibedakan lewat opasitas, warna, dan label teks.
- Transkrip: tiap giliran memuat jam (`ts` dari server) dan segmen atau judul topik; auto-scroll.
- Indikator mikrofon: prompter mengirim `stt_partial` dengan `active` selama tombol bicara ditahan; server meneruskannya ke konsol.
- Perbaikan sampingan: `busy` di snapshot mode A tidak lagi menempel `true` setelah jawaban selesai (flag `_answering`).
- Config preview baru `backend-mock-edge` (LLM mock, suara Edge asli) untuk menguji orb dengan audio sungguhan; TTS mock hanya menghasilkan keheningan, jadi amplitudo selalu nol.

**Diverifikasi di browser:** mode B (Edge TTS) dengan transisi `thinking → speaking → listening` bergantian dan amplitudo terukur sampai 0,43; mode A dengan satu orb, indikator mikrofon menyala dan mati mengikuti `stt_partial`, dan tidak ada state `thinking` yang menempel.
**Belum diverifikasi:** tampilan `prefers-reduced-motion` (belum bisa diemulasi di panel browser), mikrofon nyata lewat prompter, dan kasus dua tab konsol (tab kedua bukan pemilik audio, jadi orb memakai denyut buatan).

## Masih terbuka

- Fase 2b: lapisan TTS (`TTSProvider`, Edge default, ElevenLabs lewat `.env`, gTTS cadangan, `scripts/test_tts.py`).
- Fase 3: 3 varian Blocker dengan retry parse maksimal 2 kali, `sessions/<id>/blocker.json`.
- Fase 4: mode C, daftar peserta di engine, log `sessions/<id>/turns.jsonl`, hook `supervisor.check()` default nonaktif.
- Prompt persona, Showrunner, dan Supervisor masih menyebut "live TikTok HITS" sebagai konteks program; belum diubah supaya versi prompt tidak bergeser.
- Bagian PRD §6.1, §6.3, §11, dan Lampiran B masih memuat stage/avatar/komentar sebagai rujukan sejarah.
