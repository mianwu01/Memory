# HM3 formulation mapping (corrected by the 2026-09-21 alignment audit)

The simulator formulation and the estimator representation are different objects.
The current TCD code **does not fit the object-field SCM described below**: it fits
one binary write indicator per type, with one row per record, or one activation
indicator per segment. Its outputs are type-level temporal dependencies. Instance
links and the history parser are supplied separately. The complete-type-graph
control is mandatory before attributing memory gains to discovery. See
`structure-alignment-protocol-2026-09-21.md` for the controlling definitions.

Written to answer the question Yujia asked on 8/15 and again on 9/04 ("what is a sample, what is a variable, is the
variable set the same across regions") for the benchmark that actually carries the results. Every item names the code
object it corresponds to, so it can be checked against `code/hm3/` rather than taken on faith. The formulation is
`causal_memory_formulation.tex`; its assumptions are cited by their labels there (A-scm, gated stationarity, A-regime;
D memory carrier; Lemma frontier).

## 0. One sentence

The HM3 simulator evolves object fields, but the existing discovery bridge observes
only binary type-write indicators. It estimates a lagged dependency graph on those
indicators, then combines it with supplied instance links and a reader. It does not
infer the field SCM or establish that its output is that SCM's causal projection.

## 1. The mapping, item by item

| formulation object | HM3 object | code |
|---|---|---|
| time step `t` | one history record (one write event on one object); records are totally ordered inside an episode | `Episode.H[i]`, field `rid` = `h{i}`; segments group the records of one intervention |
| variable `x_i(t)` | one field of one object of the world (`flight.arrival`, `transfer.pickup`, `stay.checkin`, `stay.late_arrival`, `dinner.start`, `dinner.status`, `bundle.rebooked`, `activity.start`); the value at `t` is the field's value after record `t` | `Obj.fields`, reconstructed at any `t` by `core.timeline` |
| instantaneous edges (within-step SCM, A-scm) | the visible rules: `checkin = pickup + ride`, `activity.start >= checkin + min_rest`, `dinner.start >= checkin + 45` | `TravelDomain.local_payload` |
| transition mechanisms | `flight.arrival → transfer.pickup → stay.checkin`; checkin affects dinner/activity; **dinner_changed** triggers bundle updates | `TravelDomain.propagate`; this is not the shortest-path template reference or the binary indicator graph |
| regime process `u_t` (gated stationarity) | the kind of write event at `t`: user intervention (exogenous), automatic environment effect, manual transaction; edges are active only under the event that fires them (an auto-rebook edge is active only when the provider's regime is automatic) | record `kind` ∈ {intervention, auto, txn}; the per-template gate in `LearnedGraph.models` is the estimated α_e(u) |
| hidden mechanism parameters | per-entity policies that select which regime a downstream object is in: `auto_rebook[provider]`, `buffer[provider]`, `enforce_late[hotel]`, `late_seating[restaurant]`, `linked[vendor]` | `Episode.params` (never observed); `TravelDomain.infer_params` recovers them from outcome records; `keysel.key_precedent_records` reads the same records without the arithmetic |
| external memory record | an outcome record is written, persists, and may later be selected; these storage operations motivate the carrier analogy but do not establish a separating-set theorem | `H`; `required_reads.records` is evaluator witness metadata, not proof of a unique causal frontier |
| cue `c_{t0}` and task variable `y_{t1}` | the current intervention `I` (a write to the source object at `t1 − 1`) and the repair transaction set `A` at `t1` | `Episode.I`, `Episode.A`; success = EES (`core.score_plan`) |
| selected records and oracle witness set | `skeleton_reads` traverses an ungated type/template skeleton and retrieves parser-attributed witnesses; `required_reads` is an evaluator diagnostic, potentially containing redundant witnesses | Neither set has been shown to equal the lemma's unique causal frontier |
| sample | one episode `(H, S0, I, A, S1, R)`: a world, a history of prior interventions, one test intervention and its oracle repair | `generate.generate_episode`; 200 training and 60 evaluation episodes per seed |
| access regime for the frontier arithmetic | the record kind and the segment boundary decide whether a record is a witness for a key; "latest witness wins" is the hold rule | `core.segments`, `infer_params` |

## 2. Is the variable set the same across episodes, conditions, and domains?

- **Across episodes of one domain:** the actual event-panel estimator has one binary variable per object type (six in Travel, three in Shopping32), not one variable per type-field combination. Instance identities vary across episodes. The learned type-indicator graph is shared; its causal equivalence to an unrolled field mechanism has not been established.
- **Across history-length conditions:** identical. Augmentation adds foreign objects and records; the original objects, the intervention, the oracle and the required carriers are unchanged (`scaling.validate` asserts this per episode). Lengths are paired samples.
- **Across access regimes:** the same variables; what changes is which edges are active (α_e(u)). Nothing is added or removed from the variable set by a regime, which is the gated-stationarity assumption as written.
- **Across domains (Travel vs Shopping32):** different schemas. Nothing is pooled across domains; each domain has its own skeleton, gate, and panels.
- **What E0 calls a regime vs what HM3 calls one:** E0 explicitly generates access phases; HM3 records event kinds (intervention/auto/txn). The bridge does not estimate access-phase-specific graphs. A conceptual analogy is not an empirical demonstration of the same write/hold/read model; name and evaluate the two separately.

## 3. What is observed, and what is learned from what

- **Observed at run time:** `H` (every record with its kind, object, delta, segment), `S0`, `I`, including instance links inside `S0`. Hidden policy parameters, oracle affected set and gold `A` are not selector inputs. The supplied instance graph must not be described as discovered.
- **Learned from interventional training trajectories:** the type skeleton and the per-template gates (`LearnedGraph`), because every training episode records a known intervention and what followed. This is the interventional estimator.
- **Estimated from event indicators:** lagged type dependencies, by regression/PCMCI+/GRACE. Regression excludes intervention rows as targets; the GRACE wrapper currently discards the exogenous mask, so this handling is not shared across estimators. High recall against the template projection does not establish causal identification or utility. No explicit write/hold/read access mechanism is estimated in this HM3 bridge.
- **Forward use:** read the selector's chosen records (`graph_select`, `tcd_select`); parser-free variants use same-key precedent segments. None has been proved to equal the formulation's `F_t`.
- **Backward use:** from anomalous task variables, walk the same skeleton to the carriers on the path, re-rank by leave-one-out, validate by clean replacement (`provenance`).

## 4. Where the instance departs from the formulation, stated plainly

1. The frontier lemma concerns a distribution-level separating set under stated assumptions. Type aggregation, selected records, and correctness-preserving replay subsets are different estimands; an equivalence has not been established. Instance links are read from the state, never discovered.
2. `u_t` in HM3 is observed (record kind), which is the A-regime assumption in its easy case; no change-point detection is needed.
3. The carriers are external records, i.e. the "external store as a variable with identity dynamics" remark of the formulation; there is no internal-state (KV-cache, activation) instantiation in this paper. That was the 7/22 example and remains future work.
4. The executor's arithmetic is shared across arms. The reader combines type filtering, supplied instance links and parser/precedent logic; the complete-type-graph control produces identical GRACE-open/parser inputs on 1,531/1,531 audited episode-conditions. These results do not isolate a benefit from discovered type structure.

## 5. Sentences for the setting section

- "An evaluation unit is an episode. For the existing discovery bridge, an episode contributes one series with one row per write event and one binary indicator per object type. Field values belong to the simulator, not this estimator's variable set. Instance links are supplied separately. Observed event kinds are not an inferred write/hold/read regime process."
- "The selector reaches objects through supplied links filtered by a fitted type graph and retrieves historical witnesses. Its contribution is evaluated against the same selector without type filtering. History augmentation preserves the required witnesses by construction, so a constant oracle read size is a sanity check rather than an independent discovery result."
