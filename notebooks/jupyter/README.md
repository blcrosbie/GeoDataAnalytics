# JupyterLab (local)

Local JupyterLab with `../../data` and `../../scripts` mounted.

The `POSTGRES_*` settings point at the warehouse that used to run on the host
at `:5434` (reached through `host.docker.internal`). That warehouse was
retired on 2026-11-13, so those settings do nothing now. To read the lake from
a notebook, `pip install duckdb` in the container and query the Parquet on S3
directly.

```bash
cp .env.example .env      # set JUPYTER_TOKEN
docker compose up -d
```

Open <http://127.0.0.1:8888/>. The port binds to localhost only. If you run this
on a remote box, tunnel to it instead of exposing it:
`ssh -L 8888:127.0.0.1:8888 <host>`.
