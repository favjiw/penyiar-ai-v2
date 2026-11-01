# Serah terima: branch `feat/topik-percakapan` (WIP, per 2 Nov 2026)

Acuan tunggal tetap `PRD.md` (v2.5). Rincian hasil uji: `docs/CATATAN-PROGRES.md`. Audit penghapusan: `docs/AUDIT-STRIP.md`.

## Tujuan
Memfokuskan riset pada **kualitas percakapan** (podcast: Opening, maks 3 topik, Closing; target 40+ menit). Avatar, komentar, OBS, dan live TikTok ditunda. Branch ini 15 commit di depan `main`, belum di-merge dan belum ada PR. Kondisi sebelum penghapusan: branch `archive/avatar-dan-komentar` dan tag `pre-strip`.

## Sudah selesai
- Fase 1: avatar T1, MuseTalk T2, halaman stage, dan setelan komentar dihapus (role WS `stage` hilang; konsol satu-satunya pemutar audio).
- Fase 2: orb per penyiar AI (idle/listening/thinking/speaking, amplitudo lewat Web Audio), indikator mikrofon, transkrip berjam dan bertopik.
- Fase 2b: lapisan TTS (`TTSProvider`), Edge default, ElevenLabs lewat `.env`, gTTS cadangan, retry 1x, peringatan ke operator.
- Fase 3: Tema → 3 varian Blocker, retry parse 2x, aturan kunci (3-5 poin/topik), `sessions/<id>/blocker.json`, rundown di prompter.
- Fase 4: mode A/B/C, peserta berupa daftar, `sessions/<id>/turns.jsonl`, ringkasan obrolan, hook `supervisor.check` (default off).
- Uji: 139 tes backend lulus, `tsc` dan build frontend bersih. Mode B real time 34,2 menit (127 giliran) tanpa crash. Mode A dan C diuji di browser dengan Gemini dan Edge asli.

## Belum / belum diverifikasi
- **Mikrofon dan Web Speech nyata** di Chrome (yang diuji: `/api/ptt/turn` dengan teks dan sinyal mikrofon simulasi).
- **Kualitas percakapan**: transkrip 34 menit belum dinilai (pengulangan, konsistensi persona, efek ringkasan, AI yang menimpali).
- ElevenLabs lewat lapisan baru: backend memuatnya tanpa peringatan; latensi dan kredit nyata belum diukur. Jalankan `python scripts/test_tts.py --providers elevenlabs`.
- Penilaian layak siar 8 dari 10 tema (KT FR-1), `prefers-reduced-motion`, sesi mode A/C yang panjang, kalibrasi Showrunner mode saran di C.
- PRD §6.1, §6.3, §11, Lampiran B, §5, dan README masih menyebut stage/avatar/komentar; README belum memuat mode C.
- Tahap 7 (harness eksperimen FR-14) belum dimulai; evaluasi Supervisor `rules`/`full` belum dijalankan.
- Prompt persona, Showrunner, Supervisor masih menyebut "live TikTok HITS".

## File kunci
- Engine: `backend/app/show/engine.py` (mode B), `show/mode_a.py` (`HumanLedEngine`, mode A dan C), `show/participants.py`, `show/turnlog.py`, `show/api.py`, `ws.py`, `config.py`.
- Agen: `agents/persona.py`, `summary.py`, `supervisor.py`, `showrunner.py`; prompt `prompts/persona.md` (v2), `blocker.md` (v3), `summary.md`.
- TTS: `tts/base.py`, `provider.py`, `voices.py`, `filler.py`. Blocker: `blocker/generator.py`, `store.py`.
- Skrip: `scripts/run_show.py`, `mode_a_probe.py` (`--mode A|C`), `test_tts.py`, `report.py`.
- Frontend: `console/LivePanel.tsx`, `VoiceStage.tsx`, `Orb.tsx`, `orb.css`, `BlockerEditor.tsx`; `live/useLiveSession.ts`; `prompter/PrompterPage.tsx`.

## Keputusan penting
- **Dua kelas, bukan satu engine:** `ShowEngine` (B) dan `HumanLedEngine` (A/C) berbagi kerangka; `ShowEngine` tidak ditulis ulang karena sudah teruji. Peserta berupa daftar (`>2` AI sudah lulus tes unit).
- **Mode C:** AI yang disapa menjawab ("kalian" = keduanya, tanpa sapaan bergantian); AI lain boleh menimpali (`MODE_C_CHIME_PROBABILITY=0.6`), maks `MODE_C_MAX_AI_STREAK=2`; hanya manusia yang memindah topik.
- **TTS:** Edge untuk pengembangan, ElevenLabs untuk demo (`TTS_PROVIDER`, `TTS_FALLBACK=edge,gtts`). Edge dari laptop ini lambat dan kadang timeout (20% giliran jatuh ke gTTS di uji 34 menit); gTTS satu suara untuk dua persona.
- **Default dari uji panjang:** `PERSONA_TIMEOUT_MS=20000` (10 s membuat 16,5% giliran jadi kalimat kaleng), `MAX_TURNS_PER_TOPIC=60` (40 membatasi sesi ke ±34 menit), `TTS_TIMEOUT_SEC=12`.
- `SUPERVISOR_MODE` default `off` (pass-through); isi penuh FR-5 dipertahankan (inti skripsi). Showrunner dipertahankan; keputusan dipetakan ke `lanjut | pindah_topik | tutup`.
- Field blocker `pertanyaan_penonton` tidak diubah; kata "tulis di komentar" diganti netral (`blocker-v3`).
- MuseTalk di laptop MX250: RTF ±410, tidak layak; belum diukur di GTX 1080. Clone di `D:\programming\work\musetalk` dibiarkan.

## Langkah berikutnya
1. Coba mode A dan C dengan mikrofon nyata di Chrome, lalu ukur latensi lepas-tombol sampai suara dengan ElevenLabs (KT FR-7).
2. Nilai transkrip `backend/sessions/show_20261030_113137_5204/turns.jsonl` dan perbaiki prompt/ringkasan sesuai temuan.
3. Isi penilaian FR-1 di `docs/kt/FR-1-blocker.md`; putuskan merge atau PR ke `main`.
4. Bersihkan PRD dan README dari sisa stage/avatar/komentar dan tambahkan mode C.
5. Mulai Tahap 7: harness offline (LLM `compat:`, `TTS_MODE=mock`) untuk kondisi Supervisor dan Showrunner.

## Catatan kerja
- `.env`, `backend/logs/`, `backend/sessions/`, `backend/cache/` di-ignore git. `.env` lokal saat ini `TTS_PROVIDER=elevenlabs`, `SUPERVISOR_MODE=off`.
- `load_personas()` di-cache: tes tidak boleh memutasi hasilnya (salin dulu).
- Konsol Windows (cp1252) gagal mencetak "≤" atau "→"; skrip memakai `PYTHONIOENCODING=utf-8` atau `reconfigure`.
- Server preview kadang dihentikan aplikasi; nyalakan ulang bila halaman tidak terbuka.
