# Repo split plan

## Recommendation: keep it mostly whole (`edu/` has since been dropped)

This repo has three jobs:

1. Test the GeoAgent LLM component.
2. Analyze the data that's been scraped and organized.
3. Be the central database other repos, notebooks and scripts read from.

All three depend on the same schema, the same ETL and the same data. Splitting
them would turn one coordinated change into a pull request in each of three
repos and a version pin between them, with nothing gained. Moving the data to
Wasabi plus pg_duckdb already did the decoupling that matters: no consumer
needs this repo checked out, or the data on its disk, to use the data.

| Segment | Decision | Why |
|---|---|---|
| `warehouse/`, `scripts/`, `utils/`, `transfer/` | **Keep** (core) | Tightly coupled: the schema in `warehouse/init-db` is exactly what `scripts/census_ingest_pipeline.py` writes. |
| `notebooks/` (now includes the old `delab/`), `reports/` | **Keep** (analysis) | They are the "analyze the data" goal. The hosted Jupyter + nginx proxy were retired 2026-10-05; the lab is local-only. |
| `geo-llm-lab/` (was `llm/`) | **Keep, rebuild as an eval suite** (see below) | The eval's value is in its questions, gold answers and fixtures, and those are tied to this schema and data. |
| `spark-sedona-lab/` | **Keep, point it at the lake** | Tiny (5 files). Reading the same `curated/` GeoParquet from Sedona makes the "same data, different engine" point directly. |
| `edu/` | **Done: removed** | Coursework with no coupling to anything else. |

### Should `geo-llm-lab/` be its own repo?

**Not now.** Split it out when one of these becomes true:

- The eval needs to **import private GeoAgent code** (the agent, prompts, tool
  definitions). A public repo can't depend on a private one. When that happens,
  the runner moves into the private GeoAgent repo, and this repo keeps the public
  **eval dataset**: questions, gold SQL and expected answers, run against the
  warehouse.
- The eval needs its own release cadence or CI with model API keys and spend.
- Someone other than you will consume it as a package.

Until then, the cleanest boundary is this repo hosting the eval dataset and a
runner that calls the agent through a **public interface**, either an HTTP/MCP
endpoint or a CLI. The private repo then never leaks into this one, and this one
never needs the agent's internals.

Today `geo-llm-lab/` is SQL test scaffolding. Its compose files mount folders that don't
exist, and its tests query `serving.*` and `staging.*` tables that nothing
creates. Rebuild it against what exists:

```
geo-llm-lab/  (target layout)
  datasets/geo_qa.jsonl        question, gold_sql, expected (rows / tolerance), tags
  fixtures/                    small AOI snapshots for offline runs
  runner.py                    calls agent endpoint → compares to gold against the warehouse
  results/                     gitignored
```

## Order of operations

### Phase 0: done in this pass

- [x] Raw data fully in Wasabi `origin/`. Local `data/irs` and `data/natural_earth` removed after checksum verification.
- [x] `warehouse/` stood up: PG17, PostGIS, h3, pg_duckdb on `:5434`, Wasabi secret, `lake.*` views.
- [x] `geographic_boundaries` and `geographic_data` exported to `curated/` GeoParquet, verified per partition.
- [x] Schema moved from `transfer/init-db` to `warehouse/init-db`. Duplicate `transfer/upload_data.py` removed.
- [x] Private domain templated, absolute paths made relative, compose secrets moved to env, personal email scrubbed, pycache untracked.

### Phase 1: one database: done 2026-10-05

The old PG16 `geodata` DB (run from the private GeoAgent repo, public on `:5432`)
is **stopped** with its restart policy set to `no`. Its data directory is kept
until it's deleted deliberately. Its app tables were all empty.

1. Full archive: `s3://<bucket>/backups/geodata-pg16-postgis34-20261005.dump`
   (`pg_dump -Fc`, 20 GB). Read back in full and verified:
   4,952,945 boundaries and 80,162,262 data rows.
2. Imported into `warehouse` with
   `warehouse/migrations/2026-10-05-import-legacy-pg16.sh`. Every source row is
   accounted for:

   | | rows |
   |---|---|
   | `public.geographic_boundaries` | 4,952,930 (identical to source per layer/year: counts, vertices, area, geoid+name hash) |
   | `legacy.boundaries_quarantine` (empty geoid) | 15 |
   | `public.geographic_data` | 46,814,748 |
   | `legacy.data_quarantine` (empty geoid, or conflicting values) | 16,316,678 |
   | identical duplicate cells collapsed | 17,030,836 |
   | **total** | **80,162,262** |

3. `curated/` GeoParquet re-exported from the warehouse. Lake files for the 15
   fully quarantined layer/years (AREALM, ZCTA520, CD118 2022) were removed.
4. Still to do: give each consumer its own login role that inherits `geo_reader`.

### Phase 2: tidy the layout (one PR, mostly `git mv`)

```
warehouse/          (unchanged)
pipelines/          ← scripts/ + utils/        (update notebooks/jupyter mount, notebook sys.path)
analysis/           ← notebooks/ + reports/
labs/geo-llm-lab/   ← geo-llm-lab/ rebuilt as above
labs/notebooks/     ← notebooks/
labs/spark-sedona/  ← spark-sedona-lab/       (read curated/ via s3a)
```

Known path couplings to update in that PR:

- `notebooks/jupyter/docker-compose.yml` mounts `../../scripts` and `../../data`.
- `notebooks/*.ipynb` use `sys.path.append(<repo root>)` then `from utils.geometry import ...`.
- Scripts write to `<repo>/data` and `<repo>/reports` via `Path(__file__).parent.parent`.

### Phase 3: `edu/`: done

Removed from the tree. It's still in git history; the Phase 4 rewrite can purge
it, along with the graded submissions, if you want it gone from the public repo
entirely.

### Phase 4 (optional): shrink history

`.git` is about 830 MB, mostly IRS/Natural Earth CSVs and zips from earlier
commits. `git filter-repo --path data/ --invert-paths` would cut that down. It
rewrites public history, so every clone and fork has to re-clone, and open PRs
break. Do it only once, after Phase 2. Add `--path edu/` to purge the coursework too.

## Open issues found along the way

- `scripts/.env` holds Wasabi credentials that **can't read `geoagent-dev-s3`**
  (403). Its `S3_BUCKET_NAME` points to `geoagent-archive`, which doesn't exist
  for the working key. The bucket is in **us-central-1**, but script defaults
  assume us-east-1. The S3 mode of `census_ingest_pipeline.py` needs the working
  key and endpoint.
- `geographic_data` holds only TIGER attributes (`aland`, `awater`, `intpt*`,
  `source_file`, ...), all in the `other` partition. No ACS/IRS survey values
  are loaded yet.
- **Cross-layer geoid collisions (schema).** Different TIGER layers reuse the
  same id string in the same year: county `01001`, SLDU `01001` and SLDL `01001`
  all exist. Under PK `(geoid, year)` the last layer loaded overwrites the
  others. That's why SLDU has about 2k boundaries in total instead of ~1.9k per
  year, and why 259,528 attribute cells conflict (quarantined). **Fix before
  reloading:** key boundaries on `(boundary_type, geoid, year)`, or store the
  fully qualified `GEOIDFQ`, then reload the affected layers.
- **Empty-geoid collapse.** `ZCTA520` (1 row per year) and `AREALM` (1 row per
  year, ~1M attributes each) were loaded with `geoid = ''`. The boundary loader
  read only the `GEOID` column, but ZCTA files use `GEOID20` and landmark files
  use `AREAID`, so every feature upserted onto one row. **Fixed in
  `scripts/census_boundary_processor.py`** (`GEOID_FIELDS` fallback, and records
  with no ID are skipped). The bad rows are in `legacy.*`; reload those two
  layers from TIGER.
- **Duplicate EAV cells: resolved.** 17.0M identical duplicates were collapsed
  on import. `uq_geo_cell` now prevents new ones.
- `spark-sedona-lab` is titled "Interview Lab". Consider renaming it for the portfolio.
- `reports/` has no committed content. Promote finished reports (PDF/MD) into
  a tracked `analysis/reports/` folder.
