# 04 · Terrain analysis as a siting/tasking decision aid

## Objective

Frame a DEM as a **siting decision aid**, not just a pretty hillshade: given
a candidate site (a ground station, a sensor emplacement, a staging area),
use SRTM elevation and its derived slope/aspect to decide whether the site
is actually workable, or where nearby it would be better.

This is the USGS-data analogue of the S5P lab's aerosol
mission-planning scenario: the deliverable here is a go/no-go-style
recommendation grounded in terrain, not a map for its own sake — the JD's
"develop prototype... imagery products and sample intelligence products
that demonstrate unique capabilities," applied to elevation data instead of
atmospheric data.

## Setup

- Preset: **All datasets**, dataset `USGS/SRTMGL1_003` (SRTM 1 arc-second
  global elevation — see
  [`GLOSSARY.md`](../scenarios-usgs/GLOSSARY.md#terrain--elevation-srtm)).
- Pick a real candidate site and a concrete siting requirement you can state
  precisely: e.g. "needs slope under 5° for a stable pad" or "needs clear
  line of sight to the northeast horizon for an antenna look angle."
- AOI: the candidate site plus enough surrounding terrain to evaluate
  alternates — don't draw the AOI so tight that you can't see whether a
  slightly different spot nearby would be better.
- Derived products: compute slope and aspect from the elevation band (the
  plugin's terrain tools, or Earth Engine's `ee.Terrain.slope` /
  `ee.Terrain.aspect`, if calling the API directly) — these are not
  separate datasets, they're computed from the one DEM band you extracted.

## Steps

1. Extract elevation for the AOI.
2. Compute slope and aspect layers from it.
3. Load elevation as a hillshade or color ramp for context, then overlay
   slope styled with a hard break at your requirement's threshold (e.g.
   everything under 5° in one color, everything over in another).
4. Identify the candidate site's own slope/aspect value, and scan the AOI
   for any nearby alternate that scores better against the same
   requirement.
5. Note any data voids in the AOI (see glossary) and flag them rather than
   silently treating a void as flat or zero elevation.

## What to look for

- Whether the candidate site itself actually clears your stated threshold,
  or whether you've been assuming it does without checking.
- Whether a materially better alternate exists nearby — "the site we were
  told to evaluate" and "the best site in the area" are not always the same
  answer, and a siting study that only checks the former isn't doing the
  job.
- Whether dense tree cover (cross-check against a land-cover layer, or just
  common sense for the area) means your DEM reading is biased toward
  canopy height rather than true bare-ground elevation at that pixel — this
  matters a lot for a ground-level siting decision and should be called out
  explicitly if it applies.

## Why it matters

A DEM pixel doesn't move or change day to day the way an atmospheric or
thermal signal does, but that's exactly what makes terrain the right
backbone for a siting decision rather than an activity-monitoring one — it
answers "is this physically workable here," not "what happened here
recently." Treating a single elevation value as sufficient for a go/no-go
call without checking slope, aspect, canopy bias, and voids is the terrain
equivalent of reading one cloudy atmospheric pixel as a clean result — the
data point is real, but incomplete on its own.

## Deliverable

Save to `results/04-terrain-mission-planning/`:

- The elevation extract and the derived slope/aspect layers.
- A marked-up screenshot showing the candidate site, your threshold break,
  and any better-scoring alternate you found.
- A short recommendation memo: go/no-go (or "go, with this caveat") on the
  original site, the alternate if any, and the canopy-bias/void caveat if
  it applies.
