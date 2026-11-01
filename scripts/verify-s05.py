"""Reproducible real CLI + extracted-wheel smoke on synthetic local copies only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    results: dict[str, object] = {'evidence': 'actual_local_synthetic_fixture_execution'}
    with tempfile.TemporaryDirectory(prefix='data-optimizer-s05-smoke-') as temporary:
        root = Path(temporary)
        source = root / 'events with spaces.ndjson'
        source.write_bytes((repo / 'examples/s04-events.ndjson').read_bytes())
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        request = repo / 'examples/s05-conversion-request.json'
        artifacts = root / 'artifacts'

        def cli(arguments: list[str], expected: int = 0,
                environment: dict[str, str] | None = None) -> dict[str, object]:
            process = subprocess.run([sys.executable, '-m', 'data_optimizer.cli', *arguments],
                                     cwd=root, env=environment, capture_output=True,
                                     text=True, timeout=90, check=False)
            assert process.returncode == expected, (process.returncode, process.stderr)
            return json.loads(process.stdout)

        listing = cli(['candidate-list', str(source), '--request', str(request)])
        candidates = listing['candidates']
        assert isinstance(candidates, list)
        first = cli(['convert', str(source), '--request', str(request), '--root', str(artifacts)])
        count_before = len(list(artifacts.rglob('manifest.json')))
        again = cli(['convert', str(source), '--request', str(request), '--root', str(artifacts)])
        count_after = len(list(artifacts.rglob('manifest.json')))
        assert count_before == count_after == 6
        outcomes = first['outcomes']
        repeated = again['outcomes']
        assert isinstance(outcomes, list) and isinstance(repeated, list)
        assert all(o['status'] in ('reused', 'excluded') for o in repeated)
        results['input_sha256'] = before
        results['candidate_count'] = len(candidates)
        results['first_run'] = [{
            'format': o['configuration']['format'], 'codec': o['configuration']['codec'],
            'row_group_rows': o['configuration']['row_group_rows'],
            'partition_by': o['configuration']['partition_by'],
            'sort_by': o['configuration']['sort_by'],
            'status': o['status'], 'reasons': o['reasons'],
            'physical_bytes': o['manifest']['physical_bytes'] if o['manifest'] else None,
            'file_count': o['manifest']['file_count'] if o['manifest'] else None,
            'integrity_status': o['manifest']['integrity']['status'] if o['manifest'] else None,
            'workload_status': o['manifest']['integrity']['workload_status']
            if o['manifest'] else None,
            'conversion_seconds': o['manifest']['conversion_seconds'] if o['manifest'] else None,
            'peak_rss_kib': o['manifest']['peak_rss_kib'] if o['manifest'] else None,
        } for o in outcomes]
        results['repeat_statuses'] = [o['status'] for o in repeated]
        results['manifest_count_before_after_reuse'] = [count_before, count_after]
        selected = next(c['configuration'] for c in candidates
                        if c['configuration']['codec'] == 'zstd')
        configuration = root / 'configuration.json'
        configuration.write_text(json.dumps(selected))
        bad = root / 'negative-zero.ndjson'
        bad.write_text('{"value":-0.00}\n')
        bad_request = root / 'bad-request.json'
        req = json.loads(request.read_text())
        req.update(source={'format': 'ndjson'}, workload={})
        bad_request.write_text(json.dumps(req))
        failed = cli(['convert', str(bad), '--request', str(bad_request),
                      '--configuration', str(configuration), '--root', str(root / 'failed')], 1)
        results['semantic_loss_rejected'] = failed['outcomes'][0]['reasons']
        assert not list((root / 'failed').rglob('manifest.json'))
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        assert not list(artifacts.rglob('.partial-*'))
        results['source_unchanged'] = True
        results['unpublished_partials_remaining'] = 0
        # Exercise the packaged CLI + worker, without replacing the editable environment.
        package = root / 'wheel'
        wheel = repo / 'backend/dist/data_optimizer-0.1.0-py3-none-any.whl'
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(package)
        environment = dict(os.environ, PYTHONPATH=str(package))
        imported = subprocess.run([sys.executable, '-c',
                                   'import data_optimizer; print(data_optimizer.__file__)'],
                                  cwd=root, env=environment, check=True,
                                  capture_output=True, text=True)
        assert str(package) in imported.stdout
        wheel_result = cli(['convert', str(source), '--request', str(request),
                            '--configuration', str(configuration),
                            '--root', str(root / 'packaged-artifacts')], environment=environment)
        assert wheel_result['outcomes'][0]['status'] == 'validated'
        results['extracted_wheel_cli_and_worker'] = 'passed'
        results['engine_versions'] = wheel_result['outcomes'][0]['manifest'][
            'configuration']['context']['engine_versions']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n')
    print(f'S05 CLI, reuse, semantic rejection and packaged worker passed: {args.output}')


if __name__ == '__main__':
    main()
