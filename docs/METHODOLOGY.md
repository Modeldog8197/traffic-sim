# CityLab 2.0 methodology

## Question and experimental unit

Can a bounded road or signal intervention improve movement without concealing journeys or groups that become worse off? A **simulation run is the replicate**. Individual vehicles within one run are not independent experimental replications. Demand is generated, not observed unless an explicitly supplied observation dataset is fitted.

The engine is SUMO 1.27.1. Timestep is 0.5 s, position recordings nominally every 2 s plus an exact final sample for an odd horizon. The generation horizon and clearance sum to the evaluation horizon H. Origin, departure and class RNG streams are independently derived by SHA256 from the demand seed. SUMO dynamics use a separate seeded engine RNG.

## Matched comparison contract

The backend checks network content hash, exact manifest hash, horizon, warm-up, measurement version, SUMO engine version, routing policy and occupancy assumptions. The UI and paired exports use this same function. A mismatch suppresses numerical differences; export returns HTTP 409. Search uses the baseline's exact manifest for every candidate in a seed/condition block. Fixed service routes/stops and vehicle attributes remain identical unless service mix is the declared demand condition.

Routing is a static shortest-time assignment before departure on permitted directed roads; there is no en-route rerouting. Road closure removes candidate route edges, including endpoints. A fixed bus service is invalid if its saved route is blocked. Invalid demand remains in the denominator. Vehicle accounting at each step is:

`requested = scheduled + waiting-to-enter + active + completed + invalid + otherwise-unserved`.

At H, scheduled demand is zero. Teleportation is disabled. Collision warnings are retained as model-quality warnings; they do not silently remove demand.

## Metrics, censoring and units

- Completed travel time = arrival time minus **scheduled** departure, including insertion delay. Mean, median, p95, delay and bus mean use completed post-warm-up requests only. Delay subtracts an unedited free-flow reference; it is not field-measured delay.
- Completion rate = completed / all requested, including invalid and unfinished requests. Service accounting includes warm-up requests; outcome means/loss use the declared post-warm-up cohort.
- Full-demand loss for request i: completed travel time when completed; otherwise `(H - scheduled_departure_i) + H`. Report the cohort mean in s/request. The additional horizon is an explicit decision penalty, not an estimated future arrival. Unfinished travel times remain censored.
- Person loss weights that score by saved occupancy: default 1.5 people/car, 30 people/bus. Vehicle-weighted and person-weighted results are distinct.
- Queues count speeds <0.1 m/s on unique incoming lanes of each signal. Integrate at 0.5 s to vehicle-seconds. Shared controlled-lane references are deduplicated.
- SUMO `HBEFA3/PC_G_EU4` and `HBEFA3/Bus` emission classes provide mg/s rates. Integrate CO2 rate × 0.5 s, divide by 1,000,000 for kg; NOx divide by 1,000 for g. These are modelled tailpipe emissions. Always inspect completions alongside totals.
- OD/class tables retain requested/completed sample sizes; groups with fewer than ten requests are flagged. OD spread is maximum minus minimum full-demand group loss among groups with at least ten requests; unavailable with fewer than two eligible groups.
- Corridor cohorts use current assigned routes intersecting the selected edges. Rerouting can change group membership, so these are descriptive impacts rather than a fixed matched population. Edge-entry totals can count one vehicle on multiple edges.
- Explicit bus service defines ordered directed edges, lane-specific stop positions, dwell and headways or departure times. Stop vehicle-seconds describe scheduled vehicle stops; no passenger-waiting inference is made. Terminal headway summaries use completed services only and display n. Missing observations remain unavailable.

## Cyclic movement-pressure controller

Inspired by Varaiya (2013), *The max-pressure controller for arbitrary networks of signalized intersections*, Transportation Research Part C 36, 177–195. [Author's publications](https://people.eecs.berkeley.edu/~varaiya/publications.html), [related primary manuscript](https://connected-corridors.berkeley.edu/sites/default/files/Variants%20of%20Max%20Pressure%20Control%20for%20Signalized%20Intersections.pdf).

`getControlledLinks` maps each signal index to incoming/outgoing/via lane connections. CityLab groups each unique (incoming,outgoing) movement and retains all associated indices. A queued vehicle contributes to the movement matching its next assigned route edge; when multiple outgoing lanes match, its contribution is divided. Movement pressure = assigned incoming queue minus outgoing lane queue. Green-phase score sums unique served movements.

After minimum green, end the current green when another phase's score exceeds it by 0.5; otherwise retain it until maximum green. SUMO advances through the original cyclic phase order, yellow and all-red. No phase is jumped or invented. Every green has a finite maximum, yielding a cyclic service bound. The older responsive alternative compares deduplicated green-lane and opposing queue totals with a two-vehicle threshold.

Approaching buses on a served movement may defer a termination for at most the configured priority budget (0–10 s), subject to maximum green. Once that phase's budget is exhausted, it cannot be renewed until a phase change. Ordinary pressure-based retention can continue if a competing-pressure termination is no longer requested; this is distinct from a priority extension. `priority_used` is consumed budget, capped at the configured limit. Transition phases are never extended by priority.

This is a **cyclic pressure-gated adaptation**, not the published unconstrained max-pressure scheduler: it uses queue proxies and assigned routes, no calibrated saturation flows/turning fractions, no proof of stability, and fixed phase order. Decision logs expose movements, current/downstream queues, scores, phase age, action and safeguard. See [SUMO traffic-light retrieval](https://sumo.dlr.de/docs/TraCI/Traffic_Lights_Value_Retrieval.html) and [vehicle retrieval/units](https://sumo.dlr.de/docs/TraCI/Vehicle_Value_Retrieval.html).

## Finite intervention search and inference

Only permitted parameter dimensions vary: global/junction green durations, fixed/responsive/pressure controller, bounded priority, directed-road speeds or access. Exhaust a finite grid, or sample uniformly without replacement using the saved search seed. Always include the baseline and deduplicate identical configurations. A conservative upper bound is displayed before execution; the hard cap is validated by the backend. Candidate selection is deterministic, with feasibility first and the first selected objective as the training tie-break ranking. Other selected objectives define Pareto dominance.

Search uses training seeds and uniform demand. A shortlist is challenged on separate tuning seeds under peak demand; the shortlist and applicable priority/downstream ablations are frozen before held-out runs. Tuning is a reported challenge stage, not a second optimizer. All shortlisted candidates are evaluated even when tuning is adverse. Research requires at least ten held-out seeds per selected condition. Conditions: uniform, peak, 1.5× demand (capped at 2,000), larger bus share/shorter explicit-service headways, and a saved road disruption.

Service constraints apply **to every seed and condition**, not just pooled averages: minimum completion, maximum paired completion decrease and maximum invalid share. Only feasible evaluated candidates enter the Pareto frontier; unavailable objectives prevent ranking. Emissions or mean reductions due to non-completion cannot silently pass these guards.

Paired differences are candidate minus baseline, with per-seed values, sample SD, standardized paired effect (unavailable for zero SD), and deterministic 2,000-resample percentile bootstrap intervals for the mean. Overall candidate intervals first average conditions within each seed, avoiding treating reused seeds as independent samples. Condition-specific pairs are the primary inference. Intervals are exploratory, unadjusted for multiple comparisons and unreliable for tiny samples; quick mode is demonstrative. This is neither a global optimality proof nor citywide generalization.

## Calibration

CSV counts describe directed-road entries over half-open time intervals; optional speed is mean speed **at entry**, not time-mean link speed. Preserve raw observations and their content hash. Validate units/IDs, finite values, nonnegative integer counts, class overlap and interval overlap. Bound the demand/bus-share grid. Fit count MAE over early intervals and fitting seeds; save the selection before evaluating disjoint later intervals and held-out seeds. With explicit schedules, bus fraction is not a free parameter. Report observed/predicted scatter, residuals, count MAE/RMSE and coverage. Count coverage refers to evaluated measurement cells, not a probabilistic confidence interval. Speed coverage is the fraction of supplied speed cells with simulated entries. The supplied fixture is generated SUMO data, never a Bangalore measurement.

## Playback and events

Indexed gzip chunks contain 32 frames. Retrieval reads only relevant chunks; browser caches at most six chunks per map. Detailed position/control recordings are omitted for search; aggregate metrics remain. A selected v2 candidate or matched pair can be deterministically rerun with positions. Vehicles are processed in stable ID order; the rerun verifier allows at most 1e-9 absolute or 1e-12 relative numerical tolerance for historical floating-point sums, while counts and source manifests must match. Frame interpolation follows lane polylines and valid lane connections, including internal junction lanes; absent paths or missing samples hold the last observation. Vehicle appearance/disappearance follows observed frames. Visual interpolation never feeds the engine or metrics.

Events are computed from the run: saved closures at t=0; a new network approach-queue high when it exceeds the prior high by at least five vehicles; recovery when a sampled positive approach queue reaches zero; controller ends/priority decisions at frame sampling times. Full 0.5 s decisions are retained separately for detailed runs. Events are descriptive detectors, not independent causal findings.

## Geographic provenance and limitations

The offline synthetic 4×4 network has one lane per direction and left-hand traffic. Separately, the HSR OSM bbox was downloaded on 2026-09-25. Converted topology has 642 external directed roads and weak components of 320, 9 and 4 nodes. OSM/SUMO missing-attribute defaults and inferred signal settings are assumptions. The extract contains no demand or field validation. Attribution: © OpenStreetMap contributors, [ODbL](https://www.openstreetmap.org/copyright). Preserve source XML, hashes and conversion settings when redistributing.
