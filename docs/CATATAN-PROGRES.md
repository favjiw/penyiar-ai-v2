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

## Fase 2b: lapisan TTS yang bisa diganti (selesai, 30 Okt 2026)

- Antarmuka `TTSProvider.synthesize(text, persona) -> AudioResult` di `backend/app/tts/base.py`. Engine, bank filler, dan cek pra-live hanya memakai `FailoverTTS.synthesize(text, persona_id)`; tidak ada pemanggilan provider langsung.
- Provider: `EdgeTTSProvider` (default, tanpa key; Raka `id-ID-ArdiNeural`, Salsa `id-ID-GadisNeural`, rate dan pitch per persona dari `.env`), `ElevenLabsTTSProvider` (dipindah, voice ID per persona), `GTTSProvider` (`id`, cadangan).
- Pemilihan lewat `.env`: `TTS_PROVIDER=edge|elevenlabs` (menggantikan `TTS_PRIMARY`), `TTS_FALLBACK` (daftar dipisah koma, default `gtts`), `TTS_RETRIES=1`, `TTS_TIMEOUT_SEC=12`. Demo ke pembimbing: `TTS_PROVIDER=elevenlabs` dan `TTS_FALLBACK=edge,gtts`.
- Kegagalan: provider utama diulang sekali (galat, timeout, atau audio kosong/durasi 0), lalu cadangan berurutan; breaker melewati provider yang gagal beruntun selama 60 s. Operator melihat peringatan saat cadangan dipakai (sekali per provider) dan saat sebuah giliran tidak punya suara sama sekali.
- `TTS_PROVIDER=elevenlabs` tanpa key atau model: peringatan di konsol (banner di bawah header, juga di log) dan jatuh ke Edge, tanpa crash.
- Log giliran: `tts_provider`, `tts_fallback_used` (dan `tts_fallback_reason`). Header konsol menampilkan provider aktif, mis. "TTS: Edge (gratis)" atau "TTS: ElevenLabs → Edge (gratis) aktif".
- Kunci cache audio memuat voice, rate, dan pitch; mengubah prosodi tidak memutar audio lama. Filler baru menimpa file lama.
- `scripts/test_tts.py`: satu kalimat per persona per provider yang tersedia; memeriksa audio tidak kosong, durasi lebih dari 0, MP3 valid, dan suara Raka berbeda dari Salsa.

**Diverifikasi**
- 107 tes backend lulus (termasuk retry, fallback berurutan, breaker, audio kosong, pemetaan voice, prosodi Edge, pemilihan provider, peringatan tanpa key, dan log `tts_fallback_used`).
- `test_tts.py` nyata untuk Edge dan gTTS: 4 sintesis lulus; durasi hitungan CBR Edge sama dengan jumlah frame MP3 (4,39 s dan 5,64 s).
- Rantai cadangan nyata dengan key ElevenLabs sengaja salah (HTTP 401, tanpa biaya): ElevenLabs diulang sekali, breaker terbuka, lalu Edge, lalu gTTS; tanpa cadangan muncul galat jelas.
- Mode B 3 menit di browser (LLM mock, Edge asli): 24 giliran, semuanya Edge, 0 cadangan, tanpa galat; latensi TTS p50 3,1 s, p95 4,7 s, maks 9,1 s. Label header dan orb sesuai.

**Belum diverifikasi**
- ElevenLabs dengan key valid lewat lapisan baru (kode sama dengan yang sudah teruji di Tahap 0, tetapi tidak dijalankan ulang agar tidak memakai kredit); jalankan `python scripts/test_tts.py --providers elevenlabs` sebelum demo.
- Seberapa natural suara Edge dengan rate/pitch bawaan (Raka `+4%`/`-2Hz`, Salsa `+6%`/`+2Hz`): ini titik awal tebakan, belum didengar. Berkas contoh ada di `backend/cache/test_tts/`.
- Tampilan banner peringatan di browser (logikanya diuji di backend dan lewat typecheck).

**Catatan**
- Edge dari laptop ini lambat dan berjitter (1,6 s sampai 9 s per kalimat). Timeout awal 8 s sempat terlewati satu kali dalam uji, jadi default dinaikkan ke 12 s: pindah ke suara lain di tengah siaran lebih buruk daripada menunggu.
- gTTS hanya punya satu suara, sehingga Raka dan Salsa terdengar sama selama cadangan ini dipakai.
- Edge adalah pustaka tidak resmi; bila diblokir, gTTS menjadi satu-satunya suara gratis.

## Fase 3: pembuatan topik, Tema → Blocker (selesai, 30 Okt 2026)

Sebagian besar sudah ada dari FR-1 (Tahap 1) dan dipertahankan: tema → 3 varian (default 3, pilihan 2-3), 1-3 topik per varian, tiap topik berisi judul, sudut pandang, poin, pertanyaan ke penonton, dan kalimat transisi; keluaran LLM berupa JSON terstruktur yang divalidasi; editor inline (ubah semua field, tambah/hapus/geser poin dan topik, maks 3 topik); kunci dengan versi baru untuk perubahan. Yang ditambah di Fase 3:

- **Retry parse maksimal 2 kali** (3 percobaan), tiap ulang membawa alasan penolakan terbaru. Sebelumnya hanya 1 kali. Log `blocker_generations.jsonl` mencatat jumlah percobaan; UI menampilkan "diulang N×".
- **Aturan saat mengunci** (server `validate_for_lock`, dicerminkan di UI `lockProblems`): 3-5 poin per topik, hook Opening, rangkuman dan ajakan Closing, serta sudut pandang, pertanyaan, dan transisi tiap topik tidak boleh kosong. Semua masalah dilaporkan sekaligus, dan UI menolak sebelum dialog konfirmasi muncul. Draf boleh belum rapi; tombol "+ Poin" berhenti di 5.
- **`sessions/<session_id>/blocker.json`**: tiap sesi (mode A dan B) menyalin blocker terkunci yang dipakai saat dimulai. Folder default berada di samping `LOG_DIR` (`backend/sessions/`, di-ignore git), bisa diubah dengan `SESSIONS_DIR`.
- **Prompter menampilkan blocker terkunci**: snapshot memuat `rundown`; prompter menampilkan langkah Opening → topik → Closing (selesai, sedang, berikutnya), hook dan poin Opening besar saat Opening, rangkuman dan ajakan saat Closing, sudut pandang dan kalimat transisi saat topik, dan panel "Seluruh blocker".
- Konteks AI dari blocker terkunci sudah ada sejak Tahap 2 (opening, topik aktif beserta poin yang belum tercakup, transisi); tidak diubah.

**Diverifikasi**
- 116 tes backend lulus (retry 1-3 percobaan, gagal tepat 3 panggilan, aturan kunci per kasus, blocker.json mode A dan B, rundown di snapshot).
- Browser dengan Gemini asli (`gemini-3.5-flash-lite`): tema "Ospek" menghasilkan 3 varian dalam 8,5 s tanpa ulang; "+ Poin" berhenti di 5; kunci dengan poin kurang ditolak tanpa dialog dan menyebut "Topik 1: 1 poin, harus 3-5"; kunci valid menghasilkan `blk_20261030_ospek_ca19`; mode A dengan blocker itu menulis `sessions/<id>/blocker.json` (4/3/3 poin) dan prompter menampilkan hook, langkah rundown, dan kalimat transisi.

**Belum diverifikasi / catatan**
- Retry dengan LLM asli yang benar-benar gagal parse (hanya diuji dengan LLM tiruan; satu-satunya generate asli berhasil percobaan pertama).
- Penilaian "layak siar" 8 dari 10 tema (KT FR-1) masih menunggu Anda: `docs/kt/FR-1-blocker.md`.
- Konsol belum menampilkan peringatan khusus untuk poin `perlu_cek` selain konfirmasi saat mengunci (perilaku lama).
- Blocker lama yang sudah terkunci dengan kurang dari 3 poin tetap bisa dipakai (aturan hanya berlaku saat mengunci).

## Fase 4: mode A / B / C, log riset, hook Supervisor (30 Okt 2026)

**Keputusan desain: satu kerangka, dua kelas.** Spesifikasi meminta satu engine bersama dengan daftar peserta. Saya tidak menulis ulang `ShowEngine` (pipelining, skip, kuota, batas waktu mode B sudah teruji 21 menit) dan memilih:
- `ShowEngine` (mode B) dan `HumanLedEngine` (mode A dan C, di `show/mode_a.py`) **berbagi** state machine, konteks persona, hook Supervisor, TTS, pemutaran, ringkasan obrolan, dan log.
- Peserta berupa daftar (`show/participants.py`: `Participant`, `build_participants`, `addressed_ais`). Kode tidak lagi menyebut "raka" atau "salsa" di jalur giliran; `_pick_speaker` bergilir menurut daftar, dan tes mode B dengan tiga AI lulus.
- Yang belum satu kelas: loop otomatis (B) dan pertukaran dipicu manusia (A/C) tetap dua implementasi giliran. Menyatukannya menunggu alasan nyata (mis. mode dengan manusia yang bisa diam lama).

**Mode**
- **A:** manusia + 1 AI pilihan operator. PTT → filler → jawaban singkat; manusia menekan "Topik berikutnya". (Perilaku sebelumnya, kini lewat kerangka bersama.)
- **B:** AI bergantian otomatis; Showrunner memutuskan. Antarmuka keputusan: `continue/steer` = `lanjut`, `transition` = `pindah_topik`, `close` = `tutup` (medan `aksi` di keputusan dan log); override operator = tombol Next/Stop.
- **C:** manusia + Raka + Salsa. AI yang disapa namanya menjawab ("kalian" menyapa keduanya; tanpa sapaan bergantian). AI lain boleh menimpali (peluang `MODE_C_CHIME_PROBABILITY=0.6`, wajib bila dua AI disapa), maksimal `MODE_C_MAX_AI_STREAK=2` giliran AI berturut-turut, lalu kembali ke manusia. Hanya manusia yang memindah topik. Selagi menunggu manusia kedua orb `listening`; orb `thinking` hanya untuk AI yang sedang membuat jawaban (`snapshot.thinking`, bukan tebakan sisi klien lagi).

**Prompt persona** (`persona-v2`): daftar peserta lain dengan perannya, ringkasan obrolan sebelumnya, instruksi menimpali (mode C), dan tanpa rujukan ke komentar. Panjang jawaban mode A dan C 1-3 kalimat (menimpali 1-2).

**Ringkasan obrolan** (`agents/summary.py`, prompt `summary-v1`): giliran yang keluar dari jendela 12 giliran dirangkum di latar belakang tiap 10 giliran dengan model peran Showrunner (tidak menahan giliran). LLM gagal → kutipan ekstraktif. Ini biaya +1 panggilan LLM per 10 giliran.

**Supervisor:** `Supervisor.check()` berada di antara LLM dan TTS pada semua mode, kosakata `teruskan | koreksi | ganti`. `SUPERVISOR_MODE` kini default **`off`** (pass-through). Isi lengkap FR-5 tetap ada dan menyala dengan `rules` atau `full`; tidak dihapus karena itu inti skripsi.

**Log riset** `sessions/<id>/turns.jsonl` (manusia dan AI): medan wajib `session_id, mode, turn_idx, speaker, is_human, topic_idx, text, t_start, t_end, latency_asr_ms, latency_llm_ms, latency_tts_ms, model, tts_chars, filler_used`, ditambah nama, segmen, `raw_text`, `latency_supervisor_ms`, `gap_before_play_ms`, `supervisor_action`, `tts_provider`, `tts_fallback_used`, `dialog_act`, `interrupted`. Arti waktu: AI = audio mulai dan selesai diputar; manusia = tombol bicara ditekan dan dilepas (`speech_ms` dari prompter). `latency_asr_ms` pada giliran AI pertama sesudah manusia = ASR ucapan pemicunya. `tts_chars` = jumlah karakter yang dikirim ke TTS (jumlah bagian kalimat). `topic_idx` berbasis 0, `null` di Opening/Closing. Log event lengkap tetap di `logs/<id>.jsonl`.

**Filler:** bank disiapkan paralel (4 sekaligus) untuk semua AI. Sebelumnya berurutan: dengan Edge, 36 filler butuh lebih dari satu menit, dan ucapan pertama penyiar di mode C sempat tidak mendapat filler untuk AI kedua.

**Diverifikasi**
- 139 tes backend lulus (turunan: peserta, sapaan, urutan AI, batas streak, "kalian", prompt menimpali, `thinking` di snapshot, interupsi, `turns.jsonl` manusia + AI + mode B, hook, ringkasan sukses dan gagal, tiga AI di mode B, API mode C).
- Browser dengan Gemini dan Edge asli: mode C dipilih di UI (dua orb, indikator mikrofon, tombol prompter), "Salsa, menurut lo ospek itu seru atau malah bikin capek?" dijawab Salsa (orb `thinking` ±8 s, lalu `speaking`), Raka menimpali ("Ciee yang tebar pesona..."), streak berhenti di 2 dan kedua orb kembali `listening`; `turns.jsonl` berisi tiga baris (manusia 350 ms ASR, Salsa, Raka) dengan semua medan wajib.
- Probe headless mode C (`scripts/mode_a_probe.py --mode C`) dengan LLM tiruan.

**Uji mode B panjang (headless, real time, Gemini `gemini-3.5-flash-lite` dan Edge asli, blocker Ospek 3 topik)**

| | Sesi 1 | Sesi 2 |
|---|---|---|
| Konfigurasi | `PERSONA_TIMEOUT_MS=10000`, `MAX_TURNS_PER_TOPIC=40`, target 34 menit | `PERSONA_TIMEOUT_MS=20000`, `MAX_TURNS_PER_TOPIC=40`, target 42 menit |
| Hasil | selesai, tanpa crash | selesai, tanpa crash |
| Durasi | **28,5 menit**, 127 giliran | **34,2 menit**, 127 giliran |
| Giliran berupa kalimat kaleng (persona timeout) | **21 dari 127 (16,5%)** | 3 dari 127 (2,4%) |
| Giliran dengan suara cadangan gTTS | 9 | **25 (20%)** |
| Giliran tanpa suara sama sekali | 1 (Edge dan gTTS sama-sama timeout) | 0 |
| Latensi persona p50 / p95 / maks | 2,3 s / 8,1 s / 9,4 s (hanya yang berhasil) | 3,1 s / 16,0 s / 19,9 s |
| TTS p50 / p95 / maks | 3,6 s / 9,7 s / 11,5 s | 3,7 s / 9,7 s / 11,7 s |
| Jeda sebelum suara p50 / p95 / maks | 0 / 11,9 s / 24,0 s | 0,3 s / 17,5 s / 23,1 s |
| `turns.jsonl` | 127 baris, 0 terpotong | 127 baris, 0 terpotong, span 34,0 menit |
| Keputusan Showrunner | 42 (budget 1+) | 42: lanjut 12, arahkan 27, pindah 2, tutup 1 |

Temuan:
- **Syarat 30 menit tercapai pada sesi 2** (34,2 menit); sesi 1 berhenti di 28,5 menit karena target 34 menit habis lebih cepat dari jatah topik.
- **Batas 40 giliran per topik (`MAX_TURNS_PER_TOPIC`) membatasi sesi.** Pada sesi 2 ketiga topik berhenti di 41 giliran (3 transisi `forced`), padahal jatah waktu belum habis. Dengan sekitar 15 s per giliran, 40 giliran × 3 topik hanya muat ±34 menit. Default dinaikkan ke **60** supaya target 40+ menit mungkin.
- **Persona timeout 10 s terlalu ketat untuk Gemini free tier hari ini:** 16,5% giliran menjadi kalimat kaleng ("Oke, lanjut."), yang merusak transkrip riset. Default dinaikkan ke **20 s** (sesi 2: 2,4%). Konsekuensinya jeda sunyi bisa sampai ±23 s di sesi yang tidak ditonton; untuk demo langsung pakai nilai lebih kecil atau model lain.
- **Edge TTS dari laptop ini tidak stabil:** 20% giliran sesi 2 diputar dengan gTTS karena Edge timeout 12 s dua kali beruntun (breaker 60 s). gTTS satu suara untuk dua persona, jadi dua penyiar terdengar sama pada giliran itu. Untuk uji dengar atau demo pakai ElevenLabs; untuk sesi Edge yang panjang pertimbangkan `TTS_TIMEOUT_SEC=20`.
- Tidak ada galat engine, kuota harian tidak habis (tanpa pindah model), 0 giliran terpotong.

**Catatan dari uji**
- **Edge TTS lambat untuk mode A/C:** jawaban tiga kalimat Salsa butuh TTS 11,3 s (sekitar 3-4 s per kalimat) dan jeda lepas-tombol sampai suara 7,7 s. Ini batas Edge dari laptop ini, bukan engine; ElevenLabs sebelumnya p50 0,55 s. Untuk uji latensi FR-7 pakai `TTS_PROVIDER=elevenlabs`.
- Pembukaan "kita berdua penyiar AI HITS" muncul pada jawaban pertama di segmen Opening karena instruksi pengungkapan AI; ini membuat jawaban pertama lebih dari 1-3 kalimat.
- AI yang menimpali mengutip rekannya dengan baik, tetapi persona di prompt masih mengandalkan "live TikTok HITS" sebagai konteks program (belum diubah).

## Masih terbuka

- Uji mode A dan C dengan **mikrofon dan Web Speech nyata** di Chrome (yang diuji: `/api/ptt/turn` dengan teks dan sinyal mikrofon simulasi).
- Sesi mode A/C yang panjang (hanya mode B yang diuji 30+ menit). Showrunner mode saran di C menghitung satu pertukaran sebagai 1 + jumlah giliran AI; belum dikalibrasi.
- Kualitas percakapan itu sendiri: belum ada penilaian terhadap transkrip 34 menit (pengulangan, konsistensi persona, keterkaitan dengan blocker, efek ringkasan). Transkripnya ada di `backend/sessions/show_20261030_113137_5204/turns.jsonl`; log riset sudah lengkap untuk itu.
- Persona di mode C yang menimpali kadang terlalu panjang atau mengulang rekannya; belum diukur.
- Mode B dengan tiga AI hanya diuji di level unit (belum ada kartu persona ketiga).
- Prompt persona, Showrunner, dan Supervisor masih menyebut "live TikTok HITS" sebagai konteks program; belum diubah supaya versi prompt tidak bergeser.
- Bagian PRD §6.1, §6.3, §11, dan Lampiran B masih memuat stage/avatar/komentar sebagai rujukan sejarah.
