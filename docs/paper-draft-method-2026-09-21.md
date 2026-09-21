# Paper draft — Method section (2026-09-21, for Yujia to cut)

Companion to `docs/paper-draft-experiments-2026-09-20.md` (experiments) and
`docs/full-status-method-experiments-paper-2026-09-21.md` (status). Notation follows `causal_memory_formulation.tex`.
Status after the alignment audit: this is an alternative read-intervention method,
not an approved replacement for Yujia's requested structure-discovery pipeline.
Empirical results must be attributed to the actual selector used. The protocol in
`structure-alignment-protocol-2026-09-21.md` controls the active claim set.

## 3 Method: the memory frontier by read interventions

### 3.1 Setting

An agent acts in episodes. In episode e it holds a history H = (m_1, …, m_n) of records written by earlier
interventions and their consequences, observes the current state S_0 and a cue I (a change it must respond to), and
emits a decision Y = π(S_0, I, R) where R ⊆ H is the set of records it reads. π is the policy: a deterministic executor
in the controlled setting, a language model in the actor experiments. Correctness c(Y) ∈ {0,1} is scored against a
reference (§5). The read set controls context visibility. A correctness-preserving
subset for one episode is not automatically the distribution-level separating set
in the causal-frontier lemma; redundancy, stochasticity and the conditioning set
must be addressed before asserting an equivalence.

### 3.2 Reads are interventions

The access regime is set by the memory system. At replay time it can be set freely: re-run π on the logged
(S_0, I) with R = S for any S ⊆ H and score the result. This is the intervention do(g = 1_S) on the read gates, with
an assignment chosen by the experimenter. Paired replays estimate effects of the
specified visibility change on the fixed policy, provided the other inputs are
held fixed and stochastic responses are sampled independently. They do not by
themselves recover the write mechanism or hidden intent.

**Definition 1 (sufficient, minimal, π-frontier).** S ⊆ H is *sufficient* for e if c(π(S_0, I, S)) = 1. It is
*minimal* if no proper subset is sufficient. A minimal sufficient set is a *π-frontier* F^π_e.

**Assumption 1 (monotone use).** If S is sufficient and S ⊆ T ⊆ H then T is sufficient.

Assumption 1 must be checked, not inferred from deterministic execution: a later
conflicting witness can overwrite the correct value without removing its key.
Majority voting can reduce oracle noise; it does not repair non-monotonicity.

**Observation 1 (a deterministic-chain faithfulness failure).** For a chain
a → b → c with w_b = f(w_a), w_c = g(w_b), both w_c ⟂ w_b | w_a and
w_c ⟂ w_a | w_b hold. Thus this distribution can violate faithfulness to the
chain. This is a standard counterexample, not a novel impossibility theorem for
all observational estimators. It also does not prove that the current binary
event indicators obey those exact functional equations. The observed PCMCI
failures are empirical findings whose encoding and assumptions must be reported.

**Algorithmic guarantee (exact deterministic oracle).** Starting from an accepted
set, the implemented deletion algorithm terminates at an accepted 1-minimal set:
no single record can be removed while preserving acceptance. Under monotonicity
this also rules out every sufficient proper subset. It need not be the smallest
cardinality set or a unique set. The previous general O(k log n) bound is
withdrawn: a group-testing theorem does not establish that bound for this ddmin
implementation with arbitrary or redundant sufficient sets. Report measured calls;
the generic worst-case bound for this deletion procedure is quadratic. A noisy
LLM needs fresh sufficiency and member-deletion validation before minimality is
claimed.

Read interventions and observational structure discovery answer different
questions. The former can validate a policy's reliance on visible records; the
latter targets relations in the logged process. A failure of one CI estimator is
not a reason to discard every observational approach.

### 3.3 Algorithm

**Algorithm 1 (discover).** For each training episode e with c(π_H) = 1: run `minimal_sufficient(H, S ↦ c(π_S))`
(ddmin: try removing halves, then quarters, …; restart at the coarsest granularity after a success; stop when no
single block can be removed). Output the accepted subset and replay count. It is
1-minimal for an exact deterministic oracle and a minimal frontier only under
the conditions stated above. For a language-model π the oracle is the majority
of k calls at temperature 0 (k = 3 in the historical runs). Episodes with
c(π_H) = 0 are skipped by this algorithm; under non-monotonicity a successful
subset can still exist, so this is a coverage restriction, not impossibility.

**Algorithm 2 (amortise).** Fit p_θ(m ∈ F | φ(m, e)) on the discovered sets, where φ is parser-free and readable
from the record and the state: the typed path from the cue's object to the object the record's segment is keyed to;
the record's kind and changed fields; the segment's signature (the multiset of kind:type:fields it contains); the
relation of the record's object to the keyed object; the segment's recency among segments sharing its key, and among
those sharing key and signature; the record's position in its segment. The projection of the positive anchor paths to
type pairs is the predicted type-path template E_θ, not a demonstrated causal
mechanism graph. At decision time, without replays: reach the objects from the
cue's object over instance links whose type pair is in E_θ; read {m : p_θ ≥ τ} (record level) or the whole segment of
any such record (segment level); show the reached objects, the read records' referents and their one-hop links.

**Algorithm 3 (localise).** Given an anomalous decision on objects O in episode e with a suspect history H′, order
candidate records by the structural trace (records keyed to objects on the typed paths from the cue to O, nearest
first, most recent first) followed by history order; find by prefix doubling and binary search the shortest prefix
whose replacement by its reference version restores the reference decision; return its last record.
The logarithmic query bound requires a monotone restoration predicate. Interpreting
that last record as the culprit additionally depends on the single-corruption setup;
it is not a general guarantee for noisy policies or multiple interacting corruptions.

Both procedures use replay, but the historical localisation implementation uses
the earlier parser-assisted structural trace as its ordering prior. Its result is
not evidence that the replay-fitted selector learned that prior. Clean-reference
replacement also requires a clean-reference/diff baseline.

### 3.4 What is learned and what is assumed

- Learned from interventions the system performs: F^π_e per training episode (exact under Assumption 1), E_θ, p_θ.
- Assumed: a replayable log (S_0, I, H per episode) and a correctness score for the replayed decision at training
  time. Deployment needs neither: reads follow p_θ and E_θ.
- Policy specificity: sufficient sets can differ across policies. Equality with a
  world-model causal frontier has not been established. Executor-supervised gains
  cannot be reported as gains from LLM-specific supervision.
- Cost: report measured replay and selection costs. Prefix localisation is
  logarithmic only when the restoration predicate is monotone in prefix length.
- Failure modes stated: (i) noisy π makes the oracle noisy (vote; report disagreement); (ii) redundant witnesses make
  the minimal set non-unique (p_θ pools over episodes; selection reads every high-probability record); (iii) p_θ can be
  imprecise on histories built to contain same-key distractors (§5.3 reports the read/accuracy trade-off).

### 3.5 Relation to the controlled study and to the observational estimators

E0 evaluates regime-conditioned estimation under a controlled SCM. Conditioning
and intervention are not generally equivalent operations; the HM3 event-kind
encoding is also different from E0's access regime. GRACE and PCMCI remain
candidate discovery components with explicitly reported assumptions and recovery
metrics. Equivalence of their downstream selections is an interface observation;
complete-type-graph controls determine whether the learned filtering contributes.
