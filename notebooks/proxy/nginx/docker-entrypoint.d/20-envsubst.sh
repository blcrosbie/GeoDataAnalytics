#!/bin/sh
set -eu

template="/etc/nginx/templates/${NGINX_TEMPLATE}"
output="/etc/nginx/conf.d/default.conf"

if [ ! -f "$template" ]; then
  echo "Missing nginx template: $template" >&2
  exit 1
fi

envsubst '${DOMAIN} ${JUPYTER_UPSTREAM} ${JUPYTER_PORT}' < "$template" > "$output"
