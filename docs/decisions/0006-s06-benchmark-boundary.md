# Decision 0006: bounded Docker trials over the typed workload path

Date: 2026-11-02 (Asia/Kolkata)

- Keep Python/PyArrow/DuckDB and the existing lock. Build a local Python 3.12.3 image from
  the recorded base digest and a hash-locked export of backend dependencies. Resolve the
  resulting image to an immutable ID per assessment; never implicitly pull at runtime.
- Use Docker cgroup v2, memory without swap, CPU quota/rlimit, bounded tmpfs, read-only
  mounts/root, output cap, unprivileged user and network none. Fail closed on unavailable
  effective controls. This replaces the S05 process-only boundary for benchmark execution.
- Snapshot only verified manifest parts. Preserve request/configuration/integrity lineage;
  recheck file hashes and candidate query-result fingerprints inside the container.
- Reuse the typed S04 loader, extracted into a shared function with a single budget across
  ordered parts. Measure full typed load and subsequent in-memory queries separately.
  Native file scans/pushdown are not implemented or inferred from these numbers.
- Randomize within repeat rounds using a recorded seed. Fresh/warm process labels always
  state that OS cache is uncontrolled, including pre-reading for hash checks. No cold claim.
- Preserve raw observations, unknown scanned bytes, null tail estimates and explicit failed
  or stopped trials. Summaries cannot make a failed candidate feasible or free. S08 owns
  ranking, and must respect this execution model and partial/failed coverage.
- Persist offline JSON now; authenticated storage/DB/queue, recovery and tenant admission
  remain S09. No API socket access, live cloud tests, production deployment or pricing.

Method, controls, commands and limitations: [benchmark method](../benchmark-method.md).
