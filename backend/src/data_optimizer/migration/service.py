"""Fixed commands and typed local reproduction, retaining the original source."""

from __future__ import annotations

import json
import platform
from pathlib import Path

from data_optimizer.candidates.generator import context
from data_optimizer.conversion.service import convert
from data_optimizer.optimization.assessment import assess
from data_optimizer.profiling.engine import input_digest
from data_optimizer.profiling.models import fingerprint
from data_optimizer.reports.models import AssessmentBundle
from data_optimizer.sandbox import docker


def instructions(bundle: AssessmentBundle) -> str:
    selected = next(
        (
            c
            for c in bundle.decision.candidates
            if c.candidate_id == bundle.decision.selected_candidate_id
        ),
        None,
    )
    reader = (
        "Use the selected configuration and manifest reader in bundle.json, including "
        "codec, exact schema, ordered parts, partition and sort settings"
        if selected
        else "No selected tested configuration"
    )
    return f"""## Prerequisites and deliberate migration

Use Python 3.12, this project's locked package and matching PyArrow/DuckDB versions.
Full assessment reproduction additionally requires Linux Docker/cgroup v2 and the recorded
immutable benchmark image (build locally with `make benchmark-image` in the matching checkout).
Use a private local source copy and a new empty workspace. Preserve the original source,
its fingerprint, all retained copies and a backup of the prior reader configuration.
Required reader support: {reader}. Never switch a transactional database on this evidence.
Check target reader support for decimals, null/missing fields, timestamps and codecs.
Budget peak space using the cost section; Unknown requires a separate estimate before migration.
Local output needs room for baseline plus all tested alternatives during assessment reproduction.

After extracting all files together, reproduce the full assessment:

```sh
data-optimizer reproduce ./bundle.json --source '/path/to/local source' \\
  --root /tmp/new-assessment --output /tmp/new-reproduction.json
```

Paths above are placeholders: supply your private source and new destinations as quoted arguments.
The command checks the input digest and engine versions before running, compares the outcome and
selected configuration, and records disagreement explicitly. Timing variation is expected.
For metadata-only/startup guidance no raw-data reproduction or migration is authorized by evidence.
For keep_current retain the current reader; for insufficient_evidence answer the missing questions.

Only for a tested change, create and validate a local candidate copy:

```sh
sh ./migrate.sh '/path/to/local source' /tmp/new-migration /tmp/new-migration-result.json
```

The script uses fixed package commands and positional arguments, never dataset/AI shell content.
Read the resulting manifest: it records the exact configuration, schema/reader, output files,
physical bytes and full semantic integrity evidence. Every canonical-content/multiplicity and
workload-result check must pass. The source remains unchanged. No reader is switched automatically.

## Canary and rollback

1. Save the prior reader configuration and original SHA-256; keep source and backup accessible.
2. Run the bundle's complete constrained workload against the new manifest parts. Local conversion
   already checks these results against the source, including declared tolerances and duplicates.
3. Before any real switch, replay representative queries in the actual target reader/environment;
   compare counts, null/missing semantics, decimals, timestamps and results. Measure that reader's
   latency/concurrency against your requirements; local worker timings cannot substitute for this.
4. A human may then direct a limited canary to the copy, retaining the previous reader configuration
   and source. Stop on any result/schema mismatch, missing part, integrity failure, unacceptable
   latency, higher cost, retention violation or unsupported reader behavior.
5. On a trigger, stop directing new canary reads to the copy. Restore the saved prior reader
   configuration pointing at the retained original; verify the original SHA-256 and rerun the same
   workload on it. Confirm normal reads and record the failed candidate/evidence IDs for review.
   Keep both copies for investigation and meet existing retention rules. These instructions perform
   no automatic deletion, production mutation, external transfer or source cleanup.
"""


def migration_script() -> str:
    # Entire template is static. Even filenames containing quotes/$()/backticks stay arguments.
    return """#!/bin/sh
set -eu
if [ "$#" -ne 3 ]; then
  echo "Usage: sh migrate.sh SOURCE NEW_WORKSPACE NEW_RESULT.json" >&2
  exit 2
fi
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec data-optimizer reproduce "$bundle_dir/bundle.json" --mode migration \\
  --source "$1" --root "$2" --output "$3"
"""


def reproduce(
    bundle: AssessmentBundle, source: Path, root: Path, *, migration: bool = False
) -> dict[str, object]:
    request = bundle.request
    if bundle.evidence != "local_assessment" or request.conversion is None:
        raise ValueError("guidance_has_no_executable_raw_evidence")
    if input_digest(source, request.conversion.source.max_raw_bytes) != bundle.input_fingerprint:
        raise ValueError("source_fingerprint_mismatch")
    configs = bundle.candidates.candidates if bundle.candidates else ()
    if not configs or any(c.configuration.context != context() for c in configs):
        raise ValueError("execution_context_mismatch")
    if bundle.benchmark:
        matrix = bundle.benchmark
        if matrix.workload_fingerprint != fingerprint(
            request.conversion.workload.model_dump(mode="json")
        ) or any(
            m.input_fingerprint != bundle.input_fingerprint
            or m.verification_request.workload != request.conversion.workload
            for m in matrix.manifests
        ):
            raise ValueError("workload_or_manifest_fingerprint_mismatch")
        if not migration:
            cpu_model = next(
                (
                    line.split(":", 1)[1].strip()
                    for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")
                ),
                "unavailable",
            )
            expected = {
                "image_id": docker.image_id(),
                "host_kernel": platform.release(),
                "host_machine": platform.machine(),
                "cpu_model": cpu_model,
                "docker_version": docker.control(["version", "--format", "{{.Server.Version}}"]),
            }
            if any(matrix.environment.get(k) != v for k, v in expected.items()):
                raise ValueError("benchmark_environment_mismatch")
    if root.exists() or root.is_symlink() or source.resolve().is_relative_to(root.resolve()):
        raise ValueError("new_workspace_required")
    if migration:
        if bundle.decision.outcome != "change":
            raise ValueError("only_tested_change_has_migration")
        chosen = next(
            (
                c
                for c in bundle.decision.candidates
                if c.candidate_id == bundle.decision.selected_candidate_id
            ),
            None,
        )
        if chosen is None or chosen.feasibility != "feasible" or chosen.configuration.baseline:
            raise ValueError("selected_configuration_not_verified_feasible")
        # Recheck against the actual report manifest, not only a selected label.
        original = (
            next((m for m in bundle.benchmark.manifests if m.key == chosen.candidate_id), None)
            if bundle.benchmark
            else None
        )
        if original is None or original.configuration != chosen.configuration:
            raise ValueError("selected_manifest_missing")
        result = convert(source, root, request.conversion, chosen.configuration)
        if result.manifest is None:
            raise ValueError("migration_conversion_or_integrity_failed")
        return {
            "version": "s12.1",
            "mode": "migration",
            "bundle": bundle.bundle_fingerprint,
            "outcome": result.model_dump(mode="json"),
            "source_preserved": input_digest(source, request.conversion.source.max_raw_bytes)
            == bundle.input_fingerprint,
            "production_reader_switched": False,
        }
    report = assess(source, root, request)
    expected_config = next(
        (
            c.configuration
            for c in bundle.decision.candidates
            if c.candidate_id == bundle.decision.selected_candidate_id
        ),
        None,
    )
    actual = next(
        (
            c.configuration
            for c in report.decision.candidates
            if c.candidate_id == report.decision.selected_candidate_id
        ),
        None,
    )
    matches = report.decision.outcome == bundle.decision.outcome and expected_config == actual
    return {
        "version": "s12.1",
        "mode": "assessment",
        "bundle": bundle.bundle_fingerprint,
        "matches_original_decision": matches,
        "comparison": "Timings and timing-derived forecasts may vary; inspect fresh evidence.",
        "original_outcome": bundle.decision.outcome,
        "report": json.loads(report.model_dump_json()),
        "source_preserved": input_digest(source, request.conversion.source.max_raw_bytes)
        == bundle.input_fingerprint,
    }
