"""Explicit adapter from S06 local sample evidence to labeled cost assumptions."""

from __future__ import annotations

import statistics
from decimal import Decimal, localcontext

from data_optimizer.benchmarking.models import BenchmarkReport
from data_optimizer.conversion.models import ConversionManifest
from data_optimizer.economics.models import ConfigurationCost, CostRequest, Quantity
from data_optimizer.pricing.models import Amount, Contract, Source
from data_optimizer.profiling.models import fingerprint


class ReplayAssumption(Contract):
    replays_per_month: Amount | None


def bind_benchmark(
    request: CostRequest,
    report: BenchmarkReport,
    candidate_key: str,
    replays_per_month: Decimal | None,
) -> CostRequest:
    """Bind measured data bytes, full replay duration and conversion CPU. Never scale bytes."""
    assumption = ReplayAssumption(replays_per_month=replays_per_month)
    report = BenchmarkReport.model_validate(report.model_dump())
    if (
        report.report_fingerprint
        != fingerprint(report.model_dump(mode="json", exclude={"report_fingerprint"}))
        or report.request_fingerprint != fingerprint(report.request.model_dump(mode="json"))
        or report.environment_fingerprint != fingerprint(report.environment)
    ):
        raise ValueError("benchmark_fingerprint_mismatch")
    manifests = {m.key: m for m in report.manifests}
    baselines = [m for m in report.manifests if m.configuration.baseline]
    if (
        len(manifests) != len(report.manifests)
        or len(baselines) != 1
        or candidate_key not in manifests
        or candidate_key == baselines[0].key
    ):
        raise ValueError("benchmark_requires_one_baseline_and_selected_alternative")
    baseline, candidate = baselines[0], manifests[candidate_key]
    for manifest in report.manifests:
        if manifest.manifest_fingerprint != fingerprint(
            manifest.model_dump(mode="json", exclude={"manifest_fingerprint"})
        ) or manifest.integrity.report_fingerprint != fingerprint(
            manifest.integrity.model_dump(mode="json", exclude={"report_fingerprint"})
        ):
            raise ValueError("benchmark_manifest_integrity_fingerprint_mismatch")
        if (
            manifest.input_fingerprint != baseline.input_fingerprint
            or manifest.request_fingerprint != baseline.request_fingerprint
            or manifest.integrity.workload_fingerprint != report.workload_fingerprint
            or manifest.integrity.workload_status != "passed"
        ):
            raise ValueError("incompatible_benchmark_lineage")
    if (
        baseline.integrity.baseline is None
        or candidate.integrity.candidate is None
        or baseline.integrity.baseline.content_fingerprint
        != candidate.integrity.candidate.content_fingerprint
    ):
        raise ValueError("equivalent_benchmark_content_required")
    logical = baseline.integrity.baseline.content_fingerprint
    ref = f"benchmark:{report.report_fingerprint}"

    def bind(config: ConfigurationCost, manifest: ConversionManifest) -> ConfigurationCost:
        trials = [t for t in report.trials if t.candidate == manifest.key]
        expected_queries = {q.query_id: q.candidate_fingerprint for q in manifest.integrity.queries}
        complete = (
            len(trials) == report.request.repeats
            and {t.repeat for t in trials} == set(range(report.request.repeats))
            and all(
                t.status == "passed"
                and t.observation
                and len(t.observation.queries) == len(expected_queries)
                and {q.query_id: q.result_fingerprint for q in t.observation.queries}
                == expected_queries
                for t in trials
            )
        )
        duration = None
        if complete and assumption.replays_per_month is not None:
            seconds = [
                Decimal(str(t.observation.load_seconds))
                + Decimal(str(t.observation.workload_seconds))
                for t in trials
                if t.observation
            ]
            duration = (statistics.median(seconds) * assumption.replays_per_month / 3600).quantize(
                Decimal("0.000000000001")
            )
        source = Source(
            kind="local_measurement",
            reference=f"{ref}/manifest:{manifest.manifest_fingerprint}",
            note="Measured sample data bytes only; "
            "metadata/copies/retention remain supplied assumptions. "
            f"Matrix stop reason: {report.stop_reason}; selected complete repeats: {complete}.",
        )
        compute_source = Source(
            kind="assumption",
            reference=ref,
            note=f"Monthly forecast: median typed load + in-memory workload seconds * "
            f"{assumption.replays_per_month} supplied replays/month / 3600. "
            "Assumes rates for active engine time; excludes startup, warmups and orchestration. "
            "No native scans/cloud/concurrency inference. "
            "Incomplete trials or unknown usage stay null.",
        )
        charges = tuple(
            c.model_copy(
                update={
                    "quantity": Quantity(
                        value=duration,
                        unit="compute_hour",
                        source=compute_source,
                    )
                }
            )
            if c.component == "query_compute" and c.basis == "usage"
            else c
            for c in config.recurring
        )
        return config.model_copy(
            update={
                "id": manifest.key,
                "footprint": config.footprint.model_copy(
                    update={
                        "logical_fingerprint": logical,
                        "data_file_bytes": tuple(a.physical_bytes for a in manifest.artifacts),
                        "data_source": source,
                    }
                ),
                "recurring": charges,
            }
        )

    scenarios = []
    with localcontext() as context:
        context.prec = 80
        for scenario in request.scenarios:
            conversion_source = Source(
                kind="assumption",
                reference=f"{ref}/manifest:{candidate.manifest_fingerprint}",
                note="One conversion forecast using S05 measured whole-worker CPU hours, "
                "including verification; assumes the conversion rate bills process CPU time. "
                "S05 process boundary differs from S06 containers. Not an actual provider charge.",
            )
            migration = scenario.migration.model_copy(
                update={
                    "forecast": tuple(
                        c.model_copy(
                            update={
                                "quantity": Quantity(
                                    value=(Decimal(str(candidate.cpu_seconds)) / 3600).quantize(
                                        Decimal("0.000000000001")
                                    ),
                                    unit="compute_hour",
                                    source=conversion_source,
                                )
                            }
                        )
                        if c.component == "conversion"
                        else c
                        for c in scenario.migration.forecast
                    )
                }
            )
            scenarios.append(
                scenario.model_copy(
                    update={
                        "baseline": bind(scenario.baseline, baseline),
                        "candidate": bind(scenario.candidate, candidate),
                        "migration": migration,
                    }
                )
            )
    return CostRequest.model_validate(
        request.model_copy(update={"scenarios": tuple(scenarios)}).model_dump()
    )
