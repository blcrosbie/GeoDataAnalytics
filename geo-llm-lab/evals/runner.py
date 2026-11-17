#!/usr/bin/env python3
"""
Geo QA eval: ask an agent geographic questions, grade its answers against gold
SQL run live on the lake (DuckDB over S3 GeoParquet, no server needed).

Agents
  gold    runs the gold SQL as the "answer" (checks the dataset and the lake)
  claude  baseline: Claude with two tools, run_sql (DuckDB over the lake, read-only)
          and submit_answer
  http    any agent behind an HTTP endpoint, e.g. GeoAgent.app (contract in README)

Grading by answer_type
  scalar   |agent - gold| <= tolerance * |gold|
  set      F1 of the ID sets >= min_f1 (default 1.0); IDs are zero-padded to gold width
  abstain  the agent must decline (the data isn't in the lake)

Env
  LAKE_TARGETS / LAKE_<NAME>_*   see warehouse/lake_targets.py (primary is read)
  ANTHROPIC_API_KEY (or an `ant auth login` profile)  for --agent claude
  GEOAGENT_EVAL_URL, GEOAGENT_EVAL_TOKEN               for --agent http

Usage
  python runner.py --agent gold
  python runner.py --agent claude --effort medium --tags spatial
  python runner.py --agent http --ids zip-pop-001,radius-pop-001
  python runner.py --agent claude --export-sft      # correct trajectories -> fine-tuning JSONL
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import statistics
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eval")

# $ per 1M tokens: input, output, cache read, cache write (5 min)
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
}

SQL_TIMEOUT_S = 120
MAX_ROWS = 50
MAX_TURNS = 16


# ---- lake ---------------------------------------------------------------------
class Lake:
    def __init__(self):
        self.target = lake_targets.load_targets()[0]
        self.base = self.target.url("curated")
        self.con = duckdb.connect()
        for ext in ("httpfs", "spatial"):
            self.con.install_extension(ext)
            self.con.load_extension(ext)
        lake_targets.register_duckdb(self.con, [self.target])
        self.lock = threading.Lock()

    def has(self, rel: str) -> bool:
        try:
            return self.con.execute("SELECT count(*) FROM glob(?)",
                                    [f"{self.base}/{rel.rstrip('/')}/*.parquet"]).fetchone()[0] > 0
        except duckdb.Error:
            return False

    def query(self, sql: str, limit: int | None = None) -> tuple[list[str], list[tuple]]:
        """Run one statement with a wall-clock timeout."""
        with self.lock:
            timer = threading.Timer(SQL_TIMEOUT_S, self.con.interrupt)
            timer.start()
            try:
                cur = self.con.execute(sql)
                cols = [d[0] for d in cur.description]
                rows = cur.fetchmany(limit) if limit else cur.fetchall()
                return cols, rows
            finally:
                timer.cancel()


READ_ONLY = re.compile(r"^\s*(with|select|from|describe|summarize)\b", re.I)


def safe_sql(sql: str) -> str | None:
    """Reject anything but a single read statement. Returns an error message or None."""
    body = sql.strip().rstrip(";")
    if ";" in body:
        return "one statement per call"
    if not READ_ONLY.match(body):
        return "only SELECT / WITH / FROM / DESCRIBE / SUMMARIZE statements are allowed"
    if re.search(r"\b(copy|attach|install|load|set|pragma|create|insert|update|delete|drop|export)\b\s",
                 re.sub(r"'[^']*'", "''", body), re.I):
        return "statement contains a write or configuration keyword"
    return None


def jsonable(v):
    if isinstance(v, (bytes, bytearray)):
        return f"<{len(v)} bytes>"
    if isinstance(v, (int, float, str, bool)) or v is None:
        return v
    s = str(v)
    return s if len(s) <= 200 else s[:200] + "..."


# ---- gold + grading -------------------------------------------------------------
def gold_answer(lake: Lake, q: dict):
    if q["answer_type"] == "abstain":
        return None
    _cols, rows = lake.query(q["gold_sql"].format(lake=lake.base))
    if q["answer_type"] == "scalar":
        return float(rows[0][0]) if rows and rows[0][0] is not None else None
    return sorted({str(r[0]) for r in rows if r[0] is not None})


def norm_ids(ids, width: int) -> set[str]:
    out = set()
    for i in ids or []:
        s = str(i).strip()
        out.add(s.zfill(width) if s.isdigit() else s)
    return out


def grade(q: dict, gold, ans: dict) -> tuple[bool, dict]:
    t = q["answer_type"]
    if t == "abstain":
        return bool(ans.get("abstain")), {}
    if ans.get("abstain"):
        return False, {"reason": "abstained"}
    if t == "scalar":
        v = ans.get("value")
        if v is None or gold is None:
            return False, {"reason": "no value"}
        err = abs(float(v) - gold) / (abs(gold) or 1.0)
        return err <= q.get("tolerance", 0.01) + 1e-12, {"rel_err": round(err, 6)}
    width = max((len(g) for g in gold), default=0)
    got, want = norm_ids(ans.get("ids"), width), set(gold)
    tp = len(got & want)
    p = tp / len(got) if got else 0.0
    r = tp / len(want) if want else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return f1 >= q.get("min_f1", 1.0), {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
                                        "missing": sorted(want - got)[:10], "extra": sorted(got - want)[:10]}


# ---- agents -------------------------------------------------------------------
class GoldAgent:
    name = "gold"

    def __init__(self, lake: Lake):
        self.lake = lake

    def answer(self, q: dict) -> dict:
        g = gold_answer(self.lake, q)
        if q["answer_type"] == "abstain":
            return {"abstain": True}
        return {"value": g} if q["answer_type"] == "scalar" else {"ids": g}


class HttpAgent:
    """POST {"id", "question"} -> {"value"?, "ids"?, "abstain"?, "sql"?, "usage"?}"""
    name = "http"

    def __init__(self):
        import requests
        self.requests = requests
        self.url = os.getenv("GEOAGENT_EVAL_URL") or sys.exit("set GEOAGENT_EVAL_URL")
        self.headers = {"Content-Type": "application/json"}
        if os.getenv("GEOAGENT_EVAL_TOKEN"):
            self.headers["Authorization"] = f"Bearer {os.environ['GEOAGENT_EVAL_TOKEN']}"

    def answer(self, q: dict) -> dict:
        r = self.requests.post(self.url, headers=self.headers, timeout=600,
                               json={"id": q["id"], "question": q["question"]})
        r.raise_for_status()
        return r.json()


SYSTEM = """You answer questions about United States geography and demographics by querying a data lake with DuckDB SQL.

Use the run_sql tool to explore and compute, then call submit_answer exactly once with your final answer. Base every answer on query results, not on memory. If the lake does not contain the data a question needs (for example newspapers, digital outlets, station ownership groups beyond the FCC licensee name, or anything not listed below), call submit_answer with abstain=true and say what is missing.

Lake base path: {lake}
Read files with read_parquet('<path>'). The spatial extension is loaded; geometry columns are GEOMETRY in EPSG:4326 (lon/lat degrees).

1. Boundaries: {lake}/boundaries/boundary_type=<T>/year=<Y>/part-0.parquet
   Columns: geoid, name, year, boundary_type, h3_r5, h3_r7, xmin, ymin, xmax, ymax, geometry.
   Types present: {types}
   GEOIDs: STATE 2 digits, COUNTY 5 (state+county), TRACT 11, BG 12, PLACE 7 (state+place), CBSA 5, ZCTA520 5, CD<congress> 4.
   Filter on geoid prefixes and the bbox columns (xmin/xmax/ymin/ymax) before touching geometry; national files are large.

2. ACS 5-year estimates: {lake}/acs/vintage=<Y>/table=<table id, lowercase>/part-0.parquet  (vintages 2014-2024; 2014-2019 hold only b01002 b01003 b11001 b15003 b17001 b19013 b19301 b23025 b25001 b25003 b25064 b25077 at sumlevs 010/040/050/140/150/160/310/860, and their tracts, block groups and ZCTAs are 2010-census geographies)
   Columns: GEO_ID, sumlev, component, geoid, and <TABLE>_E<line> (estimate) / <TABLE>_M<line> (margin of error), upper case, line zero-padded to 3 digits.
   Use component = '00'. sumlev: 040 state, 050 county, 140 tract, 150 block group, 160 place, 310 CBSA, 860 ZCTA.
   Useful tables: b01003 total population (B01003_E001), b11001 households (B11001_E001), b19013 median household income (B19013_E001), b01002 median age, b25077 median home value.
   Negative values below -100000000 are Census sentinels (not available), not data.

3. Reference tables (may be absent; check with glob('{lake}/reference/**/*.parquet')):
   reference/ruca/vintage=2020/level=tract  (TractFIPS20, StateFIPS20, PrimaryRUCA 1-10, SecondaryRUCA, UrbanAreaCode20, Population, LandArea, PopDensity)
   reference/ruca/vintage=2020/level=zip    (ZIPCode, State, PrimaryRUCA, SecondaryRUCA)
   reference/gazetteer/layer=<zcta|place|counties|tracts|ua|cbsa|cousubs>/year=<Y>  (GEOID, ALAND m2, AWATER m2, INTPTLAT, INTPTLONG)
   reference/rel2020/pair=zcta520_tract20 (and _county20, _place20, _cousub20): ZCTA-to-geography parts with AREALAND_PART
   reference/lodes/kind=<wac|rac|od|xwalk>/year=<Y>/state=<st>  LEHD LODES 8 jobs by census block (w_geocode/h_geocode, C000 total jobs)

4. Derived urbanicity: {lake}/derived/urbanicity/vintage=2024/level=<tract|county|cbsa|zcta|place>/part-0.parquet
   tract: geoid, class (urban|suburban|exurban|rural|NULL unpopulated), detail, ruca, population, households, hh_density
   other levels: geoid, population, pop_urban/pop_suburban/pop_exurban/pop_rural, share_urban/.../share_rural (0-1), class (plurality)

5. FCC broadcast (snapshot=<date>; use the latest): {lake}/media/fcc/...
   stations/snapshot=<D>/part-0.parquet: band (fm|tv|am), facility_id, callsign, service (FM full power, DTV, DCA class A, AM, FX translator, FL LPFM, LPD/LPT low power TV), status (LIC = licensed), city, state, licensee, frequency, erp_kw, lat_nad27, lon_nad27
   contours/snapshot=<D>/band=<b>/part-0.parquet: facility_id, callsign, service, field, field_unit, contour_source, geometry (service contour polygon)
   coverage/snapshot=<D>/level=<station|county|cbsa|zcta|tract>/part-0.parquet: band, facility_id, geoid, pop_covered, pop_total, share (share of the area's population inside the contour); level=station has pop_covered and pop_urban/suburban/exurban/rural

Spatial notes: ST_Area on 4326 geometry is in square degrees, fine for ratios only. For distances in meters, compute a haversine from ST_X/ST_Y. For "inside" tests on small units use ST_PointOnSurface(geometry).
Results from run_sql are capped at {max_rows} rows; aggregate in SQL rather than paging rows back.
For set answers, return the GEOIDs as strings. For fractions, return a number between 0 and 1."""

TOOLS = [
    {
        "name": "run_sql",
        "description": "Run one read-only DuckDB SQL statement against the lake and return up to "
                       f"{MAX_ROWS} rows as JSON. Errors come back as text so you can fix the query.",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "A single SELECT/WITH/DESCRIBE statement."}},
            "required": ["sql"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "submit_answer",
        "description": "Submit the final answer. Call once, at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": ["number", "null"], "description": "Numeric answer, or null."},
                "ids": {"type": "array", "items": {"type": "string"},
                        "description": "GEOIDs for list answers; empty otherwise."},
                "abstain": {"type": "boolean", "description": "True when the lake lacks the needed data."},
                "explanation": {"type": "string", "description": "One or two sentences: method and caveats."},
            },
            "required": ["value", "ids", "abstain", "explanation"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class ClaudeAgent:
    name = "claude"

    def __init__(self, lake: Lake, model: str, effort: str):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.lake, self.model, self.effort = lake, model, effort
        types = sorted({p.split("boundary_type=")[1].split("/")[0]
                        for p in self._glob("boundaries/*/*/*.parquet")})
        self.system = SYSTEM.format(lake=lake.base, types=", ".join(types) or "unknown", max_rows=MAX_ROWS)

    def _glob(self, rel):
        try:
            return [r[0] for r in self.lake.con.execute("SELECT file FROM glob(?)", [f"{self.lake.base}/{rel}"]).fetchall()]
        except duckdb.Error:
            return []

    def run_sql(self, sql: str) -> tuple[str, bool]:
        err = safe_sql(sql)
        if err:
            return f"Rejected: {err}", True
        try:
            cols, rows = self.lake.query(sql, MAX_ROWS + 1)
        except duckdb.InterruptException:
            return f"Query exceeded {SQL_TIMEOUT_S}s; filter on geoid prefixes or bbox columns first.", True
        except duckdb.Error as e:
            return f"{type(e).__name__}: {str(e)[:1500]}", True
        more = len(rows) > MAX_ROWS
        out = {"columns": cols, "rows": [[jsonable(v) for v in r] for r in rows[:MAX_ROWS]],
               "truncated": more}
        return json.dumps(out, default=str), False

    def answer(self, q: dict) -> dict:
        messages = [{"role": "user", "content": q["question"]}]
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                 "cache_creation_input_tokens": 0}
        steps, final = [], None
        for _turn in range(MAX_TURNS):
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=self.system,
                tools=TOOLS,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            for k in usage:
                usage[k] += getattr(resp.usage, k, 0) or 0
            if resp.stop_reason == "refusal":
                cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
                return {"abstain": False, "error": f"refusal ({cat})", "usage": usage, "steps": steps}
            messages.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                if resp.stop_reason == "pause_turn":
                    continue
                # Answered in prose without submitting: nudge once, then give up.
                if final is None and _turn < MAX_TURNS - 1 and not any(s.get("nudged") for s in steps):
                    steps.append({"nudged": True})
                    messages.append({"role": "user", "content": "Please call submit_answer with your final answer."})
                    continue
                break
            results = []
            for c in calls:
                if c.name == "submit_answer":
                    final = dict(c.input)
                    results.append({"type": "tool_result", "tool_use_id": c.id, "content": "Recorded."})
                elif c.name == "run_sql":
                    sql = c.input.get("sql", "") if isinstance(c.input, dict) else ""
                    out, is_err = self.run_sql(sql)
                    steps.append({"sql": sql, "result": out[:2000], "error": is_err})
                    results.append({"type": "tool_result", "tool_use_id": c.id, "content": out, "is_error": is_err})
                else:
                    results.append({"type": "tool_result", "tool_use_id": c.id,
                                    "content": f"Unknown tool {c.name}", "is_error": True})
            messages.append({"role": "user", "content": results})
            if final is not None:
                break
        ans = final or {"abstain": False, "error": "no submit_answer"}
        ans["usage"], ans["steps"] = usage, steps
        ans["model_served"] = self.model
        return ans

    def cost(self, usage: dict) -> float | None:
        p = PRICES.get(self.model)
        if not p:
            return None
        return round((usage["input_tokens"] * p[0] + usage["output_tokens"] * p[1]
                      + usage["cache_read_input_tokens"] * p[2]
                      + usage["cache_creation_input_tokens"] * p[3]) / 1e6, 5)


# ---- run ------------------------------------------------------------------------
def load_questions(path: Path, ids: str | None, tags: str | None, limit: int | None) -> list[dict]:
    qs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if ids:
        keep = set(ids.split(","))
        qs = [q for q in qs if q["id"] in keep]
    if tags:
        want = set(tags.split(","))
        qs = [q for q in qs if want & set(q.get("tags", []))]
    return qs[:limit] if limit else qs


def sft_record(system: str, q: dict, ans: dict) -> dict:
    """Provider-neutral chat transcript of a correct run, for later fine-tuning."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": q["question"]}]
    for i, s in enumerate(x for x in ans.get("steps", []) if "sql" in x):
        call_id = f"call_{i}"
        msgs.append({"role": "assistant", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": "run_sql", "arguments": json.dumps({"sql": s["sql"]})}}]})
        msgs.append({"role": "tool", "tool_call_id": call_id, "content": s["result"]})
    final = {k: ans.get(k) for k in ("value", "ids", "abstain", "explanation")}
    msgs.append({"role": "assistant", "tool_calls": [
        {"id": "call_final", "type": "function", "function": {"name": "submit_answer", "arguments": json.dumps(final)}}]})
    return {"id": q["id"], "tags": q.get("tags", []), "messages": msgs}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=["gold", "claude", "http"], default="gold")
    ap.add_argument("--dataset", default=str(HERE / "datasets" / "geo_qa.jsonl"))
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--ids")
    ap.add_argument("--tags")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--export-sft", action="store_true")
    a = ap.parse_args(argv)

    lake = Lake()
    log.info("lake: %s (%s)", lake.base, lake.target.name)
    agent = {"gold": lambda: GoldAgent(lake), "http": HttpAgent,
             "claude": lambda: ClaudeAgent(lake, a.model, a.effort)}[a.agent]()

    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{a.agent}-{uuid.uuid4().hex[:6]}"
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    res_path = out_dir / f"{run_id}.jsonl"
    sft = open(out_dir / f"{run_id}.sft.jsonl", "w", encoding="utf-8") if a.export_sft and a.agent == "claude" else None

    rows = []
    with open(res_path, "w", encoding="utf-8") as fh:
        for q in load_questions(Path(a.dataset), a.ids, a.tags, a.limit):
            missing = [r for r in q.get("requires", []) if not lake.has(r)]
            rec = {"run_id": run_id, "id": q["id"], "tags": q.get("tags", []), "agent": a.agent,
                   "model": a.model if a.agent == "claude" else None,
                   "effort": a.effort if a.agent == "claude" else None}
            if missing:
                rec.update(status="skipped", missing=missing)
                log.info("%-22s SKIP  missing %s", q["id"], missing)
            else:
                try:
                    gold = gold_answer(lake, q)
                    t0 = time.time()
                    ans = agent.answer(q)
                    rec["latency_s"] = round(time.time() - t0, 2)
                    ok, detail = grade(q, gold, ans)
                    rec.update(status="pass" if ok else "fail", gold=gold, detail=detail,
                               answer={k: ans.get(k) for k in ("value", "ids", "abstain", "explanation", "error")},
                               usage=ans.get("usage"), sql_calls=sum(1 for s in ans.get("steps", []) if "sql" in s),
                               sql_errors=sum(1 for s in ans.get("steps", []) if s.get("error")),
                               steps=ans.get("steps"))
                    if a.agent == "claude" and ans.get("usage"):
                        rec["cost_usd"] = agent.cost(ans["usage"])
                    if ok and sft:
                        sft.write(json.dumps(sft_record(agent.system, q, ans)) + "\n")
                    log.info("%-22s %s  %s", q["id"], rec["status"].upper(), detail or "")
                except Exception as e:  # keep the run going; record the failure
                    rec.update(status="error", error=f"{type(e).__name__}: {e}"[:500])
                    log.warning("%-22s ERROR %s", q["id"], rec["error"])
            fh.write(json.dumps(rec, default=str) + "\n")
            rows.append(rec)
    if sft:
        sft.close()
    summarize(rows, res_path)


def summarize(rows: list[dict], path: Path) -> None:
    graded = [r for r in rows if r["status"] in ("pass", "fail", "error")]
    passed = sum(r["status"] == "pass" for r in graded)
    print(f"\n{passed}/{len(graded)} passed, {sum(r['status'] == 'skipped' for r in rows)} skipped -> {path}")
    tags: dict[str, list[bool]] = {}
    for r in graded:
        for t in r["tags"]:
            tags.setdefault(t, []).append(r["status"] == "pass")
    for t, v in sorted(tags.items()):
        print(f"  {t:16} {sum(v)}/{len(v)}")
    lat = [r["latency_s"] for r in graded if "latency_s" in r]
    if lat:
        print(f"  latency p50 {statistics.median(lat):.1f}s  max {max(lat):.1f}s")
    cost = [r["cost_usd"] for r in graded if r.get("cost_usd") is not None]
    if cost:
        print(f"  cost ${sum(cost):.3f} total, ${sum(cost) / len(cost):.4f}/question")


if __name__ == "__main__":
    main()
