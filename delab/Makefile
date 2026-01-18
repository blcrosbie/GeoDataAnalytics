.PHONY: help postgis-up postgis-down postgis-logs postgis-env \
	jupyter-up jupyter-down jupyter-logs jupyter-env \
	proxy-up proxy-down proxy-logs proxy-env

help:
	@echo "Targets:"
	@echo "  postgis-env   Copy .env.example to .env for PostGIS"
	@echo "  postgis-up    Start PostGIS stack"
	@echo "  postgis-down  Stop PostGIS stack"
	@echo "  postgis-logs  Tail PostGIS logs"
	@echo "  jupyter-env   Copy .env.example to .env for JupyterLab"
	@echo "  jupyter-up    Start JupyterLab stack"
	@echo "  jupyter-down  Stop JupyterLab stack"
	@echo "  jupyter-logs  Tail JupyterLab logs"
	@echo "  proxy-env     Copy .env.example to .env for Nginx proxy"
	@echo "  proxy-up      Start Nginx proxy + certbot"
	@echo "  proxy-down    Stop Nginx proxy + certbot"
	@echo "  proxy-logs    Tail Nginx logs"

postgis-env:
	@cp -f delab/postgis/.env.example delab/postgis/.env

postgis-up:
	@cd delab/postgis && docker compose up -d

postgis-down:
	@cd delab/postgis && docker compose down

postgis-logs:
	@cd delab/postgis && docker compose logs -f

jupyter-env:
	@cp -f delab/jupyter/.env.example delab/jupyter/.env

jupyter-up:
	@cd delab/jupyter && docker compose up -d

jupyter-down:
	@cd delab/jupyter && docker compose down

jupyter-logs:
	@cd delab/jupyter && docker compose logs -f

proxy-env:
	@cp -f delab/proxy/.env.example delab/proxy/.env

proxy-up:
	@cd delab/proxy && docker compose up -d

proxy-down:
	@cd delab/proxy && docker compose down

proxy-logs:
	@cd delab/proxy && docker compose logs -f
