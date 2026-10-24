# Setup OBS / TikTok LIVE Studio (Tahap 3, FR-10)

## Cara A (disarankan): Browser Source

Audio dan video stage diputar di dalam OBS, jadi tidak perlu menangkap jendela atau audio desktop.

1. Jalankan backend dan frontend (lihat README), pastikan konsol bisa dibuka di `http://localhost:5173`.
2. OBS → kanvas **1080×1920** (Settings → Video → Base/Output 1080x1920).
3. Sources → **+ Browser**:
   - URL: `http://localhost:5173/stage?clean=1`
   - Width 1080, Height 1920
   - centang **Control audio via OBS** (audio stage masuk mixer OBS);
   - jangan centang "Shutdown source when not visible".
4. Di konsol tab **Live**, panel Output harus menulis "Audio: stage". Stage yang pertama tersambung menjadi satu-satunya pemutar audio; konsol diam.
5. Klik **Cek pra-live**: TTS dipanaskan (suara ElevenLabs kadang cold start 15–20 s di request pertama).

Bila Browser Source OBS memblokir autoplay (jarang), klik kanan source → Interact, lalu klik sekali di halaman stage.

## Cara B: jendela popup

Tombol **Buka Stage** di konsol membuka popup 540×960 (`/stage?clean=1`). Di OBS pakai **Window Capture** ke jendela itu dan **Application Audio Capture** ke browser. Klik sekali di popup bila muncul pesan "Klik di mana saja untuk mengaktifkan audio".

## Mode A (Tahap 4)

Panel atas = kamera studio sebagai source OBS terpisah di atas stage; panel bawah = avatar AI. Stage menyisakan panel atas untuk itu.

## Pemeriksaan sebelum live (KT FR-10)

- Buka `http://localhost:5173/stage?zones=1` untuk melihat zona yang tertutup UI TikTok (header 0–10%, daftar komentar 65–91% tinggi × 0–70% lebar, bar bawah 93–100%, margin sisi 5%). Wajah dan teks penting tidak boleh di zona merah.
- Label **AI** di nameplate tiap panel harus terlihat sepanjang siaran.
- Aktifkan pengaturan label konten AI di TikTok, dan sebutkan di pembukaan bahwa penyiar adalah AI (persona melakukannya otomatis di giliran pertama).
- Uji dulu di akun TikTok pribadi.

## Klip avatar (FR-8)

Letakkan klip Google Flow di `assets/avatar/<raka|salsa>/<kode>.mp4` dengan kode sesuai Lampiran A PRD, dan `manifest.json` di folder yang sama (contoh format: jalankan `python assets/make_dummy_clips.py`, lalu salin strukturnya). Panel stage berbentuk 9:8, jadi klip 9:16 dipotong; atur `focus_y` (0 = atas, 1 = bawah, default 0,35) supaya wajah tetap di tengah panel. Saat membuat klip di Flow, letakkan wajah di sepertiga atas frame.
