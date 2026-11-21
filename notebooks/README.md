# notebooks/ (data lab)

Scratch space for exploring new data after a fetch: notebooks, plus Docker
stacks to run them locally.

The notebooks and both stacks predate the lake and were built around the
Postgres warehouse, which was retired on 2026-11-13. To explore the lake
itself, open DuckDB in any Python session and read the Parquet straight from
S3, as in the [top-level README](../README.md#example-how-many-jobs-are-in-phoenix).

| Path | What |
|---|---|
| `*.ipynb` | H3 explorations: census and world borders mapped to hex grids (`Relate Borders to H3`, `World Borders Admin 0 to H3`) |
| `jupyter/` | Local JupyterLab (127.0.0.1 only) with `../data` and `../scripts` mounted. Its Postgres settings point at the retired warehouse. |
| `postgis/` | A throwaway local copy of the retired warehouse: the same image and schema as `../warehouse`. Its lake settings still default to the Wasabi bucket, which is gone. |
| `mcp-servers/` | Placeholder for MCP server configs |
| `scratch/` | Personal working files, **gitignored**. Promote something into the folder above when it's worth keeping. |

```bash
make -C notebooks jupyter-env   # then edit notebooks/jupyter/.env
make -C notebooks jupyter-up    # http://127.0.0.1:8888
```

Nothing here is meant to be hosted publicly. To use a lab on a remote box, run
it there and tunnel in (`ssh -L 8888:127.0.0.1:8888 <host>`).
