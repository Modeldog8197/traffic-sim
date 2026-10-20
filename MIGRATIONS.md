# Storage and artifact migration

Back up the complete data directory before moving an existing installation. CityLab uses additive SQLite migration version 2: existing scenario/job tables and payloads remain; settings, tasks, observations and a migration log are added. Scenario schema 1 is read into schema 2 defaults in memory. Saving preserves its stable scenario ID; renaming never creates another row. Duplicate generates an independent ID.

Historical results are never recomputed silently. Missing result schema/measurement version is interpreted as v1. The comparison contract rejects v1/v2 measurement pairs. A legacy scenario can be edited into a new v2 experiment; it is not called an exact legacy rerun. Future scenario schemas are rejected.

Historical maps use result.network, never the currently selected draft network. New jobs copy both network.net.xml and network.json before execution. Renaming or switching draft networks cannot alter that snapshot. Missing records produce an explicit unavailable state, and missing saved baselines can be replaced.

Legacy frames.ndjson is converted once to 32-frame indexed gzip chunks on first retrieval; the original file remains. Incomplete trailing JSON is ignored rather than invented. New runs write atomic chunk/index updates. Do not copy a live data directory as a transactional backup; stop the local server first.

Queued/running/cancelling work is marked interrupted after restart. Batch checkpoints retain completed trial IDs and frozen candidates. Resume skips finished trials, reruns interrupted ones and publishes a report only after all planned work succeeds. Cancellation closes TraCI/SUMO; worker process groups and a parent-death watchdog prevent orphan SUMO subprocesses after server termination. At most two worker tasks run concurrently; each study executes trials serially. Each simulation has a 600-second wall-clock timeout.

Deletion requires exporting the run's evidence ZIP first. Study-owned runs cannot be deleted individually, protecting references. Keep or archive a whole study/data root together. This is a local research retention mechanism, not a secure audit or multi-user authorization system.
