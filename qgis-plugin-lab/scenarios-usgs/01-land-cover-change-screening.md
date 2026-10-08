# 01 · Land cover change screening over a growing metro fringe

## Objective

A hypothetical customer asks: *"Which parts of this county have actually
converted from agricultural or forest land to development over the last
decade, and where is it happening fastest?"* Screen a region for land-cover
change using a free, categorical, decade-deep USGS product — and be honest
about what a 30 m categorical screen can and can't tell them.

This is the JD's "conduct first-principles... analysis to formulate
hypotheses for... novel use cases" and "perform feasibility studies... to
support development of early-stage mission and data concepts," run as an
exercise, the same way the S5P lab's methane screening scenario is.

## Setup

- Preset: **All datasets** (or search `NLCD` directly — it should surface
  `USGS/NLCD_RELEASES/2023_REL/NLCD`, the annual national land-cover
  product this scenario uses).
- Band: the `landcover` classified band. Confirm in **Details…** which
  year's layer you're pulling — the annual product has one image per year
  back to 1985; you pick the year, not a date range. See
  [`GLOSSARY.md`](../scenarios-usgs/GLOSSARY.md#national-land-cover-database-nlcd)
  on epoch vs. annual releases.
- AOI: draw a box or hexagon over a real, named county or metro fringe
  you'd expect to have grown — a Sun Belt metro's exurban edge is an easy,
  independently verifiable pick.
- Comparison: two years roughly a decade apart (e.g. 2013 and 2023), not
  adjacent years — NLCD's year-to-year noise can exceed a single year's
  real change, so a short baseline makes the signal hard to trust.
- Resolution: start at **Native** (30 m); this is a small-enough pixel that
  auto-scaling is unlikely to kick in unless your AOI is county-sized or
  larger.

## Steps

1. Open the dock, select the preset, confirm the dataset, band, and *year*
   in **Details…** — do this twice, once per year you're comparing.
2. Set the AOI, extract year A's classified layer, then year B's, to
   separate GeoJSON/raster outputs.
3. Load both as layers with the same categorical palette (**Style layer**)
   so classes read identically across both.
4. Compute the difference: cells whose class changed from a
   non-developed category (forest, shrub, cropland, pasture) in year A to a
   developed category in year B.
5. Visually scan for a **spatially coherent conversion front** — a
   contiguous edge of change, not scattered single-pixel flips.

## What to look for

- A **spatially coherent conversion front** (a contiguous band of
  newly-developed cells along a road corridor or existing built-up edge) is
  far more credible than scattered isolated flips, which are as likely to
  be classification noise as real development.
- Whether the converted area actually borders existing development (sprawl
  pattern) or appears disconnected from it (which is more interesting, but
  also a cue to double-check you're not looking at a classification
  artifact — a reservoir drawdown misclassified as bare ground, for
  instance).
- Rate: dividing total converted area by the number of years tells you
  whether this is a slow, steady trend or a recent acceleration — the
  second is a much more actionable finding for a customer than the first.

## Why it matters

A single 30 m NLCD pixel can't tell a planner which specific parcel changed
hands or broke ground. What a decade-deep, free, nationally consistent
classification *is* good for is exactly what the objective asked: deciding
which part of a large area is actually converting, how fast, and whether
it's accelerating — the kind of screening result that justifies a follow-up
parcel-level or high-resolution-imagery study. That's the same **cueing**
relationship (see glossary) the S5P lab builds toward with EO/IR fusion,
just one step earlier in the resolution chain — coarse categorical data
pointing at where a finer look is worth the cost.

## Deliverable

Save to `results/01-land-cover-change-screening/`:

- Both years' exported classified layers.
- A screenshot of the styled change layer with the AOI and the conversion
  front circled.
- A short write-up (5–10 sentences): what you found, the rate of change,
  how confident you are given NLCD's known classification accuracy, and
  what you'd recommend as a follow-up (parcel records, high-res imagery,
  a site visit) and why.
