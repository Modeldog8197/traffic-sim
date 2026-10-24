# A small HSR traffic study

Start with a specific question about one junction or short corridor, including connecting approaches. Record the network version and explicitly select directed roads. A street name may cover both directions; never guess the mapping.

1. Write the question, intervention, primary outcome and success criterion in Study. Review directions, turn permissions, signal plans, bus routes, occupancy and modelled classes. Lock criteria before evaluation; older runs are retrospective evidence.
2. Choose safe, lawful observation points and a documented method. Count entries at fixed points in nonoverlapping intervals. Preserve date, timezone, offset, direction, conditions and source. Reserve untouched validation periods before fitting; repeat across days to examine temporal variability.
3. Download the CSV template. The synthetic example copies authentic generated counts; its year-2000 dates are placeholders, never field dates.
4. Explicitly map each location to a directed model road. Leave uncertain mappings unresolved. Correct invalid nonblank road IDs in the CSV. Importing does not change the simulation.
5. Prepare local calibration. In Data lab select the exact dataset and network, the specified fitting end and validation start, and a sufficient scenario horizon. Inspect untouched validation errors and export that report. A fitted volume does not establish accurate junction dynamics.
6. Compare matched baseline/intervention runs, check unfinished demand and adverse groups, and challenge the proposal with independent seeds and demand conditions in Explorer. Freeze the study pair; export JSON with its planning brief.

## CSV fields

| Column | Meaning |
|---|---|
| `location_id` | Stable observation-point label; no personal identifiers |
| `road_id` | Known directed road; blank requires explicit mapping |
| `to_road_id` | Connected outgoing road for turning counts only |
| `date` | `YYYY-MM-DD`; split at midnight |
| `start_time`, `end_time` | `HH:mm:ss`, start inclusive / end exclusive |
| `timezone`, `utc_offset` | IANA zone, e.g. `Asia/Kolkata`, and `+05:30` |
| `metric` | `road_entries`, `entry_speed`, `turn_count`, `queue`, `signal_green` |
| `value`, `unit` | Nonnegative finite measurement; units below |
| `vehicle_class` | `all`, `passenger`, `bus`, `motorcycle`, `auto_rickshaw` |
| `direction` | Field direction cross-checked against the model |
| `method`, `source` | Collection technique and provenance |
| `period` | `calibration`, `validation`, `context` |
| `synthetic` | Explicit `true` for generated data, `false` for supplied field data |

Limits: 5 MB, 2,000 total attached rows, 500 characters per cell. Quoting supports commas, quotes and line breaks. Unknown roads, missing required values, invalid dates/zones/units/ranges, duplicate or overlapping intervals/classes are rejected. Measured zero is valid; unknown is not zero. Omit unknown measurements and explain coverage in notes.

## Supported uses

| Measurement | Unit | Model use |
|---|---|---|
| Road entries | `vehicles`, integer | Demand fitting or held-out checking |
| Mean entry speed | `m/s` | Held-out checking with matching positive count and period |
| Turning count | `vehicles`, integer | Context only; connected incoming/outgoing IDs required |
| Queue snapshot | `vehicles`, integer | Context only; document physical queue definition and sampling |
| Green duration | `s` | Context only; review valid signal phases manually |

Motorcycles and auto-rickshaws stay contextual because separate model classes are absent. An all-vehicle count may fit volume while misrepresenting mixed traffic; do not claim otherwise.

Calibration uses one date/zone at a time and rejects mixed synthetic/field sources. Fitting must end before validation begins across all roads. Count MAE is average absolute error in vehicles per interval; RMSE gives large errors more weight. Both include zeros without percentage division. Missing speed is unavailable. Queue counts, speeds and green timing do not share an interchangeable error measure.

A period labelled validation is reserved data, not proof of successful validation. Retain the actual Data lab report and its run IDs with the study. The brief reports attached observations and never claims field validity merely because a CSV was imported. Separate days and independent seeds measure different variability; vehicles in one run are not independent experiments.

## Resident records and operational review

The resident form records date, directed road, recurring period, problem type and a short description, labelled **Unverified local observation**. These are qualitative browser-local records exportable to CSV/JSON. Avoid names, contacts, plates, faces or identifying accounts. Nothing is sent to authorities.

Before proposing an operational change: obtain appropriate collection permissions, review network/signal safety with qualified local practitioners, collect real multi-period observations, establish held-out baseline performance, model local vehicle mix and bus occupancy, and investigate spillovers and pedestrian/cyclist effects. Synthetic examples do not supply these requirements or authorise changes.
