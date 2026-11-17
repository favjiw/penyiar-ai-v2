#!/usr/bin/env bash
# Jalankan DI VPS dari /opt/penyiar:  ./deploy.sh [IMAGE_TAG]
# Menarik image, menjalankan ulang aplikasi, dan menunggu sampai sehat. Tanpa argumen memakai IMAGE_TAG dari .env.
set -euo pipefail
cd "$(dirname "$0")"

TAG="${1:-}"
if [ -n "$TAG" ]; then
  if grep -q '^IMAGE_TAG=' .env; then sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${TAG}|" .env; else echo "IMAGE_TAG=${TAG}" >> .env; fi
fi

docker compose pull app
docker compose up -d
echo "Menunggu aplikasi sehat..."
for i in $(seq 1 30); do
  status="$(docker inspect -f '{{.State.Health.Status}}' penyiar-app-1 2>/dev/null || echo starting)"
  [ "$status" = "healthy" ] && { echo "Sehat."; docker compose ps; exit 0; }
  sleep 2
done
echo "Aplikasi belum sehat; lihat log: docker compose logs --tail 80 app" >&2
exit 1
