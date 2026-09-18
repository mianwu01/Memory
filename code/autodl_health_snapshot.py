import argparse
import collections
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Record live health metadata without inspecting scores.')
parser.add_argument('--base', type=Path, required=True)
BASE = parser.parse_args().base.resolve()
(BASE / 'monitoring').mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT / 'code'))
from autodl_completion_report import classify_failure

now = time.time()
old_paths = sorted((BASE / 'monitoring').glob('health_*.json'))
old = json.loads(old_paths[-1].read_text()) if old_paths else {}
previous = old.get('time', now - 300)
states = collections.Counter()
api_errors = collections.Counter()
new_errors = collections.Counter()
recent_errors = collections.Counter()
transport_receipts = collections.Counter()
transport_failed_receipts = collections.Counter()
new_transport_failed_receipts = collections.Counter()
recent_transport_failed_receipts = collections.Counter()
last_429_receipt = None
lengths = collections.Counter()
tokens = collections.Counter()
new_durations = []
failed = []
llm = new_llm = core_terminal = core_complete = 0
scan_errors = []


def read_json_retry(path):
    for number in range(3):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            error_type = type(exc).__name__
            if number < 2:
                time.sleep(0.1)
    scan_errors.append({'path': str(path.relative_to(BASE)), 'error_type': error_type, 'read_attempts': 3})
    return None


for state_path in sorted(BASE.glob('cases/*/*/*/*/case_state.json')):
    state = read_json_retry(state_path)
    if state is None:
        continue
    states[state['state']] += 1
    core = state['arm'] in ('ours', 'noGcompact', 'query_only')
    core_terminal += int(core and state['state'] in ('complete', 'failed'))
    core_complete += int(core and state['state'] == 'complete')
    for attempt in state.get('attempts', []):
        folder = state_path.parent / attempt['directory']
        events = folder / 'events.jsonl'
        rows = []
        if events.exists():
            for line in events.read_text().splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append(row)
                event = row.get('event')
                when = row.get('time', 0)
                receipts = ((row.get('transport') or {}).get('attempts') or []) if event == 'llm' else ((row.get('attempts') or []) if event == 'api_error' else [])
                for receipt_index, receipt in enumerate(receipts):
                    status = receipt.get('status_code')
                    key = str((status, receipt.get('error_type')))
                    transport_receipts[key] += 1
                    if status != 200 or receipt.get('error_type'):
                        transport_failed_receipts[key] += 1
                        if when > previous:
                            new_transport_failed_receipts[key] += 1
                        if when > now - 300:
                            recent_transport_failed_receipts[key] += 1
                    if status == 429 and (last_429_receipt is None or when >= last_429_receipt['response_event_time']):
                        subsequent_seconds = sum(r.get('seconds', 0) or 0 for r in receipts[receipt_index + 1:])
                        subsequent_waits = sum(r.get('retry_wait_seconds', 0) or 0 for r in receipts[receipt_index:])
                        last_429_receipt = {'key': state['key'], 'attempt': attempt['directory'],
                                            'response_event_time': when, 'event': event,
                                            'attempt_index': receipt_index, 'request_duration_seconds': row.get('duration_seconds'),
                                            'attempt_time_upper_bound_from_remaining_logged_waits': when - subsequent_seconds - subsequent_waits}
                if event == 'api_error':
                    key = str((row.get('error_type'), row.get('status_code')))
                    api_errors[key] += 1
                    if when > previous:
                        new_errors[key] += 1
                    if when > now - 300:
                        recent_errors[key] += 1
                if event != 'llm':
                    continue
                llm += 1
                if when > previous:
                    new_llm += 1
                    if row.get('duration_seconds') is not None:
                        new_durations.append(row['duration_seconds'])
                if any(c.get('finish_reason') == 'length' for c in row.get('choices', [])):
                    lengths[row.get('phase')] += 1
                usage = row.get('usage') or {}
                tokens['input'] += usage.get('prompt_tokens', usage.get('input_tokens', 0)) or 0
                tokens['output'] += usage.get('completion_tokens', usage.get('output_tokens', 0)) or 0
                details = usage.get('completion_tokens_details') or usage.get('output_tokens_details') or {}
                tokens['reasoning'] += details.get('reasoning_tokens', 0) or 0
        status_path = folder / 'status.json'
        status = (read_json_retry(status_path) or {}) if status_path.exists() else {}
        if attempt.get('finished_at') and not status.get('complete'):
            failed.append({'key': state['key'], 'attempt': attempt['directory'],
                           **classify_failure(status, rows, attempt)})
old_failed = {(r['key'], r['attempt']) for r in old.get('failed_attempts', [])}
workers = []
other = []
max_pss = collections.defaultdict(float)
total_pss = 0
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        argv = (proc / 'cmdline').read_bytes().decode().split('\0')
        if len(argv) < 2 or 'python' not in argv[0]:
            continue
        script = next((a for a in argv[1:3] if str(ROOT / 'code') in a and a.endswith('.py')), '')
        if Path(script).name not in ('faithful_arena_run.py', 'faithful_locomo_validate.py', 'faithful_memory_validate.py'):
            continue
        out = argv[argv.index('--out') + 1] if '--out' in argv else ''
        item = {'pid': int(proc.name), 'script': Path(script).name, 'out': out}
        if str(BASE) not in out:
            other.append(item)
            continue
        pss = next(float(line.split()[1]) / 1024 ** 2 for line in (proc / 'smaps_rollup').read_text().splitlines() if line.startswith('Pss:'))
        item['pss_GiB'] = pss
        workers.append(item)
        total_pss += pss
        arm = argv[argv.index('--arm') + 1]
        max_pss[arm] = max(pss, max_pss[arm])
    except (OSError, ValueError, UnicodeError, StopIteration):
        continue
memavailable = next(line.split(':', 1)[1].strip() for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
protocol = json.loads((BASE / 'protocol.json').read_text())
result = {'time': now, 'campaign_elapsed_seconds': now - protocol.get('created_at', now),
          'window_seconds': now - previous, 'dispatch_limit': json.loads((BASE / 'dispatch_control.json').read_text())['workers'],
          'case_states': dict(states), 'core_terminal': core_terminal, 'core_complete': core_complete,
          'llm_calls': llm, 'new_llm_calls': new_llm, 'new_llm_calls_per_second': new_llm / max(1, now - previous),
          'api_errors': dict(api_errors), 'new_api_errors': dict(new_errors), 'last_300s_api_errors': dict(recent_errors),
          'transport_attempt_receipts': dict(transport_receipts),
          'transport_failed_attempt_receipts': dict(transport_failed_receipts),
          'new_transport_failed_attempt_receipts': dict(new_transport_failed_receipts),
          'last_300s_response_events_transport_failed_receipts': dict(recent_transport_failed_receipts),
          'last_observed_429_receipt': last_429_receipt,
          'transport_window_note': 'Attempt receipts have durations but no wall-clock timestamps. New/300s windows use the enclosing response/api_error event time. In-flight retries are not yet visible. Failed receipts overlap api_error events; do not add the two counts.',
          'length_responses_by_phase': dict(lengths), 'failed_attempts': failed,
          'new_failed_attempts': [r for r in failed if (r['key'], r['attempt']) not in old_failed],
          'live_workers': len(workers), 'other_api_workers': other, 'total_api_workers': len(workers) + len(other),
          'total_pss_GiB': total_pss, 'worker_pss_max_GiB': dict(max_pss), 'memavailable': memavailable,
          'loadavg': Path('/proc/loadavg').read_text().strip(),
          'new_llm_p50_seconds': statistics.median(new_durations) if new_durations else None,
          'new_llm_p95_seconds': sorted(new_durations)[min(len(new_durations)-1,int(len(new_durations)*0.95))] if new_durations else None,
          'token_usage': dict(tokens), 'scan_errors': scan_errors,
          'snapshot_note': 'Live metadata scan is not atomic; no scores inspected. Unreadable metadata is retried then listed in scan_errors, never treated as a completed case.'}
path = BASE / 'monitoring' / ('health_' + str(int(now)) + '.json')
temporary = path.with_suffix('.json.tmp')
temporary.write_text(json.dumps(result, indent=2) + '\n')
temporary.replace(path)
print(json.dumps({k:v for k,v in result.items() if k not in ('failed_attempts', 'worker_pss_max_GiB')}, indent=2))
print('saved', path)
