#!/usr/bin/env bash
# Cadangan harian di VPS: dump Postgres + arsip data siaran (log, sesi, kuota; tanpa cache audio).
# Dipasang lewat cron (lihat deploy/README.md). Cadangan DI VPS yang sama tidak melindungi dari VPS hilang:
# salin folder ini ke tempat lain secara berkala (BACKUP_DIR).
set -euo pipefail
cd "$(dirname "$0")"

DEST="${BACKUP_DIR:-/opt/penyiar/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date +%F_%H%M)"
umask 077
mkdir -p "$DEST"
chmod 700 "$DEST"

docker compose exec -T db pg_dump -U penyiar -d penyiar --format=custom > "$DEST/db-$STAMP.dump.tmp"
mv "$DEST/db-$STAMP.dump.tmp" "$DEST/db-$STAMP.dump"

docker run --rm -v penyiar_app-data:/data:ro -v "$DEST":/out alpine \
  tar czf "/out/app-data-$STAMP.tgz" --exclude=./cache -C /data .

find "$DEST" -type f \( -name 'db-*.dump' -o -name 'app-data-*.tgz' \) -mtime +"$KEEP_DAYS" -delete
echo "Cadangan selesai: $DEST (db-$STAMP.dump, app-data-$STAMP.tgz)"
