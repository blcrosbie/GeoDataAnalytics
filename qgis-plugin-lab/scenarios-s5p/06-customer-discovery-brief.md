# 06 · Customer discovery: packaging a finding as a product brief

## Objective

Everything so far has been analysis. This scenario is the other half of the
JD: "support customer discovery and engagement efforts, translating
operational pain points and needs into technical requirements and derived
data solutions" and "support creation of technical proposals and white
papers that articulate the differentiation and mission utility."

Take one or two completed scenarios from this lab and write them up as a
one-page brief aimed at a **named, hypothetical end user** — not a lab
report aimed at yourself.

## Setup

No new extraction. Pick a result you already have in `results/` (methane
screening, activity monitoring, hazard response, or the tasking cue
scenario all work) and invent a specific, plausible customer for it:

- A midstream oil & gas operator (for scenario 01).
- A port authority or environmental regulator (for scenario 02).
- A disaster-response or aviation-safety office (for scenario 03).
- An imagery tasking/collection manager (for scenario 04).

Naming a specific, plausible customer — rather than writing for a generic
reader — is itself part of the exercise. The brief should read differently
depending on who's reading it.

## Steps

1. Write one paragraph: **the pain point**. What decision is this customer
   trying to make, and why can't they make it well today?
2. Write one paragraph: **the data product**. What you pulled, at what
   cadence and resolution, and what it shows — in plain language, not
   dataset IDs.
3. Write one paragraph: **the honest limitation**. Resolution, revisit
   cadence, latency, or confidence caveat that a technically sophisticated
   customer would ask about if you didn't mention it first.
4. Write one paragraph: **the recommended next step**. What would you build
   or task next to close the gap between "interesting signal" and
   "operational product" — a finer sensor, a longer baseline, an automated
   recurring feed, a different AOI.

Keep the whole thing to roughly one page. A brief that needs three pages to
make its point usually hasn't decided what its point is.

## What to look for

- Whether you can explain the finding without any jargon from
  [`GLOSSARY.md`](../GLOSSARY.md) leaking in unexplained — if a term from
  there is load-bearing to the argument, define it inline in one clause.
- Whether the limitations paragraph is genuinely honest, or a token caveat
  that doesn't actually constrain the claim being made above it.
- Whether the "next step" is something a customer could actually fund or
  decide on, not just "do more research."

## Why it matters

This is the gap between being a capable analyst and being useful to a
business: the same finding, written for the wrong reader or without naming
its own limits, either gets ignored or gets oversold. Both failure modes
show up constantly in early-stage, "zero-to-one" product work, which is
exactly the operating mode the JD describes — hypothesize, prototype,
engage a customer, repeat, before any of it is a mature pipeline.

## Deliverable

Save to `results/06-customer-discovery-brief/`:

- `brief.md` — the one-page write-up itself.
- Optionally, the one or two screenshots from the source scenario that the
  brief references.
