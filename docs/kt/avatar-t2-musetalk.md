# Avatar T2: MuseTalk 1.5 untuk Raka (FR-9)

Tanggal: 25 Okt 2026. Pemicu: uji mode A oleh Favian. Gerak mulut klip T1 tidak sinkron dengan suara; Favian meminta riset MuseTalk dan mencobanya untuk Raka.

## Riset

| Aspek | Temuan |
|---|---|
| Versi | MuseTalk 1.5 (TMElyralab, rilis Maret 2025), mode *realtime*: avatar disiapkan sekali, lalu setiap audio dirender dari latent yang di-cache. |
| Lisensi | Kode MIT. Bobot model boleh dipakai untuk apa pun, termasuk komersial. Komponen pihak ketiga (Whisper, sd-vae-ft-mse, DWPose, S3FD) mengikuti lisensi masing-masing. Data uji MuseTalk hanya untuk riset non-komersial (tidak kita pakai). |
| Cara kerja | Wajah dipotong 256×256. Setengah bawah wajah dibuat ulang oleh UNet (satu langkah, bukan difusi berulang) berdasarkan fitur audio Whisper-tiny, lalu ditempel kembali dengan mask rahang (BiSeNet). |
| Kecepatan acuan | 30 fps lebih di Tesla V100 (klaim repo). Konfigurasi minimum yang dilaporkan: RTX 3050 Ti 4 GB fp16, ±5 menit untuk video 8 s. Tidak ada angka untuk GPU Pascal. |
| Ketergantungan | Repo asli memakai mmpose/mmcv (DWPose) untuk landmark, yang sulit dipasang di Windows. |

Sumber: https://github.com/TMElyralab/MuseTalk

## Yang dibangun

- **`avatar-worker/`:** `prepare` membuat material avatar dari klip T1. `serve` menjalankan `POST /render?persona=` (audio → MP4 tanpa audio, header `X-RTF`).
  - DWPose diganti `face-alignment` (68 landmark, skema sama), jadi tidak perlu mmcv.
  - `torch.compile` dimatikan karena Triton tidak mendukung GPU Pascal.
  - fp16 hanya dipakai di GPU Volta ke atas (`MUSETALK_FP16` untuk memaksa).
- **Backend (`AVATAR_TIER=t2`):** setiap audio TTS (mode B per giliran, mode A per kalimat) dikirim ke worker. `video_url` ikut di event `turn` / `audio_part`. Bila worker gagal atau lebih lama dari `AVATAR_RENDER_TIMEOUT_MS`, giliran tetap memakai klip T1.
- **Stage:** video lip-sync menggantikan klip bicara selama audionya diputar dan disamakan ke posisi audio. Setelah video habis, avatar kembali ke klip T1.
- Avatar Raka disiapkan dari `talk_calm_1.mp4`, 5 s pertama (125 frame, diputar maju-mundur menjadi siklus 250 frame).

## Hasil di laptop (MX250 2 GB, Windows 10)

| Audio | Presisi | Durasi audio | Waktu render | RTF | VRAM puncak |
|---|---|---|---|---|---|
| Raka, ElevenLabs | fp16 | 2,59 s | 1.089 s | 421 | 2,77 GB |
| Raka, ElevenLabs | fp16 | 4,08 s | 1.664 s | 408 | 2,77 GB |

- Memuat model butuh 69 s. Menyiapkan avatar (125 frame) butuh ±5,7 menit.
- Kebutuhan VRAM (2,77 GB) melebihi 2 GB, sehingga Windows memindahkan sebagian ke RAM bersama. Ditambah fp16 yang sangat lambat di Pascal, hasilnya RTF ±400. **Tidak bisa dipakai di laptop ini**, baik live maupun pra-render.

**Kualitas** (contoh `docs/kt/raka-musetalk-contoh.mp4`, lokal dan tidak di-commit):
- Bentuk mulut membuka dan menutup mengikuti suku kata.
- Wajah, mata, dan kepala tetap dari klip Flow.
- Ujung atas mic yang menempel di dagu ikut terkena mask rahang dan tampak buram. Bisa dikurangi dengan memilih klip yang mic-nya lebih jauh dari dagu, atau dengan memperkecil mask (`left/right_cheek_width`, `extra_margin`).

## Gerbang FR-9 dan langkah berikutnya

- Gerbang (RTF ≤0,8 mode B, ≤0,3 mode A) **belum bisa diputuskan**: harus diukur di PC lab GTX 1080 (8 GB, fp32), dengan langkah pasang yang sama (`avatar-worker/README.md`).
- **Perkiraan kasar, belum diukur:** GTX 1080 ±9 TFLOPS fp32, ±1/3 dari V100 dengan fp16 tensor core. Bila V100 mencapai 30 fps, GTX 1080 mungkin ±5–10 fps, atau RTF ±2,5–5 pada 25 fps. Itu kemungkinan masih di atas gerbang mode B. Pilihan bila meleset: render resolusi panel lebih kecil, batch lebih besar, atau GPU yang lebih baru.
- Sampai gerbang lolos, default tetap `AVATAR_TIER=t1`.
