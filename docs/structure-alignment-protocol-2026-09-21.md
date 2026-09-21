# Structure discovery alignment: protocol and decision rules

This protocol supersedes the claim that the 9/20 GRACE bridge establishes the
benefit or causal correctness of discovery. Historical artifacts remain intact.
It implements the user's request to correct and redo misaligned work.

## Scientific target

Yujia's latest request is an explicit, established structure discovery procedure
whose output is used for memory, with representative utility and actionable audit
evidence. Calling a causal discovery library alone does not meet the empirical
requirement. Read intervention is a possible validation instrument or a separately
motivated change of estimand; it is not evidence of advisor approval for a pivot.

Keep these objects separate:

| Object | Source | Interpretation |
|---|---|---|
| Field transition mechanism | simulator `propagate` and field updates | controlled mechanism, not inferred from write indicators |
| Type write indicator | `tcd_logs.event_panel`, one row per record | observed variable used by the current TCD estimators |
| Lagged type dependency | fitted regression / PCMCI+ / GRACE | estimated relation on that indicator encoding |
| Typed path template | `LearnedGraph`, episode intervention outcomes | supervised propagation template, not a ground-truth direct edge |
| Instance links | `S0.objects[*].links` | given relational metadata, never discovered |
| Selected witness records | parser or generic precedent selector | retrieval result, not automatically a causal frontier |
| Policy read dependence | independent replay interventions on a fixed policy | dependence on visible context; not recovered private thoughts |

Travel's code makes bundle updates conditional on **dinner_changed**. The old
five-edge template projection contains stay->bundle because of a shortest linked
path. Preserve that reference as `template_reference`; report a separately named
`mechanism_reference` with dinner->bundle. Neither a type projection nor a
record-order lag is automatically a field-level causal graph. Shopping's template
projection is not promoted to a direct mechanism ground truth.

## A. Unchanged-task structure controls

- Domains: Travel and Shopping32. Historical test seeds: 30, 31, 32.
- Native, 100 mixed, c100 (Travel), and 500 mixed histories; 64 requested episodes
  per cell. Use existing augmentation and report all rejected episodes.
- Frozen graph artifacts: GRACE open, open x3, PCMCI-G2; no refitting on test data.
- Compare all-pairs type adjacency (no learned type filter), empty adjacency
  (query source only), and three predetermined type permutations (seeds 17, 29,
  43, resolve duplicate permutations deterministically).
- Cross each graph with parser and latest same-key precedent selection (n=2).
- Add full history, BM25-16, recency-16 as diagnostic references.
- Report deterministic task score, oracle-witness recall as a diagnostic, record
  and object counts, complete selection identity, and serialized prompt hashes.
- Matched random-record controls keep the reference objects and exactly its
  record count, and minimize token-length differences without seeing task labels.
  Token counts use cl100k_base as an explicitly named proxy, NOT DeepSeek's exact
  tokenizer. Report residuals; do not call non-matching cells token matched.
- Wrong-graph comparisons retain their natural budgets and also get a fixed-budget
  version (same object context and record count as the reference). Reference counts
  are diagnostic control information, not a deployable selection method.
- Complete-graph equivalence is a failing result for a claim about the benefit of
  learned type filtering, even when wrong/random controls fail badly.

## B. One bounded parser-free retrieval correction

Hypothesis fixed before new evaluation: latest same-key lookup often takes a
direct intervention on the witness object, which need not reveal its response to
an upstream change. Prefer segments initiated on another, linked object; retain
the whole segment to preserve the stimulus and response (including absent response).
Prefer the query object's own connected component when equally recent evidence
exists, and label component preference separately if tested. Do not use IDs,
oracle parameters, required_reads, correct actions, or augmentation provenance.

Development: seeds 0 and 1, 32 episodes each, native/c100/500 Travel and native/500
Shopping. Compare against the original n=2 precedent rule and the parser ceiling.
Freeze the implemented rule before evaluation on fresh seeds 40, 41, 42 (64
episodes per cell, training seeds 140, 141, 142 if any training is required).
No repeated feature search on those fresh seeds. A gain in this selector is a
retrieval/temporal-context result, not automatically a CD contribution.

## C. Actor verification and evidence boundaries

Actor calls require the existing service configuration, currently absent from this
checkout/environment. Prepare reproducible v1-only input manifests and compare
identical full messages before reusing any existing actor output. Changed messages
require fresh calls. Include full context, query-only, no-type-filter, discovered
graph, matched wrong graphs, BM25 and recency on the same episodes. Named memory
systems need actual adapters and the same protocol; raw embedding retrieval must
be labelled as such. Do not synthesize API results or substitute executor scores.

Record truncation for first and repair responses separately. Cost and output
completion effects cannot be presented as recovered-structure accuracy gains.
An audit of normal-looking correct decisions needs independent intervention
validation of reliance on a disallowed source; membership in one sufficient set
alone does not establish actual reliance or deception.

Execution update: the user supplied `api/api.txt`; a minimal connectivity check
returned `deepseek-v4-flash-0731` from the legacy AutoDL endpoint. Credentials stay
in the ignored file. The initial actor diagnostic uses the first 8 episodes of
seeds 30/31/32, Travel c100 and 500, all 12 declared arms, 16,384 output tokens,
v1/verbose, at most 8 concurrent requests, and a $40 accounting cap using the
existing cost assumptions. This is a small diagnostic, not a replacement for the
old 64-episode main table. Exact duplicate messages within an episode share one
call and are explicitly identified; they are not independent observations.

Interface correction discovered during the first actor pilot: 44/46 reference
inputs contained selected records about objects absent from visible state
(mean 5.39 missing referents). The raw TCD executor interface is insufficient for
an LLM and does not reproduce legacy `graph_closed`. That pilot was stopped;
its ledger remains in `actor_v1_pilot` as an interface diagnostic, not a method
comparison. Calls in flight at termination may not be represented in its ledger.
The replacement pilot (`actor_v1_closed`) adds each selected record's referent
and its one-hop context using the existing rule. Fixed-budget controls keep that
same object context and only choose records whose referents are visible. Record
count and token-proxy residual are still reported. This is an interface repair,
not a prompt or outcome-dependent selector change.

The replacement actor pilot has a $30 cap; the earlier interrupted diagnostic
cost is reported separately. After fixing the rule on development data, the
parser-free correction is exposed as `component_key2` in both existing HM3
runners. It remains explicitly a no-discovery baseline. No test-seed-driven
changes to its ranking rule are permitted.

Source audit follow-up: the first frozen executor-proposed suspect failed LLM
validation (all four conditions correct 3/3). Preserve it as a negative result.
A separate actor-based procedure freezes up to eight lexicographic correct pilot
inputs, qualifies the first with a fresh full-success/empty-failure pair at fixed
object context, discovers a read subset from this actor's own calls, and then
uses fresh triplicate full/subset/empty/member-deletion calls. Maximum 64 calls;
no candidate replacement after independent validation. The entire supplied
memory bundle receives an external controlled-source label. This tests reliance
on that source group; it does not infer source authorization, intent, or the
necessity of each subset member in the original redundant full history.

## D. Bounded discovery redesign pilot (development, then fresh-episode validation)

Instead of fitting an all-write-indicator graph and then relying on a supplied
component, test whether established TCD can recover **read-gate dependencies**.
For one fixed native HM3 episode, independently randomize each record's visibility
G_i(t) with probability .8; reset state/policy inputs and record replay correctness
Y(t+1). Fit PCMCI+ (ParCorr alpha .01) and the existing GRACE+G2 wrapper (lag 1,
default lambda, seed 0, 150 epochs/patience 30) to these observed series.
The variable set is fixed within this fit (one gate per record plus outcome), and
all candidate lagged relationships are offered to the discovery algorithm.

Freeze Travel development seed 0 episodes 0–2, 512 gate assignments, 64 independent
held-out contexts per gate for flip-effect diagnostics. These diagnostics are
empirical sensitivity references, not proof of a complete ground-truth graph.
Use the actual HM3 executor; no new simulated world or changed task. No LLM calls
or claim of LLM transfer. This is a candidate redesign to review with Yujia, not
evidence she has accepted a change from write structure to read structure.

After the frozen development pilot, evaluate the unchanged two estimators on
fresh Travel test seeds 50/51/52, episodes 0–3 each, with the same 512 training
gate assignments and 64 independent effect contexts. This is a per-episode fit,
not cross-episode amortized generalization. Add three fixed record-count and
token-proxy matched random read sets (17/29/43) per recovered parent set; keep
the entire object state fixed. No hyperparameter or encoding changes on these
12 episodes. Report all episodes, including zero-effect, rare-failure and
insufficient-selection cases. These remain executor results.

Post-hoc component attribution (declared after observing these 12 results):
reconstruct the identical training panels and run only the exact PCMCI-G²
skeleton used by GRACE (pc_alpha .05). Do not refit GRACE or tune a threshold.
Compare incoming outcome-parent sets, not just downstream accuracy. This is an
attribution diagnostic, not a retrospectively pre-registered new main comparison.
It returned identical sets on 12/12 episodes; both methods give 11/12 correct
selected-read replays. The earlier ParCorr comparator uses alpha .01, so that
comparison changes both CI test and threshold; it cannot isolate neural refinement.

Outcome-parent evaluation does not score the whole discovered graph. Because read
gates were randomized independently, inferred edges into those gates are spurious:
24 lagged edges across PCMCI-ParCorr fits and 91 across GRACE fits. Report these
explicitly; do not claim reliable recovery of the full temporal graph.

## Execution result index

The completed result and claim-scope handoff is
`yujia-alignment-results-2026-09-21.md`. The machine-generated report is
`../results/real/hm3/alignment/report.md`. All 24 historical control cells
(1,531 valid episode-condition evaluations) and 18 fresh reader cells
(1,152 evaluations) are complete. The closed-context actor diagnostic contains
430 unique completed inputs across 46 valid episode-condition pairs. Both frozen
source-audit attempts failed to establish the intended stable LLM audit result.

## Decision rule

Preserve reusable code and data. Withdraw unearned mechanism/identifiability and
discovery-benefit claims immediately. If A shows complete-graph equivalence, do
not headline these results as evidence that discovering type edges helps. B can
produce useful memory improvements but must be attributed to its actual design.
Rebuilding a full causal-memory claim then needs a setting/representation in which
learned dependencies distinguish valid from invalid read paths, with controls for
given links and parsers. Do not alter the benchmark merely to make a preferred
method win, and do not expand simulation as a substitute for the memory evidence.
