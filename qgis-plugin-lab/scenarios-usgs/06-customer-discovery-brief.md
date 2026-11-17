# 06 · Customer discovery: packaging a USGS-data finding as a product brief

## Objective

Everything so far in this set has been analysis. This scenario is the other
half of the JD: "support customer discovery and engagement efforts,
translating operational pain points and needs into technical requirements
and derived data solutions" and "support creation of technical proposals
and white papers that articulate the differentiation and mission utility."

Take one or two completed scenarios from this set and write them up as a
one-page brief aimed at a **named, hypothetical end user** — not a lab
report aimed at yourself. This mirrors the S5P lab's own customer-brief
scenario; do this one with a different, USGS-flavored customer so the two
briefs read genuinely differently rather than being the same template with
new nouns.

## Setup

No new extraction. Pick a result you already have in `results/` (land-cover
change screening, thermal activity monitoring, flood response, terrain
siting, or the archive-depth trend check all work) and invent a specific,
plausible customer for it:

- A county planning department or conservation land trust (for scenario
  01).
- A utility or industrial-site security office (for scenario 02).
- A county emergency-management office or a flood insurer (for scenario
  03).
- A ground-station or facilities-siting program office (for scenario 04).
- Any of the above, reframed around "how confident should we be in this
  trend" (for scenario 05).

Naming a specific, plausible customer — rather than writing for a generic
reader — is itself part of the exercise. The brief should read differently
depending on who's reading it, and differently from whatever customer you
picked in the S5P lab's version of this scenario.

## Steps

1. Write one paragraph: **the pain point**. What decision is this customer
   trying to make, and why can't they make it well today?
2. Write one paragraph: **the data product**. What you pulled, at what
   resolution and over what time span, and what it shows — in plain
   language, not dataset IDs or band names.
3. Write one paragraph: **the honest limitation**. Resolution, revisit
   cadence, classification accuracy, canopy bias, or cloud-availability
   caveat that a technically sophisticated customer would ask about if you
   didn't mention it first.
4. Write one paragraph: **the recommended next step**. What would you build
   or task next to close the gap between "interesting signal" and
   "operational product" — a finer-resolution image, parcel-level records,
   a radar sensor for cloud penetration, an automated recurring feed.

Keep the whole thing to roughly one page. A brief that needs three pages to
make its point usually hasn't decided what its point is.

## What to look for

- Whether you can explain the finding without any jargon from
  [`GLOSSARY.md`](../scenarios-usgs/GLOSSARY.md) leaking in unexplained — if
  a term from there is load-bearing to the argument, define it inline in
  one clause.
- Whether the limitations paragraph is genuinely honest, or a token caveat
  that doesn't actually constrain the claim being made above it.
- Whether the "next step" is something a customer could actually fund or
  decide on, not just "do more research."
- Whether this brief's limitations section names *different* caveats than
  the atmospheric-data version would — if every brief in both sets reads
  with the same hedge regardless of dataset, you haven't actually
  internalized what's specific to each data family.

## Why it matters

This is the gap between being a capable analyst and being useful to a
business: the same finding, written for the wrong reader or without naming
its own limits, either gets ignored or gets oversold. Doing this exercise
twice, once per data family, is also a check on whether you're writing from
genuine understanding of each dataset's tradeoffs or just filling in a
template — a planning-department brief about land-cover change and an
aviation-safety brief about an SO2 plume should not sound interchangeable.

## Deliverable

Save to `results/06-customer-discovery-brief/`:

- `brief-usgs.md` — the one-page write-up itself (named distinctly from the
  S5P set's `brief.md` if you're keeping both in the same `results/`
  folder).
- Optionally, the one or two screenshots from the source scenario that the
  brief references.
