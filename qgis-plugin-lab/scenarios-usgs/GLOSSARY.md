# Domain glossary — why these words matter

The scenarios assume this vocabulary. Skimming it first is faster than
hitting an unfamiliar term mid-scenario and guessing. This set leans on
USGS-stewarded (and USGS/NASA joint) data: Landsat, the National Land Cover
Database, and SRTM elevation. It's a deliberately different data family from
[`scenarios-s5p/GLOSSARY.md`](../scenarios-s5p/GLOSSARY.md) — moderate-resolution,
multi-decade, mostly-weekly-or-slower, instead of coarse, daily, and global.
Read both; the contrast is the point.

## Landsat / USGS EROS archive

- **Landsat program** — a joint USGS/NASA effort running continuously since
  1972 (Landsat 1), making it the longest continuous space-based record of
  Earth's land surface that exists. USGS operates the ground archive (EROS
  Center, Sioux Falls) and is the data steward; NASA builds and launches the
  satellites. When the plugin's catalog shows a `LANDSAT/...` collection,
  that's this program — "USGS data" in this lab means USGS-stewarded, not
  only things with a literal `USGS/` prefix.
- **Collection 2, Level 1 vs. Level 2** — Level 1 is top-of-atmosphere
  radiance/reflectance, minimally processed. Level 2 is *surface*
  reflectance and surface temperature, atmospherically corrected so the same
  ground target reads consistently regardless of haze or sun angle. Prefer
  Level 2 (`..._L2` collection IDs) for anything analytic, the same way the
  S5P glossary tells you to prefer tropospheric column over total column —
  it's the "someone already did the correction for you" version.
- **Collection, Tier (T1/T2)** — "Collection 2" is USGS's current reprocessing
  baseline (supersedes the older Collection 1). Within it, **Tier 1 (T1)**
  scenes meet the tightest geometric-accuracy standard and are the ones worth
  using for anything involving precise locations or change detection; **Tier
  2 (T2)** scenes failed some accuracy check and should be treated with more
  suspicion. The plugin's catalog entries show which tier a collection is.
- **Surface reflectance bands vs. surface temperature (ST) band** — Landsat
  8/9's OLI/TIRS instruments produce both: numbered `SR_B*` bands (visible,
  NIR, SWIR — reflected light) and `ST_B10` (thermal — emitted heat, same
  physical quantity as Landsat's older TIRS/TM thermal bands). A reflectance
  band tells you what's *there*; the thermal band tells you how *hot* it is.
  They answer different questions and shouldn't be averaged together.
- **QA_PIXEL / cloud and shadow masking** — Landsat Level 2 products ship a
  per-pixel bitmask flagging cloud, cloud shadow, cirrus, snow/ice, and
  water. Skipping this and treating every pixel as clean is the single most
  common way to turn a cloud into a false "change." Directly analogous to
  S5P's QA flagging — different bits, same discipline.
- **Scene vs. AOI query** — Landsat is natively organized as fixed WRS-2
  path/row scenes (~185 km swaths), not an arbitrary query grid. The plugin
  abstracts this away (you draw an AOI, it mosaics whatever scenes
  intersect), but a seam between two scenes acquired on different days can
  still show up as a visible edge in time-sensitive comparisons — worth
  knowing when a boundary artifact appears exactly where you wouldn't expect
  a real one.
- **Spectral indices (NDVI, NDWI, NBR)** — unlike S5P's ready-made trace-gas
  columns, Landsat ships raw bands; indices are band math *you* compute:
  - NDVI (vegetation): `(NIR − Red) / (NIR + Red)`
  - NDWI (open water): `(Green − NIR) / (Green + NIR)`
  - NBR (burn severity): `(NIR − SWIR2) / (NIR + SWIR2)`

  This is the central practical difference between this dataset family and
  S5P's: here, the analytic product doesn't exist until you build it from
  bands. That's more work, but also more control over exactly what question
  you're asking.
- **Resolution** — 30 m for OLI/TIRS multispectral bands (15 m
  pan-sharpened using Landsat 8/9's panchromatic band, where used); thermal
  is natively coarser (~100 m) but delivered resampled to 30 m to match. Far
  finer than S5P's multi-km pixels, far coarser than Sentinel-2's 10 m.
- **Revisit cadence** — 16 days per satellite; 8 days combined now that
  Landsat 8 and 9 both fly. Slow compared to S5P's daily global coverage —
  the tradeoff for 100–200x finer ground resolution.

## National Land Cover Database (NLCD)

- **NLCD** — a USGS-produced, categorical land-cover classification for the
  US (16 classes: open water, developed-low/medium/high intensity, various
  forest/shrub/crop/wetland types, etc.), derived *from* Landsat but
  delivered as a finished classification, not raw reflectance.
- **Epoch vs. annual product** — older NLCD releases were multi-year epochs
  (2001, 2006, 2011, 2016, 2019 roughly every 3–5 years); the current annual
  release (`USGS/NLCD_RELEASES/2023_REL/NLCD`) has one classified layer per
  year back to 1985. Check which release and which year's layer you're
  actually looking at before comparing two "NLCD" extracts — comparing an
  old epoch product to the new annual one can introduce a classification
  methodology change that looks like real land-cover change.
- **Classification accuracy is not 100%, and class boundaries are not
  precise edges** — NLCD is a statistical classification with documented
  per-class accuracy well under 100%, assigned per 30 m pixel independently.
  Treating a single-pixel class change as ground truth, or treating a class
  boundary as a surveyed property line, is a category error.

## Terrain / elevation (SRTM)

- **SRTM (Shuttle Radar Topography Mission)** — a 2000 radar mapping mission
  (NASA/NGA-flown, USGS-distributed as the standard public DEM) that
  produced a near-global digital elevation model, void-filled and
  distributed at 1 arc-second (~30 m) resolution as `USGS/SRTMGL1_003`.
- **DEM (Digital Elevation Model)** — a raster where each pixel's *value* is
  ground elevation, not reflectance or temperature. Everything else
  (slope, aspect, hillshade, viewshed) is a **derived product** computed
  from the DEM, not something you request directly — the plugin's terrain
  tools (or Earth Engine's `ee.Terrain` functions) compute these on demand.
- **Slope vs. aspect** — slope is steepness (degrees or %); aspect is the
  compass direction a slope faces. Both matter for siting: a ground station
  wants low slope and a specific aspect for antenna look angle; a flood
  model wants slope for flow direction.
- **Voids and canopy bias** — SRTM has data voids over very steep terrain
  and, being a 2000-era radar measurement, it measures the *top of whatever
  was there* at the time — including forest canopy, not bare ground. A DEM
  reading over dense forest is a canopy-height estimate wearing an
  elevation model's clothes; don't treat it as bare-earth elevation without
  checking land cover first.

## GEOINT-adjacent analytic vocabulary

(Shared with the S5P set — repeated here because they apply just as
directly.)

- **Change detection** — comparing the same location across two time periods
  to find what's different. With Landsat's multi-decade archive, this can
  mean "last year vs. this year" or "1985 vs. now" — the same analytic move
  at two very different timescales.
- **Baseline** — the "normal" state you compare an observation against.
  Harder to get wrong with Landsat than with a single-day atmospheric
  retrieval, because you usually have 40+ years of candidate baseline years
  to choose from — but that also means *picking* the baseline year is itself
  an analytic decision worth justifying in writing.
- **Feasibility study / trade study** — before building a product: does the
  data actually support the hypothesis, at what cost, with what
  limitations, compared to what alternatives? Applies here exactly as it
  does in the S5P set.

## Red flags to catch yourself on

- Comparing Level 1 (TOA) to Level 2 (surface reflectance) imagery, or
  mixing Collection 1 and Collection 2 products, and attributing the
  resulting difference to real ground change.
- Skipping `QA_PIXEL` cloud/shadow masking and reading a cloud or its shadow
  as a land-cover or thermal change.
- Comparing an old multi-year NLCD epoch product to the new annual product
  (or two different release years of NLCD) without checking whether a
  classification-methodology change, not real land cover, explains the
  difference.
- Treating a DEM pixel over dense forest as bare-ground elevation rather
  than canopy-top height.
- Reading a scene-seam line (where two Landsat scenes acquired on different
  days or with different cloud cover meet) as a real spatial boundary.
- Presenting a 30 m categorical class assignment as if it were a precise,
  surveyed boundary.
- Picking a single comparison year without saying why that year, not some
  other year in a 40+-year archive, is the right baseline.
