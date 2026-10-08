# QGIS Plugin Lab — Earth Engine Catalog Query (`ee_s5p_plugin`)

A learning lab for driving [`ee_s5p_plugin`][plugin] the way an analyst would
actually use it, not the way its own test suite exercises it. The plugin repo
proves the tool works; this lab proves *you* can point it at a real question
and get a defensible answer out the other side.

[plugin]: https://github.com/blcrosbie/ee_s5p_plugin

The scenarios here are modeled on what a **Senior Applied Scientist, Geospatial**
role (EO/IR imagery, atmospheric remote sensing, feasibility studies,
prototype intelligence products, customer discovery) is actually asked to do
day to day — see [`scenarios-s5p/`](scenarios-s5p/) and
[`scenarios-usgs/`](scenarios-usgs/) for the lists. The point isn't to
memorize a job description; it's to use a real one as a filter for "is this
use case substantive, or a toy." Atmospheric trace-gas monitoring from
Sentinel-5P, cross-checked against EO/IR imagery and framed as a product
someone could hand to a customer, is substantive — and running the same
kind of exercise against USGS-stewarded data (Landsat, NLCD, SRTM) is a
deliberate second pass with a different resolution/cadence/processing
tradeoff, not a repeat of the first.

## Layout

| Path | What it is |
|---|---|
| [`SETUP.md`](SETUP.md) | One-time environment setup: QGIS, the Google Earth Engine plugin + account, and `ee_s5p_plugin` symlinked from its sibling repo for live development. |
| [`scenarios-s5p/`](scenarios-s5p/) | Sentinel-5P/TROPOMI atmospheric scenarios — one `.md` file per use case (objective, setup, steps, what to look for, why it matters, what to save) — plus its own [`GLOSSARY.md`](scenarios-s5p/GLOSSARY.md) for the remote-sensing and GEOINT vocabulary those scenarios assume. |
| [`scenarios-usgs/`](scenarios-usgs/) | Landsat / NLCD / SRTM scenarios, same shape, plus its own [`GLOSSARY.md`](scenarios-usgs/GLOSSARY.md) for the USGS-specific vocabulary (Collection/Tier, surface reflectance vs. TOA, spectral indices, DEM voids). |
| `results/` | Your actual extracts, QGIS projects, screenshots, and write-ups, one subfolder per scenario across both sets. **Gitignored** — see below. |

## How a scenario works

Every file in `scenarios-s5p/` and `scenarios-usgs/` follows the same shape:

1. **Objective** — the question you're answering, framed the way a customer or
   mission owner would ask it, not the way a dataset ID would.
2. **Setup** — which catalog preset, dataset, band, AOI and time window to use.
3. **Steps** — what to click, in order.
4. **What to look for** — the signal that tells you whether the hypothesis
   holds, and the usual way to fool yourself.
5. **Why it matters** — the domain reason this is a real analytic move, not
   busywork.
6. **Deliverable** — what to save under `results/<scenario-slug>/` and in what
   form.

Work through each set roughly in order — later scenarios in a set (EO/IR or
archive-depth fusion, the customer brief) assume you've already got output
sitting in `results/` from the earlier scenarios in that same set. The two
sets are otherwise independent; run `scenarios-s5p/` and `scenarios-usgs/`
in either order, or interleave them.

## Keeping results out of git

`results/` is gitignored at the repo root
(`qgis-plugin-lab/results/` in the top-level `.gitignore`). Earth Engine
extracts, QGIS project files and screenshots get large fast and are fully
reproducible from the scenario instructions — none of it belongs in version
control. If a finding is actually worth keeping, promote the *write-up* (not
the raw data) into a "Findings" section at the bottom of the relevant
scenario file, the same way `notebooks/scratch/` promotes work into
`notebooks/`.

## Relationship to the plugin repo

This lab does not vendor or modify the plugin. It assumes `ee_s5p_plugin` is
checked out as a sibling of this repo (`../ee_s5p_plugin`) and symlinked into
your QGIS profile per `SETUP.md`, so edits made there are live here without a
rebuild. Bugs found while running a scenario belong in that repo's issue
tracker, not in this lab.
