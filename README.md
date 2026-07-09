# Causal Memory — a four-part web series

An ordered set of self-contained web artifacts that render the **Causal Memory** research
program — memory defined as identifiable temporal causal structure in the data-generating
process — from two source LaTeX documents (`causal_memory_formulation.tex` v0.1 and its
companion `causal_memory_onboarding.tex`).

Read **in order**:

| # | Artifact | What it covers | Live |
|---|----------|----------------|------|
| 01 | **The Thesis** | The one-paragraph claim, the two-layer program, the write–hold–read motif, trustworthy memory (D3), and positioning against the memory-agent literature. | https://claude.ai/code/artifact/666eab19-67ec-4271-9ddb-fdb51bf6a720 |
| 02 | **The Machinery** | SCMs and d-separation, the unrolled temporal graph, causal discovery, the identifiability impossibility / classes / two routes, MCC, and the selection confound. | https://claude.ai/code/artifact/fa83cd20-089d-49f5-86b7-4f563c94b7cb |
| 03 | **The Formulation v0.1** | Assumptions A1–A9, the causal-frontier lemma with its worked example and two-half proof, Observations 1–2, Conjectures 1–2, Predictions P1–P4, experiments E0/E1, positioning table, and open questions Q1–Q7. | https://claude.ai/code/artifact/6b553c0a-60ed-4663-990f-26b329f92e2f |
| 04 | **The Plan** | Requirement traceability R1–R9, status snapshot and state machine, the Q1–Q7 decision trees, the 14-day plan, the E0 runbook, the risk register, and the timeline to the Fall 2027 cycle. | https://claude.ai/code/artifact/89685ae4-ac33-4bc8-9e06-4629b8042201 |

## Files

```
artifacts/
  01-overview.html        # 01 · The Thesis
  02-theory-primer.html   # 02 · The Machinery
  03-formulation.html     # 03 · The Formulation v0.1
  04-execution.html       # 04 · The Plan
```

Each file is a self-contained fragment (title + inlined `<style>` + content). It renders both
as a published Artifact and when opened directly in a browser. The in-page series navigation
links to the live artifact URLs above.

## Design

One shared design system across all four pages:

- **Type** — a humanist serif (Iowan / Palatino / Charter / Georgia stack) for all reading
  text, paired with a monospace face for eyebrows, labels, identifiers, and code. Math is
  hand-typeset with styled spans; no external MathJax.
- **Color** — a cool "paper" ground with **carrier teal** as the accent (the color the source
  papers use for the memory carrier). Amber and rose carry status semantics, kept distinct from
  the accent. Full light and dark themes, driven by `prefers-color-scheme` with an explicit
  `data-theme` override.
- **Figures** — the key TikZ diagrams (the motif, the three d-separation motifs, the unrolled
  graph, the identifiability indeterminacy, the frontier worked example, the rotation/frozen
  block, the selection collider, the pipeline, and the project state machine) redrawn as clean
  inline SVG.

Every page was render-verified (light / dark / mobile, no console errors, no horizontal
overflow) and reviewed for fidelity against the source `.tex`.
