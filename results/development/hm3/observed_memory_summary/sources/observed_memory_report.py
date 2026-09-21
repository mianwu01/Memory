"""Read-only aggregation of the bounded observed-memory campaigns; no API calls."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .paired_actor import load_rows

DEV = Path('results/development/hm3')
REAL = Path('results/real/hm3')
OUT = DEV / 'observed_memory_summary'


def read(path):
    return json.loads(Path(path).read_text())


def paired_difference(a, b):
    seeds = sorted(set(a) & set(b))
    values = np.array([a[s] - b[s] for s in seeds])
    rng = np.random.default_rng(20260922)
    bootstrap = values[rng.integers(len(values), size=(10000, len(values)))].mean(axis=1)
    return dict(episodes=len(values), difference=float(values.mean()),
                episode_bootstrap_95=np.quantile(bootstrap, [.025, .975]).tolist(),
                scope='Conditional on this configuration, fixed trained model and sampling protocol')


def decoder_summary(directory):
    result = read(directory / 'report.json')
    table = result['table']
    compact = {key: {k: v for k, v in row.items() if k != 'episode_scores'} for key, row in table.items()}
    comparisons = {control: paired_difference(table['learned@8']['episode_scores'], table[control]['episode_scores'])
                   for control in ['full@8', 'topology@8', 'complete@8', 'ledger@8', 'recency@8']}
    return dict(table=compact, structure=result['structure'], comparisons=comparisons,
                metric='Expected accuracy of fixed decoder beliefs, not actual LLM accuracy')


def epistemic_summary():
    directory = DEV / 'room_actor_v1'
    profiles = {p['case']: p for p in read(directory / 'case_profiles.json')}
    rows = list({r['job_id']: r for r in load_rows(directory / 'ledger.jsonl')}.values())
    out = defaultdict(lambda: Counter())
    for row in rows:
        if row['event'] != 'result':
            continue
        beliefs = profiles[row['case']]['decoder_beliefs'][row['arm']]
        expected = beliefs[0] if len(beliefs) == 1 else None
        counts = out[row['mode'] + '/' + row['arm']]
        counts['completed'] += 1
        counts['location_correct'] += bool(row['correct'])
        counts['consistent_with_available_evidence'] += bool(row['parse_ok'] and row['answer'] == expected)
        counts['abstained'] += bool(row['parse_ok'] and row['answer'] is None)
        counts['unsupported_nonnull'] += bool(row['parse_ok'] and row['answer'] is not None and len(beliefs) != 1)
    return dict(out)


def cost_audit():
    actor_dirs = ['paired_actor_s82', 'room_actor_v1', 'room_native_actor_v1', 'room_controls_v1', 'room_controller_v1']
    sources = [DEV / d / 'ledger.jsonl' for d in actor_dirs]
    sources += sorted((DEV / 'room_native').glob('*/*/memory_calls.jsonl'))
    sources += sorted((DEV / 'room_native_recovery').glob('*/*/memory_calls.jsonl'))
    sources += sorted((DEV / 'room_native_http_probe').glob('*.json'))
    by_source, all_fresh, ignored = {}, [], 0
    for path in sources:
        rows = load_rows(path) if path.suffix == '.jsonl' else [read(path)]
        fresh = [r for r in rows if not r.get('reused_from')]
        ignored += len(rows) - len(fresh)
        successful = [r for r in fresh if r['event'] == 'result']
        all_fresh.extend(fresh)
        by_source[str(path)] = dict(responses=len(successful), failed_attempts=len(fresh) - len(successful),
            reused_responses_excluded=len(rows) - len(fresh),
            prompt_tokens=sum((r.get('usage') or {}).get('prompt_tokens', 0) for r in successful),
            completion_tokens=sum((r.get('usage') or {}).get('completion_tokens', 0) for r in successful))
    success = [r for r in all_fresh if r['event'] == 'result']
    intents, unresolved_intents, budget_exceedances = 0, [], []
    for name in actor_dirs:
        directory = DEV / name
        requests = load_rows(directory / 'requests.jsonl')
        recorded = {(r['job_id'], r.get('attempt', 0)) for r in load_rows(directory / 'ledger.jsonl')}
        budget = read(directory / 'protocol.json')['max_tokens']
        budget_exceedances += [dict(directory=name, job_id=r['job_id'], requested_max_tokens=budget,
                                    reported_completion_tokens=r['usage']['completion_tokens'],
                                    finish_reason=r['finish_reason'])
                               for r in load_rows(directory / 'ledger.jsonl')
                               if r['event']=='result' and r['usage'].get('completion_tokens',0)>budget]
        intents += len(requests)
        unresolved_intents += [dict(directory=name, job_id=r['job_id'], attempt=r['attempt'])
                               for r in requests if (r['job_id'], r['attempt']) not in recorded]
    return dict(by_source=by_source, completed_responses=len(success),
                failed_attempts=len(all_fresh) - len(success),
                prompt_tokens=sum((r.get('usage') or {}).get('prompt_tokens', 0) for r in success),
                completion_tokens=sum((r.get('usage') or {}).get('completion_tokens', 0) for r in success),
                reasoning_tokens_subset=sum(((r.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens', 0) or 0 for r in success),
                models=dict(Counter(r.get('returned_model') for r in success)),
                reused_responses_excluded=ignored, actor_request_intents=intents,
                unresolved_actor_intents=unresolved_intents,
                reported_output_budget_exceedances=budget_exceedances,
                notes=['Reasoning tokens are already included in completion tokens; never add twice',
                       'Provider pricing unknown; no dollar/cny bill inferred',
                       'Mem0 all 44 responses are recorded under first case due to module cache; aggregate only',
                       'Includes original failed native attempts and probes; excludes exact replayed responses',
                       'Method alias rows are not new API responses; corpus embedding CPU cost not estimated'])


def figure(actor, controller):
    """Fixed case 6100; actual empirical outputs, not an idealized success plot."""
    case = 'room-s6100-t50-mary'
    labels = [('full', 'Full observed memory'), ('source_blocked', 'Restricted stream removed'),
              ('source_changed', 'Restricted values changed'), ('neutral_blocked', 'Neutral stream removed')]
    rows = []
    for i, (arm, label) in enumerate(labels):
        answer = actor['table']['enabled/' + arm]['per_case'][case]['answers']
        text = ', '.join('null' if a is None else a for a in answer)
        y = 306 + 36 * i
        rows.append(f'<text x="46" y="{y}" class="body">{label}</text><text x="355" y="{y}" class="mono">{text}</text>')
    sensor = controller['table']['enabled/sensor_available']['per_case'][case]['answers']
    sensor_text = ', '.join('null' if a is None else a for a in sensor)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1160" height="630" viewBox="0 0 1160 630">
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#176b67"/></marker></defs>
<style>.title{{font:700 24px sans-serif;fill:#123442}}.head{{font:700 18px sans-serif;fill:#123442}}.body{{font:16px sans-serif;fill:#213e4b}}.small{{font:14px sans-serif;fill:#42606c}}.mono{{font:15px monospace;fill:#123442}}</style>
<rect width="1160" height="630" fill="#f6fafb"/>
<text x="30" y="38" class="title">Observed dynamics → memory selection → source intervention</text>
<text x="30" y="66" class="small">Controlled RoomEnv extension. Shared trained world model. Not recovery of hidden LLM thoughts.</text>
<rect x="30" y="88" width="1100" height="142" rx="10" fill="#e7f2ef"/>
<text x="46" y="116" class="head">Actual discovered lag-1 edges (3 retained; finite reference also contains 4 missed edges)</text>
<text x="46" y="147" class="body">bathroom–study wall(t)</text><path d="M330 142 H465" stroke="#176b67" stroke-width="2" marker-end="url(#arrow)"/>
<text x="485" y="147" class="body">john location(t+1), context: john in bathroom at t</text>
<text x="46" y="180" class="body">living–kitchen wall(t)</text><path d="M330 175 H465" stroke="#176b67" stroke-width="2" marker-end="url(#arrow)"/>
<text x="485" y="180" class="body">mary location(t+1), context: mary in kitchen OR living at t</text>
<text x="46" y="214" class="small">PCMCI+/G² on 64 fully observed training trajectories; test memory contains only local observations.</text>
<text x="30" y="269" class="head">Fixed case 6100: correct ordinary answer = bathroom; thinking enabled, 3 responses</text>
{''.join(rows)}
<rect x="30" y="444" width="1100" height="126" rx="10" fill="#eaf0fb"/>
<text x="46" y="474" class="head">Actionable controlled response</text>
<text x="46" y="505" class="body">Independent authorized sensor → fresh actor responses: {sensor_text}</text>
<text x="46" y="535" class="body">Sensor unavailable → model-assisted gate refuses unsupported guesses.</text>
<text x="30" y="600" class="small">All four fixed cases retained. This is one illustrative development case, not a perfect-detection or generalization claim.</text>
</svg>'''


def main():
    required = ['room_native_actor_v1', 'room_controls_v1', 'room_controller_v1']
    for name in required:
        completion = read(DEV / name / 'completion.json')
        if completion['unresolved']:
            raise RuntimeError(f'Unresolved executions: {name}')
    small = decoder_summary(REAL / 'observed_room_small')
    medium = decoder_summary(REAL / 'observed_room_medium')
    actor = read(DEV / 'room_actor_v1/report.json')
    native = read(DEV / 'room_native_actor_v1/report.json')
    controls = read(DEV / 'room_controls_v1/report.json')
    controller = read(DEV / 'room_controller_v1/report.json')
    cost = cost_audit()
    result = dict(hm3_gate=read(DEV / 'paired_actor_s82/report.json'), small=small, medium=medium,
                  actor=actor, epistemic=epistemic_summary(), native=native,
                  controls=controls, controller=controller,
                  posthoc_controls=read(DEV / 'room_posthoc_controls/report.json'),
                  joint_phase_diagnostic=read(DEV / 'room_belief_diagnostic.json'),
                  decoder_audit=read(REAL / 'room_source_audit/report.json'), cost=cost,
                  scope='Controlled component evidence; original memory-state SCM and broad actor generalization remain unestablished')
    acceptance = dict(
        mature_temporal_discovery_run=True,
        original_environment_time_preserved=True,
        learned_graph_changes_reader_inputs=small['table']['complete@8']['same_as_learned'] < small['table']['complete@8']['queries'],
        small_controlled_utility_signal=small['comparisons']['topology@8']['episode_bootstrap_95'][0] > 0,
        medium_topology_superiority_supported=medium['comparisons']['topology@8']['episode_bootstrap_95'][0] > 0,
        actor_scope='Four development cases; repeated responses are not independent tasks',
        full_graph_recovery=False,
        learned_agent_memory_state_dynamics=False,
        held_out_actor_test_completed=False,
        native_memsys_same_interface_completed=True,
        native_memsys_equal_tokens=False,
        safety_scope='Known source policy and shared-model-assisted gate in controlled environment',
        yujia_approval_of_narrower_research_object='Not recorded',
        full_research_requirements_met=False)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    (OUT / 'cost_audit.json').write_text(json.dumps(cost, indent=2) + '\n')
    (OUT / 'acceptance.json').write_text(json.dumps(acceptance, indent=2) + '\n')
    source_names = ['observed_room', 'paired_actor', 'room_actor', 'room_source_audit',
                    'room_memsys', 'room_amem_probe', 'room_amem_recover', 'room_native_actor',
                    'room_closure', 'room_posthoc_controls', 'room_belief_diagnostic',
                    'observed_memory_report', 'test_observed_memory']
    source_hashes = {}
    for name in source_names:
        path = Path('code/hm3') / (name + '.py')
        raw = path.read_bytes()
        source_hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        (OUT / 'sources').mkdir(exist_ok=True)
        (OUT / 'sources' / path.name).write_bytes(raw)
    (OUT / 'source_hashes.json').write_text(json.dumps(source_hashes, indent=2) + '\n')
    (OUT / 'structure_and_source.svg').write_text(figure(actor, controller))
    print(json.dumps(dict(output=str(OUT), completed_responses=cost['completed_responses'],
                          unresolved=cost['unresolved_actor_intents'])))


if __name__ == '__main__':
    main()
