"""Bounded development controls and fresh authorized-source validation."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re

from .continuation_actor import write_once
from .observed_room import init, selection
from .paired_actor import CONFIG, load_rows, run_jobs
from .room_actor import parse
from .room_native_actor import full_messages, replace_memory
from .room_source_audit import belief, collect, load_model
from .structure_alignment import digest

SOURCE = 'living|kitchen|vertical'


def sensitivity_graph(model):
    """Only compare observed training-table rows, not the environment oracle."""
    graph = defaultdict(set)
    table = model['table']
    for (obj, room, bits), next_room in table.items():
        walls = sorted(model['incident'][room])
        assert len(bits) == len(walls)
        for i, wall in enumerate(walls):
            flipped = tuple(1 - value if j == i else value for j, value in enumerate(bits))
            alternate = table.get((obj, room, flipped))
            if alternate is not None and alternate != next_room:
                graph[obj, room].add(wall)
    return graph


def rotate_graph(graph, walls, shift):
    mapping = dict(zip(walls, walls[shift:] + walls[:shift]))
    return {key: {mapping[w] for w in values} for key, values in graph.items()}


def bm25(records, k):
    tokenize = lambda text: re.findall(r'[a-z0-9]+', text.lower())
    docs = [Counter(tokenize(json.dumps(record))) for record in records]
    query = set(tokenize('Where is mary at environment time 50?'))
    n = len(docs)
    average = sum(sum(doc.values()) for doc in docs) / max(1, n)
    df = Counter(term for doc in docs for term in doc)
    def score(i):
        doc = docs[i]
        return sum(math.log(1 + (n - df[term] + .5) / (df[term] + .5)) *
                   doc[term] * 2.5 / (doc[term] + 1.5 * (.25 + .75 * sum(doc.values()) / max(average, 1)))
                   for term in query if doc[term])
    indices = sorted(range(n), key=lambda i: (score(i), records[i][1], i), reverse=True)[:k]
    return [records[i] for i in sorted(indices, key=lambda i: (records[i][1], i))]


def safe_answer(parsed, answer, allowed):
    return answer if parsed and len(allowed) == 1 and answer == allowed[0] else None


def prepare(args):
    base, old = init(args.checkout, 'small-01', 120)
    model, graph = load_model(args.model, base)
    out = Path(args.out)
    profiles = json.loads((Path(args.actor) / 'case_profiles.json').read_text())
    truths = {p['case']: p['truth'] for p in profiles}
    jobs, plans, cases, tool_calls = [], [], [], []
    prior = {}
    if args.stage == 'controls':
        for row in load_rows(Path(args.actor) / 'ledger.jsonl'):
            if row['event'] == 'result':
                prior[row['case'], row['mode'], row['prompt_sha256'], row['repeat']] = row['job_id']
    shared = {}
    sensitivity = sensitivity_graph(model)
    for seed in range(6100, 6104):
        case = f'room-s{seed}-t50-mary'
        data = collect(base, model, seed)
        memory = data['snapshots'][50]['records']
        original = full_messages(args.actor, case)
        arms = {}
        allowed = {}
        if args.stage == 'controls':
            for policy in ['complete', 'ledger', 'recency']:
                arms[policy + '8'] = selection(policy, memory, 'mary', 50, 8, model, graph, random.Random(seed), old)
            arms['bm25_8'] = bm25(memory, 8)
            arms['query_only'] = []
            for shift in [1, 2, 3]:
                arms[f'cyclic_wrong{shift}_8'] = selection('learned', memory, 'mary', 50, 8, model,
                    rotate_graph(graph, model['walls'], shift), random.Random(seed), old)
            arms['table_sensitivity8'] = selection('learned', memory, 'mary', 50, 8, model,
                                                   sensitivity, random.Random(seed), old)
            modes = ['enabled']
        else:
            blocked = [r for r in memory if not (r[0] == 'wall' and r[2] == SOURCE)]
            # Replace values from an independently collected global sensor log.
            restored = []
            for r in memory:
                if r[0] == 'wall' and r[2] == SOURCE:
                    value = data['sensor'][SOURCE, r[1]]
                    restored.append(('wall', r[1], SOURCE, value))
                    tool_calls.append(dict(case=case, tool='authorized_historical_sensor',
                                           time=r[1], source=SOURCE, returned=value))
                else:
                    restored.append(r)
            arms = dict(sensor_available=restored, sensor_unavailable=blocked)
            allowed = {arm: sorted(belief(old, records, 'mary', 50, model, data['rooms']))
                       for arm, records in arms.items()}
            modes = ['enabled', 'disabled']
        cases.append(dict(case=case, truth=truths[case], allowed_beliefs=allowed,
                          records={arm: len(records) for arm, records in arms.items()}))
        for arm, records in arms.items():
            messages = replace_memory(original, json.dumps(records))
            sha = digest(messages)
            for mode in modes:
                for repeat in range(3):
                    key = (case, mode, sha, repeat)
                    job_id = digest([case, arm, mode, repeat, sha, args.stage, 'room_closure_v1'])
                    plan = dict(case=case, arm=arm, mode=mode, repeat=repeat, records=len(records),
                                prompt_sha256=sha, job_id=job_id, allowed_beliefs=allowed.get(arm))
                    if key in prior:
                        plan.update(response_directory=args.actor, response_job_id=prior[key], reused=True)
                    elif args.stage == 'controls' and key in shared:
                        plan.update(response_directory=args.out, response_job_id=shared[key], reused=True)
                    else:
                        plan.update(response_directory=args.out, response_job_id=job_id, reused=False)
                        jobs.append({**plan, 'messages': messages})
                        shared[key] = job_id
                    plans.append(plan)
    write_once(out / 'planned_evaluations.json', plans)
    write_once(out / 'case_profiles.json', cases)
    write_once(out / 'tool_calls.json', tool_calls)
    write_once(out / 'sensitivity_graph.json', [dict(object=o, room=r, walls=sorted(ws))
                                              for (o, r), ws in sorted(sensitivity.items())])
    return truths, jobs


def report(out):
    out = Path(out)
    plans = json.loads((out / 'planned_evaluations.json').read_text())
    cases = {p['case']: p for p in json.loads((out / 'case_profiles.json').read_text())}
    ledgers = {d: {r['job_id']: r for r in load_rows(Path(d) / 'ledger.jsonl')}
               for d in {p['response_directory'] for p in plans}}
    rows = []
    for plan in plans:
        row = ledgers[plan['response_directory']].get(plan['response_job_id'])
        if row is None:
            rows.append({**plan, 'event': 'missing'})
            continue
        combined = {**row, **plan}
        if plan['allowed_beliefs'] is not None and row['event'] == 'result':
            answer = safe_answer(row['parse_ok'], row['answer'], plan['allowed_beliefs'])
            combined.update(controller_answer=answer, controller_abstained=answer is None,
                            controller_correct=answer == cases[plan['case']]['truth'],
                            controller_wrong=answer is not None and answer != cases[plan['case']]['truth'])
        rows.append(combined)
    groups = defaultdict(list)
    for row in rows:
        groups[row['mode'] + '/' + row['arm']].append(row)
    table = {}
    for group, rr in groups.items():
        valid = [r for r in rr if r['event'] == 'result']
        per_case = {case: dict(answers=[r.get('answer') for r in rr if r['case'] == case],
                              correct=sum(r.get('correct', False) for r in rr if r['case'] == case))
                    for case in sorted(cases)}
        table[group] = dict(correct=sum(r['correct'] for r in valid), completed=len(valid),
                            expected=len(rr), per_case=per_case,
                            truncations=sum(r['finish_reason'] == 'length' for r in valid),
                            mean_input_tokens=sum(r['usage'].get('prompt_tokens', 0) for r in valid) / max(1, len(valid)),
                            reused=sum(r['reused'] for r in valid),
                            controller_correct=sum(r.get('controller_correct', False) for r in valid),
                            controller_abstained=sum(r.get('controller_abstained', False) for r in valid),
                            controller_wrong=sum(r.get('controller_wrong', False) for r in valid))
    result = dict(table=table, evaluations=len(rows),
                  unique_response_keys=len({(r['response_directory'], r['response_job_id']) for r in rows}),
                  scope='Same four development cases; controller uses shared trained deterministic model')
    write_once(out / 'evaluated_rows.json', rows)
    write_once(out / 'report.json', result)
    print(json.dumps(result), flush=True)


def main(args):
    truths, jobs = prepare(args)
    if args.prepare:
        print(json.dumps(dict(fresh_jobs=len(jobs), stage=args.stage)))
        return
    if args.report:
        report(args.out)
        return
    def scorer(job, text):
        ok, answer = parse(text)
        return dict(parse_ok=ok, answer=answer, correct=ok and answer == truths[job['case']])
    config = {**CONFIG, 'stage': args.stage, 'workers': 6, 'shuffle_seed': 2026092205,
              'source_sha': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol': 'docs/observed-memory-next-protocol-2026-09-22.md',
              'seed_panel': list(range(6100, 6104))}
    run_jobs(args.out, jobs, scorer, args.key_file, config)
    report(args.out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', choices=['controls', 'controller'], required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--actor', default='results/development/hm3/room_actor_v1')
    p.add_argument('--checkout', default='/tmp/observed-memory-20260922-LMbAYg/room-env')
    p.add_argument('--model', default='results/development/hm3/observed_room_small')
    p.add_argument('--key-file', default='api/api.txt')
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--report', action='store_true')
    main(p.parse_args())
