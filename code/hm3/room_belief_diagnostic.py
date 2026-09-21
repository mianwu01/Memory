"""Check constant-phase consistency; old decoder marginals are not epistemic truth."""
import itertools
import json
from pathlib import Path

from .continuation_actor import write_once
from .room_native_actor import MEMORY_MARKER, QUESTION_MARKER


def joint_belief(records, knowledge, obj, query_time):
    patterns = knowledge['patterns']
    phases = {wall: set(range(len(pattern))) for wall, pattern in patterns.items()}
    for kind, time, entity, value in records:
        if kind == 'wall' and time <= query_time:
            pattern = patterns[entity]
            phases[entity] = {phase for phase in phases[entity] if pattern[(time + phase) % len(pattern)] == value}
    if any(not values for values in phases.values()):
        return dict(rooms=[], inconsistent_observations=True, missing_transition=False, assignments=0)
    sightings = [(time, value) for kind, time, entity, value in records
                 if kind == 'sight' and entity == obj and time <= query_time]
    if not sightings:
        return dict(rooms=knowledge['rooms'], no_sighting=True, missing_transition=False, assignments=0)
    start, initial_room = max(sightings)
    table = {(r['room'], tuple(r['wall_bits'])): r['next_room'] for r in knowledge['transitions']}
    walls = sorted(patterns)
    answers, missing, assignments = set(), False, 0
    for offset in itertools.product(*(sorted(phases[wall]) for wall in walls)):
        phase = dict(zip(walls, offset))
        room = initial_room
        for time in range(start, query_time):
            bits = tuple(patterns[wall][(time + phase[wall]) % len(patterns[wall])]
                         for wall in knowledge['incident_walls'].get(room, []))
            if (room, bits) not in table:
                # Unknown trained-table transition: no justified unique-room conclusion.
                missing = True
                answers.update(knowledge['rooms'])
                break
            room = table[room, bits]
        else:
            answers.add(room)
        assignments += 1
    return dict(rooms=sorted(answers), missing_transition=missing, assignments=assignments,
                phase_counts={w: len(v) for w, v in phases.items()},
                scope='Exact constant phases, latest retained sighting, shared trained transition table')


def main():
    root = Path('results/development/hm3/room_actor_v1')
    knowledge = json.loads((root / 'shared_learned_model.json').read_text())
    manifest = json.loads((root / 'manifest.json').read_text())
    profiles = {r['case']: r for r in json.loads((root / 'case_profiles.json').read_text())}
    rows = []
    for job in manifest:
        if job['mode'] != 'enabled' or job['repeat'] != 0:
            continue
        messages = json.loads((root / 'inputs' / (job['prompt_sha256'] + '.json')).read_text())
        raw = messages[1]['content'].split(MEMORY_MARKER, 1)[1].split(QUESTION_MARKER, 1)[0]
        check = joint_belief(json.loads(raw), knowledge, 'mary', 50)
        prior = profiles[job['case']]['decoder_beliefs'][job['arm']]
        rows.append(dict(case=job['case'], arm=job['arm'], old_decoder=prior,
                         same_rooms=prior == check['rooms'], joint_phase_check=check))
    dest = Path('results/development/hm3/room_belief_diagnostic.json')
    write_once(dest, rows)
    print(json.dumps(dict(cases=len(rows), differences=[r for r in rows if not r['same_rooms']],
                          missing_transition=sum(r['joint_phase_check']['missing_transition'] for r in rows))))


if __name__ == '__main__':
    main()
