"""Portable reports reconcile real saved evidence; exports never execute user prose."""

import hashlib
import json
import os
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from data_optimizer.migration.service import migration_script, reproduce
from data_optimizer.optimization.assessment import AssessmentReport
from data_optimizer.profiling.models import fingerprint
from data_optimizer.reports.service import (
    archive,
    export_files,
    make_bundle,
    read_bundle,
    render_html,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def saved_report():
    return AssessmentReport.model_validate_json(
        (ROOT / "docs/evidence/s11-measured-change-report.json").read_bytes()
    )


def test_export_preserves_metrics_and_necessary_evidence(saved_report):
    bundle = make_bundle(saved_report)
    assert read_bundle(bundle.model_dump_json().encode()) == bundle
    assert bundle.original_report_fingerprint == saved_report.report_fingerprint
    assert bundle.benchmark == saved_report.benchmark
    assert bundle.candidates == saved_report.candidates
    assert bundle.profile.sample_fraction == saved_report.profile.sample_fraction
    assert bundle.decision.selected_candidate_id == saved_report.decision.selected_candidate_id
    md = render_markdown(bundle)
    html = render_html(bundle)
    for candidate, original in zip(
        bundle.decision.candidates, saved_report.decision.candidates, strict=True
    ):
        assert candidate.horizon_total == original.horizon_total
        assert f"Horizon total including migration: {original.horizon_total}" in md
        assert str(original.horizon_total) in html
        if original.costs:
            assert candidate.costs.space == original.costs.space
            for scope in ("baseline", "candidate", "migration_forecast"):
                b = getattr(candidate.costs, scope)
                assert b.total == sum(i.amount for i in b.items) if b.total is not None else True
    assert bundle.request.conversion == saved_report.request.conversion
    assert bundle.request.policy == saved_report.request.policy
    for phrase in ("rollback", "Unknown", "concurrency", "synthetic", "Canary", "tariffs"):
        assert phrase.lower() in md.lower()
    assert archive(bundle) == archive(bundle)
    with zipfile.ZipFile(BytesIO(archive(bundle))) as z:
        assert set(z.namelist()) == set(export_files(bundle))
        assert z.read("bundle.json") == export_files(bundle)["bundle.json"]


def test_export_omits_narrative_secrets_but_keeps_typed_workload(saved_report):
    data = saved_report.model_dump(mode="json")

    def mark(value):
        if isinstance(value, dict):
            for key in value:
                if key in {"note", "reference", "assumption", "discount_assumption"}:
                    value[key] = "SECRET_SUMMARY_TOKEN"
                elif key in {"source_references", "assumptions"}:
                    value[key] = ["https://user:SECRET_SUMMARY_TOKEN@example.invalid/?token=secret"]
                else:
                    mark(value[key])
        elif isinstance(value, list):
            for child in value:
                mark(child)

    mark(data)
    data["report_fingerprint"] = fingerprint(
        {k: v for k, v in data.items() if k != "report_fingerprint"}
    )
    report = AssessmentReport.model_validate(data)
    bundle = make_bundle(report)
    assert "SECRET_SUMMARY_TOKEN" not in bundle.model_dump_json()
    assert bundle.request.conversion.workload == report.request.conversion.workload
    assert "may be sensitive" in render_markdown(bundle)


def test_html_and_markdown_do_not_activate_untrusted_text(saved_report):
    data = saved_report.model_dump(mode="json")
    data["decision"]["limitations"] = ["<script>alert(1)</script> [run](javascript:alert(1))"]
    data["report_fingerprint"] = fingerprint(
        {k: v for k, v in data.items() if k != "report_fingerprint"}
    )
    bundle = make_bundle(AssessmentReport.model_validate(data))
    assert "<script>" not in render_html(bundle)
    assert "<script>" not in render_markdown(bundle)
    assert "[run](javascript:" not in render_markdown(bundle)


def test_tampered_report_and_bundle_fail(saved_report):
    bad = saved_report.model_copy(update={"report_fingerprint": "0" * 64})
    with pytest.raises(ValueError, match="report_fingerprint"):
        make_bundle(bad)
    bundle = make_bundle(saved_report)
    data = bundle.model_dump(mode="json")
    data["decision"]["outcome"] = "keep_current"
    with pytest.raises(ValueError, match="bundle_fingerprint"):
        read_bundle(json.dumps(data).encode())


@pytest.mark.parametrize("mode", [False, True])
def test_wrong_source_rejected_before_workspace_creation(saved_report, tmp_path, mode):
    source = tmp_path / "different.ndjson"
    source.write_text('{"id":"different"}\n')
    with pytest.raises(ValueError, match="source_fingerprint_mismatch"):
        reproduce(make_bundle(saved_report), source, tmp_path / "work", migration=mode)
    assert not (tmp_path / "work").exists()


def test_engine_mismatch_rejected_before_work(saved_report, tmp_path, monkeypatch):
    import data_optimizer.migration.service as service

    monkeypatch.setattr(service, "context", lambda: None)
    with pytest.raises(ValueError, match="execution_context"):
        reproduce(make_bundle(saved_report), ROOT / "examples/s04-events.ndjson", tmp_path / "work")
    assert not (tmp_path / "work").exists()


@pytest.mark.parametrize("outcome", ["keep_current", "insufficient_evidence"])
def test_non_change_never_runs_migration(saved_report, tmp_path, outcome):
    bundle = make_bundle(saved_report)
    bundle = bundle.model_copy(
        update={"decision": bundle.decision.model_copy(update={"outcome": outcome})}
    )
    with pytest.raises(ValueError, match="only_tested_change"):
        reproduce(bundle, ROOT / "examples/s04-events.ndjson", tmp_path / "work", migration=True)
    assert not (tmp_path / "work").exists()


def test_static_script_passes_hostile_paths_as_exact_arguments(tmp_path):
    directory = tmp_path / "dir ' $(touch PWNED) `touch BAD` space"
    directory.mkdir()
    script = directory / "migrate.sh"
    script.write_text(migration_script())
    binary = tmp_path / "bin"
    binary.mkdir()
    stub = binary / "data-optimizer"
    stub.write_text("#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n")
    stub.chmod(0o700)
    paths = ["source ' \" $(touch PWNED) `touch BAD`\nline", "new work", "result.json"]
    result = subprocess.run(
        ["sh", str(script), *paths],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": str(binary) + ":" + os.environ["PATH"]},
        cwd=tmp_path,
        check=True,
    )
    args = json.loads(result.stdout)
    assert args == [
        "reproduce",
        str(directory / "bundle.json"),
        "--mode",
        "migration",
        "--source",
        paths[0],
        "--root",
        paths[1],
        "--output",
        paths[2],
    ]
    assert not (tmp_path / "PWNED").exists()
    assert not (tmp_path / "BAD").exists()


def test_cli_export_immutable_and_mismatch_error(saved_report, tmp_path):
    from data_optimizer.cli import main

    report = tmp_path / "original.json"
    report.write_text(saved_report.model_dump_json())
    directory = tmp_path / "export"
    main(["export", "--report", str(report), "--output-dir", str(directory)])
    original = hashlib.sha256(report.read_bytes()).hexdigest()
    with pytest.raises(SystemExit) as exit_info:
        main(["export", "--report", str(report), "--output-dir", str(directory)])
    assert exit_info.value.code == 2
    wrong = tmp_path / "wrong.ndjson"
    wrong.write_text("{}\n")
    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                "reproduce",
                str(directory / "bundle.json"),
                "--source",
                str(wrong),
                "--root",
                str(tmp_path / "work"),
                "--output",
                str(tmp_path / "result.json"),
            ]
        )
    assert exit_info.value.code == 2
    assert not (tmp_path / "result.json").exists()
    assert not (tmp_path / "work").exists()
    assert hashlib.sha256(report.read_bytes()).hexdigest() == original


def test_workload_mismatch_cannot_reuse_evidence(saved_report, tmp_path):
    bundle = make_bundle(saved_report)
    conversion = bundle.request.conversion
    changed = conversion.model_copy(
        update={"workload": conversion.workload.model_copy(update={"queries": ()})}
    )
    bundle = bundle.model_copy(
        update={"request": bundle.request.model_copy(update={"conversion": changed})}
    )
    with pytest.raises(ValueError, match="workload_or_manifest_fingerprint_mismatch"):
        reproduce(bundle, ROOT / "examples/s04-events.ndjson", tmp_path / "work")
    assert not (tmp_path / "work").exists()


def test_different_benchmark_image_rejected_before_work(saved_report, tmp_path, monkeypatch):
    from data_optimizer.sandbox import docker

    monkeypatch.setattr(docker, "image_id", lambda: "sha256:" + "f" * 64)
    monkeypatch.setattr(docker, "control", lambda _: "29.1.3")
    with pytest.raises(ValueError, match="benchmark_environment_mismatch"):
        reproduce(make_bundle(saved_report), ROOT / "examples/s04-events.ndjson", tmp_path / "work")
    assert not (tmp_path / "work").exists()


def test_scenario_guidance_cannot_claim_raw_reproduction(tmp_path):
    report = AssessmentReport.model_validate_json(
        (ROOT / "docs/evidence/s11-startup-report.json").read_bytes()
    )
    with pytest.raises(ValueError, match="guidance_has_no_executable_raw_evidence"):
        reproduce(make_bundle(report), ROOT / "examples/s04-events.ndjson", tmp_path / "work")
    assert not (tmp_path / "work").exists()


def test_redaction_preserves_columns_named_like_narrative_fields(saved_report):
    from data_optimizer.reports.service import redact

    names = (
        "note",
        "reference",
        "assumption",
        "discount_assumption",
        "source_references",
        "assumptions",
        "kind",
        "source",
        "prices",
        "rates",
        "currency",
    )
    options = saved_report.request.conversion.source.model_copy(
        update={"schema_overrides": {name: "string" for name in names}}
    )
    assert redact(options.model_dump(mode="json")) == options.model_dump(mode="json")
