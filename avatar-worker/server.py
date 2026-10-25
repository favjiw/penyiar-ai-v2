"""Worker HTTP avatar T2 (FR-9). Jalan di mesin ber-GPU (PC lab), dipanggil backend.

    python server.py prepare raka ../assets/avatar/raka/talk_calm_1.mp4
    python server.py serve --port 8100

POST /render?persona=raka  (badan: audio mp3/wav)  →  video/mp4 tanpa audio,
dengan header X-Render-Sec, X-Audio-Sec, X-RTF.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AVATARS = HERE / "avatars"


def serve(port: int, device: str, batch_size: int) -> None:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request, Response

    from lipsync import LipSync

    engine = LipSync(AVATARS, device=device, batch_size=batch_size)
    app = FastAPI(title="avatar-worker")

    @app.get("/health")
    def health() -> dict:
        import torch

        return {"avatars": sorted(engine.avatars), "device": device,
                "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None}

    @app.post("/render")
    async def render(persona: str, request: Request) -> Response:
        if persona not in engine.avatars:
            raise HTTPException(404, f"avatar {persona} belum disiapkan")
        body = await request.body()
        with tempfile.TemporaryDirectory() as tmp:
            audio, video = Path(tmp) / "in.audio", Path(tmp) / "out.mp4"
            audio.write_bytes(body)
            import asyncio

            info = await asyncio.to_thread(engine.render, persona, audio, video)
            data = video.read_bytes()
        print(f"render {persona}: {info}", flush=True)
        return Response(data, media_type="video/mp4", headers={
            "X-Render-Sec": str(info["render_sec"]), "X-Audio-Sec": str(info["audio_sec"]), "X-RTF": str(info["rtf"])})

    uvicorn.run(app, host="0.0.0.0", port=port)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("persona")
    p.add_argument("clip", type=Path)
    p.add_argument("--max-sec", type=float, default=5.0)
    p.add_argument("--device", default="cuda")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8100)
    s.add_argument("--device", default="cuda")
    s.add_argument("--batch-size", type=int, default=4)
    args = ap.parse_args()
    if args.cmd == "prepare":
        from lipsync import prepare_avatar

        prepare_avatar(args.clip.resolve(), AVATARS / args.persona, args.max_sec, args.device)
    else:
        serve(args.port, args.device, args.batch_size)


if __name__ == "__main__":
    main()
