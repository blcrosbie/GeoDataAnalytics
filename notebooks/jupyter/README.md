JupyterLab (Hetzner)

1) Copy .env.example to .env and set a strong JUPYTER_TOKEN.
2) Run: docker compose up -d
3) Open http://<server-ip>:${JUPYTER_PORT}${JUPYTER_BASE_URL}
