# Lab stacks. Works from any directory: make -C notebooks <target>
LAB := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))

.PHONY: help postgis-up postgis-down postgis-logs postgis-env \
	jupyter-up jupyter-down jupyter-logs jupyter-env

help:
	@echo "Targets:"
	@echo "  postgis-env   Copy .env.example to .env for the lab warehouse copy"
	@echo "  postgis-up    Start the lab warehouse copy"
	@echo "  postgis-down  Stop the lab warehouse copy"
	@echo "  postgis-logs  Tail its logs"
	@echo "  jupyter-env   Copy .env.example to .env for JupyterLab"
	@echo "  jupyter-up    Start local JupyterLab (127.0.0.1)"
	@echo "  jupyter-down  Stop JupyterLab"
	@echo "  jupyter-logs  Tail JupyterLab logs"

postgis-env:
	@cp -n $(LAB)/postgis/.env.example $(LAB)/postgis/.env

postgis-up:
	@cd $(LAB)/postgis && docker compose up -d

postgis-down:
	@cd $(LAB)/postgis && docker compose down

postgis-logs:
	@cd $(LAB)/postgis && docker compose logs -f

jupyter-env:
	@cp -n $(LAB)/jupyter/.env.example $(LAB)/jupyter/.env

jupyter-up:
	@cd $(LAB)/jupyter && docker compose up -d

jupyter-down:
	@cd $(LAB)/jupyter && docker compose down

jupyter-logs:
	@cd $(LAB)/jupyter && docker compose logs -f
