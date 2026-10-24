# Reproducible case study

Seed 42, fixed 30 → 15 s: completed 130 → 132 of 160; completed-trip mean 158.8 → 159.9 s; full-demand loss 225.2 → 222.0 s/request. These are simulated outcomes, not measured Bangalore traffic.

Research: 266 actual simulations, conservative maximum 366, hard cap 370. Five conditions, ten held-out seeds each.

| Candidate | Completion % | Loss s/request | Bus mean s | Feasible |
|---|---:|---:|---:|---|
| Baseline | 76.01 | 244.62 | Unavailable | False |
| Candidate 738c | 76.70 | 241.39 | Unavailable | False |
| Candidate d48a | 75.29 | 247.57 | Unavailable | False |
| Candidate 738c · no-priority | 75.84 | 244.32 | Unavailable | False |
| Candidate d48a · no-priority | 76.01 | 244.62 | Unavailable | False |

## Adverse and inconclusive findings

- Baseline: Below minimum completion.
- Candidate 738c: Below minimum completion, Completion loss exceeds paired constraint.
- Candidate d48a: Below minimum completion, Completion loss exceeds paired constraint.
- Candidate 738c · no-priority: Below minimum completion, Completion loss exceeds paired constraint.
- Candidate d48a · no-priority: Below minimum completion.

## Paired held-out full-demand loss

| Candidate / condition | Mean difference s/request | 95% bootstrap interval | n |
|---|---:|---|---:|
| 738cca548f / uniform | -0.71 | -11.80 to 10.99 | 10 |
| 738cca548f / peak | -0.16 | -9.31 to 9.68 | 10 |
| 738cca548f / high_demand | -9.01 | -14.93 to -3.42 | 10 |
| 738cca548f / bus_mix | -7.75 | -18.90 to 3.54 | 10 |
| 738cca548f / disruption | 1.48 | -3.38 to 5.94 | 10 |
| d48a77c239 / uniform | 8.08 | -1.37 to 17.90 | 10 |
| d48a77c239 / peak | 4.83 | 0.04 to 10.25 | 10 |
| d48a77c239 / high_demand | 0.61 | -5.13 to 6.25 | 10 |
| d48a77c239 / bus_mix | 1.20 | -4.35 to 7.50 | 10 |
| d48a77c239 / disruption | 0.00 | 0.00 to 0.00 | 10 |
| 738cca548f-no-priority / uniform | 4.94 | -6.09 to 16.58 | 10 |
| 738cca548f-no-priority / peak | 9.03 | 0.74 to 16.87 | 10 |
| 738cca548f-no-priority / high_demand | -7.31 | -12.30 to -2.38 | 10 |
| 738cca548f-no-priority / bus_mix | -9.64 | -21.19 to 1.55 | 10 |
| 738cca548f-no-priority / disruption | 1.48 | -3.38 to 5.94 | 10 |
| d48a77c239-no-priority / uniform | 0.00 | 0.00 to 0.00 | 10 |
| d48a77c239-no-priority / peak | 0.00 | 0.00 to 0.00 | 10 |
| d48a77c239-no-priority / high_demand | 0.00 | 0.00 to 0.00 | 10 |
| d48a77c239-no-priority / bus_mix | 0.00 | 0.00 to 0.00 | 10 |
| d48a77c239-no-priority / disruption | 0.00 | 0.00 to 0.00 | 10 |

## Synthetic calibration

Selected demand 80; held-out interval count MAE 1.917, RMSE 2.401 vehicles over 8 simulations. The source is SUMO seed 9, not field measurements.

Reproduce with `CITYLAB_DATA=data-reproduction python -m scripts.build_demo`, then `python -m scripts.finalize_demo` with the same data root. Inspect the saved specification, manifests, frozen candidates, per-seed results and reports. Intervals are exploratory and not adjusted for multiple comparisons. Generated transit routes cross n11 and n21; the disruption condition closes a service-route edge, leaving that explicit service invalid instead of silently moving its stops.

## Prespecified controller ablation

The independent controller study runs movement pressure with 5 s priority, no-priority and no-downstream variants plus baseline across the same five conditions with ten held-out seeds. This is a declared mechanistic comparison, not selection using held-out results. It executed 208 additional runs. Multiplicity caveats apply across both studies.

| Controller variant | Completion % | Loss s/request | Feasible |
|---|---:|---:|---|
| Baseline | 76.01 | 244.62 | False |
| Candidate b7cc | 77.62 | 237.67 | False |
| Candidate b7cc · no-priority | 77.99 | 236.11 | False |
| Candidate b7cc · no-downstream | 78.95 | 233.16 | False |
