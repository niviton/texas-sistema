#!/usr/bin/env bash
# Coloca uma versão no ar (ou volta para uma anterior). Roda dentro da VM, chamado pelo publicar.ps1:
#   publicar.sh v1.4                 publica a versão marcada v1.4 (ou a branch com esse nome)
#   publicar.sh v1.3 --restaurar     volta para v1.3 E devolve o banco ao estado de antes da última publicação
#                                    (cuidado: registros feitos depois dessa publicação são perdidos)
# Se a versão nova não subir, volta sozinho para a anterior.
set -euo pipefail

BASE=/opt/polaris
APP="$BASE/app"
PY="$BASE/venv/bin/python"
ALVO="${1:?Informe a versão, ex.: publicar.sh v1.4}"
RESTAURAR="${2:-}"
cd "$APP"

saudavel() {
  for _ in $(seq 1 20); do
    [ "$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/ || true)" = "200" ] && return 0
    sleep 2
  done
  return 1
}

ANTES="$(git rev-parse HEAD)"
echo "==> Versão atual: $(git describe --tags --always)"

"$APP/deploy/vm/backup.sh" antes-de-publicar

echo "==> Baixando $ALVO"
git fetch --tags --prune origin
if git rev-parse -q --verify "refs/tags/$ALVO" >/dev/null; then REF="refs/tags/$ALVO"; else REF="origin/$ALVO"; fi
git checkout -q --detach "$REF"

echo "==> Instalando dependências, atualizando o banco e os arquivos"
"$BASE/venv/bin/pip" install -q -r requirements.txt
if [ "$RESTAURAR" = "--restaurar" ]; then
  ULTIMO="$(ls -1t "$BASE"/backups/db_*antes-de-publicar.sqlite3.gz | sed -n 2p || true)"
  if [ -n "$ULTIMO" ]; then
    echo "==> Restaurando o banco de $ULTIMO"
    sudo systemctl stop polaris
    gunzip -c "$ULTIMO" > "$BASE/dados/db.sqlite3"
  else
    echo "Nenhum backup anterior para restaurar; seguindo só com o código."
  fi
fi
"$PY" manage.py migrate --noinput
"$PY" manage.py collectstatic --noinput >/dev/null
sudo systemctl restart polaris

echo "==> Conferindo se o Polaris subiu"
if saudavel; then
  echo "PRONTO. No ar: $(git describe --tags --always)"
  exit 0
fi

echo "FALHOU. Voltando para a versão anterior..."
git checkout -q --detach "$ANTES"
"$BASE/venv/bin/pip" install -q -r requirements.txt
sudo systemctl stop polaris
ULTIMO="$(ls -1t "$BASE"/backups/db_*antes-de-publicar.sqlite3.gz | head -1)"
gunzip -c "$ULTIMO" > "$BASE/dados/db.sqlite3"
"$PY" manage.py collectstatic --noinput >/dev/null
sudo systemctl start polaris
if saudavel; then echo "Voltou para $(git describe --tags --always). A versão nova NÃO foi publicada."; else echo "ATENÇÃO: não subiu nem a versão anterior. Veja: journalctl -u polaris -n 80 --no-pager"; fi
exit 1
