# Serah terima: branch `feat/topik-percakapan` (WIP, per 2 Nov 2026, setelah revisi responsi HITS 30 Okt)

Acuan tunggal tetap `PRD.md` (v2.5). Rincian hasil uji: `docs/CATATAN-PROGRES.md`. Audit penghapusan: `docs/AUDIT-STRIP.md`.

## Tujuan
Memfokuskan riset pada **kualitas percakapan** (podcast: Opening, maks 3 topik, Closing; target 40+ menit). Avatar, komentar, OBS, dan live TikTok ditunda. Branch ini di depan `main` (jumlah commit: `git log main..HEAD`), belum di-merge dan belum ada PR. Kondisi sebelum penghapusan: branch `archive/avatar-dan-komentar` dan tag `pre-strip`.

## Revisi responsi HITS (R1–R4, sesi 2 Nov 2026) — selesai, sudah di-commit
- **R1 `396f06a`** Mode C (1 manusia + 2 AI) dihapus; sisa mode A dan B. `HumanLedEngine` kini hanya mode A (`ai_persona` wajib); daftar peserta berbasis list dipertahankan (dipakai mode B). Tes khusus C dibuang; sisanya dipindah ke `tests/test_session_features.py`.
- **R2 `abbb8de`, `ac6bd80`** Hasil generate = draf tersimpan yang langsung bisa dipakai. `POST /api/show/start` mengunci draf otomatis (422 beserta alasan bila tidak lolos aturan 3-5 poin; persona dan suara divalidasi sebelum mengunci). Dropdown live memuat draf dan terkunci; poin `perlu_cek` meminta konfirmasi. Blocking terkunci tidak bisa diubah; edit lewat "Buat versi baru". Tombol "+ Topik" sudah ada (batas 3 topik).
- **R3 `b8fe942`** Daftar suara terkurasi `backend/app/data/voices.json` (isi: Pratama, Aita, Ardi, Gadis; **TODO Favian: tambah suara lain**). `GET /api/voices`; pilihan suara di `/api/show/start` dan `/api/precheck` (`voices: {persona: id}`), menang atas `.env` dan kartu persona, berlaku per provider. Filler disimpan per suara. Suara tercatat di `session_start.voices` dan `turns.jsonl` (`tts_voice`, suara yang benar-benar dipakai).
- **R4 `ced5617`** Batas waktu obrolan per **poin** (`POINT_TIME_LIMIT_S`, default 60, rencana uji 90; 0 = mati dan kembali ke Showrunner per topik, dipakai untuk baseline eksperimen). Kode: `show/pointclock.py`, `engine._decorate_point` / `_timed_after_turn`, `mode_a._close_point_if_due`, `persona.py` (fokus poin, anggaran kata, giliran penutup).
  - Waktu dari durasi audio: `committed_s` (giliran yang sudah dibuat, dipakai keputusan) dan `played_s` (audio selesai diputar, untuk countdown). Di mode A, `speech_ms` penyiar ikut dihitung.
  - Sisa waktu <= `POINT_WRAP_S` (15) → giliran berikutnya menutup poin dan mengantar ke poin berikutnya (poin terakhir topik memakai jalur `transition_to`/`to_closing`). Anggaran kata = sisa × `TTS_WORDS_PER_SEC` (2,0; Edge 2,3, gTTS 1,9 dari sesi 34 menit; **ElevenLabs belum terukur**). Teks yang melewati 1,3× anggaran dirapikan dengan membuang kalimat utuh (`trim_to_budget`); audio tidak pernah dipotong.
  - Mode B: timer = batas atas; Showrunner (policy `llm`) menilai satu poin dan boleh menutup lebih awal setelah `POINT_MIN_TURNS`. Mode A: jawaban AI menutup lalu poin pindah otomatis; "Next topik" tetap manual.
  - Saat timer aktif, `MAX/MIN_TURNS_PER_TOPIC` dan `SESSION_TARGET_MIN` tidak dipakai. Policy `fixed_turns`/`coverage_only` hanya bermakna dengan `POINT_TIME_LIMIT_S=0`.
  - Log: event `point_start`, `point_end` (reason: timer | early | skip | advance | wrap | stop), `point_trim`; event WS `point_clock`; snapshot `point_clock`. UI: countdown "Poin 2/4 · 0:42" di konsol dan prompter.
  - Tes lama di-pin `POINT_TIME_LIMIT_S=0`; tes timer di `tests/test_point_timer.py`.

## Sudah selesai
- Fase 1: avatar T1, MuseTalk T2, halaman stage, dan setelan komentar dihapus (role WS `stage` hilang; konsol satu-satunya pemutar audio).
- Fase 2: orb per penyiar AI (idle/listening/thinking/speaking, amplitudo lewat Web Audio), indikator mikrofon, transkrip berjam dan bertopik.
- Fase 2b: lapisan TTS (`TTSProvider`), Edge default, ElevenLabs lewat `.env`, gTTS cadangan, retry 1x, peringatan ke operator.
- Fase 3: Tema → 3 varian Blocker, retry parse 2x, aturan kunci (3-5 poin/topik), `sessions/<id>/blocker.json`, rundown di prompter.
- Fase 4: mode A/B (mode C sudah dihapus di R1), peserta berupa daftar, `sessions/<id>/turns.jsonl`, ringkasan obrolan, hook `supervisor.check` (default off).
- Uji (sebelum R1–R4): 139 tes backend lulus, `tsc` dan build frontend bersih. Mode B real time 34,2 menit (127 giliran) tanpa crash. Mode A dan C diuji di browser dengan Gemini dan Edge asli (sebelum R1–R4).

## Belum / belum diverifikasi
- **R1–R4 belum diuji end-to-end dengan LLM, mikrofon, dan ElevenLabs nyata:** hanya tes otomatis (165 lulus) dan satu cek countdown di browser dengan mock. Periksa: apakah 60 detik per poin terasa pas (coba 90), apakah AI benar-benar menutup natural, apakah kata per detik ElevenLabs cocok dengan 2,0, dan jam di mode A setelah PTT (hitungan melompat saat `speech_ms` tiba).
- Saran Showrunner di mode A ("siap pindah") masih per topik, bukan per poin. Daftar blocking di dropdown live bertambah terus (semua draf lama tampil); perlu pembatasan atau pengelompokan.
- Alert fallback TTS belum menyebut nama suara yang dipakai. Kondisi `DEFAULT_AI_IDS` dipakai untuk memvalidasi persona di mode B.
- Catatan temuan (tidak diperbaiki, di luar cakupan): voice id masih tertulis di `data/persona/*.json` (PRD §0 aturan 3); `sessions/` jatuh ke `backend/sessions/`, bukan root repo seperti di PRD.
- **Hook VAD (di luar cakupan sesi ini):** tempat yang pas untuk deteksi giliran otomatis mode A adalah `HumanLedEngine.human_turn(text, stt_ms, speech_ms)` (`show/mode_a.py`), yang kini dipanggil dari `/api/ptt/turn`; VAD cukup mengganti pemicunya (akhir ucapan terdeteksi menggantikan spasi dilepas) dan mengisi `speech_ms`.
- **PRD belum diperbarui** (aturan §0: lapor konflik dulu). Usulan v2.6 ada di akhir sesi; konflik: mode C [F] di §3/§6.4/FR-2/§1.3.1, jadwal slot per topik dan peran Showrunner (FR-4, §6.2, §14.2) saat timer poin aktif, dan README/docs yang masih menyebut mode C.
- **Mikrofon dan Web Speech nyata** di Chrome (yang diuji: `/api/ptt/turn` dengan teks dan sinyal mikrofon simulasi).
- **Kualitas percakapan**: transkrip 34 menit belum dinilai (pengulangan, konsistensi persona, efek ringkasan, AI yang menimpali).
- ElevenLabs lewat lapisan baru: backend memuatnya tanpa peringatan; latensi dan kredit nyata belum diukur. Jalankan `python scripts/test_tts.py --providers elevenlabs`.
- Penilaian layak siar 8 dari 10 tema (KT FR-1), `prefers-reduced-motion`, sesi mode A/C yang panjang, kalibrasi Showrunner mode saran di C.
- PRD masih menyebut stage/avatar/komentar di §4, §5, §6.1, §6.3, §9.2 (`clips`), §11, dan FR-7 ("halaman stage"). README masih menyebut konfigurasi preview `backend-edge` yang sudah dihapus.
- Tahap 7 (harness eksperimen FR-14) belum dimulai; evaluasi Supervisor `rules`/`full` belum dijalankan.
- Prompt persona, Showrunner, Supervisor masih menyebut "live TikTok HITS".

## File kunci
- Engine: `backend/app/show/engine.py` (mode B), `show/mode_a.py` (`HumanLedEngine`, mode A), `show/pointclock.py`, `show/participants.py`, `show/turnlog.py`, `show/api.py`, `ws.py`, `config.py`.
- Agen: `agents/persona.py`, `summary.py`, `supervisor.py`, `showrunner.py`; prompt `prompts/persona.md` (v2), `blocker.md` (v3), `summary.md`.
- TTS: `tts/base.py`, `provider.py`, `voices.py`, `filler.py`. Blocker: `blocker/generator.py`, `store.py`.
- Skrip: `scripts/run_show.py`, `mode_a_probe.py` (`--mode A|C`), `test_tts.py`, `report.py`.
- Frontend: `console/LivePanel.tsx`, `VoiceStage.tsx`, `Orb.tsx`, `orb.css`, `BlockerEditor.tsx`; `live/useLiveSession.ts`; `prompter/PrompterPage.tsx`.

## Keputusan penting
- **Dua kelas, bukan satu engine:** `ShowEngine` (B) dan `HumanLedEngine` (A/C) berbagi kerangka; `ShowEngine` tidak ditulis ulang karena sudah teruji. Peserta berupa daftar (`>2` AI sudah lulus tes unit).
- **Mode C dihapus (R1):** keputusan [F] 30 Okt dibatalkan oleh arahan pembimbing; kodenya ada di riwayat git (sebelum `396f06a`).
- **TTS:** Edge untuk pengembangan, ElevenLabs untuk demo (`TTS_PROVIDER`, `TTS_FALLBACK=edge,gtts`). Edge dari laptop ini lambat dan kadang timeout (20% giliran jatuh ke gTTS di uji 34 menit); gTTS satu suara untuk dua persona.
- **Default dari uji panjang:** `PERSONA_TIMEOUT_MS=20000` (10 s membuat 16,5% giliran jadi kalimat kaleng), `MAX_TURNS_PER_TOPIC=60` (40 membatasi sesi ke ±34 menit), `TTS_TIMEOUT_SEC=12`.
- `SUPERVISOR_MODE` default `off` (pass-through); isi penuh FR-5 dipertahankan (inti skripsi). Showrunner dipertahankan; keputusan dipetakan ke `lanjut | pindah_topik | tutup`.
- Field blocker `pertanyaan_penonton` tidak diubah; kata "tulis di komentar" diganti netral (`blocker-v3`).
- MuseTalk di laptop MX250: RTF ±410, tidak layak; belum diukur di GTX 1080. Clone di `D:\programming\work\musetalk` dibiarkan.

## Langkah berikutnya
1. Coba mode A dengan mikrofon nyata di Chrome, lalu ukur latensi lepas-tombol sampai suara dengan ElevenLabs (KT FR-7).
2. Nilai transkrip `backend/sessions/show_20261030_113137_5204/turns.jsonl` dan perbaiki prompt/ringkasan sesuai temuan.
3. Isi penilaian FR-1 di `docs/kt/FR-1-blocker.md`; putuskan merge atau PR ke `main`.
4. Setujui usulan PRD v2.6 lalu bersihkan PRD dan README (stage/avatar/komentar dan mode C; mode kini hanya A dan B).
5. Uji R1–R4 dengan LLM, mikrofon, dan ElevenLabs nyata; kalibrasi 60 vs 90 detik dan kata per detik ElevenLabs.
6. Mulai Tahap 7: harness offline (LLM `compat:`, `TTS_MODE=mock`) untuk kondisi Supervisor dan Showrunner.

## Catatan kerja
- `.env`, `backend/logs/`, `backend/sessions/`, `backend/cache/` di-ignore git. `.env` lokal saat ini `TTS_PROVIDER=elevenlabs`, `SUPERVISOR_MODE=off`.
- `load_personas()` di-cache: tes tidak boleh memutasi hasilnya (salin dulu).
- Konsol Windows (cp1252) gagal mencetak "≤" atau "→"; skrip memakai `PYTHONIOENCODING=utf-8` atau `reconfigure`.
- Server preview kadang dihentikan aplikasi; nyalakan ulang bila halaman tidak terbuka.
