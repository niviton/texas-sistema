#!/usr/bin/env bash
# Backup do banco e das fotos. Roda todo dia às 2h30 (cron) e antes de cada publicação.
#   backup.sh [rotulo]      ex.: backup.sh antes-de-publicar
# Guarda em /opt/polaris/backups: os 14 últimos bancos (compactados) e uma cópia espelho das fotos.
set -euo pipefail

BASE=/opt/polaris
DEST="$BASE/backups"
ROTULO="${1:+_$1}"
CARIMBO="$(date +%F_%H%M)"
mkdir -p "$DEST/media"

if [ -f "$BASE/dados/db.sqlite3" ]; then
  # .backup é uma cópia consistente, mesmo com o sistema em uso
  sqlite3 "$BASE/dados/db.sqlite3" ".backup '$DEST/db_${CARIMBO}${ROTULO}.sqlite3'"
  gzip -f "$DEST/db_${CARIMBO}${ROTULO}.sqlite3"
fi
rsync -a "$BASE/dados/media/" "$DEST/media/"

# mantém os 14 mais recentes (os de "antes-de-publicar" ficam fora da conta de dias, mas entram no limite de 30)
ls -1t "$DEST"/db_*.sqlite3.gz 2>/dev/null | tail -n +31 | xargs -r rm -f
ls -1t "$DEST"/db_*[0-9].sqlite3.gz 2>/dev/null | tail -n +15 | xargs -r rm -f

echo "Backup feito: $(ls -1t "$DEST"/db_*.sqlite3.gz | head -1)"
