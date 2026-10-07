# QGIS Plugin Lab — Earth Engine Catalog Query (`ee_s5p_plugin`)

A learning lab for driving [`ee_s5p_plugin`][plugin] the way an analyst would
actually use it, not the way its own test suite exercises it. The plugin repo
proves the tool works; this lab proves *you* can point it at a real question
and get a defensible answer out the other side.

[plugin]: https://github.com/blcrosbie/ee_s5p_plugin

The scenarios here are modeled on what a **Senior Applied Scientist, Geospatial**
role (EO/IR imagery, atmospheric remote sensing, feasibility studies,
prototype intelligence products, customer discovery) is actually asked to do
day to day — see [`scenarios/`](scenarios/) for the list. The point isn't to
memorize a job description; it's to use a real one as a filter for "is this
use case substantive, or a toy." Atmospheric trace-gas monitoring from
Sentinel-5P, cross-checked against EO/IR imagery and framed as a product
someone could hand to a customer, is substantive.

## Layout

| Path | What it is |
|---|---|
| [`SETUP.md`](SETUP.md) | One-time environment setup: QGIS, the Google Earth Engine plugin + account, and `ee_s5p_plugin` symlinked from its sibling repo for live development. |
| [`GLOSSARY.md`](GLOSSARY.md) | The remote-sensing and GEOINT vocabulary the scenarios assume, plus the "why" behind conventions that are easy to get subtly wrong (tropospheric vs. total column, revisit cadence, sensor lifetime). |
| [`scenarios/`](scenarios/) | One `.md` file per use case: objective, setup, steps, what to look for, why it matters, and what to save. |
| `results/` | Your actual extracts, QGIS projects, screenshots, and write-ups, one subfolder per scenario. **Gitignored** — see below. |

## How a scenario works

Every file in `scenarios/` follows the same shape:

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

Work through them roughly in order — later scenarios (EO/IR fusion, the
customer brief) assume you've already got output sitting in `results/` from
the earlier atmospheric ones.

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
