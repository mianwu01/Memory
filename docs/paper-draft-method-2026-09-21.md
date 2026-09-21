# Paper draft — Method section (2026-09-21, for Yujia to cut)

Companion to `docs/paper-draft-experiments-2026-09-20.md` (experiments) and
`docs/full-status-method-experiments-paper-2026-09-21.md` (status). Notation follows `causal_memory_formulation.tex`.
Every claim here is either proved below in two lines or is measured in the experiments; nothing is promised.

## 3 Method: the memory frontier by read interventions

### 3.1 Setting

An agent acts in episodes. In episode e it holds a history H = (m_1, …, m_n) of records written by earlier
interventions and their consequences, observes the current state S_0 and a cue I (a change it must respond to), and
emits a decision Y = π(S_0, I, R) where R ⊆ H is the set of records it reads. π is the policy: a deterministic executor
in the controlled setting, a language model in the deployed one. Correctness c(Y) ∈ {0,1} is scored against a
reference (§5). In the formulation of §2, H holds the memory carriers, the read set R is the access regime u at the
decision step (α_e(u) = 1 on the read edge of m_s iff m_s ∈ R), and the causal frontier F_t(Y) restricted to carriers
is the smallest set of records whose read edges must be active for Y to be determined (Lemma 1).

### 3.2 Reads are interventions

The access regime is set by the memory system. At replay time it can be set freely: re-run π on the logged
(S_0, I) with R = S for any S ⊆ H and score the result. This is the intervention do(g = 1_S) on the read gates, with
an assignment that is exogenous by construction, so the effect of any record on the decision is identified without
assumptions on the process that wrote the records.

**Definition 1 (sufficient, minimal, π-frontier).** S ⊆ H is *sufficient* for e if c(π(S_0, I, S)) = 1. It is
*minimal* if no proper subset is sufficient. A minimal sufficient set is a *π-frontier* F^π_e.

**Assumption 1 (monotone use).** If S is sufficient and S ⊆ T ⊆ H then T is sufficient.

Assumption 1 holds exactly for the executor (a later witness never removes a key it already has). For a language
model it is the statement that extra records do not hurt; its violation is the conflicting-evidence effect measured
in §5 and is handled by voting and by the 1-minimality fallback below.

**Proposition 1 (observational discovery fails on deterministic agent logs).** Let writes be deterministic in their
parents along a chain a → b → c (w_b = f(w_a), w_c = g(w_b)). Then w_c ⟂ w_b | w_a and w_c ⟂ w_a | w_b both hold, so
the observational distribution is unfaithful to the mechanism graph and any constraint-based method removes at least
one edge of the chain and may retain a → c at lag 2. *Proof.* Given w_a, w_b is a constant, so w_c is independent of
it; given w_b, w_c is a constant. Both independences are tested and both remove an edge. ∎ Agent logs are of this
kind: an agent's own writes are functions of what it read. §5.2 reports the instance: PCMCI+ and GRACE on a PCMCI+
skeleton keep the head of every chain and route the tail to the head at lag 2–3; on Shopping, where every write
follows the cart within one step, they return the empty graph.

**Proposition 2 (identification and replay cost).** Under Assumption 1, F^π_e is identified from the replay oracle
S ↦ c(π_S), and adaptive elimination (halving with backtracking; Algorithm 1) returns a minimal sufficient set with at
most O(|F^π_e| log n) oracle calls. Without Assumption 1 it returns a 1-minimal sufficient set (no single record can be
removed) with the same bound. *Proof.* Identification: g is set exogenously, so c(π_S) is the interventional outcome
and sufficiency of S is observed directly. Cost: with a monotone oracle, deciding which of k elements of an n-set are
necessary is group testing with defectives = the frontier; generalised binary splitting uses at most k log₂(n/k) + 2k
tests. Without monotonicity, ddmin's termination guarantee is 1-minimality with the same worst case. ∎

Proposition 2 is the reason the method does not depend on faithfulness: the intervention is on reads, and the
determinism of writes is irrelevant to it. Proposition 1 is the reason an observational estimator is the wrong tool
for the same logs.

### 3.3 Algorithm

**Algorithm 1 (discover).** For each training episode e with c(π_H) = 1: run `minimal_sufficient(H, S ↦ c(π_S))`
(ddmin: try removing halves, then quarters, …; restart at the coarsest granularity after a success; stop when no
single block can be removed). Output F^π_e and the replay count. For a language-model π the oracle is the majority
of k independent calls at temperature 0 (k = 3 in our runs); episodes with c(π_H) = 0 carry no sufficient set and are
skipped.

**Algorithm 2 (amortise).** Fit p_θ(m ∈ F | φ(m, e)) on the discovered sets, where φ is parser-free and readable
from the record and the state: the typed path from the cue's object to the object the record's segment is keyed to;
the record's kind and changed fields; the segment's signature (the multiset of kind:type:fields it contains); the
relation of the record's object to the keyed object; the segment's recency among segments sharing its key, and among
those sharing key and signature; the record's position in its segment. The projection of the positive anchor paths to
type pairs is the recovered type-level structure E_θ. At decision time, without replays: reach the objects from the
cue's object over instance links whose type pair is in E_θ; read {m : p_θ ≥ τ} (record level) or the whole segment of
any such record (segment level); show the reached objects, the read records' referents and their one-hop links.

**Algorithm 3 (localise).** Given an anomalous decision on objects O in episode e with a suspect history H′, order
candidate records by the structural trace (records keyed to objects on the typed paths from the cue to O, nearest
first, most recent first) followed by history order; find by prefix doubling and binary search the shortest prefix
whose replacement by its reference version restores the reference decision; return its last record. Cost O(log n)
replays; one replay when the prior puts the record first.

Forward reading and backward localisation are the same primitive (a replay under a chosen read set) applied in
opposite directions; both are amortised by the same p_θ and the same E_θ.

### 3.4 What is learned and what is assumed

- Learned from interventions the system performs: F^π_e per training episode (exact under Assumption 1), E_θ, p_θ.
- Assumed: a replayable log (S_0, I, H per episode) and a correctness score for the replayed decision at training
  time. Deployment needs neither: reads follow p_θ and E_θ.
- Actor-specific: F^π depends on π. For the executor it is the world's frontier (§5.2: it coincides with the
  interventional skeleton up to the edges whose child needs no read). For a language model it differs (§5.5): the
  model leans on different witnesses than the parser does, so its frontier is discovered from its own replays.
- Cost: discovery is O(k log n) replays per training episode (14–28 at 18–500 records, §5.2); decision time reads
  are the amortised model's selection; localisation is O(log n) replays per incident.
- Failure modes stated: (i) noisy π makes the oracle noisy (vote; report disagreement); (ii) redundant witnesses make
  the minimal set non-unique (p_θ pools over episodes; selection reads every high-probability record); (iii) p_θ can be
  imprecise on histories built to contain same-key distractors (§5.3 reports the read/accuracy trade-off).

### 3.5 Relation to the controlled study and to the observational estimators

The controlled study (§5.2, E0) makes the same point in a simulated SCM: conditioning on the access regime identifies
the gated read edges where pooled estimators fail. Read interventions are the constructive version of that
conditioning: the memory system chooses the regime. The observational estimators (pooled lagged regression, PCMCI+,
GRACE) are kept as the comparison that Proposition 1 predicts and §5.2 confirms; where their recovered graphs reach
the same objects, the forward and backward pipeline gives the same numbers, which is reported so that the reader can
see that the pipeline consumes reach and that the estimators differ in what they identify while selecting the same reads.
