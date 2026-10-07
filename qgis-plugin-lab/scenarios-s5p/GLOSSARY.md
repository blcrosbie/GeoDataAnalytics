# Domain glossary — why these words matter

The scenarios assume this vocabulary. Skimming it first is faster than
hitting an unfamiliar term mid-scenario and guessing.

## Sentinel-5P / TROPOMI

- **TROPOMI** — the single instrument on the Sentinel-5 Precursor satellite:
  a push-broom UVN (ultraviolet-visible-near-infrared) and SWIR spectrometer.
  One instrument, many trace-gas products, because each gas absorbs light at
  known wavelengths and the instrument measures the whole spectrum.
- **DOAS (Differential Optical Absorption Spectroscopy)** — the retrieval
  technique behind these products: measure how much light at a gas's known
  absorption lines is missing from the spectrum reaching the satellite, and
  back out a column amount. You don't need the algorithm to use the data, but
  knowing it exists explains why products ship with heavy QA flagging —
  clouds, sun glint and surface brightness all corrupt the retrieval.
- **Column density vs. mixing ratio** — most S5P products report a *column*
  (total molecules in a vertical slice of atmosphere, e.g. mol/m²), not a
  ground-level concentration. CH4 is the exception, reported as a
  **column-averaged dry-air mixing ratio** (parts per billion) because it's a
  well-mixed background gas and absolute column amount alone isn't
  informative. Conflating a column with a surface concentration is the most
  common beginner mistake — it isn't what you'd breathe.
- **Tropospheric vs. total column** — some products (NO2 especially) offer
  both a total-column and a tropospheric-only value. Tropospheric is almost
  always what you want for human-activity questions — it excludes the
  stratospheric background that has nothing to do with what's happening on
  the ground.
- **OFFL vs. NRTI vs. RPRO** — offline (few-hour latency, full QA), near-real-time
  (faster, less QA), reprocessed (final, most consistent, slowest to arrive).
  The plugin's catalog entries make clear which you're looking at. Latency
  vs. quality is a real tradeoff to name explicitly in anything you'd hand to
  a customer, not something to gloss over.
- **Why gas choice matters**:
  | Gas | Typical atmospheric lifetime | What it's a proxy for |
  |---|---|---|
  | NO2 | hours | combustion activity, right now — traffic, power generation, industry |
  | SO2 | hours to ~1 day | volcanic degassing/eruption, heavy fuel oil, smelting |
  | CO | weeks | biomass burning, long-range transport of combustion |
  | CH4 | ~decade | long-lived, well-mixed — a single overpass tells you little about a single source without many repeat looks |
  | HCHO | hours | biogenic emissions (vegetation), some industrial VOCs |
  | O3 | variable (stratosphere: years; troposphere: days-weeks) | ozone layer condition; also a secondary pollutant at ground level |
  | Aerosol Index (UVAI) | — (qualitative index, not a gas column) | smoke, dust, volcanic ash — anything that absorbs UV light |

  Lifetime is the whole story: a short-lived gas tells you about *right now*
  near the source; a long-lived gas tells you about accumulated, mixed,
  global background. Picking the wrong gas for the question is a bigger
  error than any resolution or QA issue.

## EO/IR imagery

- **Electro-optical (EO)** — imaging in visible/near-infrared wavelengths,
  i.e. what the eye roughly sees plus a bit past red. Sentinel-2, Landsat's
  optical bands.
- **Infrared (IR) / thermal** — longer wavelengths past NIR. Thermal IR
  (Landsat's TIRS) measures emitted heat, not reflected light — useful for
  surface temperature, fire detection, industrial heat signatures, at night
  as well as day.
- **Multispectral vs. hyperspectral** — multispectral: a handful of broad
  bands (Sentinel-2: 13; Landsat: ~11). Hyperspectral: hundreds of narrow,
  contiguous bands, enough to resolve a material's full spectral signature
  rather than just sample a few points of it. Most free satellite EO data is
  multispectral; hyperspectral is still comparatively rare and higher-value.
- **Radiance vs. reflectance** — radiance is what the sensor actually
  measures (energy arriving at the detector); reflectance is radiance
  corrected for illumination geometry and atmosphere so the same surface
  reads the same value regardless of sun angle or season. "Surface
  reflectance" products have already had this correction done — prefer them
  over raw top-of-atmosphere radiance unless you have a specific reason not
  to.
- **Ground sample distance (GSD) / native resolution** — the size of one
  pixel on the ground. Sentinel-5P trace gases: ~5.5×3.5 km (post-2019) to
  ~7×3.5 km, coarse enough that one pixel can cover an entire industrial
  complex. Sentinel-2/Landsat EO bands: 10–30 m. That three-orders-of-magnitude
  gap is *why* fusing the two is interesting — atmospheric data tells you
  something anomalous happened somewhere in a multi-km cell; EO/IR imagery at
  the same place and time tells you what's actually there.
- **Revisit cadence** — how often a satellite reimages the same ground spot.
  S5P: daily, global. Sentinel-2: ~5 days (with both satellites). Landsat:
  16 days per satellite. A coarse-but-daily instrument and a fine-but-slow
  one are complementary for exactly this reason.

## GEOINT-adjacent analytic vocabulary

- **Pattern of life** — the normal, repeating rhythm of activity at a place
  (a facility's weekday/weekend cycle, a port's shipping schedule). You can't
  call something anomalous without first establishing what normal looks
  like — this is why scenarios ask for a time series, not a single date.
- **Activity-based intelligence** — inferring operational tempo or behavior
  from indirect signals (here, trace-gas emissions) rather than from direct
  observation of the activity itself. NO2 as a combustion proxy is a textbook
  example.
- **Change detection** — comparing the same location across two time
  periods to find what's different. The simplest and most defensible
  analytic move available, and the one every scenario here ultimately relies
  on.
- **Cueing** — using a coarse, cheap, frequent sensor to decide *where* to
  point a fine, expensive, rare one. This is the honest relationship between
  Sentinel-5P and EO/IR imagery: S5P can't resolve a single facility's stack,
  but it can tell you which ten facilities out of ten thousand are worth a
  tasking request.
- **Feasibility study / trade study** — before building a product: does the
  data actually support the hypothesis, at what cost, with what
  limitations, compared to what alternatives? A feasibility study that
  concludes "no, and here's why" is just as valuable as one that concludes
  yes — the scenarios ask you to write down the honest answer either way.

## H3 / tiling (plugin-specific)

- **H3 index** — a hierarchical hexagonal cell id. The plugin tiles
  requests too large for one Earth Engine call into H3 cells, picking the
  coarsest resolution that fits the request budget.
- **Resolution** — H3's zoom level; lower number = bigger cells. Res 4
  (~1,770 km²) suits a county-sized AOI; res 7 (~5.2 km²) suits a town. The
  plugin picks this for you by default — note it, don't fight it, unless a
  scenario says otherwise.

## Red flags to catch yourself on

- Reading a single overpass as a trend. One data point is a data point, not
  a pattern of life.
- Treating total column as if it were tropospheric (or vice versa) without
  checking which one the band you picked actually is.
- Drawing a conclusion from a CH4 snapshot the same way you would from NO2 —
  CH4's decade-long lifetime means a local snapshot mostly reflects global
  background, not a local source.
- Ignoring cloud fraction / QA flags and treating every retrieved pixel as
  equally trustworthy.
- Comparing two dates without checking both passed the same QA bar — a
  "disappeared" plume might just be a cloudy overpass, not resolved
  emissions.
- Presenting a coarse-resolution atmospheric anomaly as if it pinpoints a
  single building or stack. It doesn't — that's what the EO/IR cueing step
  is for.
