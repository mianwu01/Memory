# Paper draft — Method section (2026-09-21; reconciled 2026-09-22 with the alignment audit; for Yujia to cut)

Companion to `docs/paper-draft-experiments-2026-09-20.md` (experiments), `docs/paper-draft-appendix-2026-09-22.md`
and `docs/full-status-method-experiments-paper-2026-09-21.md` (status). Notation follows
`causal_memory_formulation.tex`. Claim scope follows `docs/structure-alignment-protocol-2026-09-21.md`: given
instance links are never called discovered; every empirical gain is attributed to the selector that produced it;
mechanism and identifiability statements are limited to what is proved or measured. Whether this method replaces
the observational discovery pipeline Yujia asked for on 9/20, or sits beside it as the interventional version of it,
is her decision; the text is written so that either reading works.

## 3 Method: the memory frontier by read interventions

### 3.1 Setting

An agent acts in episodes. In episode e it holds a history H = (m_1, …, m_n) of records written by earlier
interventions and their consequences, observes the current state S_0 and a cue I (a change it must respond to), and
emits a decision Y = π(S_0, I, R) where R ⊆ H is the set of records it reads. π is the policy: a deterministic
executor in the controlled setting, a language model in the actor experiments. Correctness c(Y) ∈ {0,1} is scored
against a reference (§5). In the formulation of §2, H holds the memory carriers and the read set R is the access
regime at the decision step. A correctness-preserving subset for one episode is the object we identify; its relation
to the distribution-level causal frontier of the lemma is stated in §3.6 and not assumed.

### 3.2 Reads are interventions

The access regime is set by the memory system. At replay time it can be set freely: re-run π on the logged
(S_0, I) with R = S for any S ⊆ H and score the result. This is do(g = 1_S) on the read gates, with an assignment
chosen by the experimenter and independent of everything in the log, so paired replays estimate the effect of a
visibility change on the fixed policy's decision. They identify what the policy depends on among the visible records;
they do not recover the process that wrote the records, and they do not recover hidden intent.

**Definition 1 (sufficient, minimal, π-frontier).** S ⊆ H is *sufficient* for e if c(π(S_0, I, S)) = 1. It is
*minimal* if no proper subset is sufficient. A minimal sufficient set is a *π-frontier* F^π_e; it need not be unique.

**Assumption 1 (monotone use).** If S is sufficient and S ⊆ T ⊆ H then T is sufficient.

Assumption 1 is a property of the policy and the data together. For the executor on HM3 it holds because the
augmentation validator guarantees that the consulted witness is the latest record of its key, so adding records never
overrides it; a later conflicting witness would break it. For a language model it is the statement that extra
records do not hurt; its violation is measured in §5.5 with a voted oracle, and voting reduces oracle noise without
repairing non-monotonicity.

**Observation 1 (a deterministic-chain faithfulness failure).** For a chain a → b → c with w_b = f(w_a) and
w_c = g(w_b), both w_c ⟂ w_b | w_a and w_c ⟂ w_a | w_b hold, so the observational distribution can be unfaithful to
the chain and a constraint-based test removes at least one of its edges. This is the standard counterexample, stated
because §5.2 observes its pattern on the HM3 type-indicator logs (PCMCI+ keeps the chain head, routes the tail to the
head at lag 2–3, and returns the empty graph on Shopping). It is not an impossibility result for observational
estimators in general, and the binary write indicators do not literally obey these functional equations.

### 3.3 Discovery on interventional data

Two procedures produce a read set from replays. Both are run only on training episodes whose full read is correct;
where the full read is wrong no sufficient set is defined by this algorithm (a coverage restriction, not an
impossibility).

**Procedure A (randomised gates and an established discovery algorithm).** For a fixed episode and policy, draw T
independent gate vectors g^(t) ∈ {0,1}^n, replay, and record c^(t). The trials form a panel (g^(t), c^(t+1)); run
PCMCI+ (G² test) or GRACE on it and take the outcome's parent set as the read set. The gates are independent by
construction, so the parents of c are the records whose visibility changes the decision, up to the test's power. The
lag here is trial input to trial outcome, not the agent's own time axis; correctness labels come from the benchmark
oracle at training time.

**Procedure B (adaptive deletion).** `minimal_sufficient(H, S ↦ c(π_S))` is ddmin: try removing halves, then
quarters, …; restart at the coarsest granularity after a success; stop when no single block can be removed. With an
exact oracle and a sufficient start it terminates at a 1-minimal sufficient set (no single record can be dropped);
under Assumption 1 that set has no sufficient proper subset. It need not be the smallest or the unique such set. We
report measured replay counts (14–28 per episode at 18–500 records, growing like log n in the data of §5.3); no
general O(k log n) bound is claimed for this implementation, whose generic worst case is quadratic. For a
language-model π the oracle is the majority of k = 3 calls at temperature 0.

Procedure A is the established-algorithm version and is what §5.2 reports as discovery; Procedure B is the cheaper
deterministic alternative and the source of the frontier labels for the amortised selector.

### 3.4 Amortise

Fit p_θ(m ∈ F | φ(m, e)) on the discovered sets, where φ is parser-free and readable from the record and the state:
the typed path from the cue's object to the object the record's segment is keyed to; the record's kind and changed
fields; the segment's signature (the multiset of kind:type:fields it contains); the relation of the record's object to
the keyed object; the segment's recency among segments sharing its key, and among those sharing key and signature; the
record's position in its segment. The projection of the positive anchor paths to type pairs is a predicted type-path
template E_θ; it is not a mechanism graph. At decision time, without replays: reach the objects from the cue's object
over the *given* instance links whose type pair is in E_θ; read {m : p_θ ≥ τ} (record level) or the whole segment of
any such record (segment level); show the reached objects, the read records' referents and their one-hop links.

### 3.5 Localise

Given an anomalous decision on objects O in episode e with a suspect history H′, order candidate records by a prior
(records keyed to objects on the typed paths from the cue to O, nearest first, most recent first; then history
order); find by prefix doubling and binary search the shortest prefix whose replacement by its reference version
restores the reference decision; return its last record. The logarithmic count holds when restoration is monotone in
the prefix length, which is the single-corruption setting of §5.4; with several interacting corruptions the returned
record is one cause among others. In the reported runs the prior is the parser-assisted structural trace, which is
stated where the numbers are given; a clean-reference diff baseline is reported beside it.

### 3.6 What is learned, what is assumed, and how gains are attributed

- Learned from interventions the system performs: a sufficient read set per training episode (Procedure A or B), E_θ,
  p_θ.
- Assumed: a replayable log (S_0, I, H per episode) and a correctness score for replayed decisions at training time.
  Deployment needs neither: reads follow p_θ and E_θ over the given links.
- Never discovered: the instance links in S_0. Every selector in §5, including the parser-based one, reaches objects
  over them. §5.2 therefore reports a complete-type-graph control: a selector that keeps the links and the parser and
  drops the learned type filter. Where that control selects the same records, the gain is attributed to the links
  and the parser, not to discovery.
- Policy-specific: sufficient sets differ across policies (§5.5). Equality between the executor's frontier and the
  world's causal frontier is checked, not assumed: the type projection of executor frontiers reproduces the
  supervised template's edges at precision 1.0 (§5.2), where the template itself is a typed-path projection
  (stay → bundle) and the simulator's mechanism has dinner → bundle; both references are reported.
- Costs are measured: replays per training episode (§5.3), records and tokens read at decision time (§5.3),
  replays per incident (§5.4).
- Failure modes: (i) a noisy π makes the oracle noisy (vote; report disagreement); (ii) redundant witnesses make the
  sufficient set non-unique (p_θ pools over episodes); (iii) p_θ is imprecise on histories built to contain same-key
  distractors (§5.3); (iv) on a native task where the memory has no propagation structure the discovered graph
  selects the same inputs as an empty one (§5.7).

### 3.7 Relation to the controlled study and to the observational estimators

The controlled study (E0) makes one point in a simulated SCM: conditioning on the access regime identifies the gated
read edges where pooled estimators fail. Read interventions are the constructive form of that conditioning, with the
regime chosen rather than observed, and Procedure A feeds the result to the same established algorithms. The
observational estimators on the logs as written (pooled lagged regression, PCMCI+, GRACE over type write indicators)
are kept as the comparison that Observation 1 anticipates; where their recovered graphs reach the same objects over
the given links, the pipeline gives the same numbers, and the complete-graph control shows how much of that is the
links.
