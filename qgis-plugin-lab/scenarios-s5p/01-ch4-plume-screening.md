# 01 · Methane plume screening over an oil & gas basin

## Objective

A hypothetical customer asks: *"Can you tell us which parts of this basin are
worth a closer (and more expensive) look for methane emissions?"* Screen a
known oil & gas production region for atmospheric methane anomalies using
only free, daily, global data — and be honest about what that screening can
and can't tell them.

This is the JD's "conduct first-principles... analysis to formulate
hypotheses for... novel use cases" and "perform feasibility studies... to
support development of early-stage mission and data concepts," run as an
exercise.

## Setup

- Preset: **Sentinel-5P / TROPOMI** (or search `CH4` directly — it will also
  surface `COPERNICUS/S5P/OFFL/L3_CH4`, the dataset this scenario uses).
- Band: whichever CH4 band the Details panel shows as the dry-air mixing
  ratio (confirm the unit — should read as parts per billion, not a column
  density). See [`GLOSSARY.md`](../GLOSSARY.md#sentinel-5p--tropomi) on why
  CH4 is reported differently from the other gases.
- AOI: draw a box or hexagon over a real, named oil & gas basin (Permian,
  Marcellus, or similar — pick one you can look up independently).
- Time window: one full month, not one day. CH4's ~decade-long lifetime means
  a single day mostly shows global background, not local sources — see the
  glossary's lifetime table.
- Resolution: start at **Native**; let the plugin's estimate tell you if
  that's too large and take its suggested resolution/date-window adjustment
  rather than guessing.

## Steps

1. Open the dock, select the preset, confirm the dataset and band in
   **Details…**.
2. Set the AOI and time window as above.
3. Watch the size estimate. If auto-scaling kicks in, read the tiling plan
   (tile count, H3 resolution, predicted time) before accepting it.
4. Extract to GeoJSON, load it as a layer, and apply the suggested palette
   (**Style layer**).
5. Visually scan for cells reading noticeably above the surrounding
   background — not just the single brightest pixel, but a spatially
   coherent patch.

## What to look for

- A **spatially coherent anomaly** (several adjacent elevated cells) is far
  more credible than one bright pixel, which is as likely to be retrieval
  noise as a real plume.
- Compare the anomaly's rough shape and extent against what you'd expect
  from wind-transported emissions versus a data artifact (a single pixel on
  a tile boundary, e.g.).
- Check whether the elevated area actually falls inside documented
  production acreage for the basin you picked, or somewhere you can't
  explain — the latter is more interesting, but also a cue to double-check
  your AOI and band choice before concluding anything.

## Why it matters

Sentinel-5P CH4 pixels are kilometers across — far too coarse to attribute
an anomaly to a single well pad or compressor station. What it *is* good
for is exactly what the objective asked: deciding which part of a huge area
deserves a follow-up look from something finer (airborne hyperspectral,
GHGSat, or a site visit). That's a **cueing** relationship (see glossary),
and naming it explicitly is the difference between an honest data product
and an oversold one.

## Deliverable

Save to `results/01-ch4-plume-screening/`:

- The exported GeoJSON/CSV.
- A screenshot of the styled layer with the AOI and any candidate anomaly
  circled.
- A short write-up (5–10 sentences): what you found, how confident you are,
  and what you'd recommend tasking next and why.
