# Deploy ke VPS

Arsitektur: browser operator/penyiar → **Caddy** (HTTPS + login sementara, di VPS) → **app** (FastAPI + frontend hasil build, Docker) dan **db** (Postgres, Docker, belum dipakai aplikasi). OBS dan Chrome (layar OBS, prompter, mikrofon) tetap di PC studio; mereka cukup membuka alamat web.

```
PC studio: Chrome (/stage, /prompter, konsol) + OBS ──HTTPS──▶ Caddy :443 ──▶ 127.0.0.1:8000 app ──▶ db (Postgres)
```

Aplikasi menyimpan status siaran di memori **satu proses**: satu siaran sekaligus per server, dan restart saat siaran berarti siaran berhenti.

## Alur rilis
1. Push ke GitHub. Workflow `build-image` menjalankan tes (backend + frontend) lalu membangun image dan mengirimnya ke `ghcr.io/<pemilik>/penyiar-ai-v2` dengan tag `sha-<7 huruf>` (dan `latest` dari `main`, atau tag git `v*`/`kp-*`).
2. Di VPS: `cd /opt/penyiar && ./deploy.sh sha-xxxxxxx` (tanpa argumen memakai `IMAGE_TAG` di `.env`).
3. **Rollback**: jalankan `./deploy.sh` dengan tag lama.

## Pemasangan awal (sekali)
Prasyarat di VPS: Docker + Compose, Caddy, firewall hanya 22/80/443.

```bash
sudo mkdir -p /opt/penyiar && sudo chown ubuntu: /opt/penyiar && cd /opt/penyiar
# salin docker-compose.yml, deploy.sh (chmod +x), dan .env (dari env.production.example, chmod 600)
sudo cp Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy   # dari Caddyfile.example
./deploy.sh sha-xxxxxxx
```

- `.env` di VPS berisi kunci layanan; **jangan** dimasukkan ke git atau image (`.dockerignore` sudah menolaknya).
- Sandi login sementara disimpan sebagai hash bcrypt di Caddyfile (`caddy hash-password`).
- Image dari repo publik bersifat publik dan tidak memuat rahasia. Bila repo dijadikan privat, VPS perlu `docker login ghcr.io` dengan token baca paket.

## Data dan cadangan
- Volume Docker `penyiar_app-data` (materi, log siaran, sesi, kuota, cache audio) dan `penyiar_pg-data` (Postgres).
- Cadangan manual: `docker run --rm -v penyiar_app-data:/data -v "$PWD":/out alpine tar czf /out/app-data-$(date +%F).tgz -C /data .`
- Cadangan terjadwal ke luar VPS belum diatur; wajib sebelum siaran produksi.

## Uji cepat setelah deploy
```bash
curl -u operator:SANDI https://HOST/api/health
docker compose logs --tail 80 app
```

## Belum ada (diurutkan)
1. Login aplikasi (pengguna dan peran) menggantikan login sementara Caddy.
2. Pemindahan penyimpanan file ke Postgres.
3. Cadangan terjadwal, pemantauan, dan peringatan.
