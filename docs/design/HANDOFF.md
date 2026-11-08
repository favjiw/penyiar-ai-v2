# Handoff desain → kode: Penyiar AI HITS

Dokumen ini menerjemahkan desain yang disepakati (lihat `DESIGN.md` dan `mockups/`) ke pekerjaan di repo. Baca juga `PRD-PERUBAHAN.md`: PRD.md tetap acuan tunggal, jadi perubahan di sana diterapkan dulu sebelum kode.

## 0. Ringkasan keputusan

1. **Penyiar tidak perlu klik apa pun** (pesan pembimbing). Mikrofon hands-free; giliran ketat (AI tidak bisa disela, mic dijeda saat AI bicara). Pindah topik lewat ucapan penyiar; tombol "Topik selanjutnya" (N) hanya opsional.
2. **Kendali alur mode A penuh di penyiar.** Waktu hanya panduan. AI memberi kode halus **satu kali** saat lewat ±2 menit.
3. **Stage terpisah** (`/stage`), satu-satunya pemutar audio, tanpa teks. Mode B: satu jendela 9:16 dua panel. Mode A: satu panel AI (kamera studio ditumpuk di OBS). Dibuka sebagai popup bernama tetap.
4. **Siaran 1 jam:** ±6 topik × ±9 menit + Opening 3 + Closing 3. Jumlah topik mengikuti durasi.
5. **Istilah HITS:** "materi" menggantikan "rundown/blocker"; pertanyaan penonton jadi elemen utama, bahan obrolan pendukung.
6. Light mode, Plus Jakarta Sans, warna merek HITS, tanpa AI slop.

## 1. Peta halaman → kode

| Mockup | Rute / komponen | Status kode sekarang | Yang dikerjakan |
|---|---|---|---|
| `Main` Konsol · Siapkan siaran | `/` → `console/BlockerStudio.tsx` + `console/LivePanel.tsx` (bagian pra-live) | Dua tab (Blocker, Live), pilihan varian tidak terbawa ke Live | Satukan jadi satu halaman tiga langkah: (1) tema + target pendengar → Buat materi, (2) kartu varian dengan "Pakai ini" / "Lihat & ubah", (3) panel "Siap live" yang langsung terisi varian terpilih. Hapus tab. |
| `EditorMateri` | modal/halaman dari "Lihat & ubah" → ganti `console/BlockerEditor.tsx` | Form panjang ±40 kolom | Tiga kolom: susunan materi (status per bagian + menit), editor bagian aktif, pratinjau prompter. Simpan otomatis, tanpa tombol kunci (kunci saat mulai live). Maks 8 topik. |
| `KonsolCekKesiapan` | tombol header "Cek kesiapan" + popover | `Cek pra-live` teks abu kecil | Panel: perkiraan menit aman vs target durasi, kuota per layanan (persen + "Cukup ±N menit"), pilihan bila kurang (lanjut pakai cadangan / kurangi target). |
| `KonsolLive` | `/` saat live → `console/LivePanel.tsx` | Orb gradien, transkrip, panel teknis | Progres siaran X/60 mnt per segmen, kartu siapa bicara (bar level nyata), urutan materi, poin + cincin waktu, saran pengarah acara, transkrip, status. Hapus `Orb.tsx`/`orb.css`. |
| `KonsolPeringatan` | strip peringatan di `LivePanel` | `live.alerts` satu baris | Tiga tingkat peringatan (lihat DESIGN.md §4). |
| `Tutorial` | komponen `GuidedTour` di konsol | tidak ada | Sapaan + 5 langkah, tombol "Panduan" di header, flag localStorage. |
| `PrompterGiliran/Berpikir/AIBicara/Pindah/MicPutus` | `/prompter` → `prompter/PrompterPage.tsx` | Tombol, checkbox hands-free, status kecil | Band status penuh (Giliranmu kuning / AI bicara biru / AI mikir abu / Pindah topik hijau / Mic tidak terdengar merah muda), topik + TANYA PENONTON besar + bahan obrolan, cincin waktu 3 keadaan, "Siaran m:ss / 60:00", kalimat pindah topik + tombol opsional N, layar "Menunggu produser…" sebelum live. Tanpa pengaturan di layar penyiar. |
| `StageModeA/B` | **baru** `/stage` → `stage/StagePage.tsx` | tidak ada (rute tak dikenal jatuh ke konsol) | Halaman karakter saja + pemutar audio. Rute tak dikenal → 404, bukan konsol. |

## 2. Perilaku yang harus diubah (bukan sekadar tampilan)

**Frontend**
- `App.tsx`: rute `/`, `/prompter`, `/stage`, selain itu 404. Hanya `/stage` yang memutar audio (`useLiveSession('stage')`); konsol bisu. Cegah dua pemutar aktif.
- Konsol: tombol "Buka layar OBS" membuka `window.open('/stage','hits-stage','popup,width=540,height=960')` (mode A: 540×480).
- Saat persiapan sesi baru, bersihkan transkrip/status sesi lama.
- Pilihan "Gender AI" diganti pilihan **persona** (Salsa/Raka) + suara dengan tombol dengar contoh.
- Ingat nama penyiar dan suara terakhir (localStorage).
- `window.confirm` diganti dialog/undo di dalam halaman.
- `prompter/usePushToTalk.ts`: tetap hands-free (Web Speech), mic dijeda saat AI bicara/berpikir; tampilkan status lewat band, bukan teks kecil. Hapus checkbox mode dari layar penyiar (pindah ke konsol bila perlu).
- Bar level suara dari `AnalyserNode` (Web Audio) atas stream mic dan audio TTS, bukan animasi CSS loop.

**Backend**
- Deteksi niat pindah topik dari ucapan penyiar (mode A): setiap giliran manusia final, klasifikasi ringan (LLM murah atau aturan kata kunci + kalimat transisi materi) → event `topic_change {from,to,reason:'voice'}`; bisa dibatalkan (`POST /api/show/undo-topic`).
- Showrunner mode A: tidak memindah topik; kirim `nudge` sekali saat lewat ≥120 dtk → persona menyisipkan kode halus.
- Waktu per topik ±9 menit (dari materi), bukan `POINT_TIME_LIMIT_S` 60 dtk per poin untuk mode A. Event `point_clock` menambah `total_played_s` dan `target_s`.
- Cek kesiapan (`POST /api/precheck`): kembalikan per layanan `{kind:'llm'|'tts'|'stt', percent_left, minutes_left}`, `minutes_safe` (minimum), `target_minutes`, `fallbacks`.
  - Kuota harian Gemini **harus dihitung sendiri** (API tidak memberi sisa RPD): tambah penghitung permintaan harian per model di `llm/rate_limiter.py` (reset pukul 00.00 waktu Pasifik, sesuai reset kuota Google), simpan ke file.
  - Sisa kredit ElevenLabs dari endpoint subscription akun; `tts/provider.py` sudah punya `credits_used` per sesi.
  - Menit = sisa ÷ pemakaian rata-rata per menit (ukur dari `sessions/*/turns.jsonl`; asumsi awal ±9 permintaan AI dan ±900 karakter suara per menit).
- Generator materi (FR-1): input `durasi_menit` (default 60) → jumlah topik ≈ (durasi − 6) / 9; setiap topik punya `menit`.
- Peringatan saat live: event WS `alert {level:'red'|'yellow'|'blue', code, message, actions[]}` untuk mic hening ≥8 dtk, layar OBS (klien `stage`) terputus, kuota suara ≤5 menit, cadangan aktif.

## 3. Urutan kerja yang disarankan

1. Terapkan `PRD-PERUBAHAN.md` ke PRD.md (+ catat di §17 Riwayat).
2. Token + font global (`styles.css`), komponen dasar (Button, Card, Pill, Ring, LevelBars, Alert).
3. `/stage` + pindah pemilik audio + 404. (Paling berisiko untuk live; kerjakan awal.)
4. Konsol Siapkan siaran (satu halaman) + panel Siap live + durasi.
5. Prompter baru (status band, cincin waktu, total waktu) + layar menunggu.
6. Konsol saat live + progres + peringatan.
7. Backend: durasi materi, waktu per topik, kode halus, deteksi pindah topik, cek kesiapan berbasis kuota.
8. Editor materi.
9. Panduan pengguna baru.
10. Uji mode A dan B 60 menit (mock dulu: `LLM_MODE=mock`, `TTS_MODE=mock`).

## 4. Kriteria terima desain

- Tidak ada teks yang keluar dari wadahnya atau bertabrakan (cek di 1920×1080 dan 1366×768).
- Prompter terbaca dari 1,5 m; penyiar bisa menjalankan siaran 60 menit **tanpa satu klik pun**.
- Layar OBS tidak memuat teks/komponen apa pun.
- Animasi suara diam saat hening.
- Semua istilah sesuai DESIGN.md §5.
- Kontras teks ≥4,5:1.

## 5. Isi contoh di mockup

Isi topik 2–6, bahan obrolan topik 2, Closing, angka kuota (82%, 36%, ±40 menit), "Mixer USB", dan waktu di prompter adalah contoh desain, bukan data nyata.
