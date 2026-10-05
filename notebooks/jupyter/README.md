# JupyterLab (local)

Local JupyterLab with `../../data` and `../../scripts` mounted. It connects to the
warehouse on the host (`:5434`) through `host.docker.internal`.

```bash
cp .env.example .env      # set JUPYTER_TOKEN and warehouse credentials (a geo_reader login)
docker compose up -d
```

Open <http://127.0.0.1:8888/>. The port binds to localhost only. If you run this
on a remote box, tunnel to it instead of exposing it:
`ssh -L 8888:127.0.0.1:8888 <host>`.
