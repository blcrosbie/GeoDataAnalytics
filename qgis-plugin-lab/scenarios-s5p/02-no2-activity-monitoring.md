# 02 · NO2 as an activity-level proxy

## Objective

Use NO2 — a short-lived combustion byproduct — as an **activity-based
intelligence** signal: can you detect a known change in operational tempo
at a facility, port, or city from space, without any ground truth beyond
"I know this facility runs on a weekday schedule"?

## Setup

- Preset: **Sentinel-5P / TROPOMI**, dataset `COPERNICUS/S5P/OFFL/L3_NO2`.
- Band: the **tropospheric** NO2 column, not total column — confirm which
  one you've picked in **Details…**. See
  [`GLOSSARY.md`](../GLOSSARY.md#sentinel-5p--tropomi) for why tropospheric
  is the one that reflects ground-level activity.
- AOI: a facility, port, or urban area you can reason about independently
  (a known power plant, a container port, a mid-size city core).
- Time window: pick two contrasting periods you can justify in advance —
  weekday vs. weekend for the same month, or before/after a known schedule
  change (a holiday period, a documented shutdown). Deciding the comparison
  *before* looking at the data is what keeps this an experiment instead of a
  search for a pattern that confirms itself after the fact.

## Steps

1. Extract NO2 for period A (e.g., a representative weekday) and period B
   (e.g., the adjacent weekend), same AOI, same band, same resolution.
2. Load both as separate layers with the same palette and value range so
   they're visually comparable (fix the style's min/max rather than letting
   each layer auto-scale independently — otherwise you're comparing two
   different color scales, not two states of the world).
3. Optionally, pull a short multi-week time series over the AOI and look at
   it as a trend rather than two snapshots.

## What to look for

- A visible drop in NO2 over the AOI during the lower-activity period,
  localized to the facility/AOI rather than a region-wide swing (a
  region-wide change is more likely weather or transport than local
  activity).
- Whether the "quiet" period's reading still sits above true background —
  it should, since most facilities don't go to zero.
- Noise: a single day's reading can be thrown off by one cloudy overpass.
  If the contrast you expected doesn't show up, check whether either date
  actually had a clean (non-cloud-flagged) retrieval before concluding
  there's no signal.

## Why it matters

NO2's atmospheric lifetime is hours, so what you're seeing is close to
"right now," unlike CH4's decade-long-mixed background. That short lifetime
is exactly what makes it useful for **pattern-of-life** work — you first
have to establish the normal rhythm (this scenario) before anything else can
be called anomalous. This is also the most direct analogue in this lab to
the JD's "activity-based intelligence" use of remote sensing: inferring
operational tempo from an indirect, physically-grounded proxy rather than
from direct observation.

## Deliverable

Save to `results/02-no2-activity-monitoring/`:

- Both extracts, and a side-by-side screenshot (or a before/after layout) at
  matched color scales.
- A short write-up: did the expected contrast appear, how large was it, and
  what's the most likely confound if it didn't.
