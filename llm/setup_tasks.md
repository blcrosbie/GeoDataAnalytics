# GeoAgent LLM (Text-to-SQL) Setup Tasks

This document defines a **simple, opensource, local-first** workflow for standing up a Text-to-SQL
service (Postgres + PostGIS) using **Ollama, vLLM, or TGI**, and iteratively improving it
via evaluation and optional fine-tuning.

The goal is to avoid per-request API costs, ship something usable quickly, and
improve quality over time with real data.

---

## Repository Structure

Create a dedicated subdirectory in your GeoAgent repo:

```
/llm/
  README_TASKS.md
  .env.example
  docker/
    docker-compose.vllm.yml
    docker-compose.tgi.yml
    docker-compose.ollama.yml
  models/
    ollama/
      Modelfile
      NOTES.md
    hf/
  prompts/
    system_postgis.md
    fewshot/
  schema/
    ddl/
    introspection/
  datasets/
    raw/
    curated/
    splits/
    format.md
  eval/
    cases/
    harness.py
    reports/
  server/
    geoagent_sql_proxy.py
    sql_guard.py
  notebooks/
    postgis_text2sql_data_prep.ipynb
  scripts/
    export_schema.sh
    run_vllm.sh
    run_tgi.sh
    run_ollama.sh
    build_dataset.py
    run_eval.py
  logs/
    model_requests.jsonl
    model_failures.jsonl
```

---

## Phase 0 — Decide Serving Path

Start with **one** serving backend.

- **Ollama** — fastest setup, best dev loop
- **vLLM** — OpenAI-compatible API, higher throughput
- **TGI** — Docker-first, production-style serving

**Recommendation:** start with Ollama, migrate to vLLM once prompts and eval stabilize.

---

## Phase 1 — Model Selection

Criteria:
- Decent SQL generation
- Fits on RTX 3070 (8 GB VRAM)
- Commercially usable license

Start with an existing SQL-capable model; do not train from scratch.

Keep a `models/ollama/NOTES.md` file documenting:
- model name
- source URL
- license
- known limitations

---

## Phase 2 — Ollama Setup

1. Install Ollama
2. Create a custom model using a Modelfile

Example `models/ollama/Modelfile`:

```
FROM <base-model>

SYSTEM """
You are a Postgres + PostGIS SQL generator.
Rules:
- Output SQL only
- SELECT queries only
- Always include LIMIT
- Use PostGIS functions only from an allowlist
- Never modify data
"""
```

Create and run:
```
ollama create geoagent-sql -f Modelfile
ollama run geoagent-sql
```

---

## Phase 3 — vLLM Setup

Use vLLM when you want an OpenAI-compatible API.

Example:
```
vllm serve <hf-model-id> --dtype auto --api-key local-token
```

GeoAgent points to:
- base_url: http://localhost:8000/v1
- api_key: local-token

---

## Phase 4 — Dataset Format

Define a single JSONL format and stick to it.

Example record:
```
{
  "id": "case_001",
  "question": "Which hexes intersect FEMA flood zones?",
  "schema_context": "CREATE TABLE ...",
  "constraints": {
    "read_only": true,
    "limit_required": true,
    "allowed_postgis": ["ST_Intersects","ST_DWithin"]
  },
  "sql_gold": "SELECT ... LIMIT 200;"
}
```

Start with ~200 hand-validated examples.

---

## Phase 5 — Guardrails (Mandatory)

Implement SQL validation before execution:

- SELECT-only
- single statement
- LIMIT enforced
- table/column allowlist
- restricted PostGIS function list

Files:
- `server/sql_guard.py`
- `server/geoagent_sql_proxy.py`

The proxy:
1. Receives question
2. Calls model
3. Validates SQL
4. Executes with read-only DB role
5. Returns rows or error

---

## Phase 6 — Evaluation Harness

Build an evaluation harness that measures:
- SQL validity
- Execution success
- Safety compliance
- Latency

Store reports under `eval/reports/`.

Run this in CI once stable.

---

## Phase 7 — Fine-Tuning (Optional)

Only fine-tune after collecting ≥1,000 curated examples.

Use LoRA / QLoRA:
- small GPU footprint
- teaches schema + PostGIS patterns
- avoids full retraining

Never fine-tune on unreviewed data.

---

## Phase 8 — GeoAgent Integration

Add a config-driven router:
```
LLM_PROVIDER=ollama|vllm|tgi|openai
```

Log every request and final SQL:
- `logs/model_requests.jsonl`
- `logs/model_failures.jsonl`

These logs become future training data.

---

## Definition of Done

- Local inference, no per-request API cost
- Valid Postgres + PostGIS SQL for top intents
- Guardrails prevent unsafe queries
- Eval harness shows measurable improvement
- Clear upgrade path to fine-tuning
