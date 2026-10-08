# 05 · Archive-depth fusion — confirming a trend across 40 years

## Objective

Step outside the two-date comparison entirely and use Landsat's unique
asset — a continuous public archive back to 1972 — to check whether a
change you flagged in scenario 01 or 02 is a real, sustained trend or just
an artifact of the two dates you happened to pick. Pull a short time series
of same-season scenes spanning as much of the archive as practical over the
same AOI, and look at it as a trajectory rather than a before/after pair.

Run this **after** at least one earlier scenario — you need an AOI and a
two-date finding to stress-test. This is the archive-depth counterpart to
the S5P lab's EO/IR fusion scenario: both are about refusing to trust a
two-point comparison until you've checked it against more than two points.

## Setup

- Preset: **All datasets**, searching across the Landsat family as needed:
  `LANDSAT/LC09/C02/T1_L2` and `LANDSAT/LC08/C02/T1_L2` (2013–present),
  `LANDSAT/LE07/C02/T1_L2` (1999–2022), `LANDSAT/LT05/C02/T1_L2`
  (1984–2012) — different sensors, same general band structure, so confirm
  band names in **Details…** for each collection rather than assuming
  `ST_B10` or band numbering carries over unchanged.
- AOI: the exact same AOI as the earlier scenario you're following up on.
- Time series: pick 4–6 dates spread across as much of the archive as
  you can reach, all from the **same season** (e.g. all July scenes) so
  seasonal variation doesn't masquerade as trend. Use the same band/index
  you used in the earlier scenario (NDVI, NDWI, `ST_B10`, or the NLCD class
  at that location) at each date.

## Steps

1. Extract the same band or index for each of your 4–6 dates, same AOI,
   same season.
2. Load them in date order and compare, either as a small multi-panel
   layout or by stepping through layer visibility in sequence.
3. Plot (even roughly, by eye, or in a quick spreadsheet) the value at your
   point or zone of interest across all dates.
4. Note explicitly: does the trajectory look like a steady trend, a step
   change at one particular date, or noise with no clear direction — these
   imply very different explanations and very different confidence levels.
5. Flag any date where you had to cross sensors (e.g. Landsat 5 to Landsat
   8) and note whether the transition itself introduces a visible jump —
   a sensor change is a legitimate alternative explanation for a
   discontinuity, not just real-world change.

## What to look for

- A **monotonic or clearly-directional trajectory** across most of the
  points — this is a real finding, much stronger than any two-date
  comparison alone.
- A trajectory that's flat for most of the archive and only changes
  between your two most recent dates — this means the earlier scenario's
  "trend" is actually a recent, possibly still-developing change, which is
  a different (and often more urgent) finding than a long slow drift.
- A discontinuity that lines up with a sensor transition rather than any
  real-world date — if you see this, say so plainly rather than
  interpreting it as ground change.

## Why it matters

A two-date comparison is a hypothesis; an N-date trajectory sampled across
decades is closer to a tested one. This is the specific analytic advantage
Landsat has that neither Sentinel-5P (continuous since 2017) nor most
commercial EO constellations (continuous for maybe a decade) can offer, and
it's worth being able to say precisely why that depth matters rather than
just gesturing at "long archive" — it's the difference between "we think
this changed" and "here's the shape of the change over 40 years, and here's
the one date it actually started."

## Deliverable

Save to `results/05-archive-depth-fusion/`:

- Each date's extract, as one QGIS project (`.qgz`) ordered by date.
- A screenshot or simple chart of the value-over-time trajectory at the
  zone of interest.
- A short write-up: trend, step-change, or noise — which one your
  trajectory actually shows, and whether it changes the conclusion you drew
  in the earlier two-date scenario.
