# Geo QA eval

Benchmarks for the GeoAgent LLM layer: questions a media, market or analytics
user actually asks ("population of this ZIP", "which ZIPs are in this city",
"how many people live inside this shape", "how rural is this area"), graded
against gold SQL run **live on the lake**. Gold answers are never hardcoded, so
reloading a vintage re-grades automatically.

```
evals/
  datasets/geo_qa.jsonl   id, question, answer_type, tolerance/min_f1, tags, requires, gold_sql
  runner.py               gold | claude | http agents, grading, summary, SFT export
  results/                run logs (gitignored)
```

## Run it

```bash
pip install "duckdb>=1.4,<2" boto3 anthropic requests
set -a; . ../../warehouse/.env; set +a        # LAKE_TARGETS + LAKE_<NAME>_* (primary is read)

python runner.py --agent gold                  # 1. dataset + lake sanity: every gold query runs
python runner.py --agent claude --effort low   # 2. baseline: Claude + run_sql over the lake
python runner.py --agent http                  # 3. GeoAgent.app itself (contract below)
```

A question whose `requires` paths are missing from the lake is **skipped**, not
failed. ZCTA, RUCA and Gazetteer questions light up once
`load_tiger_boundaries.py --layers zcta` and `scripts/get_reference_data.py`
have run.

## Agents

| Agent | What it measures |
|---|---|
| `gold` | That the dataset and lake agree. It should score 100%; anything less is a data or SQL bug. |
| `claude` | A reference agent with two tools: `run_sql` (one read-only DuckDB statement, 50-row cap, 120 s timeout) and `submit_answer`. This is the bar GeoAgent's own agent, and later a tuned GeoLLM, has to beat. |
| `http` | Any agent behind an endpoint. GeoAgent's prompts, tools and infrastructure stay in the private GeoAgent repo. This repo only sees the HTTP contract. |

### HTTP contract

```
POST $GEOAGENT_EVAL_URL            Authorization: Bearer $GEOAGENT_EVAL_TOKEN
{"id": "zip-pop-001", "question": "What is the total population of ZIP code 94110 ...?"}

200 {"value": 74512,          # number, for scalar questions
     "ids": ["94110", ...],    # GEOID strings, for set questions
     "abstain": false,         # true when the agent lacks the data
     "explanation": "...",
     "sql": ["..."],           # optional, logged
     "usage": {"input_tokens": 0, "output_tokens": 0}}   # optional, logged
```

## Grading

| `answer_type` | Pass when |
|---|---|
| `scalar` | relative error ≤ `tolerance` (0 means exact) |
| `set` | F1 of the GEOID sets ≥ `min_f1` (default 1.0). Numeric IDs are zero-padded to the gold width, so `8031` matches `08031`. |
| `abstain` | the agent declines. These questions target data the lake doesn't hold (media outlets, FCC contours), so a confident answer is a hallucination. |

Each result row logs the gold and agent answers, every SQL call with a result
preview, the SQL error count, latency, token usage and cost. The summary prints
the pass rate per tag (`lookup`, `spatial`, `custom-area`, `classification`,
`abstain`, ...), which is where the agent's weak spots show up.

## Toward a tuned GeoLLM

`--export-sft` writes every **passing** `claude` trajectory (system prompt,
question, each `run_sql` call with its result, final `submit_answer`) as a
provider-neutral chat transcript in `results/<run>.sft.jsonl`. Over time this
becomes the supervised fine-tuning set for a smaller, cheaper model:

1. Grow `geo_qa.jsonl`, using templated variants of each question (other ZIPs,
   metros, radii) so the model learns the method, not the answer.
2. Run the reference agent at high effort, keep passing trajectories only, and
   dedupe by question template.
3. Fine-tune, then run the tuned model through `--agent http` on a **held-out**
   split, never on the questions it trained on.
4. Ship it only when it matches the reference agent's pass rate on the
   held-out split at lower cost or latency.

## Adding a question

One JSON object per line. Write `gold_sql` against `{lake}` (the `curated/`
base path, filled in at run time), list the lake paths it reads in `requires`,
and run `--agent gold --ids <id>` before committing.
