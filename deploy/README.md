# Deploy ke VPS

Arsitektur: browser operator/penyiar → **Caddy** (HTTPS, di VPS) → **app** (FastAPI + frontend hasil build + login, Docker) dan **db** (Postgres, Docker: pengguna, sesi login, materi). OBS dan Chrome (layar OBS, prompter, mikrofon) tetap di PC studio; mereka cukup membuka alamat web.

```
PC studio: Chrome (/stage, /prompter, konsol) + OBS ──HTTPS──▶ Caddy :443 ──▶ 127.0.0.1:8000 app ──▶ db (Postgres)
                                                                                  └─ volume /data: log siaran, audio
```

Aplikasi menyimpan status siaran di memori **satu proses**: satu siaran sekaligus per server, dan restart saat siaran berarti siaran berhenti.

## Alur rilis
1. Push ke GitHub. Workflow `build-image` menjalankan tes (backend + frontend) lalu membangun image dan mengirimnya ke `ghcr.io/<pemilik>/penyiar-ai-v2` dengan tag `sha-<7 huruf>` (dan `latest` dari `main`, atau tag git `v*`/`kp-*`).
2. **Push/merge ke `main` otomatis deploy ke VPS** (job `deploy`): GitHub masuk lewat SSH dengan kunci khusus, VPS menjalankan `deploy-hook.sh`, yang menarik image `sha-<7 huruf>` commit itu. Branch lain hanya menguji dan membangun image.
   - **Ditunda bila ada siaran live atau jeda** (restart = siaran berhenti): job gagal dengan pesan jelas; jalankan ulang job `deploy` (Re-run) setelah siaran selesai. Pengecekan lewat `GET /api/health` (`"live":true`).
   - **Rollback otomatis** ke versi sebelumnya bila versi baru tidak sehat dalam 60 detik; job tetap ditandai gagal.
   - Berkas selain image tidak ikut: perubahan `docker-compose.yml`, `backup.sh`, `deploy-hook.sh`, dan Caddyfile disalin manual ke VPS (lihat bawah).
3. Manual di VPS: `cd /opt/penyiar && ./deploy.sh sha-xxxxxxx` (tanpa argumen memakai `IMAGE_TAG` di `.env`). **Rollback** manual: jalankan dengan tag lama.

### Pemasangan deploy otomatis (sekali; sudah dilakukan untuk VPS ini)
Kunci khusus tanpa sandi, dibatasi di VPS hanya untuk menjalankan `deploy-hook.sh` (tidak bisa membuka shell atau meneruskan port):

```bash
ssh-keygen -t ed25519 -N "" -C github-actions-deploy -f deploy_key
# di VPS: salin deploy/deploy-hook.sh ke /opt/penyiar (chmod 755), lalu tambahkan ke ~/.ssh/authorized_keys:
#   command="/opt/penyiar/deploy-hook.sh",restrict ssh-ed25519 AAAA... github-actions-deploy
gh secret set VPS_SSH_KEY < deploy_key          # lalu hapus deploy_key dan deploy_key.pub dari laptop
ssh-keyscan -t ed25519 <ip-vps> | gh secret set VPS_KNOWN_HOSTS
gh secret set VPS_HOST --body <ip-vps>;  gh secret set VPS_USER --body ubuntu
```

Hook hanya menerima argumen `sha-<7 hex>` (opsional ` force` untuk melewati pengecekan siaran). Mencabut akses: hapus baris `github-actions-deploy` dari `authorized_keys` dan secret `VPS_SSH_KEY`.

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

## Halaman admin (kunci API, suara, Simli)
Admin mengelola di `/admin` (tab Otak AI, Suara, Avatar Simli) tanpa menyentuh `.env`: kunci API Gemini/ElevenLabs/Simli/LLM cadangan, model, setelan suara, daftar suara, daftar wajah Simli dan pilihan wajah per penyiar. Tombol **Uji** memeriksa kunci yang tersimpan.

- Nilai di halaman admin **menimpa** `.env`; "Kembalikan ke bawaan server" menghapus timpaannya. `.env` tetap jadi nilai awal.
- Kunci API disimpan **terenkripsi** (Fernet) dengan `SECRETS_KEY` di `/opt/penyiar/.env`. **Simpan cadangan `SECRETS_KEY` terpisah dari cadangan database**: tanpanya kunci tersimpan tidak terbaca (aplikasi kembali ke `.env`). Buat: `docker compose exec app python -m app.cli gen-secrets-key`.
- Perubahan berlaku tanpa restart. Saat ada siaran live/jeda, perubahan **tersimpan dan menunggu** sampai siaran selesai (berlaku saat halaman admin dibuka, atau saat siaran berikutnya dimulai).
- Suara baru ElevenLabs harus sudah ada di akun (My Voices); ID diperiksa saat ditambahkan.
- Tab **Alur siaran**, **Penyiar AI**, **Supervisor**, dan **Kuota** mengatur parameter perilaku (batas waktu poin, riwayat prompt, peluang catchphrase, mode Supervisor, dst.). Aturan antar-setelan divalidasi bersama (mis. batas penutupan poin harus lebih kecil dari batas waktu poin).
- Tab **Penyiar AI** menyunting kartu persona; **Prompt & teks** menyunting prompt berversi dan potongan teks penyusun prompt; **Supervisor** mengelola kata terlarang dan kalimat aman. Perubahan dipakai giliran/siaran berikutnya.

## Data dan cadangan
- **Postgres** (volume `penyiar_pg-data`) menyimpan SEMUA data aplikasi: pengguna, sesi login, materi, setelan admin, daftar suara dan wajah, persona, prompt berversi, kata terlarang dan kalimat aman Supervisor, kuota harian, serta log siaran dan log giliran riset. Data awal (persona, prompt, dll.) dibaca dari `backend/seed/` sekali saat pertama jalan.
- **Volume `penyiar_app-data`** hanya cache audio (boleh hilang). Berkas lama (`logs/`, `sessions/`, `data/`) dari sebelum v2.15 diimpor sekali: `docker compose exec app python -m app.cli import-files --data-dir /data/data --log-dir /data/logs --sessions-dir /data/sessions` (aman diulang).
- **Log untuk riset**: `docker compose exec app python -m app.cli export-session <id> --out /data/export` menulis `<id>.jsonl`, `turns.jsonl`, `blocker.json` (dibaca `scripts/report.py` dan `scripts/evaluate_pilot.py`).
- **Prompt**: `python -m app.cli prompts list | add <nama> <versi> --file <berkas> | activate <nama> <versi>`. Versi lama tetap tersimpan.
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
