# Prompt Google Flow untuk bank klip avatar (Lampiran A PRD)

Dua karakter **fiktif** (jangan pakai foto orang sungguhan sebagai referensi). Setiap karakter butuh 15 klip. Simpan hasil ke `assets/avatar/<raka|salsa>/<kode>.mp4`.

## Langkah

1. **Buat gambar referensi karakter dulu** (Flow → gambar, atau generator gambar lain), satu per karakter, pakai prompt "Referensi karakter" di bawah. Pilih satu hasil terbaik.
2. Untuk setiap klip, buat video **dari gambar referensi itu** (Frames to Video / Ingredients), lalu tempel prompt klipnya. Memakai referensi yang sama di semua klip menjaga wajah, baju, dan latar tetap konsisten.
3. Rasio **9:16**, durasi 8 detik (stage memutar ulang klip, jadi awal dan akhir harus pose netral yang sama).
4. Suara dari Flow tidak dipakai (stage memutar video tanpa suara); tidak masalah bila klip punya audio.
5. Setelah unduh, cek:
   - wajah, kepala, bahu, dan mic berada di **20–65% tinggi frame** dari atas (bagian itu yang terlihat di panel stage; selebihnya terpotong);
   - tidak ada teks atau subtitle selain neon "HITS UNIKOM";
   - frame awal dan akhir hampir sama (supaya pergantian klip mulus).
6. Ganti klip dummy dengan klip Flow (nama file sama), lalu di `manifest.json` hapus baris `"dummy": true` dan **hapus entri klip yang filenya belum ada**: pemutar hanya memilih dari klip yang tercantum, dan klip tercantum yang filenya hilang gagal dimuat. Bila wajah terlalu tinggi/rendah di panel stage, ubah `focus_y` (0 = atas, 1 = bawah; default 0,35). Contoh format manifest: `python assets/make_dummy_clips.py`.

## Bagian prompt yang sama untuk semua klip

Tempelkan **[DESKRIPSI KARAKTER]** dan **[AKSI]** ke templat ini:

```
Vertical 9:16 video, medium close-up, chest-up framing. [DESKRIPSI KARAKTER], sitting behind a black broadcast microphone on a boom arm, the microphone slightly in front of the lower part of the face. Small radio studio with black acoustic foam walls and a glowing pink neon sign reading "HITS UNIKOM" on the wall behind, softly out of focus. Static locked-off camera, no camera movement, no zoom. Soft warm key light, natural skin tones, photorealistic, documentary look. The head and shoulders sit in the middle of the frame with generous empty space above the head and the desk below. [AKSI] The clip starts and ends in the same neutral relaxed pose facing the camera. No text overlays, no subtitles, no captions, no logos besides the neon sign.
```

## Deskripsi karakter

**Raka (pria)**

```
a fictional young Indonesian man in his early 20s, short neat black hair, warm friendly face, clean-shaven, wearing a dark navy bomber jacket over a plain white t-shirt
```

**Salsa (wanita)**

```
a fictional young Indonesian woman in her early 20s, shoulder-length straight dark brown hair, bright friendly face, light natural makeup, wearing a cream chunky knit cardigan over a plain black top
```

### Prompt gambar referensi (langkah 1)

```
Photorealistic vertical 9:16 portrait, medium close-up, chest-up. [DESKRIPSI KARAKTER], sitting behind a black broadcast microphone on a boom arm in a small radio studio with black acoustic foam walls and a glowing pink neon sign reading "HITS UNIKOM" behind, softly out of focus. Neutral relaxed expression looking at the camera, soft warm key light. Head and shoulders in the middle of the frame with empty space above the head. No other text.
```

## Aksi per klip

Kode = nama file. Ganti **[AKSI]** di templat dengan teks berikut (sama untuk Raka dan Salsa; ganti "he/his" menjadi "she/her" untuk Salsa).

| Kode | [AKSI] |
|---|---|
| `idle_1` | He sits still and breathes naturally, blinks occasionally, and looks calmly at the camera. |
| `idle_2` | He sits still with a relaxed posture, blinks, and briefly glances to the side before looking back at the camera. |
| `idle_3` | He sits quietly, shifts his shoulders slightly to get comfortable, and gives a faint smile to the camera. |
| `listen_1` | He listens attentively to someone off-screen to his side, nodding slowly with a small smile. |
| `listen_2` | He listens to someone off-screen, raises his eyebrows slightly with interest, and nods once. |
| `listen_3` | He listens to someone off-screen, smiles warmly, and gives two small nods of agreement. |
| `talk_calm_1` | He talks casually to the camera in a relaxed conversational way, with small natural hand gestures near the microphone. |
| `talk_calm_2` | He speaks calmly to the camera as if explaining something, tilting his head slightly, one hand making a small open-palm gesture. |
| `talk_calm_3` | He chats easily to the camera with a gentle smile, nodding lightly while he speaks. |
| `talk_hype_1` | He talks to the camera with high energy and excitement, expressive face, animated hand gestures, leaning slightly toward the microphone. |
| `talk_hype_2` | He speaks enthusiastically to the camera, laughing a little between words, with lively gestures. |
| `react_laugh` | He bursts into a genuine laugh, shoulders shaking slightly, then settles back into a relaxed smile and neutral pose. |
| `react_surprised` | He looks surprised, eyebrows raised and mouth slightly open as if saying "huh?", then relaxes back to neutral. |
| `react_thinking` | He thinks for a moment, eyes looking up, touching his chin with one hand, then lowers the hand and looks back at the camera. |
| `react_empathetic` | He shows a sympathetic expression, nodding slowly with soft eyes as if understanding someone's story, then returns to neutral. |

### Contoh prompt lengkap: Salsa `talk_hype_1`

```
Vertical 9:16 video, medium close-up, chest-up framing. A fictional young Indonesian woman in her early 20s, shoulder-length straight dark brown hair, bright friendly face, light natural makeup, wearing a cream chunky knit cardigan over a plain black top, sitting behind a black broadcast microphone on a boom arm, the microphone slightly in front of the lower part of the face. Small radio studio with black acoustic foam walls and a glowing pink neon sign reading "HITS UNIKOM" on the wall behind, softly out of focus. Static locked-off camera, no camera movement, no zoom. Soft warm key light, natural skin tones, photorealistic, documentary look. The head and shoulders sit in the middle of the frame with generous empty space above the head and the desk below. She talks to the camera with high energy and excitement, expressive face, animated hand gestures, leaning slightly toward the microphone. The clip starts and ends in the same neutral relaxed pose facing the camera. No text overlays, no subtitles, no captions, no logos besides the neon sign.
```

## Uji minimum (Tahap 0)

Bila ingin mencoba dulu sebelum membuat semua: `idle_1`, `listen_1`, `talk_calm_1` untuk tiap karakter (6 klip), dengan manifest berisi ketiga klip itu saja. Pemutar sudah menangani state yang kosong: tanpa klip `talk_hype` dipakai `talk_calm`, tanpa klip `react_*` reaksi dilewati.

## Catatan hasil Raka (25 Okt 2026)

15 klip Raka sudah terpasang di `assets/avatar/raka/` (audio dibuang, `focus_y` 0,3) dan diuji di stage dengan show mock.

- **Wajah, baju, dan neon konsisten.** Framing pas di panel 9:8: neon di atas, wajah di tengah, mic di bawah.
- **Posisi mic tidak sama antarklip.** Klip `talk_*` dan `react_*` seragam (mic dari kanan, dekat mulut). Klip `idle_*` dan `listen_*` berbeda-beda (mic di kiri atau tengah, zoom sedikit lain). Akibatnya mic terlihat pindah saat crossfade antara mendengarkan dan berbicara.
- **Frame awal dan akhir tidak sama** (PSNR 20–34 dB). Karena itu pemutar tidak lagi me-loop klip, tetapi berganti klip dengan crossfade setiap kali klip habis.
- **Durasi 10 s**, di luar spesifikasi 4–8 s, tetapi tidak masalah untuk pemutar.

**Saran perbaikan (opsional):** buat ulang `idle_1..3` dan `listen_1..3` dengan *Frames to Video* memakai frame awal `talk_calm_1` sebagai frame pertama, supaya mic dan zoom sama dengan klip bicara.

**Untuk Salsa:** buat semua 15 klip dari satu frame awal yang sama sejak awal.
