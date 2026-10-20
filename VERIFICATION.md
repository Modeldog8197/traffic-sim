# Release verification

Verified on macOS 15 / Apple Silicon, Python 3.12, SUMO 1.27.1 and Google Chrome. Raw measurements are in the JSON files beside this document.

## Actual checks

- **30 pytest tests passed**, including all original 14 checks; one upstream Starlette/AnyIO deprecation warning. Coverage includes migrations, stable rename/duplicate, accounting/units, comparison rejection, transit validation, protected transitions, bounded priority logs, seed separation/budgets, Pareto feasibility, calibration validation, frame pagination/concurrent legacy migration, cancellation, restart and interrupted-batch resume.
- Independent Python processes with different hash seeds produced identical test-run metrics and completed trips. Historical floating totals use a declared sub-nanounit rerun tolerance.
- **Five interpolation assertions passed**: lane geometry, valid connected paths, missing samples and unknown paths.
- **Real Chrome journey passed**, zero JavaScript page errors. Screenshots inspected at 1440×1000, 1024×768, 390×844 and 200% CSS zoom. Verified saves/rename/duplicate, immutable historical network, paired playback, explorer, calibration and reflow without horizontal page overflow.
- Additional Chrome checks passed: delayed stale responses, pressure-junction inspector, undo/redo and PDF export. Exact baseline/candidate playback reruns completed with matching source manifests and metrics. See browser/state and paired-rerun JSON records.
- Clean Python installation from `requirements.lock.txt` succeeded. TypeScript and Vite production build succeeded. A clean frontend install/build with pnpm 10.15.0 also passed, with esbuild explicitly permitted. Startup, bundled-recording retrieval and a real SUMO job passed from the extracted archive in the clean Python environment. The initial 10-second smoke-test deadline timed out on first startup; the bounded test deadline was increased to 60 seconds and the uninstrumented check passed.
- HSR conversion: **642 directed roads, 333 junctions, 11 signals**, three weak components. A real-SUMO smoke run completed **20/20 requests**, no warnings. This is execution verification, not field validation.
- Reports were generated from computations; every PDF page was rendered and visually inspected.
- **Docker was not executed:** unavailable on this host. Windows, production deployment, physical assistive-technology testing and city-scale performance were not exercised. Vite warns about the MapLibre-containing JS bundle (~1.22 MB before gzip); the build succeeds.

## Genuine recorded evidence

The intervention search executed **266 simulations**; a separate prespecified controller/priority/downstream ablation study executed **208**. Each uses ten held-out seeds per selected condition across uniform, peak, high demand, bus mix and disruption. Calibration executed eight simulations on explicitly synthetic observations.

Seed 42 example: completed 130 → 132 of 160; completed-trip mean 158.8 → 159.9 s; full-demand loss 225.2 → 222.0 s/request. Under the research constraints, no candidate, including the baseline, passes every service threshold. No feasible frontier is asserted. See `CASE_STUDY.md` for adverse and inconclusive findings.

## Performance: same documented inputs

Synthetic network, 48 directed roads, 1,000 requests, seed 42, 600 s demand + 180 s clearance, 0.5 s timestep. Single measurements, not a controlled multi-repetition benchmark. V2 changes RNG streams, transit semantics and recorded fields, so this is **not** an isolated algorithm-speed comparison. Other verification work may contribute contention.

| Measurement | V1 | V2 detailed | V2 aggregate |
|---|---:|---:|---:|
| Simulation wall time | 12.21 s | 29.00 s | 17.07 s |
| Trajectory bytes | 16,609,948 | 8,757,514 | 0 |
| Additional decision log | none | 13,045,649 bytes | 0 |
| 32-frame retrieval median | 26.15 ms | 62.60 ms | n/a |
| Python peak RSS | 47.76 MB | 164.20 MB | cumulative same-process peak |
| SUMO child peak RSS | not measured | 59.65 MB | 59.97 MB |

Detailed recording is slower and total detailed evidence is larger, despite a **47.3% smaller position trajectory**. Do not interpret trajectory savings as total-storage savings. Aggregate trials omit positions and full decision logs. Profiling found compression consumed 1.65 s of a 7.78 s profiled 160-request workload. Reducing gzip level lowered measured 1,000-request detailed time from 43.96 to 29.00 s, trading compression ratio for execution time.

For the **same expanded v2 payload**, the old whole-file reader pattern took 65.32 ms median, versus 62.60 ms indexed retrieval. The main benefit is bounded I/O and memory as recordings grow; no large retrieval speedup is established. Plain v2 NDJSON would be 40,017,775 bytes. See `benchmark-v2.json` and `engine-profile.txt`.

## Browser performance and memory scope

Same 1,000-request workload at simulation time 200 s, 1440×1000, six seconds of playback:

| Snapshot | V1 | V2 |
|---|---:|---:|
| Animation-frame gap median / p95 | 16.7 / 16.7 ms | 16.7 / 16.7 ms |
| Browser + renderer/helper RSS sum | 964.64 MB | 1,047.59 MB |
| JavaScript used heap | 31.68 MB | 49.89 MB |

These are process snapshots and scheduling intervals, not end-to-end memory peaks or interaction-latency measurements. Summed RSS may double-count shared pages. Python/child/browser measurements are separate, not synchronized totals. **No end-to-end memory reduction is claimed.** V2 caches at most six 32-frame windows per map and follows valid lane paths; v1 retained every downloaded frame.

## Material limitations

No Bangalore traffic observations were supplied. Demand and calibration fixtures are synthetic. Geographic defaults/inferred signals are unverified. Pressure control is a cyclic adaptation with no stability proof. Bus occupancy is assumed; passenger boarding/waiting is absent. Incomplete service makes some pooled bus means unavailable. No real-world operational recommendation follows from these experiments.
