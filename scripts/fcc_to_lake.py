#!/usr/bin/env python3
"""
FCC broadcast stations, service contours and population coverage -> lake.

  stations   FCC FM/TV/AM Query station lists (every US record: licenses,
             permits, applications), with licensee and transmitter location
  contours   protected service contour polygon per licensed facility from the
             FCC contour API (geo.fcc.gov) -- the area where the signal is
             predicted to be receivable: FM 60 dBu (54 for class B, 57 for B1),
             digital TV noise-limited (41/36/48 dBu by band), AM 2 mV/m daytime
             primary service (--am-field; the FCC's 0.5 mV/m protected contour
             runs hundreds of km and overstates practical reach)
  coverage   contour x tract population (tract interior point inside contour,
             ACS 2024 population and urbanicity class) rolled up to station,
             county, CBSA and ZCTA

Writes (curated/media/fcc/, snapshot = run date):
  stations/snapshot=<D>/part-0.parquet
  contours/snapshot=<D>/band=<fm|tv|am>/part-0.parquet          GeoParquet, OGC:CRS84
  coverage/snapshot=<D>/level=<station|county|cbsa|zcta|tract>/part-0.parquet
Raw FCC lists and contour responses stay in local --staging and are never
uploaded; the FCC serves them for free, so only the built Parquet goes to the lake.

Contour fetch is resumable (responses are appended to a local NDJSON under
--staging and skipped on re-run). The API computes each contour live (~2-3 s),
so keep --workers modest. The API reads the legacy CDBS records, so some
facilities licensed only in LMS (mostly new, facility IDs 700000+) and AM
stations without conductivity data come back empty. FM ones get a circle at
the FCC reference distance for their class (contour_source =
'class_reference_circle'); TV/AM ones are left out of contours/coverage
(stations still lists them).

Tiers (--services):
  core     full-power FM, full-power TV, Class A TV, AM            (~17k facilities)
  all      + FM translators/boosters, LPFM, LPTV                   (~32k)

Usage:
  python fcc_to_lake.py stations
  python fcc_to_lake.py contours --services core --workers 6
  python fcc_to_lake.py coverage
  python fcc_to_lake.py all --services core
"""

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time

import duckdb
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "warehouse"))
import lake_targets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fcc")

UA = {"User-Agent": "GeoDataAnalytics-fcc/1.0"}
QUERY = "https://transition.fcc.gov/fcc-bin/{band}q?list=4&size=9"
CONTOUR_API = "https://geo.fcc.gov/api/contours/entity.json"
BANDS = ("fm", "tv", "am")

# service codes in the query lists
SERVICES = {
    "core": {"fm": {"FM"}, "tv": {"DTV", "DCA"}, "am": {"AM"}},
    "all": {"fm": {"FM", "FX", "FB", "FL"}, "tv": {"DTV", "DCA", "LPD", "LPT", "DRT", "DTS"}, "am": {"AM"}},
}
SERVICE_NAMES = {
    "FM": "FM full power", "FX": "FM translator", "FB": "FM booster", "FL": "Low power FM", "FS": "FM auxiliary",
    "FA": "FM allotment", "DTV": "TV full power", "DCA": "TV Class A", "LPD": "Low power TV (digital)",
    "LPT": "Low power TV / translator", "DRT": "TV digital replacement translator", "DTS": "TV distributed transmission",
    "AM": "AM",
}
# FCC 47 CFR 73.211 reference distance (km) to the protected contour, by FM class
FM_CLASS_KM = {"A": 28, "B1": 39, "B": 52, "C3": 39, "C2": 52, "C1": 72, "C0": 83, "C": 92, "D": 6, "L1": 5.6}

URBAN_CLASSES = ("urban", "suburban", "exurban", "rural")


# ---------------------------------------------------------------------- utils
def connect(targets):
    con = duckdb.connect()
    for ext in ("httpfs", "spatial"):
        con.install_extension(ext)
        con.load_extension(ext)
    con.execute("INSTALL h3 FROM community")
    con.execute("LOAD h3")
    lake_targets.register_duckdb(con, targets)
    return con


def num(v):
    v = (v or "").split()[0] if v and v.strip() not in ("-", "") else None
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def dms(sign, d, m, s, neg):
    try:
        x = float(d) + float(m) / 60 + float(s) / 3600
    except ValueError:
        return None
    return -x if sign == neg else x


def publish(local, key, targets, out):
    if out:
        log.info("wrote %s", local)
        return
    lake_targets.publish(local, key, targets)
    os.remove(local)
    log.info("published %s", key)


# ------------------------------------------------------------------- stations
def parse_query(path: str, band: str) -> list[dict]:
    rows = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            p = [x.strip() for x in line.rstrip("\n").split("|")[1:]]
            if len(p) < 27 or not p[17].isdigit():
                continue
            freq = num(p[1])
            rows.append({
                "band": band, "facility_id": int(p[17]), "callsign": p[0], "service": p[2],
                "service_name": SERVICE_NAMES.get(p[2], p[2]),
                "frequency": freq, "frequency_unit": (p[1].split()[1] if len(p[1].split()) > 1 else None),
                "channel": p[3] or None, "station_class": None if p[6] in ("", "-") else p[6],
                "status": p[8], "city": p[9], "state": p[10], "country": p[11], "file_number": p[12],
                "erp_kw": num(p[13]), "haat_m": num(p[15]),
                "lat_nad27": dms(p[18], p[19], p[20], p[21], "S"),
                "lon_nad27": dms(p[22], p[23], p[24], p[25], "W"),
                "licensee": None if p[26] in ("", "-") else p[26],
                "am_hours": (p[5] or None) if band == "am" else None,
            })
    return rows


def run_stations(a, targets, snapshot):
    raw = os.path.join(a.staging, "fcc", snapshot, "raw")
    os.makedirs(raw, exist_ok=True)
    rows = []
    for band in BANDS:
        path = os.path.join(raw, f"{band}q.txt")
        if not os.path.exists(path):
            r = requests.get(QUERY.format(band=band), headers=UA, timeout=600)
            r.raise_for_status()
            with open(path + ".tmp", "wb") as f:
                f.write(r.content)
            os.replace(path + ".tmp", path)
        part = parse_query(path, band)
        log.info("%s: %d records", band, len(part))
        rows += part
    rows = [r for r in rows if r["country"] == "US" and r["service"] != "FA"]  # FA = vacant allotments
    ndj = os.path.join(raw, "stations.ndjson")
    with open(ndj, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    con = connect([])
    key = f"curated/media/fcc/stations/snapshot={snapshot}/part-0.parquet"
    local = os.path.join(a.out or a.staging, key.replace("/", os.sep))
    os.makedirs(os.path.dirname(local), exist_ok=True)
    con.execute(f"""COPY (
        SELECT *, regexp_replace(upper(coalesce(licensee, '')), '[^A-Z0-9 ]', '', 'g') AS licensee_norm,
               status = 'LIC' AS licensed, DATE '{snapshot}' AS snapshot
        FROM read_json('{ndj.replace(os.sep, '/')}', format = 'newline_delimited', auto_detect = true)
        ORDER BY band, facility_id, status, file_number)
      TO '{local}' (FORMAT parquet, COMPRESSION zstd)""")
    n, nl = con.execute(f"SELECT count(*), count(DISTINCT (band, facility_id)) FILTER (WHERE licensed) FROM '{local}'").fetchone()
    log.info("stations: %d US records, %d licensed facilities", n, nl)
    publish(local, key, targets, a.out)


# ------------------------------------------------------------------- contours
def wanted_facilities(a, snapshot) -> list[tuple[str, int, str, str | None]]:
    raw = os.path.join(a.staging, "fcc", snapshot, "raw")
    out, seen = [], set()
    tier = SERVICES[a.services]
    for band in BANDS:
        for r in parse_query(os.path.join(raw, f"{band}q.txt"), band):
            if r["country"] == "US" and r["status"] == "LIC" and r["service"] in tier[band]:
                k = (band, r["facility_id"])
                if k not in seen:
                    seen.add(k)
                    out.append((band, r["facility_id"], r["service"], r["station_class"]))
    return out


def run_contours(a, targets, snapshot):
    base = os.path.join(a.staging, "fcc", snapshot)
    if not os.path.exists(os.path.join(base, "raw", "fmq.txt")):
        run_stations(a, targets, snapshot)
    want = wanted_facilities(a, snapshot)
    resp_path = os.path.join(base, "contour_responses.ndjson")
    done = set()
    if os.path.exists(resp_path):
        with open(resp_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    done.add((d["band"], d["facility_id"]))
                except (json.JSONDecodeError, KeyError):
                    pass  # a line cut by an interrupted run; refetched below
    todo = [w for w in want if (w[0], w[1]) not in done]
    if a.limit:  # testing: a few of each band
        todo = [w for b in BANDS for w in [x for x in todo if x[0] == b][:a.limit]]
    log.info("contours: %d facilities in tier '%s', %d already fetched, %d to fetch",
             len(want), a.services, len(done), len(todo))

    lock = threading.Lock()
    s = requests.Session()
    s.headers.update(UA)
    s.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=a.workers))

    def one(w):
        band, fid, service, cls = w
        for attempt in range(5):
            try:
                params = {"facilityId": fid, "serviceType": band}
                if band == "am":
                    params["field"] = a.am_field
                r = s.get(CONTOUR_API, params=params, timeout=120)
            except requests.RequestException:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            try:
                body = r.json()
            except ValueError:
                body = {"status": "error", "statusMessage": r.text[:200]}
            return {"band": band, "facility_id": fid, "service": service, "station_class": cls,
                    "http": r.status_code, "body": body}
        return {"band": band, "facility_id": fid, "service": service, "station_class": cls,
                "http": 0, "body": {"status": "error", "statusMessage": "gave up"}}

    t0, n = time.time(), 0
    with open(resp_path, "a", encoding="utf-8") as out, cf.ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(one, todo):
            with lock:
                out.write(json.dumps(res) + "\n")
                n += 1
                if n % 500 == 0:
                    out.flush()
                    rate = n / (time.time() - t0)
                    log.info("  %d/%d (%.1f/s, ~%.0f min left)", n, len(todo), rate, (len(todo) - n) / rate / 60)
    build_contours(a, targets, snapshot, resp_path)


def build_contours(a, targets, snapshot, resp_path):
    base = os.path.dirname(resp_path)
    feats_path = os.path.join(base, "contour_features.ndjson")
    st = {}
    for band in BANDS:
        for r in parse_query(os.path.join(base, "raw", f"{band}q.txt"), band):
            if r["status"] == "LIC" and r["country"] == "US":
                st.setdefault((band, r["facility_id"]), r)
    ok = miss = circles = 0

    # The responses file is >1 GB of GeoJSON: never hold it in memory. Pass 1
    # notes which line has each facility's latest response (a rerun appends);
    # pass 2 parses only those lines, one at a time.
    key_re = re.compile(r'^\{"band": "(\w+)", "facility_id": (\d+),')
    latest_line = {}
    with open(resp_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            m = key_re.match(line)
            if m and line.endswith("\n"):  # skip a line cut by an interrupted run
                latest_line[(m[1], int(m[2]))] = i

    def latest_responses():
        keep = set(latest_line.values())
        with open(resp_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i in keep:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    with open(feats_path, "w", encoding="utf-8") as out:
        for d in latest_responses():
            band, fid = d["band"], d["facility_id"]
            feats = (d["body"] or {}).get("features") or [] if d["http"] == 200 else []
            info = st.get((band, fid), {})
            for i, ft in enumerate(feats):
                p = ft.get("properties", {})
                if p.get("status") not in (None, "success"):
                    continue
                cd = p.get("contourData") or []
                out.write(json.dumps({
                    "band": band, "facility_id": fid, "feature_seq": i, "callsign": p.get("callsign"),
                    "service": p.get("service") or d["service"], "station_class": p.get("station_class") or d["station_class"],
                    "application_id": p.get("application_id"), "file_number": p.get("file_number"),
                    "field": float(p["field"]) if p.get("field") not in (None, "") else None,
                    "field_unit": "mV/m" if band == "am" else "dBu",
                    "erp_kw": p.get("erp") if band != "am" else p.get("power"),
                    "am_hours": p.get("hours_operation") if band == "am" else None,
                    "channel": p.get("channel") if band != "am" else p.get("fac_frequency"),
                    "antenna_lat": p.get("antenna_lat"), "antenna_lon": p.get("antenna_lon"),
                    "max_distance_km": max((c.get("distance") or 0) for c in cd) if cd else None,
                    "contour_source": "fcc_contour_api", "geometry": json.dumps(ft["geometry"]),
                }) + "\n")
                ok += 1
            if not feats:
                cls = info.get("station_class") or d.get("station_class")
                km = FM_CLASS_KM.get(cls) if band == "fm" else None
                if km and info.get("lat_nad27") is not None:
                    out.write(json.dumps({
                        "band": band, "facility_id": fid, "feature_seq": 0, "callsign": info.get("callsign"),
                        "service": info.get("service"), "station_class": cls, "application_id": None,
                        "file_number": info.get("file_number"), "field": None, "field_unit": "dBu",
                        "erp_kw": info.get("erp_kw"), "am_hours": None, "channel": info.get("channel"),
                        "antenna_lat": info["lat_nad27"], "antenna_lon": info["lon_nad27"],
                        "max_distance_km": km, "contour_source": "class_reference_circle", "geometry": None,
                    }) + "\n")
                    circles += 1
                else:
                    miss += 1
    log.info("contour features: %d from API, %d class-reference circles, %d facilities missing", ok, circles, miss)

    con = connect(targets)
    fp = feats_path.replace(os.sep, "/")
    con.execute(f"""
    CREATE TEMP TABLE c AS
    SELECT * EXCLUDE (geometry),
      CASE WHEN geometry IS NOT NULL THEN ST_MakeValid(ST_GeomFromGeoJSON(geometry))
           -- circle of max_distance_km on a local equirectangular projection (good to <1% at these radii)
           ELSE (SELECT ST_MakePolygon(ST_MakeLine(list(ST_Point(
                    antenna_lon + max_distance_km / (111.32 * cos(radians(antenna_lat))) * cos(radians(az % 360)),
                    antenna_lat + max_distance_km / 110.57 * sin(radians(az % 360))) ORDER BY az)))
                 FROM range(0, 361, 2) t(az)) END AS geometry
    FROM read_json('{fp}', format = 'newline_delimited', auto_detect = true,
                   columns = {{band: 'VARCHAR', facility_id: 'BIGINT', feature_seq: 'INTEGER', callsign: 'VARCHAR',
                              service: 'VARCHAR', station_class: 'VARCHAR', application_id: 'BIGINT',
                              file_number: 'VARCHAR', field: 'DOUBLE', field_unit: 'VARCHAR', erp_kw: 'DOUBLE',
                              am_hours: 'VARCHAR', channel: 'VARCHAR', antenna_lat: 'DOUBLE', antenna_lon: 'DOUBLE',
                              max_distance_km: 'DOUBLE', contour_source: 'VARCHAR', geometry: 'VARCHAR'}})""")
    for band in BANDS:
        key = f"curated/media/fcc/contours/snapshot={snapshot}/band={band}/part-0.parquet"
        local = os.path.join(a.out or a.staging, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        con.execute(f"""COPY (
            SELECT * EXCLUDE (geometry),
                   h3_latlng_to_cell_string(antenna_lat, antenna_lon, 5) AS h3_r5,
                   ST_XMin(geometry) xmin, ST_YMin(geometry) ymin, ST_XMax(geometry) xmax, ST_YMax(geometry) ymax,
                   DATE '{snapshot}' AS snapshot, ST_SetCRS(geometry, 'OGC:CRS84') AS geometry
            FROM c WHERE band = '{band}' ORDER BY h3_r5, facility_id, feature_seq)
          TO '{local}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 5000)""")
        publish(local, key, targets, a.out)


# ------------------------------------------------------------------- coverage
def run_coverage(a, targets, snapshot):
    con = connect(targets)
    src = targets[0].url("")
    cont = (os.path.join(a.out, "curated", "media", "fcc", "contours").replace(os.sep, "/") if a.out
            else f"{src}curated/media/fcc/contours")
    con.execute(f"""
    CREATE TEMP TABLE c AS
    SELECT band, facility_id, callsign, service, contour_source, geometry
    FROM read_parquet('{cont}/snapshot={snapshot}/band=*/part-0.parquet', hive_partitioning = true)""")
    con.execute(f"""
    CREATE TEMP TABLE t AS
    SELECT u.geoid, u.county, u.cbsa, u.tract20, u.population, u.class,
           ST_Point(g.INTPTLONG::DOUBLE, g.INTPTLAT) AS pt
    FROM '{src}curated/derived/urbanicity/vintage={a.vintage}/level=tract/part-0.parquet' u
    JOIN '{src}curated/reference/gazetteer/layer=tracts/year=2025/part-0.parquet' g ON g.GEOID = u.geoid""")
    log.info("coverage: %d contours x %d tract points", *con.execute(
        "SELECT (SELECT count(*) FROM c), (SELECT count(*) FROM t)").fetchone())
    t0 = time.time()
    con.execute("""
    CREATE TEMP TABLE ct AS
    SELECT DISTINCT c.band, c.facility_id, t.geoid
    FROM c JOIN t ON ST_Contains(c.geometry, t.pt)""")
    log.info("  %d station x tract pairs in %.0fs", con.execute("SELECT count(*) FROM ct").fetchone()[0], time.time() - t0)

    con.execute(f"""
    CREATE TEMP TABLE zw AS
    SELECT r.GEOID_ZCTA5_20 AS zcta, t.geoid,
           r.AREALAND_PART::DOUBLE / sum(r.AREALAND_PART) OVER (PARTITION BY r.GEOID_TRACT_20) AS w
    FROM '{src}curated/reference/rel2020/pair=zcta520_tract20/part-0.parquet' r
    JOIN t ON t.tract20 = r.GEOID_TRACT_20
    WHERE r.GEOID_ZCTA5_20 IS NOT NULL AND r.AREALAND_PART > 0""")

    pops = ", ".join(f"sum(CASE WHEN t.class = '{k}' THEN t.population ELSE 0 END) AS pop_{k}" for k in URBAN_CLASSES)
    sqls = {
        "tract": "SELECT ct.band, ct.facility_id, ct.geoid, t.population, t.class FROM ct JOIN t USING (geoid)",
        "station": f"""
            SELECT ct.band, ct.facility_id, any_value(c.callsign) callsign, any_value(c.service) service,
                   any_value(c.contour_source) contour_source,
                   sum(t.population) AS pop_covered, {pops},
                   count(*) AS tracts, count(DISTINCT t.county) AS counties
            FROM ct JOIN t USING (geoid)
            JOIN (SELECT DISTINCT ON (band, facility_id) * FROM c) c USING (band, facility_id)
            GROUP BY ALL""",
    }
    for lvl, col in (("county", "county"), ("cbsa", "cbsa")):
        sqls[lvl] = f"""
            WITH tot AS (SELECT {col} AS geoid, sum(population) pop FROM t WHERE {col} IS NOT NULL GROUP BY 1)
            SELECT ct.band, ct.facility_id, t.{col} AS geoid, sum(t.population) AS pop_covered,
                   any_value(tot.pop) AS pop_total, sum(t.population) / nullif(any_value(tot.pop), 0) AS share
            FROM ct JOIN t USING (geoid) JOIN tot ON tot.geoid = t.{col}
            GROUP BY ALL"""
    sqls["zcta"] = """
        WITH tot AS (SELECT zw.zcta, sum(t.population * zw.w) pop FROM zw JOIN t USING (geoid) GROUP BY 1)
        SELECT ct.band, ct.facility_id, zw.zcta AS geoid, round(sum(t.population * zw.w)) AS pop_covered,
               round(any_value(tot.pop)) AS pop_total, sum(t.population * zw.w) / nullif(any_value(tot.pop), 0) AS share
        FROM ct JOIN t USING (geoid) JOIN zw USING (geoid) JOIN tot ON tot.zcta = zw.zcta
        GROUP BY ALL"""
    for lvl, sql in sqls.items():
        key = f"curated/media/fcc/coverage/snapshot={snapshot}/level={lvl}/part-0.parquet"
        local = os.path.join(a.out or a.staging, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        con.execute(f"COPY ({sql} ORDER BY 1, 2, 3) TO '{local}' (FORMAT parquet, COMPRESSION zstd)")
        log.info("  %s: %d rows", lvl, con.execute(f"SELECT count(*) FROM '{local}'").fetchone()[0])
        publish(local, key, targets, a.out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["stations", "contours", "coverage", "all", "rebuild-contours"])
    ap.add_argument("--snapshot", default=dt.date.today().isoformat(), help="snapshot date (default today)")
    ap.add_argument("--services", choices=list(SERVICES), default="core")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, help="testing: fetch at most N contours per band")
    ap.add_argument("--am-field", type=float, default=2.0,
                    help="AM contour field strength, mV/m (2 = primary service; FCC's 0.5 overstates reach)")
    ap.add_argument("--vintage", type=int, default=2024, help="urbanicity/ACS vintage for coverage population")
    ap.add_argument("--staging", default=os.getenv("LAKE_STAGING") or tempfile.gettempdir())
    ap.add_argument("--out", help="write parquet under this local dir instead of publishing")
    a = ap.parse_args(argv)
    a.staging = os.path.abspath(a.staging)
    if a.out:
        a.out = os.path.abspath(a.out)
    targets = lake_targets.load_targets()

    if a.step in ("stations", "all"):
        run_stations(a, targets, a.snapshot)
    if a.step in ("contours", "all"):
        run_contours(a, targets, a.snapshot)
    if a.step == "rebuild-contours":
        build_contours(a, targets, a.snapshot,
                       os.path.join(a.staging, "fcc", a.snapshot, "contour_responses.ndjson"))
    if a.step in ("coverage", "all"):
        run_coverage(a, targets, a.snapshot)


if __name__ == "__main__":
    main()
