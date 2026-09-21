"""Execute only already frozen audit inputs that cannot duplicate stage-three calls.

Shares the audit API ledger under its exclusive process lock. The main audit
runner later scores these exact cached responses and fills shared inputs.
"""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path

from .runtime import API,digest,save

base=Path('results/development/progressive_search');out=base/'audit_dev'
with (out/'run.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if not (out/'results.json').exists():
        plans=json.loads((out/'frozen_interventions.json').read_text())
        selections=json.loads((base/'evaluation_dev/frozen_selections.json').read_text())
        shared={d['prompt_sha256'] for p in selections for d in p['methods'].values()}
        jobs={}
        for p in plans:
            if not p['applicable']:continue
            source=json.loads((out/f"case_{p['case']:03d}"/'authorized_source.json').read_text())
            conditions={**p['conditions'],'authorized':source['request']}
            for req in conditions.values():
                sha=digest(req)
                if sha in shared:continue
                for repeat in range(3):jobs.setdefault((sha,repeat),req)
        save(out/'early_reader_schedule.json',dict(source=Path(__file__).read_text(),input_repeats=[list(k) for k in jobs],rule='Only frozen audit inputs absent from every stage-three prompt; exclusive ledger lock'))
        api=API(out/'api',max_requests=450)
        def worker(item):
            (sha,repeat),req=item
            api.call(f'audit/{sha}/repeat{repeat}',req)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(worker,jobs.items()))
        print(json.dumps(dict(event='early_audit_reads_complete',input_repeats=len(jobs))),flush=True)
