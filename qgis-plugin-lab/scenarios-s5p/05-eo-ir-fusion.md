# 05 · EO/IR fusion — ground-truthing an atmospheric anomaly

## Objective

Step outside the Sentinel-5P preset entirely and pull an actual EO/IR scene
over one of the anomalies you found in scenario 01, 02, or 03, to check
whether the atmospheric signal has a visible physical explanation on the
ground. This is the plugin's full catalog breadth (1,100+ datasets, not
just the S5P preset) and the JD's "proven experience working directly with
geospatial tools and manipulating raw, pixel-level data" in one exercise.

Run this **after** at least one earlier scenario — you need an AOI and date
with a candidate anomaly to go check.

## Setup

- Preset: **All datasets** (or **Elevation & land cover** if you want the
  tag filter narrower).
- Search for an EO/IR collection you can reason about: a Sentinel-2
  surface-reflectance collection for a true/false-color look, or a Landsat
  collection if you specifically want a thermal band. Use the search box and
  **Details…** rather than assuming a dataset ID — confirm band names,
  units and native resolution before picking a band.
- AOI: the exact same AOI as the earlier scenario you're following up on.
- Time window: as close as possible to the date of the anomaly you're
  checking (same day if the revisit cadence allows; within the collection's
  revisit window otherwise — see [`GLOSSARY.md`](../GLOSSARY.md#eoir-imagery)
  on Sentinel-2's ~5-day and Landsat's 16-day cadence).

## Steps

1. Extract the EO/IR scene for the matched AOI/date.
2. Load it alongside the atmospheric layer from the earlier scenario, in
   the same QGIS project, at the same extent.
3. Visually inspect what's physically present at the anomaly's location:
   a facility, a burn scar, a plume visible in true color, bare ground,
   nothing identifiable.
4. Note the resolution mismatch explicitly — the atmospheric pixel you're
   explaining is likely kilometers across; the EO/IR pixel is tens of
   meters. Be clear in your write-up about how much of the atmospheric
   cell the EO/IR scene actually covers.

## What to look for

- A plausible physical source inside the atmospheric anomaly's footprint
  (an industrial complex, a fire scar, a visible plume) — this is a
  genuine confirmation.
- No visible explanation at all — equally informative. It means either the
  source isn't visible at EO/IR wavelengths (e.g., it's underground, or it's
  a gas-only signature), the atmospheric signal was transported from
  elsewhere, or the atmospheric read was noise. Say which you think is most
  likely and why.
- Cloud cover or a missed revisit on the EO/IR side — if there's no clean
  scene near the date you need, say so rather than using a scene from a
  conveniently different (but misleading) date.

## Why it matters

A coarse atmospheric anomaly by itself is a tip, not a finding. Multi-sensor
fusion — pairing it with finer-resolution EO/IR imagery at the same place
and time — is the actual analytic move that turns a cueing signal into
something closer to a validated observation. It's also the single clearest
test of whether you understand the resolution gap between the two sensor
classes rather than just overlaying two layers and calling it a day.

## Deliverable

Save to `results/05-eo-ir-fusion/`:

- The EO/IR extract and the paired atmospheric layer from the earlier
  scenario, as one QGIS project (`.qgz`).
- A screenshot with both layers visible, the resolution mismatch called out
  (e.g. an outline of one atmospheric pixel drawn over the EO/IR scene).
- A short fusion write-up: what you found, and which of the "why it
  matters" explanations above fits best.
