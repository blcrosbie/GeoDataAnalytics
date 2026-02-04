# GeoAgent ETL: Real Estate + Environmental Risk Layers

This document defines the first-priority layers and how we ingest/normalize them for vectorization & map delivery.

## Guiding Principle
Ship layers that answer:
- "Would I regret living here?"
- "Will insurance/financing get weird?"
- "Is this area getting riskier or safer over time?"

---

## Layer 1 — Flood Exposure (P0)
### Data
- FEMA NFHL flood zones (polygons) where available
- Water bodies / rivers / coastline (polygons/lines)
- Elevation derivatives (if available): slope, flow accumulation, low-lying areas

### Outputs
- `flood_zone` polygon tileset
- `water_proximity` derived metric per hex/tract/parcel proxy (distance buckets)
- `flood_risk_score` normalized (0–100) per hex/tract

### ETL Steps
1. Ingest raw FEMA + hydro layers into PostGIS (keep raw schema in `raw.*`)
2. Normalize CRS (store in EPSG:4326 for web, keep local projected for distance calcs)
3. Clean geometries: `ST_MakeValid`, remove slivers, dissolve by category where needed
4. Derive proximity metrics (example):
   - `ST_Distance` to nearest water feature using projected CRS
   - bucket into bands (e.g., 0–250m, 250–1000m, 1–5km, 5km+)
5. Aggregate to serving geometry:
   - your choice: H3 res X, tract, ZIP, or “grid/hex” for speed
6. Vectorize:
   - polygons: simplify per zoom (`ST_SimplifyVW`) + tippecanoe (or tegola) MVT
   - metrics: store per-hex features and serve as MVT/GeoJSON

---

## Layer 2 — Weather & Extreme Rain Signals (P0)
### Data
- NOAA precipitation normals / extreme precip frequency (if you have)
- Storm event history (where you have it)
- Any “heavy rain days” / intensity indicator datasets

### Outputs
- `rain_intensity_index` per hex/tract
- optional: `storm_events` points/polygons for known events

### ETL Steps
1. Ingest rasters/tables into raw storage
2. Resample/aggregate to your serving geometry (hex/tract/ZIP)
3. Store time windows:
   - baseline normals
   - recent period (e.g., last 1–3 years)
4. Compute deltas: recent vs baseline

---

## Layer 3 — Heat / Sun / Wind (P0)
### Data
- Heat days / heat index (NOAA or derived)
- Solar radiance (global horizontal irradiance, if you have)
- Wind speed/direction summaries (if you have)

### Outputs
- `heat_stress_index` per hex/tract
- `solar_exposure_index` per hex/tract
- `wind_profile` (median speed, prevailing direction) per region

### ETL Steps
1. Normalize time granularity (monthly/seasonal rollups)
2. Aggregate to serving geometry
3. Keep a “seasonality” dimension for UI (summer vs winter)

---

## Layer 4 — Air Quality & GHG Signals (P0/P1 depending on readiness)
### Data
- Sentinel-5P (NO2, SO2, CO, O3, CH4) derived aggregates
- Ground station PM2.5 if available (optional)
- Point sources if you have (optional)

### Outputs
- `air_quality_index` per hex/tract (multi-pollutant)
- pollutant-specific layers (toggleable): `no2`, `co`, `o3`, `ch4`

### ETL Steps
1. Precompute spatial aggregates server-side (client must not crunch big rasters)
2. Store pollutant summaries:
   - median, p90, trend (delta)
3. Normalize into a single “index” for non-experts, keep raw values for experts

---

## Layer 5 — Neighborhood Trend Signals (ACS / IRS / PopEst) (P1)
### Data
- ACS 1y/5y: income, rent, education, household size, commute mode, age bands
- IRS migration: inflow/outflow
- PopEst: population change

### Outputs
- `neighborhood_trends` per tract/ZIP/CBSA
- “direction arrows”: up/down/flat for key metrics

### ETL Steps
1. Load boundaries: ZIP, tract, county, CBSA into PostGIS
2. Load ACS/IRS/PopEst tables keyed by GEOID (or ZIP where possible)
3. Join to geometry tables
4. Precompute trend windows (1y, 3y, 5y)
5. Export to MVT (polygon layer) + API for detailed drill-down

---

## Vectorization & Serving Notes
- Prefer MVT tiles for anything map-visible at scale.
- Use GeoJSON only for small selections (one place/address).
- Maintain:
  - `raw.*` (untouched)
  - `staging.*` (cleaned/normalized)
  - `serving.*` (simplified, indexed, tile-ready)

## Update Cadence (default)
- Flood/hydro: quarterly or as released
- Weather normals: yearly
- Event feeds (permits/closures): daily/weekly
- ACS: yearly
- PopEst: yearly
- IRS: yearly (release-driven)
