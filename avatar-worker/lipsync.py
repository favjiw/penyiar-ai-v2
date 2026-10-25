"""Avatar T2 (FR-9): lip-sync MuseTalk 1.5 di atas klip bicara T1.

Memakai modul dari clone MuseTalk (MIT, kode dan bobot), tetapi tanpa mmpose/mmcv:
landmark wajah diambil dengan `face-alignment` (68 titik, skema sama dengan potongan
wajah DWPose yang dipakai MuseTalk), jadi bisa dipasang di Windows tanpa kompilasi.

Dua tahap, seperti `scripts/realtime_inference.py` MuseTalk:
1. `prepare_avatar`: sekali per persona. Frame klip → bbox wajah → latent VAE + mask
   blending, disimpan ke `avatars/<persona>/`.
2. `LipSync.render`: per audio. Fitur Whisper → UNet → decode VAE → tempel ke frame
   asli → MP4 tanpa audio (stage memutar audio TTS sendiri).
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import torch

FPS = 25  # MuseTalk dilatih pada 25 fps


def use_fp16(device: str) -> bool:
    """fp16 hanya di GPU Volta ke atas: Pascal (MX250, GTX 1080) menghitung fp16 ±1/64 kecepatan fp32."""
    env = os.environ.get("MUSETALK_FP16")
    if env is not None:
        return env == "1"
    return device == "cuda" and torch.cuda.get_device_capability()[0] >= 7


def musetalk_dir() -> Path:
    d = Path(os.environ.get("MUSETALK_DIR", Path(__file__).resolve().parents[2] / "musetalk"))
    if not (d / "musetalk").is_dir():
        raise SystemExit(f"Clone MuseTalk tidak ditemukan di {d} (set MUSETALK_DIR)")
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    return d


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def read_frames(video: Path, max_sec: float) -> list[np.ndarray]:
    """Frame BGR dari klip, diresample ke 25 fps."""
    cmd = [ffmpeg_exe(), "-v", "error", "-i", str(video), "-t", str(max_sec), "-vf", f"fps={FPS}",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (w * h * 3)
    return [np.frombuffer(raw, np.uint8, w * h * 3, i * w * h * 3).reshape(h, w, 3).copy() for i in range(n)]


def face_bbox(lm: np.ndarray, height: int, extra_margin: int = 10) -> tuple[int, int, int, int]:
    """Bbox MuseTalk dari 68 landmark: atas = titik hidung 29 dikurangi jarak hidung–dagu."""
    nose_y = lm[29, 1]
    half = lm[:, 1].max() - nose_y
    x1, x2 = int(lm[:, 0].min()), int(lm[:, 0].max())
    y1, y2 = int(max(0, nose_y - half)), int(lm[:, 1].max())
    return x1, y1, x2, min(height, y2 + extra_margin)


def prepare_avatar(clip: Path, out: Path, max_sec: float = 5.0, device: str = "cuda") -> None:
    mt = musetalk_dir()
    os.chdir(mt)  # FaceParsing memuat bobot lewat path relatif ./models
    import face_alignment
    from musetalk.models.vae import VAE
    from musetalk.utils.blending import get_image_prepare_material
    from musetalk.utils.face_parsing import FaceParsing

    frames = read_frames(clip, max_sec)
    print(f"{len(frames)} frame dari {clip.name}", flush=True)
    # compile=False: torch.compile butuh Triton, yang tidak mendukung GPU Pascal (MX250, GTX 1080)
    fa = face_alignment.FaceAlignment(face_alignment.LandmarksType.TWO_D, device=device, compile=False)
    boxes = []
    for i, f in enumerate(frames):
        lms = fa.get_landmarks_from_image(f[:, :, ::-1])
        if not lms:
            raise SystemExit(f"Wajah tidak terdeteksi di frame {i}")
        boxes.append(face_bbox(lms[0], f.shape[0]))
    del fa
    torch.cuda.empty_cache()

    vae = VAE(model_path=str(mt / "models" / "sd-vae"), use_float16=use_fp16(device))
    fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)
    latents, masks, crops = [], [], []
    for f, (x1, y1, x2, y2) in zip(frames, boxes):
        face = cv2.resize(f[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
        latents.append(vae.get_latents_for_unet(face).cpu())
        mask, crop = get_image_prepare_material(f, [x1, y1, x2, y2], fp=fp, mode="jaw")
        masks.append(mask)
        crops.append(crop)

    # Maju lalu mundur supaya putaran frame tidak melompat (seperti MuseTalk).
    cycle = lambda xs: list(xs) + list(xs)[::-1]  # noqa: E731
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "frames.npy", np.stack(cycle(frames)))
    torch.save(torch.cat(cycle(latents)), out / "latents.pt")
    with open(out / "material.pkl", "wb") as fh:
        pickle.dump({"boxes": cycle(boxes), "masks": cycle(masks), "crops": cycle(crops), "clip": clip.name}, fh)
    print(f"Avatar tersimpan di {out} ({len(frames) * 2} frame siklus)")


@dataclass
class Avatar:
    frames: np.ndarray  # (N, H, W, 3) BGR
    latents: torch.Tensor  # (N, 8, 32, 32)
    boxes: list
    masks: list
    crops: list
    pos: int = 0  # posisi siklus berikutnya: render berurutan menyambung gerak kepala

    @classmethod
    def load(cls, d: Path) -> "Avatar":
        with open(d / "material.pkl", "rb") as fh:
            m = pickle.load(fh)
        return cls(np.load(d / "frames.npy"), torch.load(d / "latents.pt"), m["boxes"], m["masks"], m["crops"])


def blend(frame: np.ndarray, face: np.ndarray, box, mask: np.ndarray, crop) -> np.ndarray:
    """Tempel wajah hasil UNet ke frame dengan mask jaw (versi numpy dari get_image_blending)."""
    x1, y1, x2, y2 = box
    xs, ys, xe, ye = crop
    h, w = frame.shape[:2]
    out = frame.copy()
    region = out[max(0, ys):min(h, ye), max(0, xs):min(w, xe)]  # view
    big = frame[max(0, ys):min(h, ye), max(0, xs):min(w, xe)].copy()
    oy, ox = y1 - max(0, ys), x1 - max(0, xs)
    big[oy:oy + (y2 - y1), ox:ox + (x2 - x1)] = cv2.resize(face, (x2 - x1, y2 - y1))
    m = mask[max(0, ys) - ys:max(0, ys) - ys + region.shape[0], max(0, xs) - xs:max(0, xs) - xs + region.shape[1]]
    a = (m.astype(np.float32) / 255.0)[..., None]
    region[:] = (big * a + region * (1 - a)).astype(np.uint8)
    return out


class LipSync:
    def __init__(self, avatars_dir: Path, device: str = "cuda", batch_size: int = 4):
        mt = musetalk_dir()
        from diffusers import UNet2DConditionModel
        from transformers import WhisperModel

        from musetalk.models.unet import PositionalEncoding
        from musetalk.models.vae import VAE
        from musetalk.utils.audio_processor import AudioProcessor

        self.device = device
        self.dtype = torch.float16 if use_fp16(device) else torch.float32
        self.batch_size = batch_size
        import json

        cfg = json.loads((mt / "models/musetalkV15/musetalk.json").read_text())
        unet = UNet2DConditionModel(**cfg)
        # Muat ke CPU dulu: bobot fp32 3,4 GB tidak muat di VRAM kecil sebelum (bila perlu) dijadikan fp16.
        unet.load_state_dict(torch.load(mt / "models/musetalkV15/unet.pth", map_location="cpu"))
        self.unet = unet.to(self.dtype).to(device).eval()
        self.vae = VAE(model_path=str(mt / "models/sd-vae"), use_float16=self.dtype == torch.float16)
        self.pe = PositionalEncoding(d_model=384).to(self.dtype).to(device)
        self.whisper = WhisperModel.from_pretrained(str(mt / "models/whisper")).to(device=device, dtype=self.dtype).eval()
        self.whisper.requires_grad_(False)
        self.audio = AudioProcessor(feature_extractor_path=str(mt / "models/whisper"))
        self.avatars = {d.name: Avatar.load(d) for d in Path(avatars_dir).iterdir() if (d / "material.pkl").exists()}
        self.lock = threading.Lock()  # satu GPU, satu render pada satu waktu

    @torch.no_grad()
    def render(self, persona: str, wav: Path, out: Path) -> dict:
        av = self.avatars[persona]
        t0 = time.perf_counter()
        with self.lock:
            feats, n_samples = self.audio.get_audio_feature(str(wav), weight_dtype=self.dtype)
            chunks = self.audio.get_whisper_chunk(feats, self.device, self.dtype, self.whisper, n_samples, fps=FPS)
            n = len(chunks)
            t_audio = time.perf_counter()
            h, w = av.frames.shape[1:3]
            enc = subprocess.Popen(
                [ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(FPS),
                 "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-movflags", "+faststart", str(out)],
                stdin=subprocess.PIPE,
            )
            start, total = av.pos, len(av.frames)
            ts = torch.tensor([0], device=self.device)
            for b in range(0, n, self.batch_size):
                idx = [(start + i) % total for i in range(b, min(n, b + self.batch_size))]
                lat = av.latents[idx].to(self.device, self.dtype)
                aud = self.pe(chunks[b:b + len(idx)].to(self.device))
                pred = self.unet(lat, ts, encoder_hidden_states=aud).sample
                faces = self.vae.decode_latents(pred)
                for k, face in zip(idx, faces):
                    enc.stdin.write(blend(av.frames[k], face, av.boxes[k], av.masks[k], av.crops[k]).tobytes())
            enc.stdin.close()
            enc.wait()
            av.pos = (start + n) % total
        dur = n_samples / 16000
        took = time.perf_counter() - t0
        return {"frames": n, "audio_sec": round(dur, 3), "render_sec": round(took, 3),
                "features_sec": round(t_audio - t0, 3), "rtf": round(took / max(dur, 1e-6), 3)}

