"""Read-only campaign watcher: health snapshots and terminal-scope reports.

Never dispatches, retries, cancels, or changes an API request. Generation and
strict scoring source remain frozen. A lock prevents two watcher instances.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def atomic(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def scope_state(base, cases):
    rows = []
    counts = Counter()
    for case in cases:
        path = base / 'cases' / case['key'] / 'case_state.json'
        state = json.loads(path.read_text()) if path.exists() else {}
        name = state.get('state', 'not_started')
        counts[name] += 1
        rows.append([case['key'], name, state.get('selected_attempt'), len(state.get('attempts', []))])
    fingerprint = hashlib.sha256(json.dumps(rows).encode()).hexdigest()
    return {'expected': len(cases), 'counts': dict(counts),
            'all_terminal': counts['complete'] + counts['failed'] == len(cases),
            'fingerprint': fingerprint}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--interval-seconds', type=float, default=300)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    base = args.base.resolve()
    mon = base / 'monitoring'
    mon.mkdir(exist_ok=True)
    lock = (mon / 'watcher.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    protocol = json.loads((base / 'protocol.json').read_text())
    core = json.loads((base / 'registered_core/protocol.json').read_text())
    state_path = mon / 'watcher_state.json'
    old = json.loads(state_path.read_text()) if state_path.exists() else {}
    state = {'pid': os.getpid(), 'started_at': time.time(), 'alive': True,
             'read_only_api_policy': True,
             'last_report_fingerprints': old.get('last_report_fingerprints', {}),
             'report_runs': old.get('report_runs', [])}
    scripts = ['autodl_campaign_watch.py', 'autodl_health_snapshot.py',
               'autodl_core_report.py', 'autodl_completion_report.py',
               'autodl_report.py', 'autodl_usage_coverage.py']
    state['source_sha256'] = {name: hashlib.sha256((ROOT / 'code' / name).read_bytes()).hexdigest()
                              for name in scripts}
    atomic(state_path, state)

    def run(script, label):
        source = ROOT / 'code' / script
        if hashlib.sha256(source.read_bytes()).hexdigest() != state['source_sha256'][script]:
            raise RuntimeError('Watcher source changed after launch: ' + script)
        log_path = mon / (label + '_' + str(time.time_ns()) + '.log')
        with log_path.open('x') as log:
            proc = subprocess.run([sys.executable, '-u', str(source), '--base', str(base)],
                                  cwd='/tmp', stdout=log, stderr=subprocess.STDOUT)
        return {'script': script, 'finished_at': time.time(), 'exit_code': proc.returncode,
                'log': str(log_path.relative_to(base))}

    try:
        while True:
            started = time.time()
            control = mon / 'watcher_control.json'
            if control.exists() and json.loads(control.read_text()).get('stop'):
                state['stop_reason'] = 'watcher_control.stop'
                break
            try:
                state['last_health_run'] = run('autodl_health_snapshot.py', 'health_command')
                if state['last_health_run']['exit_code']:
                    state['health_error'] = state['last_health_run']
                else:
                    state.pop('health_error', None)
                state['full'] = scope_state(base, protocol['cases'])
                state['core'] = scope_state(base, core['cases'])
                for label, scripts_to_run in [
                    ('core', ['autodl_core_report.py']),
                    ('full', ['autodl_completion_report.py', 'autodl_report.py', 'autodl_usage_coverage.py'])]:
                    scope = state[label]
                    if not scope['all_terminal'] or state['last_report_fingerprints'].get(label) == scope['fingerprint']:
                        continue
                    runs = [run(script, label + '_report') for script in scripts_to_run]
                    state['report_runs'].extend(runs)
                    # Exit 2 is the expected strict refusal for incomplete valid matrices.
                    if all(r['exit_code'] in (0, 2) for r in runs):
                        state['last_report_fingerprints'][label] = scope['fingerprint']
                state.pop('last_error', None)
            except Exception as exc:
                state['last_error'] = {'type': type(exc).__name__, 'message': str(exc)}
            state['updated_at'] = time.time()
            atomic(state_path, state)
            print(json.dumps({key: state.get(key) for key in ('updated_at', 'core', 'full', 'health_error', 'last_error')}), flush=True)
            if args.once:
                state['stop_reason'] = 'once'
                break
            # Brief polling permits a stop file to take effect without waiting a full cycle.
            deadline = started + args.interval_seconds
            while time.time() < deadline:
                if control.exists() and json.loads(control.read_text()).get('stop'):
                    break
                time.sleep(min(15, max(0, deadline - time.time())))
    finally:
        state.update(alive=False, stopped_at=time.time())
        atomic(state_path, state)


if __name__ == '__main__':
    main()
