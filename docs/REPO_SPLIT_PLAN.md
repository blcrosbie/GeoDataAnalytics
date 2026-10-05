# Repo split plan

## Recommendation: keep it mostly whole, move out `edu/`

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
| `notebooks/`, `reports/` | **Keep** (analysis) | They are the "analyze the data" goal. |
| `llm/` | **Keep, rebuild as an eval suite** (see below) | The eval's value is in its questions, gold answers and fixtures, and those are tied to this schema and data. |
| `delab/` | **Keep** | It's the lab infrastructure for this data; small. |
| `spark-sedona-lab/` | **Keep, point it at the lake** | Tiny (5 files). Reading the same `curated/` GeoParquet from Sedona makes the "same data, different engine" point directly. |
| `edu/` | **Move out** to `blcrosbie/geog489-coursework` | 230 files and 80 MB of coursework with no coupling to anything else. It dilutes the repo's message and holds graded submissions. |

### Should `llm/` be its own repo?

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

Today `llm/` is SQL test scaffolding. Its compose files mount folders that don't
exist, and its tests query `serving.*` and `staging.*` tables that nothing
creates. Rebuild it against what exists:

```
llm/   →  eval/
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

### Phase 1: separate public geodata from the app DB

Today the `geodata` DB runs from the private GeoAgent repo. It mixes public
reference tables with app tables (`profiles`, `credits_ledger`, `usage_events`,
`uploads`, `layers`, ...). `geographic_*` also has FKs into `layers` and
`uploads`.

1. Load the hot set into `warehouse` natively from `curated/`: all
   STATE/COUNTY/CBSA/CD, plus the latest year of TRACT/BG/PLACE.
2. Point GeoAgent at the warehouse as `geo_reader` for reference data. Keep app
   tables in the app DB.
3. Drop the `layer_id`/`source_upload_id` FKs from the app copy of
   `geographic_*`, then drop those tables from the app DB.
4. Give each consumer its own login role that inherits `geo_reader`.

### Phase 2: tidy the layout (one PR, mostly `git mv`)

```
warehouse/          (unchanged)
pipelines/          ← scripts/ + utils/        (update delab/jupyter mount, notebook sys.path)
analysis/           ← notebooks/ + reports/
eval/               ← llm/ rebuilt as above
labs/delab/         ← delab/
labs/spark-sedona/  ← spark-sedona-lab/       (read curated/ via s3a)
```

Known path couplings to update in that PR:

- `delab/jupyter/docker-compose.yml` mounts `../../scripts` and `../../data`.
- `notebooks/*.ipynb` use `sys.path.append(<repo root>)` then `from utils.geometry import ...`.
- Scripts write to `<repo>/data` and `<repo>/reports` via `Path(__file__).parent.parent`.

### Phase 3: move out `edu/`

```bash
git clone --no-local GeoDataAnalytics geog489-coursework
cd geog489-coursework && git filter-repo --path edu/ --path-rename edu/:
# push to new repo, then in GeoDataAnalytics: git rm -r edu && add a link in README
```

Decide first whether the graded submissions (`L3_submission_*.zip`,
`assignment_4_*.zip`) should be published at all.

### Phase 4 (optional): shrink history

`.git` is about 830 MB, mostly IRS/Natural Earth CSVs and zips from earlier
commits. `git filter-repo --path data/ --invert-paths` would cut that down. It
rewrites public history, so every clone and fork has to re-clone, and open PRs
break. Do it only once, after Phases 2–3.

## Open issues found along the way

- `scripts/.env` holds Wasabi credentials that **can't read `geoagent-dev-s3`**
  (403). Its `S3_BUCKET_NAME` points to `geoagent-archive`, which doesn't exist
  for the working key. The bucket is in **us-central-1**, but script defaults
  assume us-east-1. The S3 mode of `census_ingest_pipeline.py` needs the working
  key and endpoint.
- The live DB is still the **pre-partitioning** schema.
  `warehouse/migrations/2026-06-06-eav-partitioning.sql` hasn't been applied
  there. `geographic_data` currently holds only TIGER attributes (`aland`,
  `awater`, `intpt*`, `source_file`); no ACS/IRS survey values are loaded yet.
- **Empty-geoid collapse.** `ZCTA520` (1 row per year) and `AREALM` (1 row per
  year, ~1M attributes each) were loaded with `geoid = ''`. The boundary loader
  read only the `GEOID` column, but ZCTA files use `GEOID20` and landmark files
  use `AREAID`, so every feature upserted onto one row. **Fixed in
  `scripts/census_boundary_processor.py`** (`GEOID_FIELDS` fallback, and records
  with no ID are skipped). The existing rows still need a reload of those two
  layers.
- **Duplicate EAV cells.** About 39% of `geographic_data` rows for 2024 (2.4M of
  6.2M) repeat a `(geoid, year, attribute_key)`. The live table has no unique
  constraint; the partitioning migration adds `uq_geo_cell`. The lake mirrors the
  source as-is, so dedupe when applying the migration, then re-export
  `attributes --force`.
- `spark-sedona-lab` is titled "Interview Lab". Consider renaming it for the portfolio.
- `reports/` has no committed content. Promote finished reports (PDF/MD) into
  a tracked `analysis/reports/` folder.
