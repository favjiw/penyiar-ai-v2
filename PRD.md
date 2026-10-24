# PRD Penyiar AI Co-Host Live TikTok HITS (v2.2)

| | |
|---|---|
| Pemilik | Muhammad Favian Jiwani (Favian) |
| Tanggal | 24 Oktober 2026 |
| Status | Draf v2.2, Tahap 0 berjalan |
| Menggantikan | Semua PRD dan dokumen desain di repo `conversational-ai`: `PRD-KP-HITS-AI-Live*.md`, `PRD HITS AI Live v1.1`, `docs/avatar/PRD Avatar 3D…`, `docs/KEPUTUSAN-DESAIN.md`, `docs/RUNDOWN-LIVE-1-JAM-DRAF.md` |
| Repo | `favjiw/penyiar-ai-v2` (public) [F] |

## 0. Cara memakai dokumen ini

- Ini **satu-satunya PRD** untuk sistem versi revisi. Jangan membuat file PRD baru. Perubahan ditulis di sini, lalu dicatat di §17 (Riwayat).
- Letakkan file ini di root repo baru sebagai `PRD.md`, dan buat `CLAUDE.md` / `AGENTS.md` yang isinya cukup satu baris: `Acuan tunggal: @PRD.md`.
- Penanda asal keputusan:
  - **[F]** keputusan Favian.
  - **[C]** usulan Claude. Boleh diubah; bila diubah, tandai menjadi [F].
  - **[P]** arahan pembimbing HITS.
- Aturan untuk agen coding (Claude Code / Antigravity):
  1. Kerjakan satu tahap (§13) per sesi. Berhenti di akhir tahap untuk diperiksa Favian.
  2. Bila kode bertentangan dengan PRD, laporkan dulu sebelum mengubah.
  3. Jangan menulis model ID, harga, atau kuota secara hard-code; semuanya lewat `.env`.
  4. Jangan menyalin seluruh repo lama; ikuti peta pemakaian ulang di §12.
  5. Perbarui tabel status di §16 setiap kali satu tahap selesai.

---

## 1. Latar belakang dan perubahan dari versi sebelumnya

### 1.1 Konteks HITS [P]
Live TikTok HITS Unikom Radio adalah kamera yang merekam studio on-air: penyiar siaran radio dan live TikTok sekaligus. Lagu diputar tim produksi lewat Bass Pro dan hanya terdengar di on-air radio, tidak di TikTok.

### 1.2 Revisi pembimbing HITS (24 Okt 2026) dan dampaknya

| # | Revisi [P] | Dampak pada sistem |
|---|---|---|
| 1 | Moderasi komentar bukan output KP | Moderasi dikeluarkan dari KP. Untuk skripsi tetap ada sebagai fitur Supervisor [F] (FR-13). |
| 2 | Musik diputar di Bass Pro, tidak di TikTok | Pemutar lagu, rekomendasi lagu, dan slot lagu dihapus. |
| 3 | Fokus pada penyiar yang mengobrol | Sistem menjadi percakapan murni seperti podcast. |
| 4 | Mode: manusia + AI, dan AI + AI | Mode A dan Mode B (§3). |
| 5 | Jadwal bukan acuan wajib; pindah sesi dipandu penyiar | Tidak ada durasi slot. Mode A: penyiar menekan "next". Mode B: agen yang memutuskan [F]. |
| 6 | Karakter realistis seperti hasil Google Flow | Avatar VRM/GLB three.js ditinggalkan. Diganti avatar berbasis video (FR-8, FR-9). |
| 7 | Tema dari input teks | Parser `.docx` dihapus. |
| 8 | LLM membuat rundown tema untuk dipilih | Generator Blocker (FR-1). |

### 1.3 Keputusan lanjutan Favian (24 Okt 2026)
- Fokus hanya ke **siaran live TikTok**; jalur suara AI ke on-air radio belum dipikirkan [F].
- Rundown hanya berisi Opening → maksimal 3 topik → Closing. Tanpa jingle, PSA, spot, atau audio statis lain [F].
- Mode A: 1 penyiar manusia + 1 AI. Penyiar memilih lawan bicara AI (Raka atau Salsa) sebelum live [F].
- Mode B: AI + AI penuh otomatis; agen tahu kapan pindah topik [F].
- Tahap awal: komentar dibaca dan dipandu penyiar manusia, AI hanya menanggapi penyiar [F].
- Tanpa biaya: semua komponen harus gratis [F], **kecuali TTS**: ElevenLabs dipakai sebagai TTS utama (keputusan 24 Okt 2026, lihat FR-6) [F].
- Agen Showrunner disetujui dan menjadi fokus publikasi [F]. Supervisor tetap fokus skripsi.
- Isi topik di blocker mengikuti usulan Claude (FR-1) [F].
- Perangkat:
  - laptop MX250 (tidak cukup untuk model video neural);
  - PC lab GTX 1080 (VRAM perlu dicek: 1080 standar 8 GB, 1080 Ti 11 GB);
  - akun Google Flow Pro tersedia [F].

---

## 2. Tujuan, ruang lingkup, dan yang tidak dikerjakan

### 2.1 Tujuan
1. **KP:** HITS bisa menjalankan live TikTok berformat obrolan, baik manusia + AI maupun AI + AI, dari tema yang diketik produser atau penyiar.
2. **Skripsi:** merancang dan mengevaluasi **Supervisor** sebagai mekanisme AI-in-the-Loop yang menggantikan peran pengawas manusia, untuk menjaga konsistensi persona, kepatuhan pada blocker, dan keamanan isi.
3. **Publikasi:** merancang dan mengevaluasi **Showrunner**, yaitu LLM yang mengendalikan alur dan waktu transisi topik dalam percakapan multi-agen.

### 2.2 Pembagian ruang lingkup

| Fitur | KP | Skripsi | Publikasi |
|---|---|---|---|
| FR-1 Generator Blocker | ✓ | ✓ | ✓ (bahan uji) |
| FR-2 Show Engine (mode A dan B) | ✓ | ✓ | ✓ |
| FR-3 Persona Engine | ✓ | ✓ | ✓ |
| FR-4 Showrunner | ✓ (mode B) | ✓ | **fokus** |
| FR-5 Supervisor | versi dasar (keamanan) | **fokus** | – |
| FR-6 TTS | ✓ | ✓ | – |
| FR-7 Input penyiar (PTT + STT) | ✓ | ✓ | – |
| FR-8 Avatar T1 (bank klip) | ✓ | ✓ | – |
| FR-9 Avatar T2 (lip-sync neural) | opsional | opsional | – |
| FR-10 Stage / output OBS | ✓ | ✓ | – |
| FR-11 Konsol operator dan prompter | ✓ | ✓ | – |
| FR-12 Logging | ✓ | ✓ | ✓ |
| FR-13 Panel komentar + Supervisor | – | ✓ | – |
| FR-14 Harness eksperimen | – | ✓ | ✓ |

### 2.3 Tidak dikerjakan
- Pemutaran dan rekomendasi lagu.
- Jingle, PSA, spot/adlibs, dan time signal.
- Parsing dokumen Tema `.docx`.
- Jalur audio ke on-air radio.
- AI membaca komentar TikTok sendiri (setidaknya di tahap awal).
- Telepon pendengar.
- Roleplay 3M/SKEMA.
- Layanan berbayar apa pun selain ElevenLabs untuk TTS [F]: HeyGen, Tavus, GPU cloud berbayar, dan sejenisnya.

---

## 3. Istilah dan definisi operasional

| Istilah | Definisi di sistem ini |
|---|---|
| **Tema** | Kata kunci atau frasa pendek yang diketik pengguna, misalnya "Ospek" atau "Zodiak". |
| **Blocker** | Rundown hasil LLM yang sudah dipilih, diedit, dan dikunci: Opening, 1–3 Topik, Closing. Dibaca penyiar manusia (prompter) dan dipakai AI sebagai konteks. |
| **Topik** | Satu bagian blocker berisi judul, sudut pandang, poin obrolan, pertanyaan ke penonton, dan kalimat transisi. |
| **Giliran (turn)** | Satu ucapan utuh satu penyiar. |
| **Mode A** | 1 penyiar manusia + 1 penyiar AI. Penyiar manusia memandu, membaca komentar, dan menekan "next topik". |
| **Mode B** | 2 penyiar AI (Raka dan Salsa), berjalan otomatis. Showrunner memutuskan transisi. |
| **Persona** | Kartu identitas penyiar AI: Raka (pria) dan Salsa (wanita). |
| **Showrunner** | Agen LLM yang memantau cakupan poin, kejenuhan obrolan, dan keputusan lanjut / arahkan / pindah topik / tutup. Di mode A hanya memberi saran. |
| **Supervisor** | Agen LLM yang memeriksa setiap ucapan AI sebelum diubah menjadi suara. Hasilnya: teruskan, koreksi (buat ulang dengan memori koreksi), atau ganti dengan kalimat aman. |
| **AI-in-the-Loop (definisi operasional skripsi)** | Fungsi pengawasan yang di siaran biasa dilakukan manusia (produser atau operator memantau isi, menegur penyiar, mengarahkan ke topik) dijalankan oleh agen AI (Supervisor, dibantu Showrunner) pada setiap giliran, tanpa persetujuan manusia per giliran. Ini **berbeda** dari makna di literatur (Natarajan et al., AAAI 2025), di mana manusia tetap memegang keputusan. Perbedaan ini wajib disebut eksplisit di Bab 2 skripsi. |
| **Arsitektur multi-agen** | Show Engine sebagai orkestrator; Persona, Showrunner, dan Supervisor sebagai agen spesialis dengan peran tetap. Diadaptasi dari pola orkestrator–evaluator skripsi Zulfi untuk loop real-time. |

---

## 4. Pengguna dan skenario

| Peran | Kebutuhan |
|---|---|
| Produser / operator | Mengetik tema, memilih dan mengedit blocker, memilih mode, memulai dan menghentikan live, memantau transkrip dan status agen, mengambil alih bila perlu. |
| Penyiar manusia (mode A) | Melihat blocker di prompter, berbicara dengan AI lewat push-to-talk, membaca komentar dari TikTok sendiri, menekan "next topik". |
| Penonton TikTok | Melihat layar 9:16: penyiar (kamera atau avatar) dan label AI; mendengar obrolan yang tidak terdengar seperti robot. |
| Peneliti (Favian) | Menjalankan eksperimen offline dan membaca log. |

**Skenario A: "Zodiak", manusia + Salsa**
1. Operator mengetik "Zodiak" dan memilih varian 2 dari 3, lalu mengedit satu poin.
2. Operator mengunci blocker dan memilih mode A dengan lawan bicara Salsa, lalu menekan Mulai.
3. Penyiar membuka obrolan, menahan tombol bicara, lalu bertanya ke Salsa. Salsa langsung menyahut dengan filler ("hmm, gue sih…"), lalu jawaban utamanya.
4. Penyiar membaca komentar dari TikTok dan melempar ke Salsa. Salsa menanggapi.
5. Panel Showrunner menyarankan "poin 3 belum dibahas" atau "siap pindah topik". Penyiar menekan "next topik".

**Skenario B: "Ospek", Raka + Salsa**
1. Blocker dikunci, mode B dimulai.
2. Raka dan Salsa membuka siaran, lalu membahas topik 1. Setelah poin-poin cukup terbahas dan obrolan mulai berulang, Showrunner memutuskan pindah.
3. Penyiar aktif mengucapkan kalimat transisi, lalu siaran berlanjut ke topik 2, topik 3, dan Closing.
4. Operator hanya memantau, dengan tombol pause, skip, dan stop.

---

## 5. Alur end-to-end

### 5.1 Sebelum live
1. Operator membuka konsol, mengetik tema, dan opsional menambah catatan (sasaran penonton, nuansa, hal yang dihindari).
2. Generator Blocker membuat 2–3 varian (FR-1). Operator memilih satu varian, mengedit (tambah, hapus, atau urutkan poin; ganti judul), lalu **mengunci**. Blocker tersimpan dengan versi.
3. Operator memilih mode:
   - A: dengan lawan AI Raka atau Salsa;
   - B: Raka + Salsa.
4. Operator menjalankan cek pra-live: kuota API, TTS, klip avatar termuat, mikrofon dan STT (mode A), dan halaman stage tersambung.
5. OBS / TikTok LIVE Studio menangkap halaman stage, plus kamera studio pada mode A.

### 5.2 Saat live: Mode A (manusia + AI)
```
Penyiar menahan PTT dan berbicara
  → STT (final transcript)
  → Show Engine menyusun konteks: blocker, topik aktif, riwayat, ucapan penyiar
  → filler pendek AI langsung diputar (audio cache) sambil menunggu
  → Persona AI → Supervisor → TTS (dipecah per kalimat) → Stage (audio + avatar berbicara)
  → avatar kembali ke klip "mendengarkan"
Setiap N giliran: Showrunner (mode saran) → panel konsol / prompter
"Next topik" ditekan penyiar/operator → topik berikutnya; AI diberi konteks topik baru
```

### 5.3 Saat live: Mode B (AI + AI)
```
loop:
  Persona aktif menulis giliran → Supervisor → TTS → antrean putar
  (giliran n+1 dibuat sambil audio giliran n diputar: pipelining)
  setiap k giliran / saat batas lunak tercapai → Showrunner memutuskan:
     continue | steer(poin) | transition | close
  transition → persona berikutnya mengucapkan kalimat transisi → topik berikutnya
  close → Closing → selesai
Operator: pause / skip topik / stop, kapan saja
```

### 5.4 Setelah live
- Log JSONL per sesi:
  - giliran;
  - keputusan Showrunner dan Supervisor;
  - latensi per tahap;
  - pemakaian kuota;
  - kejadian operator.
- Ekspor transkrip (.txt/.md) untuk evaluasi dan untuk penyiar HITS.

---

## 6. Arsitektur

### 6.1 Komponen
```
┌──────────────── Frontend (React + Vite) ────────────────┐
│ /            Konsol operator (tema, blocker, mode, kontrol, log)    │
│ /prompter    Blocker layar besar untuk penyiar (mode A)             │
│ /stage       Output 9:16 untuk OBS (avatar video + HUD + label AI)  │
└───────────── WebSocket /ws/session?role=console|prompter|stage ─────┘
                              │
┌──────────────── Backend (FastAPI, Python) ──────────────┐
│ Show Engine (orkestrator, state machine)                 │
│   ├─ Blocker Generator (LLM)                             │
│   ├─ Persona Engine (LLM, per persona)                   │
│   ├─ Showrunner (LLM)                                    │
│   ├─ Supervisor (LLM + aturan)                           │
│   ├─ TTS Service (ElevenLabs ↔ Edge TTS, cache)          │
│   ├─ STT Service (mode A)                                │
│   ├─ Avatar Service T2 (opsional, worker GPU PC lab)     │
│   ├─ Comment Ingest + Supervisor (FR-13, skripsi)        │
│   └─ Session Logger                                      │
└──────────────────────────────────────────────────────────┘
```

### 6.2 State machine Show Engine [C]
```
IDLE → BLOCKER_LOCKED → READY → LIVE{ OPENING → TOPIC(1..n) → CLOSING } → ENDED
                                 ↘ PAUSED ↗           (stop dari mana pun → ENDED)
```

| Kejadian | Mode A | Mode B |
|---|---|---|
| OPENING → TOPIC_1 | Penyiar menekan "next" | Showrunner `transition` (atau batas lunak Opening) |
| TOPIC_i → TOPIC_i+1 | Penyiar menekan "next" | Showrunner `transition` |
| TOPIC_n → CLOSING | Penyiar menekan "next" / "closing" | Showrunner `close` |
| Batas keras | Tidak ada | `MAX_TURNS_PER_TOPIC` (default 40) memaksa transisi; tercatat sebagai `forced` |
| Override operator | skip / pause / stop | skip / pause / stop |

### 6.3 Event WebSocket (minimal) [C]

| Event | Arah | Isi |
|---|---|---|
| `state` | server → semua | state, topik aktif, mode, persona |
| `turn` | server → console, stage | persona, teks, emosi, `audio_url`, durasi, `playback_id` |
| `filler` | server → stage | persona, `audio_url` |
| `speaking` | stage → server | mulai / selesai putar (untuk sinkron dan latensi) |
| `showrunner` | server → console, prompter | keputusan, poin tercakup, alasan singkat |
| `supervisor` | server → console | verdict, aksi, bukti |
| `topic_change` | server → semua | id topik, judul |
| `stt_partial` / `stt_final` | prompter/console → server | teks penyiar (mode A) |
| `comment` / `comment_flag` | server → console, prompter | (FR-13) |
| `output_status` | server → console | stage tersambung, audio terblokir, dll. |

### 6.4 API REST (minimal) [C]
- `POST /api/blocker/generate {tema, catatan?, jumlah_topik≤3, jumlah_varian 2..3}` → daftar varian.
- `PUT /api/blocker/{id}` simpan editan; `POST /api/blocker/{id}/lock`.
- `POST /api/show/start {blocker_id, mode, ai_persona?}`; `POST /api/show/next`; `POST /api/show/pause|resume|stop`.
- `POST /api/ptt/turn {text}` (bila STT di browser) atau `POST /api/ptt/audio` (bila STT di server).
- `GET /api/logs/{session_id}`; `GET /api/health` (status kuota, TTS, STT, avatar).

---

## 7. Spesifikasi fungsional

Format setiap FR: deskripsi → aturan → kriteria terima (KT).

### FR-1 Generator Blocker
- **Input:** tema (wajib, ≤60 karakter), catatan (opsional, ≤500 karakter), jumlah topik 1–3 (default 3) [F], jumlah varian 2–3 (default 3) [C].
- **Output:** varian sesuai skema §9.1. Isi tiap topik [F, dari usulan C]:
  - judul;
  - sudut pandang;
  - 3–5 poin obrolan;
  - 1 pertanyaan ke penonton;
  - kalimat transisi.

  Ditambah Opening (hook + 2–3 poin) dan Closing (rangkuman + ajakan).
- **Aturan:**
  1. Antarvarian harus berbeda sudut pandang, bukan hanya beda kata.
  2. Bahasa santai ala HITS, ditujukan untuk mahasiswa dan anak muda Bandung.
  3. Hindari klaim faktual spesifik (angka, tanggal, nama orang). Bila perlu, tandai `perlu_cek: true` agar operator memeriksa.
  4. Hindari politik praktis, SARA, dan topik medis yang bisa disalahartikan.
  5. Pakai structured output (JSON schema). Parsing gagal → ulangi sekali, lalu tampilkan galat.
- **UI:**
  - kartu varian berdampingan;
  - pilih satu varian;
  - editor inline (ubah teks, tambah/hapus poin, geser urutan, hapus topik);
  - tombol "buat ulang varian ini";
  - tombol kunci.

  Blocker yang sudah dikunci tidak bisa diubah. Untuk perubahan, buat versi baru.
- **KT:**
  - 10 tema uji (Ospek, Zodiak, Kos-kosan, Skripsi, Jajanan Bandung, Mudik, Cinta Lokasi, Magang, Hujan, Kopi) masing-masing menghasilkan varian valid sesuai skema dalam ≤20 s;
  - Favian menilai ≥8 dari 10 tema layak siar tanpa edit besar.

### FR-2 Show Engine
- Menjalankan state machine §6.2, menyusun konteks per giliran, dan mengatur pipelining.
- **Konteks persona per giliran:**
  - kartu persona;
  - gaya HITS;
  - ringkasan blocker;
  - topik aktif beserta poin yang belum tercakup;
  - riwayat N giliran terakhir (default 12) dan ringkasan sebelumnya;
  - arahan Showrunner terakhir (`steer`);
  - memori koreksi Supervisor (bila ada).
- **Pipelining mode B:** buat giliran n+1 (teks, Supervisor, TTS, dan render T2 bila aktif) selagi giliran n diputar. Kedalaman buffer `PIPELINE_DEPTH` default 1; 2–3 bila memakai T2.
- **Pemilihan pembicara mode B:**
  - default bergantian;
  - boleh Showrunner `steer` dengan `next_speaker`;
  - hindari satu persona bicara >2 kali berturut-turut.
- **KT:**
  - mode B 20 menit berjalan tanpa crash dan tanpa intervensi;
  - jeda antargiliran p50 ≤1,5 s dan p95 ≤4 s (T1);
  - semua tombol operator bekerja ≤1 s.

### FR-3 Persona Engine
- Persona Raka dan Salsa (dari repo lama), dengan field:
  - `speaking_style`, `catchphrases`, `background_facts`, `opinions`, `topic_limits`, `do_not`.
- **Gaya ucapan:**
  - kalimat pendek;
  - "gue/lu";
  - ada sahutan, tawa tertulis secukupnya, dan sapaan "Sobat Hits" sesekali;
  - tanpa markdown;
  - panjang bervariasi (pendek / sedang / panjang).
- **Output terstruktur:** `{text, emotion}`, dengan emosi ∈ {neutral, happy, excited, sad, surprised, thoughtful, empathetic}. Emosi menentukan klip reaksi avatar.
- **Mode A:** persona menanggapi ucapan penyiar manusia. Persona tidak mengarang isi komentar; ia hanya menanggapi apa yang dibacakan penyiar. Penyiar manusia diberi nama tampilan yang bisa diatur, misalnya nama penyiar HITS.
- **Mode A, panjang jawaban:** lebih pendek dari mode B (default 1–3 kalimat), supaya penyiar tetap memandu.
- **Pakai ulang:** profil prompt `natural_v2`, anti-repetisi trigram, sampler dialog act, dan catchphrase dari `conversation/engine.py`.
- **KT:**
  - 0 markdown di 200 giliran uji;
  - tingkat pengulangan pembuka ≤ baseline repo lama (metrik `naturalness.py`).

### FR-4 Showrunner (fokus publikasi)
- **Input:**
  - blocker;
  - topik aktif dan status poin;
  - riwayat giliran sejak topik dimulai;
  - jumlah giliran dan durasi audio topik;
  - (opsional) target durasi total sebagai **petunjuk lunak**, bukan aturan [F: jadwal tidak wajib].
- **Output terstruktur** (§9.3):
  - `points_covered[]`;
  - `saturation` 0–1 (seberapa jenuh atau berulang);
  - `decision` ∈ {continue, steer, transition, close};
  - `steer_hint` (poin yang perlu dibahas atau arah obrolan);
  - `next_speaker?`;
  - `reason` (≤1 kalimat).
- **Kapan dipanggil:**
  - setiap `SHOWRUNNER_EVERY_K` giliran (default 3) [C];
  - saat `MIN_TURNS_PER_TOPIC` (default 6) terlewati;
  - Showrunner tidak boleh memutuskan transisi sebelum batas minimum.
- **Mode B:** keputusan dieksekusi otomatis. `transition` → giliran berikutnya diberi instruksi transisi (memakai kalimat transisi blocker sebagai bahan, bukan dibaca mentah).
- **Mode A:** hanya saran di prompter dan konsol, misalnya "Poin tercakup 3/5 · saran: bahas 'ospek online vs offline' · siap pindah". AI juga mendapat `steer_hint` sebagai konteks.
- **Baseline publikasi** (bisa dipilih lewat config):
  - `fixed_turns` (pindah setiap X giliran);
  - `coverage_only` (pindah bila semua poin tercakup, tanpa penilaian kejenuhan).
- **KT:**
  - di 10 sesi uji mode B tidak ada topik yang berhenti sebelum ≥60% poin tercakup, kecuali `forced`;
  - tidak ada topik yang melewati `MAX_TURNS_PER_TOPIC` tanpa transisi.

### FR-5 Supervisor (fokus skripsi, AI-in-the-Loop)
Kode Supervisor di repo lama masih **stub**: prompt satu baris, tanpa koreksi dan tanpa regenerasi. Supervisor dibangun baru di sini.

- **Posisi:** setelah Persona, sebelum TTS, pada setiap giliran AI (kedua mode).
- **Pemeriksaan:**
  1. **Konsistensi persona:** bertentangan dengan `background_facts`, `opinions`, atau klaim sebelumnya di ledger; berganti identitas atau gaya; mengaku AI tanpa konteks; memakai nama lawan bicara sebagai diri sendiri.
  2. **Kepatuhan blocker:** keluar dari topik aktif tanpa jembatan, membahas topik yang sudah lewat, atau mengarang fakta spesifik.
  3. **Keamanan isi:** SARA, politik praktis, kata kasar berlebihan, medis berbahaya, data pribadi.
- **Aturan cepat sebelum LLM [C]:**
  - daftar kata terlarang;
  - markdown;
  - panjang ekstrem;
  - pengulangan persis.

  Pelanggaran yang jelas langsung ditangani tanpa memanggil LLM, untuk hemat kuota dan latensi.
- **Aksi:**
  - `forward`;
  - `regenerate`: buat ulang persona sekali dengan `CorrectionMemory` (pengingat persona, fakta yang harus ditegakkan, ringkasan percakapan);
  - `fallback`: kalimat aman pendek per persona (dari bank), dipakai bila regenerasi gagal atau waktu habis.

  Batas regenerasi `SUPERVISOR_MAX_REGEN=1`; batas waktu `SUPERVISOR_TIMEOUT_MS` (mode A 2500, mode B 5000).
- **Ledger:** klaim faktual tiap persona disimpan per sesi (contoh: "Raka suka kopi hitam") untuk cek konsistensi berikutnya.
- **Mode A:** ucapan penyiar manusia **tidak** diperiksa (bukan wewenang sistem), tetapi dipakai sebagai konteks.
- **Kondisi eksperimen:**
  - `SUPERVISOR_MODE=off` (baseline);
  - `rules` (aturan saja);
  - `full` (aturan + LLM).
- **KT:**
  - di set uji pelanggaran yang disuntikkan (≥30 kasus), recall ≥0,8 untuk pelanggaran keamanan;
  - overhead latensi p50 ≤1,5 s;
  - semua verdict tercatat di log.

### FR-6 TTS
- **Utama [F]:** ElevenLabs, model `eleven_flash_v2_5` (diatur lewat `ELEVENLABS_MODEL`, tidak di-hard-code), endpoint streaming.
  - Raka: suara **Pratama** (`q8qwd1jY2jS3AWOBeq25`); cadangan Ginanjar (`JjCMg2oeB7ExbMJUJHSK`).
  - Salsa: suara **Aita** (`ffTJE9l3Kt2ipEM32UOc`); cadangan Kira (`gmnazjXOFoOcWA59sd5m`).
  - Voice ID diatur lewat `ELEVENLABS_VOICE_*` / kartu persona.
  - Alasan (Tahap 0, `tahap0/HASIL.md`): latensi p50 0,55 s dan byte pertama ±0,45 s; transkrip setia teks. Gemini TTS free tier hanya 3 RPM dengan latensi p50 12,7 s, jadi tidak layak untuk live.
  - Suara library kadang cold start 15–20 s pada request pertama: cek pra-live wajib memanaskan (warm-up) kedua suara.
  - Pemakaian kredit dipantau (header `character-cost`, ±0,2 kredit/karakter di flash) dan ditampilkan di konsol bersama status kuota.
- **Failover [F]:** Edge TTS (pustaka tidak resmi `edge-tts`), gratis:
  - pria `id-ID-ArdiNeural`;
  - wanita `id-ID-GadisNeural`.

  Konfigurasi lama memakai `su-ID-TutiNeural` (Sunda); ganti.
- **Failover otomatis** ke Edge bila ElevenLabs galat, timeout, atau kredit habis (breaker seperti di repo lama). `aiohttp` untuk Edge memakai resolver DNS sistem (temuan Tahap 0).
- **Dipecah per kalimat untuk mode A:** kalimat pertama di-TTS dan diputar sambil sisanya dibuat.
- **Bank filler per persona:** 15–25 klip pendek ("hmm", "wah", "iya juga ya", tawa kecil, "bentar-bentar"), dibuat sekali lalu di-cache.
- Gemini TTS tidak dipakai di jalur live; boleh dipakai offline untuk bank filler bila kualitasnya lebih disukai. VoiceStudio tidak dipakai.
- **KT:**
  - 5 penilai (minimal Favian + 2 rekan + 2 penyiar HITS bila bisa) memberi skor ≥3,5/5 untuk "tidak terdengar seperti robot" pada sampel ElevenLabs (Pratama dan Aita);
  - failover teruji.

### FR-7 Input penyiar mode A (PTT + STT)
- **Push-to-talk:**
  - penyiar atau operator menahan tombol (spasi di laptop prompter, atau tombol layar besar);
  - saat dilepas, transkrip final dikirim;
  - mode alternatif "tekan sekali mulai, tekan lagi selesai".
- **STT, diputuskan di Tahap 0 [C]:**
  1. Web Speech API Chrome (`id-ID`): gratis dan cepat, tetapi audio dikirim ke server Google dan akurasi bahasa gaul belum pasti.
  2. `faster-whisper` lokal di PC lab (GTX 1080): gratis, offline, perlu diuji kecepatan dan akurasinya.
  3. Kirim audio langsung ke Gemini (multimodal): tanpa STT terpisah, tetapi memakai kuota.
- Prompter menampilkan transkrip sementara dan final. Penyiar bisa membatalkan (tekan Esc) bila salah dengar.
- **Audio:**
  - suara AI keluar dari halaman stage dan ditangkap OBS ke TikTok;
  - penyiar mendengar AI lewat headphone atau monitor (atur agar tidak masuk mikrofon dan memantul).
- **KT:**
  - akurasi STT ≥90% kata pada 20 kalimat uji gaya siaran;
  - latensi lepas tombol → filler mulai ≤0,8 s;
  - lepas tombol → jawaban utama mulai p50 ≤4 s dan p95 ≤7 s [C, target awal].

### FR-8 Avatar T1: bank klip Flow (wajib KP)
- **Aset:**
  - klip video 9:16 per karakter dari Google Flow, dengan wajah, pakaian, dan latar konsisten;
  - studio HITS dengan neon "HITS UNIKOM", seperti referensi Favian;
  - daftar klip di Lampiran A;
  - format MP4 H.264, tanpa audio, 720×1280 atau 1080×1920, durasi 4–8 s, awal dan akhir pose netral agar bisa diputar ulang.
- **Pemutar (di `/stage`):**
  - dua elemen `<video>` per karakter dengan crossfade 150–250 ms;
  - state:
    - `idle` → klip diam / mendengarkan (acak, tanpa pengulangan berturut-turut);
    - audio giliran mulai → klip reaksi sesuai `emotion` (opsional, ≤1,5 s), lalu klip berbicara diulang sampai audio selesai;
    - audio selesai → klip mendengarkan.
  - Pilihan klip berbicara mengikuti energi audio (RMS): tenang vs bersemangat.
- **Batasan yang diakui:** gerak bibir **tidak sinkron per kata**. Ini harus dijelaskan ke pembimbing HITS sebagai batasan tingkat T1.
- **KT:**
  - transisi tanpa kedip hitam;
  - tidak ada jeda video saat pergantian;
  - 60 menit tanpa kebocoran memori di laptop streaming;
  - Favian dan pembimbing menilai tampilan "realistis" dengan skor ≥3,5/5.

### FR-9 Avatar T2: lip-sync neural (opsional, butuh lolos Tahap 0)
- **Kandidat [C]:** model lip-sync open source, misalnya MuseTalk. Lisensi kode dan bobot model wajib dicek.
  - Input: klip berbicara dari T1 + audio TTS.
  - Output: video dengan bibir sinkron.
- **Jalan di PC lab GTX 1080** sebagai worker (HTTP lokal), dirender **sebelum diputar** (pipelining mode B, buffer 2–3 giliran).
- **Syarat adopsi (gerbang Tahap 0):**
  - RTF (waktu render ÷ durasi audio) ≤0,8 pada resolusi output;
  - kualitas bibir dinilai lebih baik dari T1.
- Mode A tetap T1 kecuali RTF ≤0,3 (supaya penyiar tidak menunggu).
- **Konsekuensi:** bila T2 dipakai, live dijalankan dari PC lab.
- Bila gerbang gagal, catat angka RTF sebagai temuan dan tetap pakai T1.

### FR-10 Stage / output OBS
- Kanvas 9:16 (1080×1920). Pakai ulang zona aman TikTok dari `stageLayout.ts`:
  - header 0–10%;
  - bar bawah 93–100%;
  - area komentar 65–91% tinggi × 0–70% lebar;
  - margin sisi 5%.
- **Tata letak [C]:**
  - **Mode B:** dua panel bertumpuk (atas Raka, bawah Salsa), seperti live HITS asli.
  - **Mode A:** panel atas = kamera studio (ditaruh di OBS sebagai sumber terpisah; stage menyisakan area transparan atau kosong); panel bawah = avatar AI. Urutan bisa ditukar lewat config.
- **HUD:**
  - pil program;
  - **label "AI" permanen di panel avatar**;
  - judul topik aktif;
  - pertanyaan ke penonton (dari blocker);
  - penanda siapa yang berbicara.
- `?clean=1` untuk tangkapan OBS; `?zones=1` untuk overlay zona aman.
- **Audio:** satu pemutar (stage pertama yang tersambung), seperti repo lama.
- **KT:**
  - tidak ada elemen penting di luar zona aman;
  - label AI terlihat setiap saat.

### FR-11 Konsol operator dan prompter
- **Konsol `/`:**
  - generator dan editor blocker;
  - pilih mode dan persona;
  - cek pra-live;
  - tombol Mulai / Pause / Next / Stop;
  - transkrip langsung;
  - panel Showrunner dan Supervisor;
  - indikator kuota dan latensi.
- **Prompter `/prompter`** (untuk penyiar mode A; bisa di tablet atau monitor kedua):
  - topik aktif dalam huruf besar;
  - poin dengan centang dari Showrunner;
  - pertanyaan ke penonton;
  - saran Showrunner;
  - tombol PTT dan "next topik";
  - transkrip STT.
- **KT:**
  - prompter terbaca dari jarak 1–1,5 m;
  - semua kontrol bisa dioperasikan tanpa mouse (pintasan keyboard).

### FR-12 Logging
- Satu JSONL per sesi (`logs/{session_id}.jsonl`) dengan event bertipe:
  - `session_start`, `turn`, `showrunner`, `supervisor`, `topic_change`, `operator_action`, `stt`, `error`, `quota`, `session_end`.
- `turn` memuat:
  - mode, topik, persona, `raw_text`, `final_text`, emosi;
  - verdict Supervisor;
  - jumlah regenerasi;
  - latensi (`stt`, `persona`, `supervisor`, `tts`, `avatar_render`, `gap_before_play`);
  - model yang dipakai;
  - provider TTS;
  - pemakaian filler.
- Skema lengkap di §9.4. Blocker yang dipakai disalin ke header log.
- **KT:**
  - satu sesi bisa direkonstruksi utuh dari log (transkrip + keputusan);
  - skrip `report.py` menghasilkan ringkasan latensi dan keputusan.

### FR-13 Panel komentar + Supervisor (skripsi saja)
- **Ambil komentar:** pustaka tidak resmi TikTokLive (Python), dengan cadangan input manual operator (`POST /api/comments`, pakai ulang `comments/queue.py` tanpa bagian lagu).
- Supervisor memeriksa setiap komentar dan memberi label `aman | sensitif | tolak`, beserta alasan.
- Komentar tampil di prompter untuk **penyiar manusia** (mode A) dengan warna sesuai label. AI tetap tidak membaca komentar sendiri [F].
- Diaktifkan lewat `COMMENTS_ENABLED=true`. Mati secara default di build KP.
- **KT:** pada 50 komentar uji berlabel, akurasi label ≥0,85; latensi pelabelan ≤3 s.

### FR-14 Harness eksperimen
- Menjalankan mode B **offline**: tanpa stage dan tanpa TTS (`TTS_MODE=mock`), untuk banyak sesi dengan seed tetap. Kombinasi kondisi:
  - Supervisor off / rules / full;
  - Showrunner llm / fixed_turns / coverage_only.
- **Identity drift:** pakai ulang `experiment/snapshot.py`, kuesioner, dan `scoring.py` (replikasi Choi et al. 2025). Snapshot diambil di akhir setiap topik.
- **Naturalness:** pakai ulang `experiment/naturalness.py`, dibandingkan dengan transkrip on-air HITS (`data/reference/*.txt`).
- **Mode A:** dievaluasi dari sesi uji nyata (jumlah sesi kecil), lewat log dan kuesioner penyiar.
- Output: CSV/JSON per sesi + `report.py` (statistik, uji beda).

---

## 8. Kebutuhan non-fungsional

| Aspek | Kebutuhan |
|---|---|
| Biaya | Rp0 [F] untuk semua komponen kecuali TTS: Gemini free tier, Edge TTS, model open source, perangkat yang ada. TTS utama ElevenLabs (berbayar/kredit) [F]; pemakaian kredit dicatat per sesi. |
| Kuota | Rate limiter per model (`GEMINI_RPM_*`). Model berbeda per peran untuk membagi beban: persona, Supervisor, Showrunner, blocker. Status kuota tampil di konsol. Bila kuota atau kredit habis: TTS ElevenLabs ke Edge, Supervisor ke `rules`, Showrunner ke `fixed_turns`; semua tercatat. |
| Latensi | Mode B: jeda antargiliran p95 ≤4 s (T1). Mode A: §FR-7. |
| Keandalan | Live uji 20 menit tanpa crash (KP); 60 menit (target akhir). Reconnect WS otomatis. Status live tetap benar setelah reload. |
| Kepatuhan TikTok | Label AI di layar, penyampaian di pembukaan bahwa penyiar adalah AI, dan pengaturan label konten AI TikTok diaktifkan. Uji coba di akun pribadi dulu. |
| Privasi data | Data free tier Gemini boleh dipakai Google untuk pengembangan produk. Jangan memasukkan data pribadi penonton atau dokumen rahasia HITS ke prompt. |
| Perangkat | Laptop streaming MX250: hanya T1 dan OBS. PC lab GTX 1080: T2 dan/atau faster-whisper. Chrome/OBS diatur ke GPU "High performance". |
| Kode | Python 3.12 + FastAPI; React + Vite + TypeScript; tes unit untuk modul backend; `LLM_MODE=mock` dan `TTS_MODE=mock` untuk uji tanpa kuota. |

---

## 9. Model data (JSON)

### 9.1 Blocker
```json
{
  "id": "blk_20261024_zodiak_v2",
  "tema": "Zodiak",
  "catatan": "untuk mahasiswa baru",
  "versi": 1,
  "locked": true,
  "created_at": "2026-10-24T10:00:00+07:00",
  "variant_label": "Zodiak dan pertemanan",
  "opening": {
    "hook": "Sobat Hits, lo percaya zodiak nggak sih?",
    "poin": ["sapa penonton", "kenalin tema hari ini"]
  },
  "topics": [
    {
      "id": "t1",
      "judul": "Zodiak dan cari teman di kampus",
      "sudut_pandang": "zodiak sebagai bahan obrolan, bukan ramalan",
      "poin": [
        {"id": "t1p1", "text": "pernah ditanya zodiak pas kenalan?", "perlu_cek": false},
        {"id": "t1p2", "text": "stereotip zodiak yang paling sering kedengeran", "perlu_cek": false},
        {"id": "t1p3", "text": "zodiak bikin cepat akrab atau malah ngejudge?", "perlu_cek": false}
      ],
      "pertanyaan_penonton": "Zodiak lo apa, cocok nggak sama sifat lo?",
      "transisi": "Nah, kalau soal pertemanan udah, gimana kalau urusannya hati?"
    }
  ],
  "closing": {
    "rangkuman": "zodiak seru buat obrolan, tapi kenal orang tetap dari sikapnya",
    "ajakan": "tulis zodiak kalian di komentar"
  }
}
```

### 9.2 Kartu persona
Sama dengan `PersonaCard` di repo lama (`id`, `name`, `gender`, `voice`, `speaking_style`, `catchphrases`, `topic_limits`, `background_facts`, `do_not`, `opinions`), ditambah:
```json
{ "voices": {"elevenlabs": "q8qwd1jY2jS3AWOBeq25", "edge": "id-ID-ArdiNeural"},
  "clips": "assets/avatar/raka/manifest.json",
  "filler_bank": "assets/filler/raka/" }
```

### 9.3 Keputusan Showrunner
```json
{
  "turn": 18, "topic_id": "t1",
  "points_covered": ["t1p1", "t1p2"],
  "saturation": 0.72,
  "decision": "steer",
  "steer_hint": "bahas t1p3: zodiak bikin ngejudge orang",
  "next_speaker": "salsa",
  "reason": "dua poin sudah, mulai mengulang soal stereotip",
  "policy": "llm",
  "latency_ms": 1350
}
```

### 9.4 Log giliran
```json
{
  "type": "turn", "session_id": "show_ab12", "mode": "B", "topic_id": "t1", "turn": 18,
  "persona": "raka", "raw_text": "...", "final_text": "...", "emotion": "happy",
  "supervisor": {"mode": "full", "action": "regenerate", "checks": {"persona": "ok", "blocker": "off_topic", "safety": "ok"},
                 "evidence": "...", "regenerations": 1},
  "latency_ms": {"stt": 0, "persona": 1800, "supervisor": 900, "tts": 1200, "avatar_render": 0, "gap_before_play": 300},
  "models": {"persona": "<env>", "supervisor": "<env>", "tts": "<env>"},
  "tts_provider": "gemini", "filler": null, "seed": 7
}
```

---

## 10. Pedoman prompt [C]
- Semua prompt disimpan di `backend/app/prompts/*.md`, bukan string panjang di kode, dan diberi versi (`PROMPT_VERSION` dicatat di log).
- **Persona:**
  - pakai ulang profil `natural_v2` dan `hits_style.py`;
  - contoh gaya dari transkrip on-air HITS (tiru nada, jangan salin);
  - tambahan khusus mode A: "Lawan bicaramu penyiar manusia bernama {nama}. Jawab singkat, beri ruang dia memandu."
- **Showrunner:** diberi definisi "jenuh" yang konkret:
  - pengulangan ide;
  - sahutan tanpa isi;
  - poin habis;
  - dua giliran terakhir tidak menambah informasi baru.

  Wajib keluar JSON.
- **Supervisor:**
  - rubrik per pemeriksaan;
  - contoh pelanggaran dan bukan pelanggaran;
  - bedakan *akomodasi gaya* (menyesuaikan nada lawan bicara: wajar) dari *drift* (berubah identitas atau bertentangan dengan fakta persona).
- **Generator Blocker:** contoh satu blocker ideal (few-shot), larangan klaim faktual spesifik, dan pembeda antarvarian.

---

## 11. Struktur repo baru [C]
```
penyiar-ai-v2/
├─ PRD.md · CLAUDE.md · AGENTS.md · .env.example · README.md
├─ backend/
│  ├─ app/
│  │  ├─ main.py               # FastAPI + WS
│  │  ├─ config.py
│  │  ├─ schemas.py
│  │  ├─ show/engine.py        # state machine, pipelining
│  │  ├─ blocker/generator.py
│  │  ├─ agents/persona.py · showrunner.py · supervisor.py
│  │  ├─ llm/client.py · rate_limiter.py
│  │  ├─ tts/provider.py · filler.py
│  │  ├─ stt/                   # webspeech relay / faster_whisper
│  │  ├─ avatar/t2_client.py    # opsional
│  │  ├─ comments/              # FR-13
│  │  ├─ prompts/*.md
│  │  ├─ data/persona/*.json · reference/*.txt
│  │  └─ logging/logger.py
│  ├─ experiment/               # FR-14
│  └─ tests/
├─ avatar-worker/               # FR-9, jalan di PC lab
├─ frontend/
│  └─ src/ console/ · prompter/ · stage/ (VideoAvatar, HUD, layout) · hooks/
└─ assets/avatar/{raka,salsa}/*.mp4 + manifest.json · assets/filler/
```

---

## 12. Peta pemakaian ulang dari repo lama

**Sumber.** Folder lokal `D:\programming\work\penyiar-ai` adalah clone repo GitHub `favjiw/conversational-ai`, dengan branch aktif `talk-durasi` di commit `a3e04ca`. Branch ini 4 commit di depan `main`, dan semuanya sudah di-push. Ambil dari branch itu, bukan dari `main`.

Repo lama **tidak diubah**. Beri tag `v1-format-clock` di commit `a3e04ca` dan tulis catatan arsip di README-nya. Salin hanya bagian berikut, lalu sesuaikan.

| Ambil | Dari | Catatan |
|---|---|---|
| Klien LLM + rate limiter + mock | `backend/app/llm/client.py`, `rate_limiter.py` | Tambah limiter per peran. |
| TTS (Gemini, Edge, cache, breaker, word timings) | `backend/app/tts/provider.py` | Pertahankan ElevenLabs sebagai utama (streaming, `character-cost`); buang VoiceStudio; perbaiki voice Edge wanita ke `id-ID`. |
| Prompt persona `natural_v2`, anti-repetisi, dialog act, catchphrase | `backend/app/conversation/engine.py` | Pisahkan menjadi `agents/persona.py`; buang kode slot/Tema lama. |
| Gaya HITS | `backend/app/conversation/hits_style.py` | Buang `song_recap_hint`. |
| Persona Raka dan Salsa | `backend/app/data/persona/*.json` | Tambah field §9.2. |
| Transkrip referensi HITS | `backend/data/reference/*.txt` | Untuk contoh gaya dan evaluasi naturalness. |
| Skema `PersonaCard`, `PersonaOutput`, `Emotion`, `SupervisorVerdict`, `CorrectionMemory`, `LedgerEntry`, `LatencyMs` | `backend/app/schemas.py` | Perluas sesuai §9. |
| Logger JSONL | `backend/app/session_logging/logger.py` | Ubah menjadi event bertipe. |
| Antrean komentar | `backend/app/comments/queue.py` | Hanya untuk FR-13; buang klasifikasi lagu. |
| Eksperimen identity drift dan naturalness | `backend/experiment/*` | Snapshot, kuesioner, scoring, stats, naturalness, report. |
| Pola WS console/stage, satu pemutar audio, `live_state()` | `backend/app/main.py` | Tambah role `prompter`. |
| Pipelining giliran | `backend/app/orchestrator/clock_runner.py` (bagian pipelining saja) | Tanpa `TalkBudget` / durasi slot. |
| Zona aman, HUD, overlay | `frontend/src/stage/layout/stageLayout.ts`, `components/PortraitHUD.tsx`, `SafeZoneOverlay.tsx` | Sesuaikan dengan panel video. |
| Pemutar audio + adapter WS | `frontend/src/stage/audio/AudioManager.ts`, `live/LiveBroadcastAdapter.ts` | Buang musik dan station audio. |
| Komponen konsol | `useLiveSession.js`, `TranscriptCard.jsx`, `SpeakerCards.jsx`, `PersonaEditor.jsx`, `CommentPanel.jsx`, `TTSLab.jsx` | Sesuaikan. |
| Skrip rekam demo | `frontend/scripts/record_demo.py` | Untuk demo ke pembimbing. |
| Tes | `test_llm`, `test_tts`, `test_logger`, `test_conversation`, `test_naturalness`, `test_experiment_*` | Sesuaikan impor. |
| Jendela stage popup 9:16 | `frontend/src/components/Header.jsx` (`openStageWindow`, commit `a3e04ca`) | Popup 540×960 tanpa tab, dibuka ulang di jendela bernama sama. Memudahkan OBS menangkap jendela. |
| Konfigurasi preview | `.claude/launch.json` | Pola `backend` / `backend-mock` / `backend-edge` / `frontend` untuk Windows (`cmd /c`). Buang `backend-rec`. |
| Transkrip dan analisis live HITS 20 Okt | `docs/TRANSKRIP-LIVE-TIKTOK-2026-10-20.md`, `docs/ANALISIS-LIVE-TIKTOK-2026-10-20.md` | Bahan kalibrasi Showrunner (panjang blok obrolan, pola pindah topik) dan baseline publikasi. |
| Hasil pilot identity drift | `backend/logs/experiments/exp_pilot_gemini/` | Data, bukan kode. Rujukan baseline Bab 4; tidak perlu disalin ke repo baru. |

**Ditinggalkan:**
- `clock/*`, `orchestrator/clock_runner.py` (kecuali pipelining), `orchestrator/engine.py`;
- `music/*`, submodule `hits-song-recommender`, `station_audio`, `clock-pagi-bener-live-1jam.json`, `data/tema/*`;
- seluruh avatar three.js: `stage/scene`, `face`, `expression`, `idle`, `lipsync`, model VRM/GLB;
- `ClockRundownTimeline`, `NowPlayingMusic`, `FormatPresetSelector`, `TemaLibrary`.

**Diperiksa di folder lokal, sengaja tidak diambil:**
- `frontend/public/backgrounds/studio-hits-unikom.jpg`: ilustrasi bergaya kartun/anime, bertentangan dengan arahan karakter realistis. Latar studio sekarang ikut dihasilkan di klip Flow.
- Perubahan `SceneManager.ts` / `stageLayout.ts` (backdrop foto, penyiar bawah setengah badan): khusus avatar three.js.
- `docs/Rundown-Live-TikTok-1-Jam-penyiar-ai.xlsx` (belum di-commit): rundown Format Clock lama.
- `demo-recordings/voice-samples/`: sampel ElevenLabs (berbayar).
- `demo-3d-realistic.mp4`, `demo-animation.mp4`: hanya arsip progres KP.
- `backend/logs/session_*.jsonl`, `clock_*.music.jsonl`: log uji pengembangan, bukan data eksperimen.
- `cache/`, `external/hits-song-recommender`, `data/station_audio/`, empat model VRM yang belum di-commit.
- `.env`: **jangan disalin**. Buat `.env` baru dari `.env.example`. Catatan progres lama menyebut key ElevenLabs dan Groq pernah tertulis di chat; pastikan sudah dirotasi atau dicabut. Key ElevenLabs baru hanya disimpan di `.env`.

---

## 13. Tahapan dan gerbang

Setiap tahap diakhiri demo singkat ke Favian dan pembaruan §16.

### Tahap 0: Uji kelayakan (±1 minggu)
- [ ] **Kuota:** catat RPM/RPD free tier untuk setiap model yang akan dipakai (teks dan TTS) dari AI Studio, lalu hitung kebutuhan 20 menit dan 60 menit mode B. Catat tanggal pengecekan dan tautan.
- [ ] **TTS:** 10 kalimat gaya HITS × (Gemini TTS, Edge TTS). Catat latensi dan penilaian "robot atau tidak".
- [ ] **STT:** 20 kalimat gaya siaran × (Web Speech `id-ID`, faster-whisper di PC lab). Catat akurasi kata dan latensi.
- [ ] **Avatar T1:** buat 3 klip per karakter di Flow (idle, mendengarkan, berbicara). Uji crossfade di browser laptop streaming.
- [ ] **Avatar T2:** pasang model lip-sync open source di PC lab. Ukur RTF pada 3 audio (5, 10, 20 s); cek VRAM dan lisensi.
- [ ] **Keputusan gerbang:** STT terpilih, TTS utama, T2 ya/tidak, dan nilai default `PIPELINE_DEPTH`. Tulis di §15.

### Tahap 1: Fondasi repo + Generator Blocker
- Repo baru, salin modul §12, `.env.example`, tes lulus, `LLM_MODE=mock`.
- FR-1 lengkap (backend + UI konsol).
- **Gerbang:** KT FR-1 terpenuhi; contoh blocker bisa didemokan ke pembimbing HITS.

### Tahap 2: Mode B inti (audio saja)
- FR-2, FR-3, FR-4, FR-5 (mode `rules` dulu, lalu `full`), FR-6, dan FR-12.
- Halaman stage sementara tanpa video, hanya HUD + audio.
- **Gerbang:** sesi mode B 20 menit dari blocker, tanpa intervensi; log lengkap.

### Tahap 3: Avatar T1 + stage + OBS
- FR-8, FR-10, dan bank klip lengkap (Lampiran A).
- **Gerbang:** live uji di akun TikTok pribadi 20 menit, mode B, dengan label AI.

### Tahap 4: Mode A
- FR-7, FR-11 (prompter), filler, dan Showrunner mode saran.
- **Gerbang:** sesi uji 15 menit bersama penyiar sungguhan; KT latensi FR-7.

### Tahap 5: Avatar T2 (bila lolos Tahap 0)
- FR-9: worker di PC lab, buffer mode B.
- **Gerbang:** RTF ≤0,8 saat live, dan kualitas dinilai lebih baik dari T1.

### Tahap 6: Tambahan skripsi
- FR-13 (TikTokLive + label Supervisor), dan Supervisor `full` dengan ledger dan memori koreksi lengkap.
- **Gerbang:** KT FR-5 dan FR-13.

### Tahap 7: Eksperimen
- FR-14: eksperimen skripsi dan publikasi (§14), lalu laporan.

---

## 14. Rancangan eksperimen [C]

### 14.1 Skripsi: Supervisor (AI-in-the-Loop)
- **Pertanyaan:** apakah Supervisor menurunkan identity drift dan pelanggaran blocker atau keamanan tanpa menurunkan kealamian dan tanpa latensi yang tidak bisa diterima?
- **Kondisi:** `off` vs `rules` vs `full`.
  - Mode B: offline, ≥10 tema × 3 kondisi × ≥3 seed.
  - Mode A: sesi uji nyata, jumlah kecil, sebagai studi kasus.
- **Metrik:**
  1. Identity drift: skor kuesioner di snapshot akhir tiap topik (Choi et al. 2025).
  2. Tingkat pelanggaran persona, blocker, dan keamanan: dinilai LLM-judge, lalu sampel diverifikasi manusia.
  3. Kealamian: metrik `naturalness.py` dibanding transkrip HITS, ditambah penilaian penyiar HITS (skala Likert).
  4. Overhead latensi dan kuota.
- **Uji pelanggaran tersuntik:** set ≥30 ucapan buatan yang melanggar, untuk mengukur recall dan presisi Supervisor.

### 14.2 Publikasi: Showrunner
- **Pertanyaan:** apakah keputusan transisi berbasis LLM (cakupan + kejenuhan) menghasilkan alur topik yang lebih baik daripada aturan sederhana?
- **Kondisi:** `llm` vs `fixed_turns` (X dari median giliran per topik di live HITS) vs `coverage_only`.
- **Metrik:**
  - cakupan poin blocker;
  - redundansi (pengulangan trigram dan ide) di akhir topik;
  - distribusi panjang topik dibanding blok Talk live HITS 20 Okt (±7–8 menit);
  - penilaian manusia atas ketepatan waktu transisi ("terlalu cepat / pas / terlalu lama");
  - jumlah `forced`.
- **Tambahan:** keputusan Showrunner di mode A (saran) dibanding kapan penyiar manusia benar-benar menekan "next", sebagai ukuran kesesuaian dengan intuisi penyiar.

---

## 15. Risiko dan keputusan terbuka

### 15.1 Risiko

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Kuota free tier tidak cukup untuk 60 menit | Live berhenti atau terdegradasi | Model per peran, aturan sebelum LLM, Showrunner tiap k giliran, failover (§8), live uji 20 menit dulu |
| Latensi mode A terasa canggung | Pengalaman siaran buruk | Filler, TTS per kalimat, jawaban pendek, PTT |
| Avatar T1 tidak sinkron bibir | Dinilai kurang realistis | Komunikasikan batasan; T2 bila lolos; framing kamera agak jauh / mic menutupi sebagian mulut (seperti referensi) |
| GTX 1080 terlalu lambat untuk T2 | T2 batal | T1 tetap jalan; angka RTF menjadi temuan |
| Kebijakan TikTok soal suara dan konten AI realistis | Live dibatasi atau diturunkan | Label AI, pengumuman di pembukaan, akun pribadi untuk uji, ada operator manusia |
| TikTokLive (pustaka tidak resmi) rusak | FR-13 gagal | Input manual operator |
| Edge TTS (tidak resmi) berubah atau diblokir | Cadangan TTS hilang | ElevenLabs utama; cek ulang berkala |
| Kredit ElevenLabs habis saat live | Suara berganti ke Edge di tengah siaran | Pantau kredit di konsol dan cek pra-live; perkirakan kebutuhan per sesi (±4 rb kredit per 20 menit mode B di flash, `tahap0/HASIL.md`); failover Edge |
| Generator blocker mengarang fakta | Salah informasi on-air | Larangan klaim spesifik, `perlu_cek`, operator memeriksa sebelum kunci |
| Wajah karakter Flow mirip orang nyata | Masalah etika | Pastikan karakter fiktif; jangan memakai foto orang sebagai referensi |

### 15.2 Keputusan terbuka
1. STT, TTS utama, dan T2: diputuskan di gerbang Tahap 0.
2. Nama tampilan penyiar manusia di prompt mode A.
3. Apakah Opening dan Closing mode A juga diisi AI, atau AI baru masuk di topik 1.
4. Nilai default `SHOWRUNNER_EVERY_K`, `MIN_TURNS_PER_TOPIC`, `MAX_TURNS_PER_TOPIC`, dikalibrasi dari live HITS 20 Okt.
5. Persetujuan pembimbing HITS untuk kriteria "realistis" (T1 vs T2).
6. ~~Nama repo baru.~~ Diputuskan: `penyiar-ai-v2` [F].

---

## 16. Status

| Tahap | Status | Tanggal | Catatan |
|---|---|---|---|
| 0 Uji kelayakan | Berjalan | 24 Okt 2026 | Alat uji di `tahap0/` siap. TTS terukur: Edge, Gemini (free tier 3 RPM, terlalu lambat untuk live), ElevenLabs flash (p50 0,55 s) dipilih sebagai TTS utama [F], Edge failover. Menunggu: penilaian dengar TTS, rekaman STT, kuota AI Studio, klip Flow, PC lab. Lihat `tahap0/HASIL.md`. |
| 1 Fondasi + Blocker | Menunggu pemeriksaan Favian | 24 Okt 2026 | Backend (config, skema, LLM + rate limiter, TTS ElevenLabs/Edge + breaker, persona) dan FR-1 lengkap (API + konsol: generate, bandingkan, edit, kunci, versi, buat ulang). 27 tes lulus. KT otomatis: 10/10 tema valid dalam 5,8–8,1 s (`gemini-3.5-flash-lite`, prompt `blocker-v2`). Sisa KT: penilaian layak siar ≥8/10 di `docs/kt/FR-1-blocker.md`. Catatan: repo lama ternyata tidak punya breaker TTS (FR-6), jadi dibuat baru. Repo lama sudah diberi tag `v1-format-clock` dan README arsip. |
| 2 Mode B inti | Belum | | |
| 3 Avatar T1 + OBS | Belum | | |
| 4 Mode A | Belum | | |
| 5 Avatar T2 | Belum | | |
| 6 Tambahan skripsi | Belum | | |
| 7 Eksperimen | Belum | | |

## 17. Riwayat
- **v2.0 (24 Okt 2026):** PRD tunggal setelah revisi pembimbing HITS. Menggantikan seluruh PRD dan dokumen desain v1.
- **v2.1 (24 Okt 2026):** §12 diperbarui setelah memeriksa folder lokal `penyiar-ai` (clone `conversational-ai`, branch `talk-durasi` @ `a3e04ca`):
  - sumber diganti ke branch `talk-durasi`;
  - ditambah jendela stage popup, `launch.json`, transkrip/analisis live HITS, dan data pilot identity drift;
  - ditambah daftar yang sengaja tidak diambil.
- **v2.2 (24 Okt 2026):** keputusan TTS dari hasil Tahap 0 [F]:
  - TTS utama ElevenLabs `eleven_flash_v2_5` (Pratama untuk Raka, Aita untuk Salsa), Edge TTS sebagai failover;
  - pengecualian biaya Rp0 khusus TTS (§1.3, §2.3, §8);
  - FR-6, §6.1, §9.2, §12, §15.1, dan Lampiran B disesuaikan;
  - repo diputuskan `favjiw/penyiar-ai-v2` (§0, §15.2 #6).

---

## Lampiran A: Bank klip Google Flow per karakter [C]

Buat karakter **fiktif**. Kunci wajah dengan gambar referensi yang sama (ingredients / frame awal) di setiap klip. Kamera statis, framing dada ke atas, 9:16, latar studio radio dengan neon "HITS UNIKOM", mic broadcast di depan.

| Kode | Isi | Jumlah |
|---|---|---|
| `idle_1..3` | duduk diam, napas natural, kedip, sesekali melirik ke kamera | 3 |
| `listen_1..3` | mendengarkan lawan bicara di luar frame, mengangguk kecil, senyum tipis | 3 |
| `talk_calm_1..3` | berbicara santai ke kamera, gerak tangan kecil | 3 |
| `talk_hype_1..2` | berbicara bersemangat, ekspresif | 2 |
| `react_laugh` | tertawa lepas lalu kembali netral | 1 |
| `react_surprised` | kaget / "hah?" lalu netral | 1 |
| `react_thinking` | berpikir, "hmm", menyentuh dagu | 1 |
| `react_empathetic` | ekspresi ikut merasakan, mengangguk pelan | 1 |

**Templat prompt** (Inggris biasanya lebih stabil di generator video; sesuaikan):

> Vertical 9:16 medium close-up of [CHARACTER: young Indonesian man in his early 20s, short neat black hair, dark navy bomber jacket over white t-shirt], sitting behind a black broadcast microphone on a boom arm in a small radio studio with black acoustic foam walls and a glowing neon sign reading "HITS UNIKOM" behind him. Static camera, soft warm key light. He is [ACTION: talking casually to the camera with small hand gestures]. Starts and ends in a neutral relaxed pose facing the camera. Natural, photorealistic, no text overlays, no subtitles.

- Untuk Salsa: ganti `[CHARACTER]` sesuai referensi (rambut sebahu, cardigan krem rajut, atasan hitam).
- Ganti `[ACTION]` sesuai tabel di atas.
- Simpan ke `assets/avatar/<persona>/<kode>.mp4` dan catat di `manifest.json`:

```json
{ "persona": "salsa",
  "clips": [ {"code": "talk_calm_1", "file": "talk_calm_1.mp4", "state": "talk", "energy": "calm"},
             {"code": "react_laugh", "file": "react_laugh.mp4", "state": "react", "emotion": "happy"} ] }
```

## Lampiran B: Variabel `.env` [C]
```
# Mode
LLM_MODE=live|mock            TTS_MODE=live|mock
# Gemini (model ID diisi setelah dicek di AI Studio)
GEMINI_API_KEY=
GEMINI_MODEL_BLOCKER=   GEMINI_MODEL_PERSONA=   GEMINI_MODEL_SHOWRUNNER=
GEMINI_MODEL_SUPERVISOR=  GEMINI_MODEL_TTS=   GEMINI_MODEL_JUDGE=
GEMINI_RPM_PERSONA=  GEMINI_RPM_SUPERVISOR=  GEMINI_RPM_SHOWRUNNER=  GEMINI_RPM_TTS=
# TTS
TTS_PRIMARY=elevenlabs   TTS_FALLBACK=edge
ELEVENLABS_API_KEY=   ELEVENLABS_MODEL=eleven_flash_v2_5
ELEVENLABS_VOICE_MALE=q8qwd1jY2jS3AWOBeq25   ELEVENLABS_VOICE_FEMALE=ffTJE9l3Kt2ipEM32UOc
EDGE_VOICE_MALE=id-ID-ArdiNeural   EDGE_VOICE_FEMALE=id-ID-GadisNeural
# STT (mode A)
STT_PROVIDER=webspeech|faster_whisper|gemini   FASTER_WHISPER_URL=
# Agen
SHOWRUNNER_POLICY=llm|fixed_turns|coverage_only
SHOWRUNNER_EVERY_K=3   MIN_TURNS_PER_TOPIC=6   MAX_TURNS_PER_TOPIC=40   FIXED_TURNS_PER_TOPIC=
SUPERVISOR_MODE=off|rules|full   SUPERVISOR_MAX_REGEN=1   SUPERVISOR_TIMEOUT_MS=5000
PIPELINE_DEPTH=1
# Avatar
AVATAR_TIER=t1|t2   AVATAR_WORKER_URL=
# Skripsi
COMMENTS_ENABLED=false   TIKTOK_USERNAME=
```
