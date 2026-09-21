"""Evaluate saved native memory outputs without repeating their construction."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .continuation_actor import write_once
from .paired_actor import CONFIG, run_jobs
from .room_actor import parse, report
from .structure_alignment import digest

MEMORY_MARKER = 'MEMORY RECORDS [kind,time,entity,value]\n'
QUESTION_MARKER = '\nQUESTION\n'


def replace_memory(messages, text):
    copied = [dict(message) for message in messages]
    before, memory_and_question = copied[1]['content'].split(MEMORY_MARKER, 1)
    _, question = memory_and_question.split(QUESTION_MARKER, 1)
    copied[1]['content'] = before + MEMORY_MARKER + text + QUESTION_MARKER + question
    return copied


def full_messages(actor, case):
    actor = Path(actor)
    manifest = json.loads((actor / 'manifest.json').read_text())
    entry = next(j for j in manifest if j['case'] == case and j['arm'] == 'full')
    return json.loads((actor / 'inputs' / f"{entry['prompt_sha256']}.json").read_text())


def prepare(args):
    actor = Path(args.actor)
    profiles = json.loads((actor / 'case_profiles.json').read_text())
    jobs, sources, truths = [], [], {}
    for profile in profiles:
        case = profile['case']
        truths[case] = profile['truth']
        for system in ['mem0', 'amem']:
            directory = Path(args.native) / system / case
            status = json.loads((directory / 'status.json').read_text())
            if status['status'] != 'completed':
                directory = Path(args.recovery) / system / case
                status = json.loads((directory / 'status.json').read_text())
            if status['status'] != 'completed':
                raise RuntimeError(f'Unresolved native execution: {system}/{case}')
            path = directory / 'memory_output.json'
            output = json.loads(path.read_text())
            messages = replace_memory(full_messages(actor, case), output['text'])
            sha = digest(messages)
            sources.append(dict(case=case, system=system, path=str(path),
                                file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                characters=len(output['text']), empty=not bool(output['text']),
                                prompt_sha256=sha))
            for mode in ['enabled', 'disabled']:
                for repeat in range(3):
                    jobs.append(dict(case=case, arm=f'{system}_native8', mode=mode,
                                     repeat=repeat, messages=messages, prompt_sha256=sha,
                                     job_id=digest([case, system, mode, repeat, sha, 'room_native_v1'])))
    write_once(Path(args.out) / 'native_sources.json', sources)
    return truths, jobs


def main(args):
    truths, jobs = prepare(args)
    if args.prepare:
        print(json.dumps(dict(jobs=len(jobs), cases=len(truths))))
        return
    if args.report:
        report(args.out)
        return

    def scorer(job, text):
        ok, answer = parse(text)
        return dict(correct=ok and answer == truths[job['case']], parse_ok=ok, answer=answer)

    config = {**CONFIG, 'workers': 6, 'stage': 'room_native_v1',
              'shuffle_seed': 2026092204, 'seed_panel': list(range(6100, 6104)),
              'source_sha': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol': 'docs/observed-memory-next-protocol-2026-09-22.md',
              'budget_scope': 'Native top8 entries, not matched records or tokens'}
    run_jobs(args.out, jobs, scorer, args.key_file, config)
    report(args.out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--actor', default='results/development/hm3/room_actor_v1')
    p.add_argument('--native', default='results/development/hm3/room_native')
    p.add_argument('--recovery', default='results/development/hm3/room_native_recovery')
    p.add_argument('--out', default='results/development/hm3/room_native_actor_v1')
    p.add_argument('--key-file', default='api/api.txt')
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--report', action='store_true')
    main(p.parse_args())
