# avatar-worker (FR-9, Avatar T2)

Lip-sync **MuseTalk 1.5** (TMElyralab, lisensi MIT untuk kode dan bobot) di atas klip bicara T1. Backend mengirim audio TTS tiap giliran atau kalimat; worker mengembalikan MP4 tanpa audio dengan bibir yang mengikuti audio. Stage memutar video itu sebagai pengganti klip bicara.

Berbeda dari skrip asli MuseTalk, worker ini **tidak memakai mmpose/mmcv**. Landmark wajah diambil dengan `face-alignment`, yang memakai skema 68 titik yang sama, sehingga bisa dipasang di Windows tanpa kompilasi.

## Pasang (mesin ber-GPU NVIDIA)

```bash
git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git ../../musetalk   # atau set MUSETALK_DIR
cd ../../musetalk
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install torch==2.4.1 torchvision==0.19.1 torchaudio==2.4.1 --index-url https://download.pytorch.org/whl/cu121
.venv/Scripts/python -m pip install -r ../penyiar-ai-v2/avatar-worker/requirements.txt
```

Bobot model (±4 GB) disimpan ke `musetalk/models/`:

| Folder | Sumber |
|---|---|
| `musetalkV15/` | `unet.pth`, `musetalk.json` dari `TMElyralab/MuseTalk` |
| `sd-vae/` | `config.json`, `diffusion_pytorch_model.bin` dari `stabilityai/sd-vae-ft-mse` |
| `whisper/` | `config.json`, `pytorch_model.bin`, `preprocessor_config.json` dari `openai/whisper-tiny` |
| `face-parse-bisent/` | `79999_iter.pth`, `resnet18-5c106cde.pth` dari `ManyOtherFunctions/face-parse-bisent` |

## Pakai

```bash
# sekali per persona: frame klip → bbox wajah, latent, mask (disimpan di avatars/<persona>/)
python server.py prepare raka ../assets/avatar/raka/talk_calm_1.mp4 --max-sec 5
# layanan render
python server.py serve --port 8100
```

Di `.env` backend:

```
AVATAR_TIER=t2
AVATAR_WORKER_URL=http://localhost:8100
```

Bila worker mati, lambat (lebih dari `AVATAR_RENDER_TIMEOUT_MS`), atau persona belum disiapkan, giliran tetap jalan dengan klip T1.

## Gerbang FR-9

RTF (waktu render ÷ durasi audio) harus ≤0,8 untuk mode B dan ≤0,3 untuk mode A. Setiap render mencetak RTF di log worker dan mengirimnya di header `X-RTF`. Hasil pengukuran dicatat di `docs/kt/avatar-t2-musetalk.md`.
