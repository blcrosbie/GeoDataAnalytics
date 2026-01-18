Nginx Reverse Proxy (HTTPS)

This uses Nginx + Certbot to terminate HTTPS and proxy to Jupyter.

Quick start (manual)
1) Copy .env.example to .env and set DOMAIN + EMAIL.
2) Create the shared network: docker network create delab
3) Start Nginx in HTTP mode:
   - Set NGINX_TEMPLATE=http.conf.template in .env
   - docker compose up -d nginx
4) Issue a cert:
   - docker compose run --rm --entrypoint "certbot" certbot certonly \
     --webroot -w /var/www/certbot \
     -d <your-domain> -m <your-email> --agree-tos --non-interactive
5) Switch to HTTPS:
   - Set NGINX_TEMPLATE=https.conf.template in .env
   - docker compose up -d
6) Start auto-renew:
   - docker compose up -d certbot

Port conflicts
- If host Nginx is already bound to 80/443, use PROXY_HTTP_PORT/PROXY_HTTPS_PORT
  (defaults 8080/8443) and have host Nginx proxy to those ports instead.
