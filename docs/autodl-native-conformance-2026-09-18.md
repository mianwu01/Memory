# AutoDL native memory conformance: complete LoCoMo history

The three native methods were launched concurrently with `DeepSeek-V4.1-Flash`
through the authorized AutoDL route. This is an author-interface and mechanism
check, not a reproduction of published LoCoMo scores.

The preselected conversation is `conv-30`, with all 369 turns. Its selection
predates calls: shortest complete conversation, original-order tie break.
Fixed question indices are 3, 0, 2 (categories 1, 2, 4) for Mem0 and LightMem,
plus index 79 (category 5) for A-Mem. This conversation has no category-3 probe.
Native ingestion, retrieval, prompts and parsing are retained.

Original run directory:
`results/development/autodl_native_validation_20260918/`.
`progress.json` is an automatically refreshed status snapshot, while each
arm's `validation.json` records its terminal outcome.

## Original observed outcomes

| Method | Ingested turns | Calls | Outcome |
|---|---:|---:|---|
| Mem0 | 369 / 369 | 372 | PASS; all 3 fixed QA probes completed; no failures |
| A-Mem | 44 / 369 | 154 | Native neighbor update exhausted its 1,000-token output cap |
| LightMem | 303 / 369 | 12 | Native metadata response looped on one JSON key until its 16,000-token cap |

Neither partial history is counted as a completed conformance check. Runtime
rejected `finish_reason=length` before accepting memory writes; upstream
fallback handling was also recorded as invalid. Failed runs remain intact.
Mem0's complete run used 3,205,742 input and 26,108 output tokens; this includes
369 native ingestion calls and 3 QA calls. This is execution/conformance
evidence, not an accuracy score or a claim about task superiority.

## A-Mem budget diagnostic

One additional request reused the exact failed neighbor-update messages, model,
temperature 0.7, and transport settings, changing only `max_tokens` from 1,000
to 16,000. It stopped normally after 1,289 output tokens with the same 1,816
input tokens. The unchanged author parser recovered context and tags for all
5 neighbors; the original truncated response covered only 4.

This supports treating output budget as a separately registered backbone
adaptation. It does not turn the original failed 369-turn run into a pass or
establish that a complete run with the new budget succeeds.

Evidence: `diagnostic_amem_16k/{request.json,response.json,report.json}`.

## LightMem format diagnostic

The original failed metadata request used 2,863 input tokens: a 5,601-character
system prompt and 4,240-character user content. Its 33,458-character response
repeated one malformed `source_id`-like key 1,453 times, including zero-width
characters. It contained two opening braces and no closing brace. This is an
unfinished JSON object with repetitive output, not concatenated JSON objects.

Two independent diagnostic replays retained the exact native request settings:
temperature 0.1, top_p 0.1, JSON object mode, 16,000 output tokens, and disabled
thinking. Outcomes:

- One stopped normally, producing valid JSON with 35 metadata entries.
- One again exhausted 16,000 tokens while repeating a malformed key 1,776 times.

The author's `clean_response` strips optional code fences and calls
`json.loads`; a decoding failure yields an empty list. It does not repair
concatenated or truncated objects. In the original run, Runtime rejected the
length finish first, then the author segment handler caught that exception and
returned empty metadata, which triggered the fallback rejection.

These replays diagnose output instability and are excluded from the original
native validation result. No successful replay is substituted for a failed
memory write.

Evidence: `diagnostic_lightmem_replays/{original_analysis.json,request.json,
replay_1.json,replay_2.json,report.json}`.

One final fixed compatibility diagnostic changed only `top_p` from 0.1 to 1.0,
retaining temperature 0.1, JSON mode, and the 16k cap. Again, one of two requests
returned 35 valid metadata entries; the other repeated a malformed key 1,999
times and exhausted the cap. Parameter search stops here. Neither JSON mode nor
this top_p change can be described as a demonstrated fix. Evidence is retained
in `diagnostic_lightmem_top_p_1/`.

## Separately registered A-Mem 16k full-history run

After the budget amendment was registered, a new complete `conv-30` validation
was launched in `results/development/autodl_native_validation_20260918_v2/amem`.
Its sibling `source_manifest.json` and `frozen_source/` preserve the nine source
files/amendment used at launch. The original 1k-cap failure above is retained
and is not relabeled as a run under the new configuration. A full-history result
must come from the new run's own `validation.json`.

The new run completed with **PASS** and process exit code 0: all 369 history
turns were written, all four fixed QA probes completed, and `failures` is empty.
Its 1,305 successful LLM calls comprise 1,297 history-writing calls and 8 calls
for the four native QA probes. All finished with `finish_reason=stop`. The final
snapshot contains 369 memories, and the write events cover rounds 0–368 once
each. The registered 16k budget adaptation applied to all these native A-Mem
calls; logs retain the upstream 1k budget alongside the effective budget.

API-returned usage totals are 1,773,269 input and 298,997 output tokens
(2,072,266 combined). Logs also retain 24 HTTP 429 attempts and 8 attempts with
no returned HTTP status before successful transport recovery. These are usage
and execution records, not a provider bill. Every request names
`DeepSeek-V4.1-Flash`; every response reports the provider model identifier
`DeepSeek-Flash`.

Terminal evidence is in the v2 run's `amem/validation.json`, `snapshot.json`,
`events.jsonl`, and `terminal_audit.json`. The audit checks history coverage,
fixed question indices/categories, normal completion, snapshot count and model
consistency, and records hashes of the underlying evidence. All checks pass.
This establishes native interface/mechanism conformance under the registered
budget adaptation; it does not reproduce published LoCoMo scores. Mem0 passes
its original complete-history check, while the original A-Mem and LightMem
failures remain preserved above.
