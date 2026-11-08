# Prompt pembuka untuk Claude Code

Tempel teks di bawah ini ke Claude Code di folder `penyiar-ai-v2`.

---

Kita akan menerapkan desain UI baru untuk Penyiar AI HITS. Bahan ada di `docs/design/`:

- `DESIGN.md`: token warna, font, bentuk, gerak, pola komponen, istilah UI wajib.
- `HANDOFF.md`: peta mockup → file kode, perubahan perilaku frontend/backend, urutan kerja, kriteria terima.
- `PRD-PERUBAHAN.md`: perubahan PRD hasil diskusi desain.
- `mockups/*.dc.html`: mockup statis per layar (HTML biasa di dalam `<x-dc>`, bisa dibaca sebagai acuan markup dan ukuran; abaikan `support.js` dan blok `data-dc-script` kecuali untuk `EditorMateri` dan `Tutorial` yang berisi logika interaksi contoh).

Aturan kerja:
1. PRD.md tetap acuan tunggal (CLAUDE.md). Langkah pertama: terapkan `PRD-PERUBAHAN.md` ke PRD.md (naikkan ke v2.7, catat di §17), lalu tunjukkan diff-nya ke saya sebelum lanjut.
2. Kerjakan mengikuti urutan di `HANDOFF.md` §3, satu tahap per commit. Setelah tiap tahap, jalankan tes yang ada dan uji dengan `LLM_MODE=mock` + `TTS_MODE=mock`.
3. Jangan hard-code model ID, harga, atau kuota (aturan PRD §0).
4. Ikuti istilah di `DESIGN.md` §5 untuk semua teks UI. Jangan pakai emoji sebagai ikon; pakai SVG garis.
5. Kalau ada keputusan yang tidak tercakup dokumen, tanya saya dulu, jangan menebak.

Mulai dari langkah 1.
