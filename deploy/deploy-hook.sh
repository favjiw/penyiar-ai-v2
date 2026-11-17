#!/usr/bin/env bash
# Pintu masuk deploy otomatis dari GitHub Actions. Dipanggil lewat SSH dengan kunci khusus yang di authorized_keys
# dibatasi ke skrip ini saja (command="...",restrict): kunci yang bocor hanya bisa men-deploy tag image, tidak
# bisa membuka shell. Argumen datang dari SSH_ORIGINAL_COMMAND: "sha-<7 hex> [force]".
#
# - Menolak tag yang bukan sha-xxxxxxx (tidak ada injeksi perintah).
# - Menunda bila ada siaran live/jeda (restart = siaran berhenti); "force" melewati pengecekan ini.
# - Bila versi baru tidak sehat, kembali otomatis ke versi sebelumnya.
set -euo pipefail
cd /opt/penyiar

read -r TAG FORCE _ <<< "${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$TAG" =~ ^sha-[0-9a-f]{7}$ ]]; then
  echo "Tag tidak valid: '${TAG:-}' (harus sha-xxxxxxx)" >&2
  exit 2
fi

if [ "${FORCE:-}" != "force" ]; then
  health="$(curl -fsS --max-time 5 http://127.0.0.1:8000/api/health 2>/dev/null || true)"
  if [[ "$health" == *'"live":true'* ]]; then
    echo "Ada siaran yang sedang berjalan; deploy ditunda (jalankan ulang setelah siaran selesai, atau pakai force)." >&2
    exit 3
  fi
fi

PREV="$(grep '^IMAGE_TAG=' .env | cut -d= -f2 || true)"
echo "Deploy $TAG (sebelumnya: ${PREV:-tidak ada})"
if ./deploy.sh "$TAG"; then
  echo "Deploy $TAG selesai."
  exit 0
fi

echo "Versi $TAG tidak sehat." >&2
if [ -n "$PREV" ] && [ "$PREV" != "$TAG" ]; then
  echo "Kembali ke $PREV..." >&2
  ./deploy.sh "$PREV" || echo "Rollback ke $PREV juga gagal; periksa server." >&2
fi
exit 1
