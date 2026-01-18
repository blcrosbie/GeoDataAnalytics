#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/GeoDataAnalytics}"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
JUPYTER_TOKEN="${JUPYTER_TOKEN:-}"
JUPYTER_PORT="${JUPYTER_PORT:-8888}"
OMP_NUM_THREADS="${OMP_NUM_THREADS:-16}"
OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-16}"
MKL_NUM_THREADS="${MKL_NUM_THREADS:-16}"

if [ -z "$REPO_URL" ] || [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Missing required vars: REPO_URL, DOMAIN, EMAIL" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

if [ ! -d "$INSTALL_DIR/.git" ]; then
  git clone "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" pull
fi

if ! docker network inspect delab >/dev/null 2>&1; then
  docker network create delab
fi

JUPYTER_ENV="$INSTALL_DIR/delab/jupyter/.env"
if [ ! -f "$JUPYTER_ENV" ]; then
  cp "$INSTALL_DIR/delab/jupyter/.env.example" "$JUPYTER_ENV"
fi

if [ -z "$JUPYTER_TOKEN" ]; then
  if command -v openssl >/dev/null 2>&1; then
    JUPYTER_TOKEN="$(openssl rand -hex 16)"
  else
    JUPYTER_TOKEN="changeme"
  fi
fi

sed -i \
  -e "s/^JUPYTER_TOKEN=.*/JUPYTER_TOKEN=${JUPYTER_TOKEN}/" \
  -e "s/^JUPYTER_PORT=.*/JUPYTER_PORT=${JUPYTER_PORT}/" \
  -e "s/^OMP_NUM_THREADS=.*/OMP_NUM_THREADS=${OMP_NUM_THREADS}/" \
  -e "s/^OPENBLAS_NUM_THREADS=.*/OPENBLAS_NUM_THREADS=${OPENBLAS_NUM_THREADS}/" \
  -e "s/^MKL_NUM_THREADS=.*/MKL_NUM_THREADS=${MKL_NUM_THREADS}/" \
  "$JUPYTER_ENV"

PROXY_ENV="$INSTALL_DIR/delab/proxy/.env"
if [ ! -f "$PROXY_ENV" ]; then
  cp "$INSTALL_DIR/delab/proxy/.env.example" "$PROXY_ENV"
fi

sed -i \
  -e "s/^DOMAIN=.*/DOMAIN=${DOMAIN}/" \
  -e "s/^EMAIL=.*/EMAIL=${EMAIL}/" \
  -e "s/^JUPYTER_PORT=.*/JUPYTER_PORT=${JUPYTER_PORT}/" \
  -e "s/^NGINX_TEMPLATE=.*/NGINX_TEMPLATE=http.conf.template/" \
  "$PROXY_ENV"

(cd "$INSTALL_DIR/delab/jupyter" && docker compose up -d)

(
  cd "$INSTALL_DIR/delab/proxy"
  docker compose up -d nginx
  docker compose run --rm --entrypoint "certbot" certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive
  sed -i -e "s/^NGINX_TEMPLATE=.*/NGINX_TEMPLATE=https.conf.template/" "$PROXY_ENV"
  docker compose up -d
)

echo "Done. Jupyter is available at: https://${DOMAIN}/"
