Data Engineering Lab

This folder contains reproducible local and server-side data engineering setups
based on Docker Compose. Use the .env.example files as templates and keep real
secrets in .env files (which are gitignored).

Layout
- postgis: Local PostGIS stack similar to root docker-compose.yml
- jupyter: JupyterLab stack sized for a Hetzner server
- mcp-servers: Place MCP server configs and env templates here
- proxy: Nginx + Certbot HTTPS reverse proxy

Quick start (local)
1) Copy env files:
   - make postgis-env
   - make jupyter-env
2) Start stacks:
   - make postgis-up
   - make jupyter-up

Windows note
- Use `Makefile.windows` on Windows: `make -f delab/Makefile.windows postgis-up`

Server quick start
1) Set DNS for your domain to point at the server IP.
2) Run:
   - REPO_URL=<your-repo-url> DOMAIN=<your-domain> EMAIL=<your-email> bash delab/bootstrap.sh
