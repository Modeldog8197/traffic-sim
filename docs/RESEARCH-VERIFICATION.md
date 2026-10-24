# Current verification

This file covers the neighbourhood research update. Original `docs/VERIFICATION.md` and `v2-*` outputs describe the prior release.

## Inspection baseline

Source ZIP SHA-256: `239b182793c7379b7e292689b6cc901e1e3797dd528f220495a11abb5591e6db`. All 2,578 manifest-listed files matched before changes. The original 30 Python tests, five interpolation checks, TypeScript/Vite build, browser journey and genuine SUMO smoke simulations passed. The HSR network has 642 directed roads, 333 junctions, 11 signals and three weak components. The original HSR smoke completed 20/20 requests over a 60-second departure period plus 600-second clearance. This checks execution, not field validity.

## Current checks

Verified on 24 October 2026, Linux, Python 3.12.14, Node 24.19.0, pnpm 10.15.0 and Chromium:

- **33 Python tests passed**, including genuine SUMO integration, routing/closures, calibration and missing-result regressions.
- **25 TypeScript tests passed**: CSV parsing/mapping/ranges/time zones, zero/missing values, duplicate/overlap rejection, held-out separation, local persistence, immutable history, digest verification, compatibility and report accuracy.
- **Five lane/interpolation checks passed**; TypeScript and Vite production builds passed for the local and `/traffic-sim/` static configurations.
- **Both browser journeys passed**: recorded example; new connected study; lock, duplicate, edit, save, reopen and import; valid CSV import and invalid-unit rejection; immutable snapshots; paired map playback and keyboard seeking; selected road inspector; Explorer and held-out calibration history; HTML brief download and PDF printing; direct hash navigation; desktop and 390px mobile without horizontal page overflow.
- Static journey: **zero `/api/` requests, console/page errors or broken HTTP requests**. Full local journey: no console/page errors or broken requests. Native labelled inputs, keyboard controls and visible focus were checked; this is not a formal accessibility audit.
- Current-source HSR smoke: a new genuine SUMO run completed **20/20 requests**, horizon 660 s, no warnings. This low-demand execution check is not a realistic congestion calibration or local-impact finding.

Machine-readable evidence: [static browser](research-browser-static.json), [local browser](research-browser-local.json), [HSR smoke](research-hsr-smoke.json). Reviewed screenshots are in [screenshots](screenshots/). The printable brief was generated from the selected recorded study and checked against actual run IDs and metrics. No field measurements were created.

Browser checks found and corrected missing accessible select names and in-session hash navigation. A test-fixture omission was corrected before the final passing Python run. No failing assertions were disabled.

## Publication status

Authenticated GitHub account `Modeldog8197` was verified. The repository exists and history is preserved. Enabling Pages with the supplied integration returned HTTP 403 `Resource not accessible by integration`. An account with Pages administration permission must set repository Settings → Pages → Source to GitHub Actions. The configured target `https://modeldog8197.github.io/traffic-sim/` is not yet verified as published.

## Limits

No real HSR measurements, official adoption, operational effects or mixed-traffic validity were tested. Windows, macOS and a public Python/SUMO service are unverified. Browser checks use Chromium, desktop and 390px mobile; they are not a full accessibility audit or cross-browser certification. The MapLibre vendor bundle remains large. Python tests emit an upstream AnyIO/Starlette deprecation warning.
