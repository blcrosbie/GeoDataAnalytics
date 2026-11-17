# A nationwide geographic intelligence layer

How this repo is set up to serve a product that lets users search any ZIP,
city, county or metro, draw an area on a map and get back the ZIPs, counties,
population and demographics inside it, classify places as urban or rural, and
map businesses (media outlets, stores, sites) and the areas they serve. It
also covers how an LLM answers questions like "what independent newspapers
cover urban San Francisco?" against that layer.

## 1. Storage: S3 is the database

The recurring question is PostGIS, Aurora, or "just S3 + DuckDB". This repo
runs **S3 + DuckDB only**: no database server, so no idle compute bill. A
PostGIS serving tier is an add-on with a clear trigger, not the default.

| Tier | Holds | Serves | Here |
|---|---|---|---|
| **Lake**: GeoParquet on S3 | Every vintage of every layer, ACS (all tables, all geographies), reference tables, crosswalks. The system of record. | Batch builds, analytics, the LLM agent's SQL, tile builds, drawn-shape queries via the H3/bbox prefilter | `s3://…/curated/` on AWS (primary), byte-identical archive on Wasabi (`warehouse/lake_targets.py`). Built by `scripts/tiger_to_lake.py`, `scripts/get_reference_data.py` and the ACS loader. |
| **Compute**: DuckDB (spatial + h3 + httpfs) | Nothing. It's stateless and reads the lake in place. | Any query, embedded in the process that needs it: notebook, script, Lambda/container behind the app, the eval runner | `geo-llm-lab/evals/runner.py` is a working example |
| **Tiles**: PMTiles on S3/CloudFront | Simplified display geometry per zoom | MapLibre or deck.gl rendering. No query engine is touched to draw the map. | Built by tippecanoe from the lake (the GeoAgent `geoagent-boundaries` image) |

### What makes S3-only fast enough

DuckDB can't push a spatial predicate into S3, and there's no persistent
spatial index. The layout does that work instead:

- **Partition pruning by path.** `boundary_type=ZCTA520/year=2025` touches one
  object, not the lake, and only the column chunks and row groups a query needs
  are range-read from it.
- **Scalar spatial keys.** Every boundary row has `h3_r5`, `h3_r7` and its bbox,
  sorted by `h3_r5`, so row-group statistics skip most of a file before any
  geometry is decoded. Filter on them first, then run `ST_Intersects` on the
  survivors.
- **Precomputed weights.** Drawn-shape population comes from an H3 table
  (section 3), which is a cell lookup instead of a polygon overlay.
- **Warm process.** A long-lived DuckDB process (container or provisioned
  Lambda) caches metadata and hot objects. The gold eval answers 14 questions
  straight from S3 at p50 0.4 s and max 2.1 s from a laptop.

### When to add PostGIS back (and why not Aurora)

Add a serving database (RDS PostgreSQL + PostGIS, loaded from the lake) when
one of these becomes true:

- interactive spatial queries need to be under about 100 ms at concurrency;
- the app writes its own geospatial entities (outlets, coverage areas, customer
  territories) transactionally and needs constraints on them;
- many clients need one SQL endpoint rather than embedding DuckDB.

Even then, the geography serving set (the current vintage of every layer, full
resolution) is roughly 10–20 GB, and plain RDS handles that at a fraction of
Aurora's cost. Aurora's advantages (storage that scales on its own, fast
replicas, failover across availability zones) pay off for large,
write-heavy, high-availability databases. The geography layer won't be the
reason to buy it. The lake stays the system of record either way: the database
is a disposable cache rebuilt from `curated/`, which is how this repo ran its
retired Postgres warehouse (`warehouse/README.md`).

### Lake conventions (already in place)

- Hive paths: `boundary_type=<T>/year=<Y>`, `vintage=<Y>/table=<id>`. The vintage is
  part of the path, so a reload never overwrites history silently.
- Boundaries carry `h3_r5`, `h3_r7` and the bbox columns, sorted by `h3_r5`, so row-group
  statistics prune before any geometry is read.
- Every object is written once from local staging, then uploaded to each target
  with a `sha256` in its metadata. `export_geoparquet.py verify` checks source rows
  against the primary target and keys and sizes across mirrors.

## 2. Geographic data model

```
geography (summary_level, geoid, vintage)  PK      ← one table, every layer
   name, geom (MULTIPOLYGON 4326), internal_point, aland, awater, mtfcc

geo_relationship (from_level, from_geoid, to_level, to_geoid, vintage)
   share_area, share_pop, share_hu, method      ← ZIP↔tract, ZIP↔county, place↔tract, tract→CBSA ...

geo_attribute (summary_level, geoid, vintage, attribute_key)  → value  ← ACS / RUCA / derived classes

geo_h3 (h3_r8, summary_level, geoid, vintage, share_pop)  ← fast path for drawn shapes
```

In the lake, `geography` is the `curated/boundaries/` partitions and the other
three are Parquet tables beside it. The same shapes load unchanged into PostGIS if
a serving DB is added. Rules this repo already enforces, and that any schema
built on it should copy:

- **A GEOID is never the key on its own.** County `01001`, SLDU `01001` and ZCTA
  `01001` are different places, so the key is `(summary_level, geoid, vintage)`.
  This bug collapsed the legacy ZCTA and SLDU loads (see `REPO_SPLIT_PLAN.md`).
- **GEOIDs are text.** Leading zeros are significant (`06037`, `02134`).
- **Store EPSG:4326, measure in an equal-area CRS.** Areas and overlap shares are
  computed in EPSG:5070 (CONUS Albers), 3338 (Alaska) or the Hawaii and Puerto Rico
  equivalents, or on `geography`. Never in square degrees, except as a ratio
  within one small shape.
- **One geometry for analysis, another for display.** Full TIGER/Line geometry
  for overlays, tippecanoe-simplified geometry in tiles. Cartographic boundary
  files are for small-scale maps, not for apportionment.
- **Subdivide before indexing big polygons.** Store `ST_Subdivide(geom, 256)`
  pieces in a side table for intersection-heavy layers (CBSA, UA, broadcast
  contours). It is often an order of magnitude faster than testing whole
  multipolygons.
- **ZIP ≠ ZCTA.** ZIPs are USPS delivery routes, and ZCTAs are Census's areal
  approximation of them. Map business ZIPs to ZCTAs with HUD's ZIP crosswalk (or
  the RUCA ZIP file's PO-box handling) and label the output ZCTA.

### Relationships

| Pair | Method | Source |
|---|---|---|
| tract → county → state | GEOID prefix (exact nesting) | n/a |
| tract/BG → CBSA, CSA | county membership | delineation files / county GEOID |
| ZCTA ↔ tract, county, place, county subdivision | land-area parts from Census, then **population-weighted** with 2020 block counts | `curated/reference/rel2020/` |
| place ↔ tract | spatial overlay of 2020 blocks (places don't nest) | TIGER blocks + P1 |
| vintage Y ↔ vintage Y+n | shape overlap (`boundary_crosswalk`, `attribute_on_geography()`) | `warehouse/load/build_crosswalk.sql` |

## 3. Drawn-shape analysis ("draw an area, get ZIPs and population")

Two paths, chosen by how precise the result needs to be:

1. **Fast (H3), the default.** Population and housing are precomputed per H3 cell
   (res 8, about 0.7 km²) from 2020 blocks, each cell tagged with its ZCTA, tract,
   county and place. DuckDB fills the drawn polygon with cells (`h3_polygon_wkt_to_cells`)
   and joins the cell table. That's one indexed-by-key lookup, not an overlay, so
   it's fast enough for live previews while the user drags.
2. **Exact, on release.** Block groups are prefiltered by bbox/`h3_r5` from the lake,
   intersected with the shape in DuckDB spatial, and each group's ACS counts are
   apportioned by the **population** share inside the shape (2020 block populations
   as the weight). That beats area share, which assumes people are spread evenly over
   parks, lakes and farmland. The query also returns every ZCTA and county touched,
   with its share. This is the path a PostGIS GIST index would speed up, if it ever
   becomes the bottleneck.

`geo-llm-lab/evals` covers both shapes of the problem: `radius-pop-001` is the
point-in-radius version, and `polygon-apportion-001` is the area-weighted
version with a tolerance.

## 4. Urban / suburban / exurban / rural

No single federal definition covers all four. The method is tract-level,
explainable, and built only from public sources already in the lake
(`scripts/urbanicity_to_lake.py` → `curated/derived/urbanicity/`). Density is
ACS households per land square mile. The cut points of 2,213 and 102 are Jed
Kolko's urban/suburban/rural thresholds:

| Class | Detail | Rule |
|---|---|---|
| Urban | `urban_core` | RUCA 1–3 **and** ≥ 2,213 households/sq mi |
| Suburban | `suburban` | RUCA 1, 102–2,213 households/sq mi |
| Exurban | `exurban_commuter` | RUCA 2–3 (metro commuting fringe outside the urban core) |
| Exurban | `exurban_low_density` | RUCA 1 below 102 households/sq mi |
| Exurban | `exurban_metro_town` | RUCA 4–6 inside a metropolitan CBSA (e.g. Sonoma, CA) |
| Rural | `micropolitan` / `small_town` / `remote_rural` | RUCA 4–6 elsewhere / 7–9 / 10 |

ACS 2024 national split: 22.5% urban, 48% suburban, 15% exurban, 14% rural.
The Census housing survey, where people describe their own area, gives about
27/52/21 urban/suburban/rural.

- Counties and CBSAs get exact **population mixes**, because tracts nest in them.
  ZCTAs are split by land-area share (Census relationship file) and places by
  polygon overlap, so a mixed area is never forced into one label
  ("62% suburban, 30% exurban").
- The thresholds are constants in one script, so a change in classification
  can be diffed and explained.

## 5. Coverage: who serves a geography

- **Broadcast**: `scripts/fcc_to_lake.py` builds three things.
  - **Stations**: every US FM/TV/AM record from the FCC query lists, with licensee.
  - **Contours**: the protected service contour of each licensed facility from
    the FCC contour API (360 radials computed from power, antenna height and
    terrain): FM 60/54 dBu, TV noise-limited, AM 2 mV/m.
  - **Coverage**: station × tract/county/CBSA/ZCTA population covered.

  A station "covers" an area by the share of the area's population inside its
  contour, not by any overlap at all. Tract interior points are used today;
  block-level points would sharpen this for large rural tracts.
- **Print and digital**: circulation or audience ZIP lists become ZCTA unions, with
  coverage share as above.
- **"Which outlets cover X"** is then a population-weighted overlay, ranked by
  coverage share, and joins straight back to the ownership graph.

## 6. LLM integration

The LLM never draws geometry or recalls statistics. It resolves names,
picks tools and writes SQL against a documented surface:

1. **Resolve.** "urban San Francisco" maps to place `0667000`, then to tracts
   classified urban core.
2. **Compute.** It runs read-only DuckDB SQL on the lake, or calls a typed tool
   (coverage overlay, apportionment) that does.
3. **Join.** It filters the business entities (ownership = independent).
4. **Abstain.** When a layer isn't loaded, it says so. The eval scores this
   explicitly.

`geo-llm-lab/evals` is the benchmark for each step. A reference agent (Claude
plus a read-only DuckDB tool) sets the bar, GeoAgent's production agent is
scored through an HTTP contract so its code stays private, and passing
trajectories are exported as fine-tuning data for a smaller, cheaper GeoLLM.

## 7. QA, provenance, versioning

- Vintage in every key and path. Reloads replace one `(layer, vintage)` in a single
  transaction.
- Row-count and key-parity checks after every export (`export_geoparquet.py verify`).
- Quarantine instead of dropping: rows that fail keys go to `legacy.*`, with counts
  accounted for (see the split plan).
- The gold-SQL eval doubles as a data regression test. `--agent gold` must stay at 100%.

## 8. Status

| Capability | State |
|---|---|
| Storage | S3 only (AWS primary, Wasabi archive). Postgres warehouse retired 2026-11-13 |
| TIGER state/county/tract/BG/place/CBSA/CD/SLD, 2011–2025 | In lake (AWS + Wasabi), complete. On 2026-11-16 an audit found missing states in some partitions: TRACT 2011/2016/2017/2024, BG 2025, and SLDU/SLDL in every year. The causes were corrupt or missing zips in `origin/` and gaps from the Postgres load. Those zips were replaced, the partitions rebuilt with `tiger_to_lake.py` and checked to only add rows, then published. SLD names are now NAMELSAD. Census published no CBSA file for 2022 |
| ZCTA520 2020–2025 | In lake, built from the raw zips by `scripts/tiger_to_lake.py` |
| UAC20, CSA, METDIV, COUSUB, AIANNH, PUMA20 | 2025 in lake (raw zips archived to `origin/`); earlier vintages on request |
| ACS 5-year 2020–2024, all tables and geographies | In lake |
| ACS 5-year 2014–2019, GeoAgent's 12 tables, 8 levels | In lake (`scripts/acs_api_to_lake.py`); 2010-census tracts/BGs/ZCTAs |
| Gazetteer 2025, ZCTA relationship files, RUCA 2020 | In lake (`scripts/get_reference_data.py`) |
| LODES 8 jobs, resident workers, commute flows | In lake: block level under `reference/lodes` (2024; Michigan 2021; Alaska not published since 2016), tract/county/county-to-county rollups under `derived/lodes/year=2024` (`scripts/lodes_rollup_to_lake.py`) |
| Urban/suburban/exurban/rural | In lake, ACS 2024 (`scripts/urbanicity_to_lake.py`) |
| FCC stations, contours, coverage (FM, TV, Class A, AM) | In lake (`scripts/fcc_to_lake.py --services core`); translators/LPFM/LPTV with `--services all` |
| Station ownership (parent companies) | Next: LMS dump ownership tables → licensee → parent |
| Newspapers / digital outlets | Not in FCC data; needs the client's list or a news-outlet dataset |
| Block-level population weights, H3 weights | Next |
| Agent benchmark | `geo-llm-lab/evals` (new) |
