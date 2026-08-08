#!/usr/bin/env bash
# Rebuild + restart the SoloLedger API container from the current checkout.
# Run on the VPS:  bash /opt/sololedger/deploy/rebuild.sh
#
# Why not `--force-recreate`? It races with stale named containers and can
# leave a window with NO api container (the site stops loading). Plain
# `up -d` recreates automatically only when the image changed, and
# `--remove-orphans` drops stale containers instead of colliding with them.
set -euo pipefail

cd "$(dirname "$0")"          # deploy/ — where the prod docker-compose.yml lives

echo "── pull ──"
git -C .. pull --ff-only

echo "── build ──"
docker compose build sololedger-api

echo "── up (recreate only on image change; drop orphans) ──"
docker compose up -d --no-deps --remove-orphans sololedger-api

echo "── wait for healthy ──"
for i in $(seq 1 30); do
    status=$(docker inspect -f '{{.State.Health.Status}}' sololedger-api 2>/dev/null || echo starting)
    echo "  [$i] $status"
    [ "$status" = "healthy" ] && break
    sleep 2
done

docker ps --filter name=sololedger-api --format '{{.Names}} {{.Status}}'
echo "── logs ──"
docker logs sololedger-api --tail 5 2>&1
