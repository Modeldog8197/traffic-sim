# CityLab architecture

React → typed API utilities → FastAPI → SQLite lifecycle + immutable artifact folders → bounded worker processes → SUMO/TraCI.

Frontend: `App.tsx` coordinates draft/run/baseline selection. `hooks/state.ts` owns abortable resource reads, stable scenario editing history, job polling and bounded frame caching. `domain.ts` defines run/scenario/frame contracts. `MapPanel` draws WebGL layers; `interpolation.ts` follows saved lane connectivity. Editor, Inspector, Explorer, DataLab, AnalysisPanel and Charts are focused components. A draft, selected recorded run and persistent baseline are different state values. An async response is accepted only for its current resource key/version.

Backend boundaries: `models` versioned contracts; `network/imports` geography and observations; `demand/routing` reproducible trips and routes; `engine/controllers` simulation; `analysis/metrics/statistics/comparison` measurements; `frames` indexed playback; `explorer/calibration` bounded protocols; `store/api` durable lifecycle and routes; `exports` HTML/PDF/ZIP; `bootstrap` authentic offline examples.

SQLite records scenario IDs, job/task status, baseline settings and observation provenance. Each new run stores its scenario, network content, manifest, routes, engine version, application revision, aggregate measurements and optional positions/controller decisions. Frame chunk writes and experiment checkpoint writes are atomic replacements. Configuration/network hashes and model revisions make mismatched comparisons explicit.

No server-side trajectory cache retains all frames. A current 32-frame write buffer is bounded; reads touch requested chunks. Browser storage is bounded to six 32-frame windows per map. Aggregate search trials omit positions and decision files, retain interval series/group metrics and may be rerun deterministically with playback. JSON run results still contain all manifest/completed-trip/edge-entry observations; this can grow with demand and is deliberately bounded by scenario limits.

Local API workers are capped at two. Each worker creates a process group and monitors parent death. Cooperative cancellation reaches SUMO within five simulated seconds; shutdown escalates to group termination if necessary. Restart turns unfinished work into an explicit interrupted state. This design preserves the local single-user model; authentication, distributed queues and cloud deployment are outside scope.
