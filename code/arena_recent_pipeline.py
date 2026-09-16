"""Finish the last development interface, then a fresh common evaluation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from arena_recent_memory import ARMS, ROOT
from arena_recent_report import audit_family


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', default='p2_recent_baselines_tokenrhythm_v5')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--env-port', type=int, default=8931)
    args = parser.parse_args()
    if Path(args.family).name != args.family or args.family in {'.', '..'}:
        parser.error('family must be a single directory name')
    dev = ROOT / 'results/development' / args.family
    real = ROOT / 'results/real' / args.family
    dev.mkdir(parents=True, exist_ok=True)
    state_path = dev / 'continuation_state.json'
    if state_path.exists():
        raise RuntimeError('Pipeline state already exists; inspect existing work before restarting')

    def state(stage, **extra):
        row = {'stage': stage, 'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), **extra}
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(row, indent=2) + '\n')
        temporary.replace(state_path)
        print(json.dumps(row), flush=True)

    def run(stage, command):
        state(stage, command=command)
        subprocess.run([sys.executable, *command], cwd=ROOT, check=True)

    def audit(base):
        report = audit_family(base)
        (base / 'usage_integrity_audit.json').write_text(json.dumps(report, indent=2) + '\n')
        return report

    try:
        run('running_lightmem_development', ['code/arena_recent_suite.py', '--phase', 'development',
            '--family', args.family, '--arms', 'lightmem', '--workers', '1', '--env-port', str(args.env_port)])
        cohorts = {a: ('p2_recent_baselines_tokenrhythm_v2' if a in ('noGcompact','mem0','amem') else
                       args.family if a == 'lightmem' else 'p2_recent_baselines_tokenrhythm_v3') for a in ARMS}
        reports = {name: audit(ROOT / 'results/development' / name) for name in set(cohorts.values())}
        manifests = {}
        for arm, name in cohorts.items():
            base = ROOT / 'results/development' / name
            observed = reports[name]['arms'][arm]
            if not observed['complete']:
                raise RuntimeError('Development gate ' + arm + ': ' + json.dumps(observed['issues']))
            protocol = json.loads((base / 'protocol.json').read_text())
            config = json.loads((base / 'configs' / (arm + '.json')).read_text())
            manifests[arm] = {'family': str(base.relative_to(ROOT)), 'episode_ids': [101],
                'protocol_sha256': hashlib.sha256((base / 'protocol.json').read_bytes()).hexdigest(),
                'config_sha256': hashlib.sha256((base / 'configs' / (arm + '.json')).read_bytes()).hexdigest(),
                'source_hashes': protocol['source_hashes'], 'task_specific': config['task_specific'], 'complete': True}
        if not all(m['task_specific'] == manifests['ours']['task_specific'] for m in manifests.values()):
            raise RuntimeError('Development configurations differ')
        manifest = {'schema': 'memoryarena-development-validation/v1', 'all_ten_interfaces_validated': True,
            'scope': 'Interface validation across transport repairs; no pooled development ranking.',
            'cohorts': manifests, 'evaluation_policy': 'All ten arms run freshly under one common frozen protocol.'}
        (dev / 'development_validation_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        run('development_validated_updating_budget', ['code/arena_recent_budget.py'])
        run('freezing_evaluation', ['code/arena_recent_suite.py', '--phase', 'evaluation', '--family', args.family,
                                  '--freeze', '--env-port', str(args.env_port)])
        protocol = json.loads((real / 'protocol.json').read_text())
        for name, digest in protocol['source_hashes'].items():
            if name.startswith(('upstream_commit:', 'embedding:')):
                continue
            source = ROOT / name
            if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Source changed after freeze: ' + name)
            target = real / 'frozen_source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        shutil.copy2(dev / 'development_validation_manifest.json', real / 'development_validation_manifest.json')
        run('running_paired_evaluation', ['code/arena_recent_suite.py', '--phase', 'evaluation', '--family', args.family,
            '--workers', str(args.workers), '--env-port', str(args.env_port)])
        if not audit(real)['paired_scope_complete']:
            raise RuntimeError('Evaluation integrity gate failed')
        run('official_scoring', ['code/arena_e2e_score.py', '--e2e_dir', str(real / 'e2e'), '--model', protocol['model'],
            '--arms', *ARMS, '--pairs', *['ours:' + a for a in ARMS if a != 'ours'], '--out', str(real / 'official_scores.json')])
        run('writing_offline_delivery', ['code/arena_recent_delivery.py', '--base', str(real)])
        state('complete', report=str(real / 'results.md'), audit=str(real / 'usage_integrity_audit.json'))
    except Exception as exc:
        state('stopped_for_review', error_type=type(exc).__name__, detail=str(exc)[:1600])
        raise


if __name__ == '__main__':
    main()
