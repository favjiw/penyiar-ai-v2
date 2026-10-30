# Audit strip: avatar, lip-sync, stage, dan komentar

Tanggal: 30 Okt 2026. Branch kerja: `feat/topik-percakapan`. Arsip kondisi sebelum penghapusan: branch `archive/avatar-dan-komentar` dan tag `pre-strip` (keduanya sudah di-push). **Belum ada file yang dihapus.**

Sumber audit: `git ls-files` (135 file), grep seluruh `backend/`, `frontend/src/`, konfigurasi, dan dokumen.

## Temuan utama

1. **Fitur komentar tidak pernah dibuat di repo ini.** Tidak ada modul TikTokLive, `comments/queue.py`, panel komentar di UI, atau segmen komentar (FR-13 masih Tahap 6 "Belum"). Sisanya hanya dua variabel konfigurasi (`COMMENTS_ENABLED`, `TIKTOK_USERNAME`) dan kata "komentar" di prompt (lihat bagian Prompt).
2. **Tidak ada sisa three.js, VRM, MetaHuman, Audio2Face, format clock, jingle, PSA, atau modul musik.** Semuanya sudah ditinggalkan di repo lama sejak PRD §12 dan tidak pernah disalin. `package.json` hanya memuat react, react-dom, vite, typescript.
3. **Yang harus dihapus hanya satu rumpun:** avatar berbasis video (T1), lip-sync MuseTalk (T2), halaman `/stage`, dan jejaknya di backend, konfigurasi, tes, dan dokumen.
4. **Setelah `/stage` hilang, konsol menjadi satu-satunya pemilik audio.** Orb (Fase 2) dan transkrip harus tinggal di halaman yang memutar audio, supaya `AnalyserNode` bisa membaca amplitudonya. Lihat Pertanyaan 1.

## Tabel audit

### Frontend

| File / folder | Fungsi | Kategori | Dependensi terdampak |
|---|---|---|---|
| `frontend/src/stage/StagePage.tsx` | Halaman `/stage` 9:16 untuk OBS: dua panel avatar, HUD, label AI, overlay zona aman | HAPUS | `App.tsx` (route `/stage`, import) |
| `frontend/src/stage/VideoAvatar.tsx` | Pemutar bank klip Flow: crossfade dua `<video>`, state idle/listen/talk/react, preload blob, sinkron lip-sync | HAPUS | `StagePage.tsx` |
| `frontend/src/stage/layout.ts` | Zona aman UI TikTok (header, bar bawah, "Daftar komentar", margin sisi) | HAPUS | `StagePage.tsx` |
| `frontend/src/stage/stage.css` | Gaya panel avatar, nameplate, HUD, zona | HAPUS | `StagePage.tsx` |
| `frontend/src/live/useLiveSession.ts` (bagian `lipsync`, `videos`, `LipSync`, `setLipsync`) | Video lip-sync per bagian audio | HAPUS (edit, bukan hapus file) | `StagePage.tsx` (satu-satunya pemakai `lipsync`) |
| `frontend/src/live/useLiveSession.ts` (role `'stage'`, `audioBlocked` untuk stage) | Role WS stage dan pembukaan audio yang diblokir autoplay | EDIT | `ws.py`, `LivePanel.tsx`. Pemblokiran autoplay tetap relevan untuk konsol |
| `frontend/src/live/types.ts` (`video_url`, `stage_connected`) | Tipe event | HAPUS (edit) | `useLiveSession.ts`, `LivePanel.tsx` |
| `frontend/src/console/LivePanel.tsx` (`openStage`, `STAGE_*`, tombol "Buka Stage", `stage_connected`) | Popup stage 540×960 untuk OBS | HAPUS (edit) | `api.ts` precheck |
| `frontend/src/App.tsx` (route `/stage`) | Routing | HAPUS (edit) | – |
| `frontend/src/api.ts` (`output.stage_connected` pada precheck) | Tipe respons cek pra-live | EDIT | `LivePanel.tsx` |
| `frontend/vite.config.ts` (proxy `/avatar-assets`) | Proxy aset klip | HAPUS (edit) | – |
| `frontend/src/prompter/*` | Prompter penyiar: blocker, poin, saran, PTT Web Speech, transkrip | **PERTAHANKAN** | PTT = ASR yang diminta dipertahankan |
| `frontend/src/console/BlockerStudio.tsx`, `BlockerEditor.tsx`, `VariantCard.tsx` | Generator dan editor Blocker | PERTAHANKAN | Fase 3 memakai ini |

### Backend

| File / folder | Fungsi | Kategori | Dependensi terdampak |
|---|---|---|---|
| `backend/app/avatar/` (`t2_client.py`, `__init__.py`) | Klien worker lip-sync T2 | HAPUS | `show/engine.py` (import `T2Client`, `self.t2`, `_render_avatar`), `tests/test_avatar_t2.py` |
| `backend/app/show/engine.py` (T2, `video_url` di event `turn`, `avatar_render`) | Pemanggilan render T2 per giliran | HAPUS (edit) | `mode_a.py` |
| `backend/app/show/mode_a.py` (`video_url`, `render_ms`, `_render_avatar`) | Sama, per kalimat | HAPUS (edit) | – |
| `backend/app/schemas.py` (`TurnRecord.video_url`, `LatencyMs.avatar_render`) | Medan log avatar | HAPUS (edit) | `scripts/report.py`, log lama |
| `backend/app/config.py` (`AVATAR_TIER`, `AVATAR_WORKER_URL`, `AVATAR_RENDER_TIMEOUT_MS`, `AVATAR_DIR`) | Konfigurasi avatar | HAPUS (edit) | `main.py`, `tests/test_api.py` |
| `backend/app/config.py` (`COMMENTS_ENABLED`, `TIKTOK_USERNAME`) | Saklar fitur komentar yang tidak pernah ada | HAPUS (edit) | `.env.example` |
| `backend/app/main.py` (mount `/avatar-assets`, `mkdir AVATAR_DIR`) | Menyajikan klip | HAPUS (edit) | `tests/test_api.py::test_avatar_assets_are_served` |
| `backend/app/ws.py` (role `stage`, prioritas pemilik audio `stage` > `console`, `stage_connected`) | Routing audio ke stage | EDIT: role `stage` dibuang, pemilik audio = konsol | `show/api.py`, tes WS |
| `backend/tests/test_avatar_t2.py` | Tes jalur T2 | HAPUS | – |
| `backend/tests/test_api.py` (`test_avatar_assets_are_served`, `AVATAR_DIR`) | Tes aset klip | HAPUS (edit) | – |
| `backend/tests/test_show_api.py` (`test_stage_plays_whole_show_over_websocket`) | Tes siaran lewat WS role stage | UBAH: pakai role `console` | – |
| `backend/app/tts/provider.py` | ElevenLabs, Edge, cache, breaker | PERTAHANKAN (direfaktor di Fase 2b) | – |
| `backend/app/tts/filler.py` + `data/filler.json` | Bank filler mode A | PERTAHANKAN | – |
| `backend/app/llm/*`, `blocker/*`, `agents/persona.py`, `agents/hits_style.py` | Pemanggilan LLM, Blocker, persona | PERTAHANKAN | – |

### Aset, skrip, dokumen, konfigurasi

| File / folder | Fungsi | Kategori | Catatan |
|---|---|---|---|
| `avatar-worker/` (README, `lipsync.py`, `server.py`, `requirements.txt`) | Worker MuseTalk | HAPUS | Tetap tersimpan di branch arsip |
| `avatar-worker/avatars/` (lokal, di-ignore, **680 MB**) | Material avatar hasil `prepare` | HAPUS (lokal) | Bisa dibuat ulang dari klip |
| `assets/avatar/raka/manifest.json` (terlacak) | Manifest klip Raka | HAPUS | – |
| `assets/avatar/raka/*.mp4` (lokal, di-ignore, 27 MB, 15 klip) | Klip Flow | HAPUS (lokal) | **Tidak ada di arsip git** (di-ignore). Salinan asli masih ada di `Downloads\video\raka` |
| `assets/make_dummy_clips.py` | Pembuat klip dummy | HAPUS | – |
| `tahap0/t2_rtf.py`, `tahap0/crossfade_test.html` | Uji kelayakan T2 dan crossfade | HAPUS | Sisa `tahap0/` (STT, TTS, kuota) dipertahankan |
| `docs/obs-setup.md`, `docs/flow-prompts.md` | Panduan OBS dan prompt Flow | HAPUS | – |
| `docs/kt/avatar-t2-musetalk.md` | Hasil uji MuseTalk (RTF ±410 di MX250) | HAPUS | Temuan tersimpan di branch arsip |
| `.gitignore` (blok avatar), `.env.example` (`AVATAR_*`, `COMMENTS_ENABLED`, `TIKTOK_USERNAME`) | Konfigurasi | HAPUS (edit) | – |
| `README.md` (baris stage/OBS, tabel struktur) | Dokumentasi | EDIT | – |
| `docs/ANALISIS-LIVE-TIKTOK-2026-10-20.md`, `docs/TRANSKRIP-LIVE-TIKTOK-2026-10-20.md` | Bahan kalibrasi Showrunner dan baseline | PERTAHANKAN | Nama berisi "TikTok", isinya rujukan percakapan |
| `docs/kt/*` lain (gerbang Tahap 2, FR-1, tahap4-mode-a, llm-compat) | Laporan uji | PERTAHANKAN | – |
| `PRD.md` | Acuan tunggal proyek | **EDIT setelah persetujuan** | Lihat Konflik dengan PRD |

### Di luar repo (tidak dihapus tanpa izin)

| Lokasi | Isi | Ukuran |
|---|---|---|
| `D:\programming\work\musetalk\` | Clone MuseTalk, venv CUDA, bobot model | ±5 GB (menyusul) |
| `D:\programming\work\.hf-cache`, `.pip-cache`, `.torch-cache` | Cache unduhan | menyusul |

`D:\programming\work\char-3d`, `kp`, `penyiar-ai`, `sellution` tidak terkait dan tidak disentuh.

## Kategori TANYA (tidak dihapus, hanya dilaporkan)

| Item | Temuan |
|---|---|
| Rundown format clock, jingle, PSA, iklan, state machine slot | **Tidak ada di repo ini.** Tinggal di repo lama `conversational-ai`. Tidak ada yang perlu diputuskan. |
| Modul musik | **Tidak ada.** |
| Integrasi TikTok LIVE / OBS | Hanya jejak: `docs/obs-setup.md`, README, komentar kode di `ws.py` ("output OBS"), judul dokumen live TikTok 20 Okt. Diurus bersama rumpun stage di atas. |
| **Supervisor** (`agents/supervisor.py`, `prompts/supervisor.md`, `data/supervisor/*`, `tests/test_supervisor.py`) | **Sudah diimplementasikan penuh** (aturan cepat, LLM, ledger, regenerasi, bank kalimat aman), jauh melampaui "hook pass-through yang isinya belum ada" di spesifikasi. Ini fokus skripsi. Usul: **dipertahankan**, dan hook `supervisor.check()` dibuat sebagai pembungkus tipis dengan default `SUPERVISOR_MODE=off` (pass-through). |
| **Showrunner** (`agents/showrunner.py`, `prompts/showrunner.md`) | Sudah ada tiga kebijakan (`llm`, `fixed_turns`, `coverage_only`) dan jatah waktu topik. Spesifikasi meminta "sederhana" dengan keputusan `lanjut / pindah_topik / tutup`. Usul: **dipertahankan**, dipetakan ke antarmuka yang diminta, dengan tombol override operator. |
| Mode A saat ini (`show/mode_a.py`, `ModeAEngine`) | Subkelas `ShowEngine` dengan dua persona tetap. Spesifikasi meminta satu engine dengan daftar peserta (untuk mode A/B/C dan kelak >2 AI). Butuh refaktor di Fase 4, bukan penghapusan. |
| Penamaan `ai_persona` / `human` | Terpakai di mode A, prompter, dan tes; berubah bersama refaktor peserta. |

## Prompt dan kata "komentar" (TANYA)

Kata "komentar" di prompt ada dua jenis, dan hanya jenis pertama yang sejalan dengan "hapus fitur komentar":

| Lokasi | Isi | Usul |
|---|---|---|
| `persona.py:37` (dialog act `audience`), `persona.py:278`, `data/supervisor/fallback.json:16`, `blocker/generator.py:219`, `prompts/blocker.md:16, 52`, `scripts/mode_a_probe.py:33, 37` | Ajakan ke penonton **"tulis di komentar"** atau contoh ucapan "ada komentar nih dari penonton" | Diganti kata netral ("ajak penonton menanggapi") karena live ditunda dan format menjadi podcast. Nama field blocker `pertanyaan_penonton` **tidak diubah** (ada di PRD §9.1 dan di blocker yang sudah tersimpan). |
| `persona.md:18`, `supervisor.md:15, 20` | **Larangan** mengarang isi komentar atau akun penonton | **Dipertahankan.** Ini pagar anti-halusinasi, bukan fitur komentar. |

## Dampak pada rencana fase berikutnya

- **Fase 1 (hapus):** `tsc` dan 96 tes harus tetap hijau. Tes yang hilang: `test_avatar_t2.py` (3 tes) dan satu tes aset avatar. Satu tes WS stage diubah ke role `console`.
- **Fase 2 (orb):** tidak ada lagi halaman stage. Orb, indikator mikrofon, dan transkrip dibuat di tab Live konsol, yang juga pemilik audio. Pemutaran audio berpindah dari `HTMLAudioElement` ke jalur Web Audio (`AnalyserNode`).
- **Fase 2b (TTS):** `FailoverTTS` sudah punya ElevenLabs + Edge + breaker + cache. Perubahannya: antarmuka `TTSProvider` eksplisit, `GTTSProvider` baru (dependensi `gTTS`, gratis), default Edge, dan nama variabel `TTS_PRIMARY` → `TTS_PROVIDER`.
- **Fase 4 (mode C, log):** log sesi sekarang `logs/<session_id>.jsonl` dengan event bertipe; spesifikasi meminta `sessions/<id>/turns.jsonl` dan `blocker.json` dengan field berbeda. `scripts/report.py` perlu menyesuaikan.
- **Mode B 30 menit:** kuota Gemini free tier 500 RPD per model. Dengan Supervisor `off` (pass-through) pemakaian turun, jadi 30 menit seharusnya aman. Uji panjang sebelumnya terganggu DNS laptop yang putus-sambung (`tahap2-gate-5.md`).

## Konflik dengan PRD (diminta oleh aturan PRD §0 untuk dilaporkan dulu)

PRD adalah acuan tunggal dan masih memuat bagian yang akan dihapus atau berubah:

- FR-8 (avatar T1), FR-9 (T2), FR-10 (stage/OBS), FR-13 (komentar), Lampiran A (klip Flow), §6.1 dan §11 (struktur), Tahap 3, 5, dan 6 di §13/§16.
- **Mode C** (manusia + 2 AI) tidak ada di PRD; PRD hanya mengenal mode A dan B.
- PRD menetapkan **ElevenLabs sebagai TTS utama** [F]; spesifikasi baru menjadikan Edge default selama pengembangan dan ElevenLabs untuk demo.
- PRD melarang model/kuota di-hard-code dan meminta log di `logs/{session_id}.jsonl`.

Usul: setelah Fase 1 disetujui, saya perbarui PRD menjadi v2.5 dan mencatatnya di §17, sebelum menulis kode Fase 2 ke atas.

## Pertanyaan sebelum lanjut ke Fase 1

1. **Lokasi orb dan audio.** Setelah stage dihapus, usul saya: orb + transkrip di tab **Live** konsol (pemilik audio), prompter tetap halaman terpisah untuk penyiar. Setuju, atau orb di halaman baru?
2. **Supervisor dan Showrunner.** Dipertahankan dengan default `off` / antarmuka yang diminta (usul), atau dihapus dan ditulis ulang sederhana?
3. **Kata "komentar" di prompt.** Diganti netral dan field `pertanyaan_penonton` tetap (usul), atau seluruh bahasa "penonton" ikut dibuang karena formatnya podcast?
4. **Klip Flow lokal (27 MB) dan `avatar-worker/avatars` (680 MB).** Boleh dihapus dari disk? Klip asli masih ada di `Downloads\video\raka`; yang di `assets/` hanya salinan tanpa audio.
5. **Di luar repo:** `D:\programming\work\musetalk` (clone + venv + bobot) dan cache `.hf-cache`, `.pip-cache`, `.torch-cache` dihapus juga, atau dibiarkan?
6. **Dokumen avatar** (`obs-setup.md`, `flow-prompts.md`, `avatar-t2-musetalk.md`): dihapus dari branch kerja (tetap ada di arsip), atau dipindah ke `docs/arsip/`?
