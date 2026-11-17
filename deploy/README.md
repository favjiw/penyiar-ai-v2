# Deploy ke VPS

Arsitektur: browser operator/penyiar → **Caddy** (HTTPS, di VPS) → **app** (FastAPI + frontend hasil build + login, Docker) dan **db** (Postgres, Docker: pengguna, sesi login, materi). OBS dan Chrome (layar OBS, prompter, mikrofon) tetap di PC studio; mereka cukup membuka alamat web.

```
PC studio: Chrome (/stage, /prompter, konsol) + OBS ──HTTPS──▶ Caddy :443 ──▶ 127.0.0.1:8000 app ──▶ db (Postgres)
                                                                                  └─ volume /data: log siaran, audio
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
- Image dari repo publik bersifat publik dan tidak memuat rahasia. Bila repo dijadikan privat, VPS perlu `docker login ghcr.io` dengan token baca paket.

## Login dan pengguna
Login dikelola aplikasi (cookie sesi HttpOnly; kata sandi di-hash scrypt; salah 5 kali = diblokir 15 menit). Tiga peran:

| Peran | Boleh |
|---|---|
| `penyiar` | prompter, mengucapkan giliran, tombol Topik selanjutnya; melihat status siaran |
| `operator` | + konsol, materi, mulai/jeda/akhiri siaran, layar OBS (`/stage`), suara, cek kesiapan, log |
| `admin` | + kelola pengguna (`/pengguna`) |

`docker-compose.yml` memaksa `AUTH_REQUIRED=true` dan Postgres; tanpa akun tidak ada yang bisa masuk. Akun pertama dibuat dari VPS (kata sandi tidak pernah lewat argumen perintah):

```bash
cd /opt/penyiar
docker compose exec app python -m app.cli create-user admin --role admin --display-name "Nama Admin"   # menanyakan kata sandi
docker compose exec -T app python -m app.cli create-user rani --role penyiar --password-stdin <<< "kata-sandi-min-10-karakter"
docker compose exec app python -m app.cli list-users
docker compose exec app python -m app.cli set-password rani     # lupa sandi; semua sesi login orang itu dicabut
```

Selanjutnya admin menambah, menonaktifkan, dan mengganti peran lewat halaman `/pengguna`. Pindah dari file: `python -m app.cli import-files` menyalin materi lama (DATA_DIR/blockers) ke database dan aman diulang.

## Data dan cadangan
- **Postgres** (volume `penyiar_pg-data`): pengguna, sesi login, materi, catatan pembuatan materi.
- **Volume `penyiar_app-data`**: log siaran (`logs/*.jsonl`), log giliran riset (`sessions/<id>/turns.jsonl`), kuota harian, cache audio. Ini file tambah-saja untuk riset; sengaja tidak di database.
- **Cadangan harian**: `backup.sh` membuat `db-<waktu>.dump` (pg_dump) dan `app-data-<waktu>.tgz` (tanpa cache audio) di `/opt/penyiar/backups`, menyimpan 14 hari. Pasang sekali:

  ```bash
  sudo tee /etc/cron.d/penyiar-backup >/dev/null <<'CRON'
  30 3 * * * ubuntu /opt/penyiar/backup.sh >> /opt/penyiar/backups/backup.log 2>&1
  CRON
  ```

- Pulihkan database: `docker compose exec -T db pg_restore -U penyiar -d penyiar --clean --if-exists < backups/db-<waktu>.dump`.
- Cadangan di VPS yang sama tidak melindungi bila VPS hilang: salin `/opt/penyiar/backups` ke tempat lain secara berkala (belum diotomatiskan).
- Skema dibuat otomatis saat aplikasi mulai; perubahan skema berikutnya perlu migrasi (Alembic) sebelum ada data yang tidak boleh hilang.

## Uji cepat setelah deploy
```bash
curl https://HOST/api/health                    # {"status":"ok"} tanpa login
docker compose logs --tail 80 app               # baris "Siap: ... database=postgresql login=wajib"
```

## Belum ada (diurutkan)
1. Salinan cadangan otomatis ke luar VPS, pemantauan, dan peringatan.
2. Migrasi skema (Alembic) dan pencatatan siapa memulai siaran di log.
3. Log siaran di database (sekarang file di volume).
