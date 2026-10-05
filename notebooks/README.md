# notebooks/ (data lab)

Scratch space for exploring new data after a fetch: notebooks, plus the Docker
stacks to run them locally against the warehouse.

| Path | What |
|---|---|
| `*.ipynb` | H3 explorations: census and world borders mapped to hex grids (`Relate Borders to H3`, `World Borders Admin 0 to H3`) |
| `jupyter/` | Local JupyterLab (127.0.0.1 only) with `../data` and `../scripts` mounted |
| `postgis/` | A lab copy of the central warehouse (same image + schema as `../warehouse`) for throwaway experiments |
| `mcp-servers/` | Placeholder for MCP server configs |
| `scratch/` | Personal working files, **gitignored**. Promote something into the folder above when it's worth keeping. |

```bash
make -C notebooks jupyter-env   # then edit notebooks/jupyter/.env
make -C notebooks jupyter-up    # http://127.0.0.1:8888
```

Nothing here is meant to be hosted publicly. To use a lab on a remote box, run
it there and tunnel in (`ssh -L 8888:127.0.0.1:8888 <host>`).
