#!/bin/sh
set -eu
umask 077
cd /opt/financeiro-gd
mkdir -p backups
target="backups/financeiro-$(date +%Y%m%d-%H%M%S).dump"
docker compose exec -T db pg_dump -U financeiro -d financeiro -Fc > "$target"
test -s "$target"
echo "Backup financeiro concluído."
