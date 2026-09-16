"""Document a technical rerun of missing summary results under frozen v5 code.

The original interrupted batch remains immutable. A derived result view records
the source of every arm and is excluded from cumulative billing to avoid duplicates.
"""
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
from arena_recent_report import audit_family, read_events
from arena_recent_suite import source_hashes


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized_config(config):
    return {k: v for k, v in config.items() if k != 'output'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', default='p2_recent_baselines_tokenrhythm_v5')
    args = parser.parse_args()
    if Path(args.family).name != args.family or args.family in {'.', '..'}:
        parser.error('family must be a directory name')
    original = ROOT / 'results/real' / args.family
    protocol = json.loads((original / 'protocol.json').read_text())
    if protocol['source_hashes'] != source_hashes():
        raise RuntimeError('Generation sources differ from the frozen original')
    initial = audit_family(original)
    if [a for a in ARMS if not initial['arms'][a]['complete']] != ['summary']:
        raise RuntimeError('This recovery is restricted to the missing summary arm')
    if initial['arms']['summary']['completed_ids'] or (original / 'official_scores.json').exists():
        raise RuntimeError('Unexpected completed summary or prior official scoring')
    errors, _ = read_events(original / 'e2e/summary/llm_call_usage.jsonl')
    if not any(r.get('event') == 'api_error' and r.get('error_type') == 'RemoteProtocolError'
               for r in errors):
        raise RuntimeError('Original technical failure does not match the documented cause')

    amendment = {
        'schema': 'memoryarena-technical-recovery-amendment/v1',
        'registered_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'original_family': args.family, 'original_protocol_sha256': digest(original / 'protocol.json'),
        'original_batch_complete': False, 'missing_arm': 'summary', 'episode_ids': protocol['episode_ids'],
        'cause': 'Opened response stream interrupted during episode 111 round 5; no completed summary episode.',
        'maximum_additional_summary_attempts': 2,
        'selection_rule': 'First complete technical attempt, never selected by task score. Official scoring follows complete scope only.',
        'retry_scope': 'Fresh summary stores and all three episode IDs; no other arm regenerated.',
        'method_changes': None, 'source_hashes': protocol['source_hashes'],
        'allowed_config_difference': 'output paths only',
        'frozen_request_retry_policy_changed': False,
        'interpretation': 'Post-freeze technical recovery, not a claim that the original batch completed uninterrupted.',
        'billing': 'Every original and supplemental usage response counts; derived copied outputs do not count twice.',
    }
    amendment_path = original / 'recovery_amendment.json'
    with amendment_path.open('x') as handle:
        json.dump(amendment, handle, indent=2)
    state_path = original / 'recovery_state.json'

    def state(stage, **extra):
        row = {'stage': stage, 'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), **extra}
        temporary = state_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(row, indent=2) + '\n')
        temporary.replace(state_path)
        print(json.dumps(row), flush=True)

    try:
        selected = None
        for attempt in (1, 2):
            recovery = ROOT / 'results/real' / (args.family + '_summary_recovery_' + str(attempt))
            recovery.mkdir(exist_ok=False)
            shutil.copy2(original / 'protocol.json', recovery / 'protocol.json')
            shutil.copy2(amendment_path, recovery / 'recovery_amendment.json')
            # Verify the suite's template before it can issue a paid request.
            template = json.loads((ROOT / 'results/real/p2_compact_v3/configs/travel_query-ancestry-v3-heldout-111-120.json').read_text())
            template['agent'].update(base_url=protocol['endpoint'], model_name=protocol['model'])
            template['task_specific']['llm_transport'] = 'stream_accumulate'
            template['memory'].update(local_arm='summary', memory_system_name='recent-summary')
            template['env']['env_server_url'] = 'http://127.0.0.1:8931'
            expected = json.loads((original / 'configs/summary.json').read_text())
            if normalized_config(template) != normalized_config(expected):
                raise RuntimeError('Recovery template changes frozen summary parameters')
            state('running_summary_recovery', attempt=attempt, family=recovery.name)
            completed = subprocess.run([sys.executable, 'code/arena_recent_suite.py', '--phase', 'evaluation',
                '--family', recovery.name, '--arms', 'summary', '--workers', '1', '--env-port', '8931'], cwd=ROOT)
            report = audit_family(recovery)
            (recovery / 'usage_integrity_audit.json').write_text(json.dumps(report, indent=2) + '\n')
            if completed.returncode == 0 and report['arms']['summary']['complete']:
                selected = recovery
                break
            actor, _ = read_events(recovery / 'e2e/summary/llm_call_usage.jsonl')
            memory, _ = read_events(recovery / 'e2e/summary/memory_events.jsonl')
            failures = [r for r in actor + memory if r.get('event') in ('api_error', 'llm_error', 'metadata_error')]
            technical = {'RemoteProtocolError', 'APITimeoutError', 'APIConnectionError',
                         'ReadError', 'ReadTimeout', 'InternalServerError', 'RateLimitError'}
            if not failures or any(r.get('error_type') not in technical for r in failures):
                raise RuntimeError('Supplemental failure is not eligible for the registered transport-only rerun')
        if selected is None:
            raise RuntimeError('Registered summary recovery attempts exhausted')
        if source_hashes() != protocol['source_hashes']:
            raise RuntimeError('Frozen generation sources changed during recovery')
        actual = json.loads((selected / 'configs/summary.json').read_text())
        if normalized_config(actual) != normalized_config(expected):
            raise RuntimeError('Actual recovery parameters differ from original')

        view = ROOT / 'results/real' / (args.family + '_completed')
        view.mkdir(exist_ok=False)
        manifest = {'schema': 'memoryarena-paired-recovery-view/v1', 'state': 'building',
            'original_family': args.family, 'original_batch_complete': False,
            'post_freeze_technical_recovery': True, 'billing_aggregation': 'derived_view_excluded',
            'amendment': str(amendment_path.relative_to(ROOT)), 'amendment_sha256': digest(amendment_path),
            'original_protocol_sha256': digest(original / 'protocol.json'), 'arm_sources': {}}
        marker = view / 'result_view_manifest.json'
        marker.write_text(json.dumps(manifest, indent=2) + '\n')
        shutil.copy2(original / 'protocol.json', view / 'protocol.json')
        shutil.copy2(original / 'development_validation_manifest.json', view / 'development_validation_manifest.json')
        shutil.copytree(original / 'frozen_source', view / 'frozen_source')
        (view / 'configs').mkdir()
        for arm in ARMS:
            source = selected if arm == 'summary' else original
            source_dir = source / 'e2e' / arm
            target_dir = view / 'e2e' / arm
            shutil.copytree(source_dir, target_dir)
            shutil.copy2(source / 'configs' / (arm + '.json'), view / 'configs' / (arm + '.json'))
            hashes = {str(p.relative_to(source_dir)): digest(p) for p in source_dir.rglob('*') if p.is_file()}
            if any(digest(target_dir / p) != sha for p, sha in hashes.items()):
                raise RuntimeError('Copied artifact hash mismatch: ' + arm)
            manifest['arm_sources'][arm] = {'family': str(source.relative_to(ROOT)),
                'protocol_sha256': digest(source / 'protocol.json'),
                'config_sha256': digest(source / 'configs' / (arm + '.json')),
                'e2e_artifact_sha256': hashes}
        audited = audit_family(view)
        if not audited['paired_scope_complete']:
            raise RuntimeError('Completed view failed scope audit')
        manifest['state'] = 'complete'
        marker.write_text(json.dumps(manifest, indent=2) + '\n')
        state('official_scoring_completed_view', view=view.name)
        subprocess.run([sys.executable, 'code/arena_e2e_score.py', '--e2e_dir', str(view / 'e2e'),
            '--model', protocol['model'], '--arms', *ARMS, '--pairs', *['ours:' + a for a in ARMS if a != 'ours'],
            '--out', str(view / 'official_scores.json')], cwd=ROOT, check=True)
        state('writing_offline_delivery', view=view.name)
        subprocess.run([sys.executable, 'code/arena_recent_delivery.py', '--base', str(view)], cwd=ROOT, check=True)
        state('complete', report=str(view / 'results.md'))
    except Exception as exc:
        state('stopped_for_review', error_type=type(exc).__name__, detail=str(exc)[:1600])
        raise


if __name__ == '__main__':
    main()
