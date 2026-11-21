# geo-llm-lab

Testing how well LLM agents answer geographic questions.

## Start here: [`evals/`](evals/)

The live part of this folder is the agent benchmark in `evals/`. It holds 18
plain-English geographic questions, such as "What is the population of ZIP
94110?", "Which ZIPs are in San Francisco?" and "Which FM stations cover ZIP
80202?". Each answer is graded against gold SQL that runs on the curated lake
at grading time, so the expected answers are never hardcoded.

Three agents can be scored:

| Agent | What it is |
|---|---|
| `gold` | Runs the gold SQL itself, as a check that the dataset and the lake agree. It passes 18/18. |
| `claude` | A reference agent: Claude with a read-only DuckDB tool. |
| `http` | GeoAgent's production agent, called through a public HTTP contract. |

[`evals/README.md`](evals/README.md) covers how to run it, the grading
rules, the HTTP contract and the fine-tuning export.

## Earlier scaffolding (not runnable)

Everything else in this folder is an earlier, PostGIS-based test suite. It
was written before the lake existed, for a set of databases that were never
built. The SQL tests query `serving.*` and `staging.*` tables (flood zones,
precipitation, heat, air quality, ACS demographics, vector tiles) that
nothing creates. The compose files also mount folders that don't exist. It's
kept as a record of the test categories that were planned. Nothing here
depends on it.

| Path | What it was for |
|---|---|
| `test_framework_schema.sql`, `test_data_fixtures.sql` | The test schema, helper functions and sample data |
| `test_flood_exposure.sql` | Flood-zone tests |
| `test_weather_extreme_rain.sql` | Extreme-rain tests |
| `test_heat_sun_wind.sql` | Heat, sun and wind tests |
| `test_air_quality_ghg.sql` | Air quality and greenhouse gas tests |
| `test_neighborhood_trends.sql` | ACS and IRS demographic trend tests |
| `test_geographic_validation.sql` | GEOID, CRS and geometry checks |
| `test_vectorization_mvt_performance.sql` | Vector tile tests |
| `test_runner.py` | Runs the SQL suites against a Postgres DSN and writes HTML or JSON reports |
| `docker/`, `docker-compose*.yml` | Postgres + PostGIS and Redis stacks for the suite |
| `python/`, `scripts/setup.sh` | The suite's Python requirements, database config and environment setup |
| `setup_tasks.md`, `.env.example` | The original setup checklist and its settings template |

Some of these categories may come back as eval questions, once the matching
data is in the lake.
