# 02 · Landsat thermal signature as a facility-activity proxy

## Objective

Use Landsat's thermal band — emitted heat, not reflected light — as an
**activity-based intelligence** signal: can you detect a known difference in
operating state at a thermally distinctive facility (a power plant, a
landfill, an industrial site) from a public archive, without any ground
truth beyond "I know roughly when this facility runs hot"?

This is the direct analogue, in a different data family, of the S5P lab's
NO2 activity-monitoring scenario — same analytic move, a 30 m thermal
measurement standing in for a trace-gas column.

## Setup

- Preset: **All datasets** (search `LANDSAT`), or search the dataset ID
  directly: `LANDSAT/LC09/C02/T1_L2` or `LANDSAT/LC08/C02/T1_L2` (Collection
  2, Level 2 — surface reflectance and temperature, not raw radiance; see
  [`GLOSSARY.md`](../scenarios-usgs/GLOSSARY.md#landsat--usgs-eros-archive)
  on why Level 2 is the one to use).
- Band: `ST_B10` (surface temperature). Confirm the unit in **Details…** —
  USGS delivers this band pre-scaled to Kelvin; check the scale factor
  shown rather than assuming raw digital-number values are already
  temperature.
- AOI: a thermally distinctive facility you can reason about independently
  — a power plant's cooling infrastructure, a landfill, a large industrial
  roof.
- Comparison: two scenes you can justify in advance as representing
  different operating states (a known outage/shutdown date vs. a normal
  operating date; or, if you don't have a known event, a summer vs. winter
  pair *and* say explicitly that ambient seasonal temperature, not just
  facility activity, will also move the signal).
- Cloud check: because Landsat revisits every 16 days (8 with both
  satellites), you don't get to pick an arbitrary date — search a short
  window around your target date and take the clearest available scene,
  confirmed via `QA_PIXEL`.

## Steps

1. Extract `ST_B10` for date/scene A and date/scene B, same AOI, same band,
   same resolution.
2. Load both as separate layers with the same fixed value range (not
   independently auto-scaled) so a given color means the same temperature
   in both.
3. Mask or visually discount any `QA_PIXEL`-flagged cloud/shadow cells
   before comparing — a cloud shadow over the facility will read as a cold
   anomaly that has nothing to do with operations.
4. Compare the facility's thermal footprint against the surrounding
   background in both scenes.

## What to look for

- A visible drop in the facility's thermal signature during the
  lower-activity period, localized to the facility rather than a
  region-wide swing (a region-wide shift is more likely seasonal/ambient
  than operational).
- Whether the "quiet" state still reads warmer than true ambient background
  — it usually should, since most facilities don't go fully cold.
- Whether you can actually separate ambient seasonal temperature change
  from facility-driven change with only two dates — if you can't, say so
  rather than overclaiming; a longer time series (a handful of same-season
  dates across different operating states) is the honest fix.

## Why it matters

Thermal emission is a direct physical signature of active industrial
process heat — closer to a hard observable than NO2's "proxy for
combustion," but Landsat's 16-day (8-day combined) revisit means you can't
get the kind of daily pattern-of-life baseline the S5P lab builds with NO2.
The honest framing a customer-facing product needs here is explicit about
that tradeoff: finer physical signal, much coarser temporal sampling. Naming
both, rather than quietly picking the flattering one, is the difference
between an analysis and a sales pitch.

## Deliverable

Save to `results/02-thermal-activity-monitoring/`:

- Both extracts, and a side-by-side screenshot at matched value ranges.
- A short write-up: did the expected contrast appear, how large was it, and
  whether ambient seasonal temperature is a plausible full or partial
  explanation instead of (or alongside) facility activity.
