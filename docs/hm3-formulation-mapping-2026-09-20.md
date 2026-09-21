# HM3 as an instance of the Layer-1 formulation: sample, variable, time step, regime, memory carrier, frontier (2026-09-20)

Written to answer the question Yujia asked on 8/15 and again on 9/04 ("what is a sample, what is a variable, is the
variable set the same across regions") for the benchmark that actually carries the results. Every item names the code
object it corresponds to, so it can be checked against `code/hm3/` rather than taken on faith. The formulation is
`causal_memory_formulation.tex`; its assumptions are cited by their labels there (A-scm, gated stationarity, A-regime;
D memory carrier; Lemma frontier).

## 0. One sentence

An HM3 episode is one trajectory of a temporal SCM whose variables are the fields of typed objects, whose regime
process is the sequence of write events on those objects, and whose memory carriers are the outcome records that
persist those events; the task variable is the repair transaction set after a known intervention, and the learned
structure is the type-level projection of the process's lagged edges.

## 1. The mapping, item by item

| formulation object | HM3 object | code |
|---|---|---|
| time step `t` | one history record (one write event on one object); records are totally ordered inside an episode | `Episode.H[i]`, field `rid` = `h{i}`; segments group the records of one intervention |
| variable `x_i(t)` | one field of one object of the world (`flight.arrival`, `transfer.pickup`, `stay.checkin`, `stay.late_arrival`, `dinner.start`, `dinner.status`, `bundle.rebooked`, `activity.start`); the value at `t` is the field's value after record `t` | `Obj.fields`, reconstructed at any `t` by `core.timeline` |
| instantaneous edges (within-step SCM, A-scm) | the visible rules: `checkin = pickup + ride`, `activity.start >= checkin + min_rest`, `dinner.start >= checkin + 45` | `TravelDomain.local_payload` |
| lagged edges (across steps) | propagation from an upstream change to a downstream object's next write: `flight.arrival → transfer.pickup → stay.checkin → {dinner.start, activity.start} → bundle.rebooked` | `TravelDomain.propagate`; recovered as the type skeleton by `LearnedGraph` and, from the logs alone, by `tcd_logs.fit_pooled` |
| regime process `u_t` (gated stationarity) | the kind of write event at `t`: user intervention (exogenous), automatic environment effect, manual transaction; edges are active only under the event that fires them (an auto-rebook edge is active only when the provider's regime is automatic) | record `kind` ∈ {intervention, auto, txn}; the per-template gate in `LearnedGraph.models` is the estimated α_e(u) |
| hidden mechanism parameters | per-entity policies that select which regime a downstream object is in: `auto_rebook[provider]`, `buffer[provider]`, `enforce_late[hotel]`, `late_seating[restaurant]`, `linked[vendor]` | `Episode.params` (never observed); `TravelDomain.infer_params` recovers them from outcome records; `keysel.key_precedent_records` reads the same records without the arithmetic |
| memory carrier `m_s` (D memory carrier) | an outcome record: it is written once (write regime), persists unchanged (hold), and is read when a later decision consults the entity it witnesses (read). Every active path from the past intervention that produced the record to the current repair passes through the record, because the policy it reveals is not visible in the state | `H` records; `required_reads.records` lists the carriers the oracle's decision passes through |
| cue `c_{t0}` and task variable `y_{t1}` | the current intervention `I` (a write to the source object at `t1 − 1`) and the repair transaction set `A` at `t1` | `Episode.I`, `Episode.A`; success = EES (`core.score_plan`) |
| causal frontier `F_t(Y)` (Lemma frontier) | the objects reached from the source along active lagged edges plus the carriers attributed to their policy keys; by construction of the generator these are exactly `required_reads` | `scaling.skeleton_reads` (structure), `provenance.trace` (backward) |
| sample | one episode `(H, S0, I, A, S1, R)`: a world, a history of prior interventions, one test intervention and its oracle repair | `generate.generate_episode`; 200 training and 60 evaluation episodes per seed |
| access regime for the frontier arithmetic | the record kind and the segment boundary decide whether a record is a witness for a key; "latest witness wins" is the hold rule | `core.segments`, `infer_params` |

## 2. Is the variable set the same across episodes, conditions, and domains?

- **Across episodes of one domain:** the *type-level* variable set is fixed (six object types × their fields in Travel; three types in Shopping32); the *instance-level* set differs (each world samples 6–24 objects). Structure is learned and used at type level, so the estimand is one adjacency over typed paths, shared by every episode; instances are its unrolling. This is the "grouping" Yujia allowed on 8/15: a variable is an object field, grouped by type.
- **Across history-length conditions:** identical. Augmentation adds foreign objects and records; the original objects, the intervention, the oracle and the required carriers are unchanged (`scaling.validate` asserts this per episode). Lengths are paired samples.
- **Across access regimes:** the same variables; what changes is which edges are active (α_e(u)). Nothing is added or removed from the variable set by a regime, which is the gated-stationarity assumption as written.
- **Across domains (Travel vs Shopping32):** different schemas. Nothing is pooled across domains; each domain has its own skeleton, gate, and panels.
- **What E0 calls a regime vs what HM3 calls one:** E0's `u_t` is the access phase of the memory module (idle/write/hold/read) and is applied per variable; HM3's `u_t` is the write-event kind at each step, and the hidden policy decides which kind fires. Both are gates on edges of a stationary graph; they are the same formal object instantiated at different granularity. The paper must name them separately (`docs/causal-vocabulary-and-estimators-2026-09-19.md` §2).

## 3. What is observed, and what is learned from what

- **Observed at run time:** `H` (every record with its kind, object, delta, segment), `S0`, `I`. The parameters, the graph, the affected set and `A` are not.
- **Learned from interventional training trajectories:** the type skeleton and the per-template gates (`LearnedGraph`), because every training episode records a known intervention and what followed. This is the interventional estimator.
- **Learned from the logs alone (observational):** the type skeleton, by pooled lagged regression over one indicator per object type with intervention rows exogenous (`tcd_logs`, recall 1.0 on 6/6 seeds in both domains); the gates are not recoverable this way and come from the interventional fit or from the parser. This is the Layer-1 temporal causal discovery step Yujia asked for on 7/29, and the MemoryArena-style "activated in round s" encoding is what makes the same estimator return self-loops.
- **Forward use:** read `F_t` only (`graph_select`, `tcd_select`); parser-free variant reads the latest same-key carrier segments (`key_select`).
- **Backward use:** from anomalous task variables, walk the same skeleton to the carriers on the path, re-rank by leave-one-out, validate by clean replacement (`provenance`).

## 4. Where the instance departs from the formulation, stated plainly

1. The frontier lemma is stated for a fixed variable set; HM3 applies it at type level and unrolls per instance. The unrolling is exact for the generator (links are given), and the observational recovery in §3 shows the type skeleton is identifiable from the logs, but instance links are read from the state, never discovered.
2. `u_t` in HM3 is observed (record kind), which is the A-regime assumption in its easy case; no change-point detection is needed.
3. The carriers are external records, i.e. the "external store as a variable with identity dynamics" remark of the formulation; there is no internal-state (KV-cache, activation) instantiation in this paper. That was the 7/22 example and remains future work.
4. The value pathway at execution (arithmetic on the carriers' deltas) is domain code shared by every arm; the structure decides *which* carriers are read, and the parser-free arm shows the structure suffices for that without the arithmetic being in the selector.

## 5. Sentences for the setting section

- "A sample is an episode: a world, a history of prior interventions with their outcome records, one test intervention and its oracle repair. A time step is one write event. A variable is one field of one typed object; the variable *set* is fixed at type level within a domain and unrolled per episode. The regime at a step is the kind of the write event; the hidden per-entity policies decide which kind fires. A memory carrier is an outcome record, written once, held, and read when a later decision consults the entity it witnesses."
- "The causal frontier of the repair is the set of objects reached along active lagged edges from the intervention plus the carriers attributed to their policy keys; it is what the structure-guided arms read, and it does not grow with the history."
