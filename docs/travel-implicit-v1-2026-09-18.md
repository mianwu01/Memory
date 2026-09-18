# Travel implicit v1: runnable MemoryArena history variant

`code/travel_implicit.py` implements a task transformation for the original
MemoryArena actor and full-plan evaluator. It is not the API-free DynamicTravel
prototype and does not use its oracle value decoder.

## Task and information boundaries

Every dependency sentence in the original target traveler's query is quoted
verbatim in a notice attached to the latest already-seen source traveler's query.
The notice explicitly identifies its future target and says whose first-person
voice the quote uses. A notice hosted by the base person enters the base write;
other notices enter memory only after the host traveler's round completes.
Nothing is generated from future actions or answers. Other current-person query
lines, answers, and public base plans are unchanged.

The `implicit` condition replaces each dependency sentence with a pointer that
specifies the target day/slot but no source identity or required relation. The
`explicit` condition keeps the original sentence and receives identical notices.
Both conditions therefore contain the same advance-notice channel. Histories
are not byte-identical: completed queries reflect their assigned condition and
actor-generated plans can differ. This is a paired disclosure manipulation,
not a replay with guaranteed identical historical outcomes.

Notices for future travelers are delimited and excluded from the *current*
person's selection query. Actors can see and memory methods can preserve them.
They are instructions for a future task, not current plan modifications.

## Integration

After importing `run_travel`, call:

```python
install_variant(run_travel, "implicit")  # or "explicit"
```

This wraps both the data loader and `EnvironmentClient.reset`: the official
actor actually receives the latter's observations, so changing only the loader
would silently leave the original task active. The upstream environment and
evaluator still use the unchanged original answers.

The three structured arms share exactly the same historical requirement index:

```python
notes = HistoryNotes()
clean_chunk = notes.add_chunk(original_chunk_json)
backend.add_chunk(clean_chunk)
resolved = notes.resolve(query)
selected = backend._ancestors_of(resolved.selection_query)
# Include resolved.memory_text inside actor-visible <memory_context>.
```

`add_chunk` returns the same memory record with the future-notice block removed
from its query for current-target cell parsing. It preserves the original plan.
All methods receive the same original raw chunks; conventional and author
baselines apply their own storage/retrieval algorithms. `ours`, `noGcompact` and
`query_only` all use the same index. The historical `query_only` arm name means
zero learned edges plus the shared parser; its role remains isolating the graph,
not withholding useful observations from one arm.

## Graph training and fixed split

The campaign uses dev ID 101; test IDs 111–160; and the other 219 episodes for
training. No new graph may be fitted on dev or test episodes. Construct the
indicator discovery view via `training_rows(train_rows, "implicit")`, then
`parse_episode`. This replays source writes and resolves target requirements
from previously written notices without reading answer values. Direct parsing
of the implicit query alone would incorrectly lose constraint-activation bits.
All 219 reconstructed training activation sets match the original training
constraints exactly.

## Offline evidence

`results/development/travel_implicit_v1/audit.json` records the full-corpus audit:

| Check | Result |
|---|---:|
| Episodes / target rounds | 270 / 1,869 |
| Verbatim relocated dependency sentences | 6,829 |
| Residual active-current-query named dependencies | 0 |
| Missing requirements at target retrieval | 0 |
| Notices read before their host write | 0 |
| Changed answer or base-plan records | 0 |
| Training indicator mismatches | 0 / 219 |

The audit ignores clearly delimited notices for *other* future travelers when
measuring current-query leakage. Group-member preambles remain as in the
original benchmark; names alone do not expose a dependency relation.

Six CPU-only tests additionally check immutable gold, before/after write
visibility, explicit/implicit notice equality, train-view equivalence, actual
environment observation replacement, and rejection of double transformations.

## Claim boundary

This task requires consulting historical requirements, but a named historical
notice may be solved by structured lookup. Learned-graph necessity is therefore
an empirical comparison against the zero-edge arm, not a property established
by moving query text. The original small number of people per episode also
remains; no extra difficulty or long-history claim follows automatically.
The offline audit establishes protocol integrity, not agent task performance.
