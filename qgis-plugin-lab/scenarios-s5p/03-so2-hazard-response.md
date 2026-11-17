# 03 · SO2 rapid-look for a hazard event

## Objective

Simulate a "zero-to-one" rapid-response data product: given a known
historical SO2-emitting event (a volcanic eruption, or a documented
industrial release), pull the plume, characterize its extent and evolution
over a few days, and write the kind of short, time-pressured brief a
disaster-response or aviation-safety customer would actually want.

## Setup

- Preset: **Sentinel-5P / TROPOMI**, dataset `COPERNICUS/S5P/OFFL/L3_SO2`.
- Pick a **real, documented event** you can look up independently (a named
  volcanic eruption with a known date is easiest to verify against). Use the
  eruption/release date as day zero.
- AOI: wide enough to catch plume transport over several days — bigger than
  you'd think; SO2 plumes move with wind, not just sit over the source.
- Time window: day zero through the following 3–5 days, pulled as a short
  sequence of single-day (or few-day) extracts rather than one long-window
  average — you want to see the plume move, not blur it into a smear.

## Steps

1. Extract SO2 for day zero and each following day in the window.
2. Load each day as its own layer, same palette, same fixed value range
   across all of them.
3. Step through the days (toggle layer visibility, or arrange as a small
   multi-panel layout) and note direction and rate of plume movement/decay.
4. Note which product latency tier (OFFL here) you're using, and what that
   means for how "live" this would be in an actual response — see
   [`GLOSSARY.md`](../GLOSSARY.md#sentinel-5p--tropomi) on OFFL vs. NRTI vs.
   RPRO.

## What to look for

- A plume that is spatially coherent on day zero and visibly advects
  (moves with wind) and dilutes over the following days — not just fades
  uniformly.
- Whether the plume's travel direction is physically plausible given what
  you can independently find out about wind conditions at the time (even a
  rough check is enough here).
- The point at which the signal drops back to background — that's your
  answer to "how long did this matter," which is usually the actual
  customer question.

## Why it matters

SO2 is both a volcanic-hazard signal (ash/gas plumes are an aviation
hazard) and an industrial-compliance signal (heavy fuel oil, smelting), and
its few-hour-to-day lifetime means it's genuinely time-critical in a way CH4
never is. This scenario is also where the **latency tradeoff** stops being
abstract: OFFL data is higher quality but arrives hours after the fact. If
this were a live response rather than a historical exercise, you'd need to
say explicitly whether a few hours of latency is acceptable for the decision
being made — which is exactly the kind of caveat a customer-facing product
brief has to be honest about.

## Deliverable

Save to `results/03-so2-hazard-response/`:

- The day-by-day extracts.
- A short animated-sequence screenshot set (or a single multi-panel image).
- A one-paragraph "incident brief": event, observed plume evolution,
  latency caveat, and the point at which you'd call it resolved.
