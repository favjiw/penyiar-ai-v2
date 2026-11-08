# Usulan perubahan PRD (dari diskusi desain 8 Nov 2026)

Terapkan ke `PRD.md` sebelum menulis kode, naikkan versi (mis. v2.7), dan catat di §17 Riwayat. Status di kolom kanan memakai penanda PRD: [F] = keputusan Favian.

| Bagian PRD | Sekarang | Ubah menjadi |
|---|---|---|
| §1 (baru) | – | Tambah "Keputusan desain 8 Nov 2026" yang merangkum butir di bawah, rujuk `docs/design/DESIGN.md` dan `docs/design/HANDOFF.md`. [F] |
| §3 Istilah | Blocker, Mode A: penyiar menekan "next topik" | **Materi** (istilah HITS) menggantikan "blocker" di UI; Mode A: penyiar memindah topik lewat ucapan (opsional tombol N). [F] |
| §4 Pengguna | Penyiar: push-to-talk, menekan "next topik" | Penyiar tidak wajib klik apa pun: mic hands-free, giliran ketat, pindah topik lewat ucapan. [F] |
| §5.1 Sebelum live | Operator memilih varian, mengunci, memilih mode | Satu halaman: tema + target pendengar → pilih materi → Siap live (format, **durasi**, persona+suara, cek otomatis) → Mulai live. Kunci otomatis saat mulai. [F] |
| FR-1 Generator | Jumlah topik 1–3; 3–5 poin | Input `durasi_menit` (30/45/60/90, default **60**). Jumlah topik ≈ (durasi − 6) / 9 (60 mnt → 6 topik), tiap topik punya `menit` (default 9). Pertanyaan penonton = elemen utama; 3–5 bahan obrolan pendukung. Editor: maks 8 topik, simpan otomatis. [F] |
| FR-2 Show Engine, mode A | Waktu menipis → AI menutup, poin pindah otomatis | **Tidak ada pindah otomatis** di mode A. Waktu per topik = `menit` materi (bukan 60 dtk/poin). Pindah topik dipicu niat dari ucapan penyiar atau tombol N; bisa dibatalkan. [F] |
| FR-4 Showrunner, mode A | Hanya saran | Tetap saran + `nudge` **satu kali** per topik saat lewat ≥120 dtk → persona menyisipkan kode halus. Catat durasi lewat waktu per topik di log. [F] |
| FR-6 TTS | Pilihan suara sebelum live | Ditambah: contoh suara bisa didengar; suara dan nama penyiar terakhir diingat. |
| FR-7 Input mode A | PTT (tahan/tekan), Esc batal | Hands-free (Web Speech), **tanpa menyela**: mic dijeda saat AI bicara/berpikir. Sumber suara = mikrofon studio lewat mixer; pemilihan perangkat input dan meter level di cek kesiapan. Penyiar memakai headphone. [F] |
| FR-10 Stage | Ditunda (§1.3.1) | **Dihidupkan lagi versi ringan**: `/stage` tanpa teks, satu-satunya pemutar audio, popup nama tetap (mode B 540×960 dua panel, mode A 540×480 satu panel). Avatar final = klip video realistis (gaya Google Flow); sementara memakai ilustrasi. [F] |
| FR-11 Konsol & prompter | Konsol: tab, cek pra-live; Prompter: tombol PTT & next | Sesuai `HANDOFF.md` §1: konsol satu halaman + editor materi + cek kesiapan + progres siaran + peringatan 3 tingkat + panduan pengguna baru; prompter tanpa pengaturan, band status, cincin waktu 3 keadaan, "Siaran m:ss / target". |
| §6.3 Event WS | – | Tambah `topic_change`, `nudge`, `alert`, `total_played_s`/`target_s` di `point_clock`. Role `stage` kembali dipakai. |
| §6.4 API | `POST /api/precheck` | Kembalikan kuota per layanan (persen + menit), `minutes_safe`, `target_minutes`. Tambah `POST /api/show/undo-topic`. |
| §8 Non-fungsional, Kuota | Rate limiter per menit | Tambah penghitung kuota harian per model (Gemini tidak memberi sisa RPD). Target siaran 60 menit harus tercapai dengan cadangan otomatis. |
| §13/§14 Uji | Mode B 20 menit; obrolan 40+ menit | Mode A dan B **60 menit** tanpa crash; mode A tanpa klik penyiar. |
| §15.2 Keputusan terbuka | #2 nama penyiar, #3 Opening/Closing mode A | Tutup: nama penyiar diisi sekali di konsol dan diingat; AI ikut di semua segmen. |
