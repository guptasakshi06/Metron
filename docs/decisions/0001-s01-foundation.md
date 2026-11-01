# Decision 0001: S01 foundation choices

Date: 2026-11-02 (Asia/Kolkata)

## Runtime and tooling

- Keep Python 3.12 and constrain the project to the 3.12 minor for repeatable dependency resolution.
- Use Node.js 24.22.2 LTS because the installed Node 18 runtime is end-of-life and current Vite does not support it.
- Pin uv 0.13.6 for lock generation and setup. Bootstrap both Node and uv into ignored `.tools/`; do not modify system installations.
- Commit lockfiles for Python and npm. Package versions are resolved and recorded by those lockfiles.

## API and local infrastructure

- Keep one installable `data_optimizer` Python package for the API, CLI and later workers.
- `/health` reports process liveness only. `/ready` runs bounded real probes for PostgreSQL, Redis and MinIO; there is no database-table prerequisite in S01.
- Bind local infrastructure ports to loopback, pin image releases and keep data on named volumes. Use project name `data-optimizer-local` and default host ports 55432/56379/59000/59001 to avoid the existing local PostgreSQL and Redis services discovered during S01. The example credentials are development-only.
- Use a Vite proxy for browser-to-API development traffic. The browser renders real API results and dependency readiness, with no fabricated assessment data.

## Contracts and policy

- Use Pydantic v2 versioned immutable contracts with strict extra-field rejection, UUID identities, aware timestamps, unit-aware bounds, decimal financial inputs and explicit evidence provenance.
- Use canonical sorted JSON and SHA-256 for candidate-configuration fingerprints.
- Keep lifecycle states and recommendation outcomes as distinct enums. State transitions are explicit and terminal states cannot be reopened.
- Start with a 256 MiB raw cap, 1 GiB decompressed cap, 12 candidate cap, 5 repeat cap, 60-second query timeout, 15-minute assessment budget and 2 GiB memory budget. These are unmeasured defaults pending S06/S14 calibration.
- Keep `make demo` unavailable until the real profile-to-decision pipeline exists; fail clearly instead of returning placeholder output.

## Verification boundary

Docker CLI 29.1.3 and its daemon are available through approved escalation; the Compose v2 plugin is absent, so the installed legacy Compose 1.29.2 is selected automatically. Compose syntax and actual startup were verified on 2026-11-02. The source-built MinIO, PostgreSQL and Redis all reached healthy status, and the API readiness endpoint returned HTTP 200. The local workspace already has unrelated PostgreSQL and Redis containers on conventional ports, so this app uses alternate ports and a unique Compose project to avoid touching them.
