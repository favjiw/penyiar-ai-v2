# DESIGN.md: Penyiar AI HITS

Acuan visual dan perilaku UI untuk `penyiar-ai-v2`. Disepakati lewat diskusi desain 8 Nov 2026.
Mockup lengkap: Design artifact "Penyiar AI HITS" (https://claude.ai/code/artifact/fa1d5d8c-94f6-4037-ab97-bc45705bb72b) dan salinannya di `docs/design/mockups/`.

## 1. Arah visual

- **Tema:** "Ceria, rapi, ala studio HITS". Terang (light mode), mayoritas putih, identitas dari aset HITS (logo, warna biru-kuning, garis gelap gaya stiker, balon ucapan).
- **Hindari ("AI slop"):** gradien warna, orb bercahaya, emoji sebagai ikon, kartu dengan garis tepi kiri berwarna, semua kartu berbobot sama, satu warna aksen untuk semua hal.
- **Tiga "volume" per halaman:**

| Halaman | Pengguna | Gaya |
|---|---|---|
| Konsol `/` | Produser, layar 1920 px | Putih, kalem, padat informasi, hampir tanpa animasi |
| Prompter `/prompter` | Penyiar, PC/laptop 1920×1080, dibaca dari 1–1,5 m | Light mode, teks hitam, huruf sangat besar, latar status berganti warna |
| Stage `/stage` | Penonton TikTok (via OBS) | Hanya karakter, tanpa teks atau komponen apa pun |

## 2. Token

Tempel ke `frontend/src/styles.css` sebagai CSS variables (nama boleh disesuaikan, nilai jangan diubah).

```css
:root {
  /* Merek (diambil dari logo HITS) */
  --brand-blue: #69C1D5;      /* isi tombol utama; teks di atasnya WAJIB --ink (9,05:1). Putih di atasnya gagal (2,1:1) */
  --blue-700: #106C7D;        /* teks tautan/aksi kecil di atas putih (6,06:1) */
  --blue-50: #E9FBFF;         /* latar kotak "Tanya penonton", saran, sorotan info */
  --blue-100: #DBF4FA;
  --brand-yellow: #FEE980;    /* status "Giliranmu", sorotan */
  --yellow-50: #FFF8D4;       /* peringatan kuning, baris "paling cepat habis" */
  --yellow-ink: #7D590A;      /* teks status kuning di atas putih */
  --orange-400: #FC9445;      /* badge LIVE */
  --orange-500: #E27813;      /* cincin waktu "lewat waktu" */
  --orange-ink: #934A00;
  --gold-ring: #E5AE10;       /* cincin waktu "hampir habis" */
  --ink: #111312;             /* teks utama, garis stiker */

  /* Netral (sedikit hangat) */
  --n-0: #FFFFFF;  --n-50: #F8F7F4;  --n-100: #F1F0ED;  --n-200: #E6E4E2;
  --n-300: #D5D4D1; --n-400: #A6A4A2; --n-600: #646361;  /* teks sekunder minimal n-600 (6,0:1) */
  --n-700: #494745;

  /* Status */
  --success: #077836;  --success-bg: #E8FBEB;
  --danger:  #A83630;  --danger-bg:  #FFF2F0;  --danger-band: #FFE3DF;

  /* Bentuk */
  --r-input: 10px;  --r-card: 16px;  --r-panel: 24px;  --r-pill: 999px;
  --shadow-card: 0 1px 2px rgba(17,19,18,.04), 0 4px 16px rgba(17,19,18,.06);
  --shadow-pop:  0 2px 4px rgba(17,19,18,.06), 0 16px 40px rgba(17,19,18,.14);
  --shadow-sticker: 3px 3px 0 var(--ink);   /* hanya badge LIVE (+ border 2px ink) */

  /* Gerak */
  --t-fast: 120ms; --t-base: 200ms; --t-state: 320ms; --ease: cubic-bezier(.2,.7,.2,1);
}
```

Latar halaman konsol: `radial-gradient(var(--n-200) 1.3px, transparent 1.6px) 0 0 / 24px 24px, var(--n-50)` (grid titik halus). Kartu tetap putih polos. Prompter polos putih.

## 3. Tipografi

Font tunggal: **Plus Jakarta Sans** (Google Fonts, bobot 400/500/600/700/800). Cadangan: `'Segoe UI', system-ui, sans-serif`.

| Halaman | Skala |
|---|---|
| Konsol (dasar 16px, rasio 1,2) | 12 · 13 · 14 · **16** · 19 · 23 · 28 · 33 |
| Prompter | Status 128 (Mic tidak terdengar 112) · judul topik 68 · pertanyaan penonton 44 (800, KAPITAL) · bahan obrolan 36 · info 20–34 · waktu di cincin 46 + label 20 |
| Stage | Tanpa teks |

Gaya tulisan HITS di prompter: pertanyaan penonton dan kalimat pindah topik ditampilkan **KAPITAL** dengan tanda jeda `/` (koma) dan `//` (akhir kalimat). Konversi otomatis dari teks biasa; data tetap disimpan normal.

## 4. Komponen dan pola

- **Tombol utama:** isi `--brand-blue`, teks `--ink`, tinggi 44–56px, radius 10. Tombol sekunder: putih, border 1.5px `--n-200`. Aksi berbahaya: teks/border `--danger`, dipisah dari aksi lain.
- **Target klik minimal 44×44px.** Fokus keyboard: outline 2px `--brand-blue`.
- **Badge LIVE:** oranye, border 2px ink, bayangan stiker, titik berkedip.
- **Cincin waktu:** SVG r=50 viewBox 120, stroke 11; teks waktu harus muat di dalam lingkaran. Tiga keadaan: biru (normal) → emas "hampir habis" (sisa ≤30 dtk) → oranye penuh "+m:ss lewat waktu" (hitung naik).
- **Bar level suara:** 4–5 batang. **Hanya bergerak mengikuti level audio sungguhan** (mic penyiar dari mixer, atau audio TTS AI yang sedang diputar). Saat hening: diam rata rendah. Tidak ada animasi looping.
- **Peringatan (konsol saja):** tumpuk di atas konten, terbaru di atas, bukan pop-up.
  - Merah (`--danger`): siaran terganggu, perlu tindakan sekarang; tetap tampil sampai beres.
  - Kuning (`--yellow-50` + border ink): akan jadi masalah; bisa ditutup.
  - Biru (`--blue-50`): info; hilang sendiri setelah 10 dtk.
  - Judul tab browser diberi `(!)` saat ada peringatan merah. Konsol tidak bersuara.
- **Panduan pengguna baru:** muncul otomatis saat konsol pertama dibuka (simpan flag di localStorage), bisa dibuka lagi lewat tombol "Panduan" di header. Sapaan → 5 langkah dengan sorotan elemen (posisi dihitung dari `getBoundingClientRect`, bukan angka tetap), Kembali/Lanjut, titik progres, Lewati, keyboard ←/→/Esc.
- **Stage:** karakter di tengah panel (area aman TikTok: atas tertutup bar akun, bawah kolom komentar, kanan ikon). Final memakai klip video realistis (diam/mendengarkan/bicara) yang mengisi panel, crossfade ±200 ms. Ilustrasi di mockup hanya pengganti sementara. Label AI memakai setelan konten AI bawaan TikTok, bukan teks di layar.

## 5. Istilah UI (wajib konsisten)

| Pakai | Jangan pakai |
|---|---|
| Materi (materi obrolan) | Rundown, blocker, blocking |
| Kuota (otak AI, suara AI) + persen + "Cukup ±N menit" | Permintaan, RPD, karakter, kredit |
| Otak AI, Suara AI, Pendengar suara penyiar | Gemini, ElevenLabs, STT, LLM, TTS |
| Layar untuk OBS | Stage, jendela stage |
| Cek kesiapan, Kesiapan siaran | Cek pra-live, layanan |
| Saran pengarah acara | Showrunner |
| Topik selanjutnya | Next topik, lompat topik |
| Bahan obrolan | Poin |
| Tanya penonton | Pertanyaan audiens |

Nama model/vendor dan angka mentah hanya di bagian "Detail teknis" (untuk peneliti). Bahasa konsol netral-santai; "Sobat Hits" hanya untuk ucapan AI.

## 6. Aksesibilitas

Kontras teks ≥4,5:1 (≥3:1 untuk ≥24px). Status tidak hanya dibedakan warna: selalu ada teks/ikon. Elemen interaktif memakai `<button>`, `<a>`, `<input>` + `<label>` asli. `prefers-reduced-motion`: matikan gerak skala/geser, sisakan perubahan warna.
