# 04 · Aerosol index as an EO/IR tasking cue

## Objective

Frame atmospheric data as a **sensor-tasking decision aid**, not just a
pollutant map: given a wildfire or dust event, use the UV Aerosol Index to
decide whether an EO/IR collection over the smoke/dust-affected area would
actually be usable, or whether tasking should wait (or switch to a
sensor that sees through smoke, like SAR).

This is the clearest version in this lab of the JD's "develop prototype...
imagery products and sample intelligence products that demonstrate unique
capabilities" — the product here is a go/no-go recommendation, not a map for
its own sake.

## Setup

- Preset: **Sentinel-5P / TROPOMI**, dataset `COPERNICUS/S5P/OFFL/L3_AER_AI`
  (UV Aerosol Index — note this is a unitless index, not a gas column; see
  [`GLOSSARY.md`](../GLOSSARY.md#sentinel-5p--tropomi)).
- Pick a real wildfire season/event or a dust-storm event you can look up
  independently.
- AOI: the fire/dust region plus the area downwind you'd hypothetically want
  to collect EO/IR imagery over.
- Time window: the event date, plus a day before (baseline) and a day or two
  after (clearing).

## Steps

1. Extract the Aerosol Index for the baseline day and the event day(s) over
   the same AOI and value range.
2. Identify where the index is clearly elevated above baseline — that's your
   "imagery collection would likely be degraded here" zone.
3. Decide, in writing, a threshold you'd use to call a sub-area "go" or
   "no-go" for optical collection, and mark which parts of the AOI fall on
   each side.

## What to look for

- Spatial extent of elevated aerosol index versus the area you'd actually
  want imaged — are they the same footprint, or does the smoke/dust only
  cover part of your target?
- How fast it clears: same-day recovery vs. multi-day lingering changes
  whether "wait a day" or "switch sensor" is the better recommendation.
- Whether you're tempted to treat the index as more precise than it is — it's
  a relative, qualitative indicator, not a calibrated optical-depth
  measurement. Say so in the write-up rather than implying false precision.

## Why it matters

This is where atmospheric monitoring and EO/IR imagery planning actually
meet: smoke and dust don't just show up as a feature in an image, they
determine whether the image is worth collecting at all. A data product that
tells a tasking authority "don't bother, visibility is bad, try again in two
days" or "clear now, go" is a concrete, decision-relevant deliverable — the
kind the JD calls out directly ("translating operational pain points and
needs into technical requirements and derived data solutions").

## Deliverable

Save to `results/04-aerosol-mission-planning/`:

- Baseline and event-day extracts.
- A marked-up screenshot showing your go/no-go zones.
- A short recommendation memo: the threshold you used, the call you'd make,
  and the honest confidence caveat on the index itself.
