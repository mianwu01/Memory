"""Offline attribution checks on already evaluated trajectories, explicitly post hoc."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random

from .continuation_actor import write_once
from .observed_room import init, selection
from .observed_memory_report import paired_difference
from .room_closure import rotate_graph, sensitivity_graph
from .room_source_audit import collect, load_model


def main(args):
    outputs = {}
    for size in ['small', 'medium']:
        root = Path('results/real/hm3') / f'observed_room_{size}'
        original = json.loads((root / 'query_rows.json').read_text())
        base, old = init(args.checkout, size + '-01', 120)
        model, graph = load_model(root, base)
        sg = sensitivity_graph(model)
        by_seed = defaultdict(list)
        for row in original:
            if row['policy'] == 'full' and row['budget'] == 8:
                by_seed[row['seed']].append(row)
        rows = []
        for seed, queries in by_seed.items():
            data = collect(base, model, seed)
            for query in queries:
                t, obj = query['time'], query['object']
                memory = data['snapshots'][t]['records']
                assert [list(r) for r in memory] == query['selected_records']
                truth = data['truth'][obj, t]
                arms = {'table_sensitivity': selection('learned', memory, obj, t, 8, model, sg, random.Random(seed), old)}
                for shift in [1, 2, 3]:
                    arms[f'cyclic_wrong{shift}'] = selection('learned', memory, obj, t, 8, model,
                        rotate_graph(graph, model['walls'], shift), random.Random(seed), old)
                for policy, records in arms.items():
                    prior, belief = old.answer(records, obj, t, model, data['rooms'])
                    score = prior if prior is not None else old.score(belief, truth, data['rooms'])
                    rows.append(dict(seed=seed, object=obj, time=t, policy=policy, score=score,
                                     records=len(records), selected_records=records))
        table = {}
        original_report = json.loads((root / 'report.json').read_text())
        for policy in sorted({r['policy'] for r in rows}):
            selected = [r for r in rows if r['policy'] == policy]
            episode_scores = {str(seed): sum(r['score'] for r in selected if r['seed'] == seed) / len(by_seed[seed])
                              for seed in by_seed}
            learned = [r for r in original if r['policy'] == 'learned' and r['budget'] == 8]
            originals = {(r['seed'], r['object'], r['time']): r['selected_records'] for r in learned}
            same = sum([list(x) for x in r['selected_records']] == originals[r['seed'], r['object'], r['time']]
                       for r in selected)
            table[policy] = dict(score=sum(r['score'] for r in selected) / len(selected),
                queries=len(selected), episode_scores=episode_scores, same_as_learned=same,
                learned_minus_control=paired_difference(original_report['table']['learned@8']['episode_scores'], episode_scores))
        outputs[size] = dict(table=table,
            sensitivity_edges=[dict(object=o, room=r, walls=sorted(ws)) for (o,r),ws in sorted(sg.items())],
            scope='Post-hoc comparisons on previously evaluated trajectories; no new training or LLM calls')
        write_once(Path(args.out) / f'{size}_rows.json', rows)
        print(json.dumps(dict(size=size, table={k:{x:v for x,v in r.items() if x!='episode_scores'} for k,r in table.items()})),flush=True)
    write_once(Path(args.out) / 'report.json', outputs)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkout', default='/tmp/observed-memory-20260922-LMbAYg/room-env')
    p.add_argument('--out', default='results/development/hm3/room_posthoc_controls')
    main(p.parse_args())
