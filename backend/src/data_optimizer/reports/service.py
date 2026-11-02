"""Deterministic exports from stored calculations, never generated executable prose."""

from __future__ import annotations

import html
import io
import re
import zipfile
from typing import Any

from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.profiling.models import fingerprint
from data_optimizer.reports.models import AssessmentBundle, ProfileCoverage, Provenance

LIMITATIONS = (
    "Measurements cover only the supplied input on the recorded local worker. Profile sampling "
    "does not establish full-dataset performance; metadata-only/startup guidance has no measured "
    "migration recommendation or historical savings.",
    "Typed load plus in-memory queries; OS cache uncontrolled. Native scans, cloud latency, "
    "concurrency, throughput and production tail latency remain unvalidated.",
    "Costs are forecasts, not invoices or realized savings. Synthetic prices are invented; "
    "user-supplied prices are unverified. Missing amounts remain Unknown. Fixed capacity must "
    "actually change to yield cash savings.",
    "Supported tariffs are flat linear rates with recorded minimums. Tier/free allowances, tax, "
    "FX, calendar proration, nonlinear growth and mixed-region allocation are unsupported.",
    "Search is bounded and may stop early; best tested feasible does not imply global optimality. "
    "Rerun timings and timing-based costs or decisions can differ; inspect any disagreement.",
)


def redact(value: Any) -> Any:
    """Drop unnecessary user prose at typed narrative fields, including credential-bearing URLs.

    Required field names, literal predicates and schema settings cannot be removed without
    changing executable semantics. No runtime settings, signed URLs or raw records are inputs.
    """
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: redact(v) for k, v in value.items()}
    # Recognize typed narrative containers. Arbitrary schema mappings may have columns
    # named note/reference/assumption and must retain their original interpretation.
    omitted = "Omitted from portable export; consult original owned evidence."
    if value.get("kind") in {"synthetic", "assumption", "user_supplied", "local_measurement"}:
        if "reference" in value and "note" in value:
            result.update(reference=omitted, note=omitted)
    if "discount_assumption" in value and isinstance(value.get("source"), dict):
        result["discount_assumption"] = omitted
    if "assumption" in value and isinstance(value.get("prices"), dict):
        result["assumption"] = omitted
    if isinstance(value.get("rates"), list) and "currency" in value:
        for key in ("source_references", "assumptions"):
            result[key] = ["Omitted from portable export; see original snapshot fingerprint."]
    return result


def make_bundle(report: AssessmentReport, provenance: Provenance | None = None) -> AssessmentBundle:
    if report.report_fingerprint != fingerprint(
        report.model_dump(mode="json", exclude={"report_fingerprint"})
    ):
        raise ValueError("assessment_report_fingerprint_mismatch")
    profile = report.profile
    coverage = (
        ProfileCoverage.model_validate(
            {k: getattr(profile, k) for k in ProfileCoverage.model_fields}
        )
        if profile
        else None
    )
    bundle = AssessmentBundle(
        bundle_fingerprint="0" * 64,
        original_report_fingerprint=report.report_fingerprint,
        original_request_fingerprint=fingerprint(report.request.model_dump(mode="json")),
        provenance=provenance or Provenance(),
        evidence=report.evidence,
        input_fingerprint=report.candidates.input_fingerprint if report.candidates else None,
        request=redact(report.request.model_dump(mode="json")),
        profile=coverage,
        candidates=report.candidates,
        benchmark=report.benchmark,
        costs={k: redact(v.model_dump(mode="json")) for k, v in report.costs.items()},
        decision=redact(report.decision.model_dump(mode="json")),
        search_stop_reason=report.search.stop_reason if report.search else None,
        limitations=LIMITATIONS + report.decision.limitations,
    )
    return bundle.model_copy(
        update={
            "bundle_fingerprint": fingerprint(
                bundle.model_dump(mode="json", exclude={"bundle_fingerprint"})
            )
        }
    )


def read_bundle(data: bytes) -> AssessmentBundle:
    if len(data) > 67_108_864:
        raise ValueError("bundle_byte_quota")
    bundle = AssessmentBundle.model_validate_json(data)
    if bundle.bundle_fingerprint != fingerprint(
        bundle.model_dump(mode="json", exclude={"bundle_fingerprint"})
    ):
        raise ValueError("bundle_fingerprint_mismatch")
    return bundle


def display(value: object) -> str:
    return "Unknown" if value is None else str(value)


def render_markdown(bundle: AssessmentBundle) -> str:
    # Escape all dynamic Markdown punctuation and HTML, even when only an ID is expected.
    def safe(value: object) -> str:
        text = html.escape(display(value))
        for char in "\\`*_{}[]()#+!|>":
            text = text.replace(char, "\\" + char)
        return text.replace("\n", " ").replace("\r", " ")

    d = bundle.decision
    lines = [
        "# Data Optimizer engineering handoff",
        "",
        f"Schema: {bundle.version}",
        f"Bundle: {bundle.bundle_fingerprint}",
        f"Original report: {bundle.original_report_fingerprint}",
        "",
        "## Decision and requirements",
        "",
        f"Outcome: {safe(d.outcome)}",
        f"Selected candidate: {safe(d.selected_candidate_id)}",
        f"Reason: {safe(d.reason)}",
        f"Evidence: {safe(bundle.evidence)}",
        f"Search stopped: {safe(bundle.search_stop_reason)}",
        "",
        "The JSON bundle contains the executable requirements, tested candidate configurations, "
        "workload, raw trials, integrity checks, environment and price snapshots. "
        "Nested fingerprints identify the original evidence; see export redactions.",
        "",
    ]
    if d.next_questions:
        lines += ["Next questions:", ""]
        lines += [f"- {safe(question)}" for question in d.next_questions]
        lines += [""]
    if bundle.profile:
        p = bundle.profile
        lines += [
            "## Profile coverage",
            "",
            f"Rows: {p.row_count}; profiled: {p.profiled_rows}; "
            f"fraction: {p.sample_fraction}; sampling: {safe(p.sampling)}; "
            f"input physical bytes: {p.physical_bytes}.",
            "",
        ]
    if bundle.benchmark:
        matrix = bundle.benchmark
        lines += [
            "## Reproducibility references",
            "",
            f"Input fingerprint: {bundle.input_fingerprint}",
            f"Workload fingerprint: {matrix.workload_fingerprint}",
            f"Environment fingerprint: {matrix.environment_fingerprint}",
            f"Raw benchmark reference: {matrix.report_fingerprint}",
            f"Timed repeats requested: {matrix.request.repeats}; "
            f"benchmark stopped: {matrix.stop_reason}.",
            "",
        ]
        lines += [f"- {safe(k)}: {safe(v)}" for k, v in sorted(matrix.environment.items())]
        lines += [""]
    lines += [
        "## Tested candidates and costs",
        "",
        "All amounts below are copied from the stored calculations. Unknown is not zero.",
        "",
    ]
    for candidate in d.candidates:
        c = candidate.configuration
        lines += [
            f"### {safe(c.format)} / {safe(c.codec)}",
            "",
            f"Candidate: {candidate.candidate_id}; baseline: {c.baseline}; "
            f"feasibility: {safe(candidate.feasibility)}.",
            f"Observed local load + workload seconds: {display(candidate.workload_seconds)}.",
            f"Horizon total including migration: {display(candidate.horizon_total)}.",
            f"Target file bytes: {c.target_file_bytes}; row-group rows: {c.row_group_rows}; "
            f"partition columns: {safe(', '.join(c.partition_by) or 'None')}; "
            f"sort columns: {safe(', '.join(c.sort_by) or 'None')}.",
            "",
        ]
        for coverage in candidate.coverage:
            lines += [
                f"- {safe(coverage.requirement)}: {safe(coverage.status)}; {safe(coverage.reason)}"
            ]
        costs = candidate.costs
        if costs:
            lines += [
                "",
                f"Scenario: {safe(costs.name)}; currency: {costs.currency}; "
                f"price snapshot: {costs.price_snapshot_id}.",
            ]
            scopes: tuple[str, ...]
            if c.baseline:
                lines += [
                    f"Baseline monthly: {display(costs.baseline.total)}; "
                    "one-time migration: 0 (retain baseline). "
                    "Savings, payback and migration peak are not applicable "
                    "to keeping current."
                ]
                scopes = ("baseline",)
            else:
                lines += [
                    f"Baseline monthly: {display(costs.baseline.total)}; "
                    f"candidate monthly: {display(costs.candidate.total)}; "
                    "One-time migration forecast: "
                    f"{display(costs.migration_forecast.total)}.",
                    f"Monthly savings: {display(costs.monthly_savings)}; "
                    f"horizon net savings: {display(costs.horizon_net_savings)}; "
                    f"payback months: {display(costs.payback_months)}.",
                    f"Peak migration bytes (baseline + candidate + extra scratch): "
                    f"{display(costs.space.migration_peak_bytes)}.",
                ]
                scopes = ("baseline", "candidate", "migration_forecast")
            lines += [
                "",
                "| Scope | Component | Quantity | Unit | Rate | Amount | Missing |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for scope in scopes:
                for item in getattr(costs, scope).items:
                    lines += [
                        "| "
                        + " | ".join(
                            safe(v)
                            for v in (
                                scope,
                                item.component,
                                item.quantity,
                                item.unit,
                                item.rate_amount,
                                item.amount,
                                "; ".join(item.missing_inputs) or "None",
                            )
                        )
                        + " |"
                    ]
            lines += [""]
    if bundle.request.cost_template:
        lines += ["## Price provenance", ""]
        for scenario in bundle.request.cost_template.scenarios:
            prices = scenario.prices
            lines += [
                f"- {safe(scenario.name)}: {safe(prices.source)} prices; "
                f"{safe(prices.provider)} / {safe(prices.region)} / {prices.currency}; "
                f"effective {prices.effective_at.isoformat()}; "
                f"retrieved {prices.retrieved_at.isoformat()}. "
                "Rates, units, minimums and discounts are in bundle.json. "
                "Synthetic means invented, never a provider quote."
            ]
    from data_optimizer.migration.service import instructions

    lines += ["", instructions(bundle), "", "## Coverage and limitations", ""]
    lines += [f"- {safe(line)}" for line in bundle.limitations]
    lines += ["", "## Privacy and evidence references", ""]
    lines += [f"- {safe(line)}" for line in bundle.redactions]
    return "\n".join(lines) + "\n"


def render_html(bundle: AssessmentBundle) -> str:
    # The exact human report is escaped, with no external dependencies or active content.
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Data Optimizer handoff</title>"
        "<style>body{max-width:76rem;margin:2rem auto;padding:1rem;"
        "font:16px/1.5 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        "<body><pre>"
        + html.escape(re.sub(r"\\([\\`*_{}\[\]()#+!|>])", r"\1", render_markdown(bundle)))
        + "</pre></body></html>"
    )


def export_files(bundle: AssessmentBundle) -> dict[str, bytes]:
    from data_optimizer.migration.service import migration_script

    return {
        "bundle.json": (bundle.model_dump_json(indent=2) + "\n").encode(),
        "report.md": render_markdown(bundle).encode(),
        "report.html": render_html(bundle).encode(),
        "migrate.sh": migration_script().encode(),
    }


def archive(bundle: AssessmentBundle) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, data in export_files(bundle).items():
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o600 << 16
            zipped.writestr(entry, data)
    return buffer.getvalue()
