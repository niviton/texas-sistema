#!/usr/bin/env bash
# Prepara a máquina virtual (Ubuntu Server 24.04) para rodar o Polaris em produção.
# Roda UMA vez, dentro da VM:
#
#   sudo bash provisionar.sh https://192.168.1.59:8443
#
# O endereço é o que a equipe usa no celular (o IP deste computador, ou o nome pedido ao TI).
# Antes, copie para a pasta do usuário os dois arquivos do certificado (veja deploy/LEIA-ME.md):
#   ~/polaris.crt  e  ~/polaris.key
# Pode rodar de novo sem medo: o que já existe (banco, fotos, .env) não é apagado.
set -euo pipefail

SITE_URL="${1:?Informe o endereço do servidor, ex.: sudo bash provisionar.sh https://192.168.1.59:8443}"
SITE_URL="${SITE_URL%/}"
[ "$(id -u)" -eq 0 ] || { echo "Rode com sudo."; exit 1; }

DONO="${SUDO_USER:-polaris}"
BASE=/opt/polaris
REPO=https://github.com/niviton/texas-sistema.git
RAMO=producao
HOME_DONO="$(getent passwd "$DONO" | cut -d: -f6)"

echo "==> 1/9 Pacotes do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-dev build-essential git nginx sqlite3 rsync curl \
  libjpeg-dev zlib1g-dev unattended-upgrades ufw
timedatectl set-timezone America/Fortaleza

echo "==> 2/9 Pastas (código separado dos dados: um não apaga o outro)"
mkdir -p "$BASE"/{dados/media,logs,backups,ssl}
chown -R "$DONO":"$DONO" "$BASE"

echo "==> 3/9 Código do Polaris"
git ls-remote --exit-code --heads "$REPO" "$RAMO" >/dev/null 2>&1 || RAMO=main
if [ ! -d "$BASE/app/.git" ]; then
  sudo -u "$DONO" git clone --branch "$RAMO" "$REPO" "$BASE/app"
else
  sudo -u "$DONO" git -C "$BASE/app" fetch --tags origin
fi
cd "$BASE/app"
# banco, fotos e logs ficam em /opt/polaris/dados e /opt/polaris/logs (links dentro da pasta do código)
[ -e db.sqlite3 ] || [ -L db.sqlite3 ] || sudo -u "$DONO" ln -s "$BASE/dados/db.sqlite3" db.sqlite3
[ -e media ] || [ -L media ] || sudo -u "$DONO" ln -s "$BASE/dados/media" media
[ -e logs ] || [ -L logs ] || sudo -u "$DONO" ln -s "$BASE/logs" logs

echo "==> 4/9 Ambiente Python"
[ -d "$BASE/venv" ] || sudo -u "$DONO" python3 -m venv "$BASE/venv"
sudo -u "$DONO" "$BASE/venv/bin/pip" install --upgrade pip
sudo -u "$DONO" "$BASE/venv/bin/pip" install -r requirements.txt

echo "==> 5/9 Configuração (.env)"
if [ ! -f .env ]; then
  CHAVE="$("$BASE/venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(50))')"
  cat > .env <<EOF
DJANGO_SECRET_KEY=$CHAVE
DJANGO_DEBUG=False
SITE_URL=$SITE_URL
# endereços aceitos além do SITE_URL (a conferência de saúde usa 127.0.0.1)
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
# Nginx entrega as fotos e os arquivos estáticos
SERVIR_ARQUIVOS=0
EMAIL_SEGUNDO_PLANO=1
# Gmail dos comprovantes: preencha com o mesmo usuário e a senha de app que estão no .env do desenvolvimento
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EOF
  chown "$DONO":"$DONO" .env
  chmod 600 .env
  echo "   .env criado. Preencha EMAIL_HOST_USER e EMAIL_HOST_PASSWORD:  nano $BASE/app/.env"
else
  sed -i "s#^SITE_URL=.*#SITE_URL=$SITE_URL#" .env
  grep -q '^DJANGO_ALLOWED_HOSTS=' .env || echo 'DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost' >> .env
  echo "   .env já existia: só o endereço (SITE_URL) foi atualizado."
fi

echo "==> 6/9 Certificado HTTPS"
for f in polaris.crt polaris.key; do
  if [ -f "$HOME_DONO/$f" ]; then mv "$HOME_DONO/$f" "$BASE/ssl/$f"; fi
done
if [ ! -f "$BASE/ssl/polaris.crt" ] || [ ! -f "$BASE/ssl/polaris.key" ]; then
  echo "ERRO: faltam os arquivos do certificado. Copie polaris.crt e polaris.key para $HOME_DONO e rode de novo."
  exit 1
fi
chown "$DONO":"$DONO" "$BASE"/ssl/*; chmod 600 "$BASE/ssl/polaris.key"

echo "==> 7/9 Banco de dados e arquivos estáticos"
sudo -u "$DONO" "$BASE/venv/bin/python" manage.py migrate --noinput
sudo -u "$DONO" "$BASE/venv/bin/python" manage.py collectstatic --noinput

echo "==> 8/9 Serviço do Polaris, Nginx, agendamentos e firewall"
cp deploy/vm/polaris.service /etc/systemd/system/polaris.service
sed -i "s#__DONO__#$DONO#g" /etc/systemd/system/polaris.service
cp deploy/vm/nginx-polaris.conf /etc/nginx/sites-available/polaris
ln -sf /etc/nginx/sites-available/polaris /etc/nginx/sites-enabled/polaris
rm -f /etc/nginx/sites-enabled/default
cat > /etc/cron.d/polaris <<EOF
# Backup todo dia às 2h30 e alertas da frota todo dia às 7h
30 2 * * * $DONO $BASE/app/deploy/vm/backup.sh
0 7 * * * $DONO cd $BASE/app && $BASE/venv/bin/python manage.py veiculos_alertas >> $BASE/logs/alertas.log 2>&1
EOF
cat > /etc/sudoers.d/polaris <<EOF
$DONO ALL=(root) NOPASSWD: /usr/bin/systemctl restart polaris, /usr/bin/systemctl stop polaris, /usr/bin/systemctl start polaris, /usr/bin/systemctl reload nginx, /usr/bin/systemctl is-active polaris
EOF
chmod 440 /etc/sudoers.d/polaris
chmod +x deploy/vm/*.sh
nginx -t
systemctl daemon-reload
systemctl enable --now polaris
systemctl restart nginx
ufw allow OpenSSH >/dev/null; ufw allow 8000/tcp >/dev/null; ufw allow 8443/tcp >/dev/null
ufw --force enable >/dev/null

echo "==> 9/9 Conferindo"
sleep 4
CODIGO="$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8443/ || true)"
if [ "$CODIGO" = "200" ]; then
  echo
  echo "PRONTO. O Polaris respondeu (HTTP 200) em $SITE_URL"
else
  echo "O Polaris respondeu HTTP $CODIGO. Veja:  journalctl -u polaris -n 50 --no-pager"
  exit 1
fi
