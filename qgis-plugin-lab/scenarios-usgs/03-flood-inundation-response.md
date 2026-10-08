# 03 · Flood inundation rapid-look for a hazard event

## Objective

Simulate a "zero-to-one" rapid-response data product: given a known,
documented flood event, pull the nearest clear before/after Landsat scenes,
compute an open-water index, and characterize inundation extent and
recession over the following weeks — then write the kind of short,
time-pressured brief a disaster-response or emergency-management customer
would actually want.

This is the USGS-data analogue of the S5P lab's SO2 hazard-response
scenario: same "real documented event, before/after sequence, honest
latency caveat" structure, built on optical imagery and band math instead
of a ready-made gas column.

## Setup

- Preset: **All datasets**, dataset `LANDSAT/LC09/C02/T1_L2` or
  `LANDSAT/LC08/C02/T1_L2` (whichever has a usable scene closest to your
  event).
- Pick a **real, documented flood event** you can look up independently (a
  named river flood or hurricane-driven inundation with a known date is
  easiest to verify against). Use the flood peak date as day zero.
- AOI: wide enough to cover the floodplain, not just the river channel —
  inundation extent is usually far wider than the normal waterway.
- Bands: Green and NIR (to compute NDWI — see
  [`GLOSSARY.md`](../scenarios-usgs/GLOSSARY.md#landsat--usgs-eros-archive)
  for the formula). There is no ready-made "flood" band; you build the
  index from raw surface-reflectance bands.
- Scene selection: because Landsat only revisits every 16 days (8 combined),
  you will likely **not** get a scene on the exact event date. Search a
  window of several weeks before and after, and pick the clearest scene
  before the event (baseline) and the clearest scene(s) after it — note
  explicitly how many days each pulled scene actually is from day zero.

## Steps

1. Extract the baseline (pre-event) scene and compute NDWI.
2. Extract the closest available post-event scene(s) and compute NDWI the
   same way.
3. Load both NDWI layers with the same fixed value range and a
   water-highlighting palette (**Style layer**).
4. Threshold NDWI to classify "water" vs. "not water" using a single
   consistent cutoff across both dates, and difference the two masks to
   isolate newly-inundated area.
5. If a second post-event scene is available weeks later, repeat the
   extract to see how much of the inundated area has receded.

## What to look for

- A **spatially coherent newly-flooded extent** that follows the
  floodplain's actual topography (valley bottoms, low-lying developed
  areas) rather than scattered single pixels, which are more likely cloud
  shadow or NDWI threshold noise than real water.
- Whether the "before" scene was actually dry — a wet baseline (recent
  rain, seasonal high water) will understate how much *new* flooding
  occurred.
- How much inundated area remains at the later post-event date — that's
  your answer to "how long did this matter," the question a response
  customer usually actually has.

## Why it matters

Optical flood mapping has a real limitation this scenario forces you to
confront honestly: clouds are extremely likely during and immediately after
the kind of weather that causes flooding, and Landsat's slow revisit means
you often can't get a clean scene until the water has already started
receding. That's the **latency tradeoff** again, in a different form than
S5P's few-hours-to-publish delay — here it's "the sensor literally didn't
fly over at a useful moment," which is exactly the kind of caveat a
disaster-response brief has to state up front rather than let the customer
discover on their own (and exactly why operational flood response leans on
radar sensors that see through cloud — worth naming in your write-up even
though this scenario doesn't use one).

## Deliverable

Save to `results/03-flood-inundation-response/`:

- The before/after NDWI extracts and the newly-inundated difference layer.
- A screenshot showing the inundation extent against the floodplain.
- A one-paragraph "incident brief": event, observed inundation extent, how
  many days old each scene actually was relative to the event, and the
  point at which you'd call recession substantially complete (or note that
  you don't have a late-enough scene to say).
