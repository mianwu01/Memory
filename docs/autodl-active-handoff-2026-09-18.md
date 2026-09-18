# AutoDL active run handoff

This is an operational checkpoint for continuation, not a completed-results report.

- User authorized completing all selected experiments at scale. Do not stop at launching jobs.
- Use absolute paths with shell workdir `/tmp`; workspace cwd can be slow.
- Python: `.tmp/memory-faithful-venv/bin/python`; wrapper `code/run_with_autodl.py`.
- Credential is ignored in `.secrets/autodl_api_token` (0600). Never print it. Exact-byte audit of 8,746 current text artifacts found no leaks.
- CPU only. No new permission needed. Never change the frozen Travel generation files while evaluation runs.

## Main live job

`results/real/autodl_travel_20260918`: PID284750, detached, log `campaign.log`.
1,950 cases, 50 episodes111–160, 3 repeats; implicit10 arms + explicit3.
Source/protocol frozen, all cases already registered.

Latest checkpoint: dispatch cap60, process ceiling128, reserving at most4 shared-route slots for native/development/transport recovery (total<=64). After14min at44, increased52 at1789739652; after another>13min and a full300s window with zero429 including successful retries, increased60 at1789740495. That window delivered1.698calls/s and1.57M recordedtokens/min; this is measured traffic, not a known providerTPM limit. Return44 ifTPM errors recur. Read `dispatch_control.json` for the authoritative current cap. Started64, raised96 after healthy6min real traffic, then provider returned explicit `Model tpm limit exceeded` and long requests slowed. Lowered48, then44, and applied one90-second shared-route cooldown under the existing flock schedule, without touching live streams or generation source. Record changes in `scheduling_amendments.jsonl`.

Agent `/root/baseline_readiness` monitors resources/errors and owns final strict reports. Do not raise128: the limiting resource is providerTPM, not localCPU/RAM. It is now authorized to run strict formal transport recoveries in batches of at most2 after active load reaches48 andTPM errors settle; semantic retries remain forbidden.

Read-only watcher PID405032 (`code/autodl_campaign_watch.py` + `autodl_health_snapshot.py`) is active; oldPID386918 stopped for the accounting-only monitoring update. It writes `monitoring/watcher.log` and `watcher_state.json`, takes health snapshots every5min, and invokes strict core scoring once the core is terminal, plus completion/strict-full/usage-coverage reporting once the full scope is terminal. Recovery changes trigger a fresh report. It never launches API calls or modifies main dispatch. `monitoring/watcher_control.json` with `{"stop":true}` stops only this watcher; flock prevents duplicates. Monitoring now counts failed transport attempts inside successful responses too:390 historical429 receipts, not merely the few terminal429 requests. Attempts lack absolute timestamps, so recent windows refer to the containing response-event time; they do not certify no in-flight retry.

Prespecified core view: `registered_core`, 900 cases (both query conditions ×3 structure arms ×50×3). Registered before any formal generation. Reuses same cases, no new calls. Core must be fully valid before scoring, full10-arm table separately requires full scope.

Report commands:

- `code/autodl_core_report.py --base <formal base>`
- `code/autodl_completion_report.py --base <formal base>` (coverage/errors/usage only)
- `code/autodl_report.py --base <formal base>` (strict full matrix)
- `code/autodl_usage_coverage.py --base <formal base>` (separate accounting sidecar; original completion reporter remains frozen by its analysis manifest)

`implicit/mem0/120/r0/attempt_0` is a semantic actor tool-argument JSON failure in `reasoning_history.remember`, before its `llm` event. Its returned payload/finish_reason/usage were not saved. The preceding logged response was valid and is not the failed response. Do not transport-retry this case or attribute the actor formatting failure to Mem0's memory parser. See `failure_diagnostics/implicit_mem0_120_r0_attempt0.json`; `usage_coverage.json` counts at least one unlogged returned response and reports known tokens as lower bounds. The full strict10-arm table is blocked by this invalid case; the separately registered core is still independently eligible if fully valid.

## Transport recovery

The first formal failure was `implicit/mem0/114/r0`: a broken API stream missing finish reason/usage, not model/JSON failure.
The frozen controller's retry admission misses wrapped RuntimeError without status. Keep frozen source unchanged.

New `code/autodl_transport_recovery.py` handles this using API-error receipt + exact traceback signature; no fabricatedHTTP code. It also accepts RemoteProtocolError and stream-opened RuntimeError receipts when a native caller swallowed the original exception message (no complete LLM result was emitted, before the semantic parser). It accepts ordinary transientHTTP/network failures; rejects auth, memory length, JSON semantic failures. Maximum3 total attempts, every original attempt retained and accounted. Recovery source is snapshotted by SHA; firstv1 source preserved separately.

First recovery finished successfully in exec session71083, case attempt1. Authorization/hash saved in its case folder. Do not repeat this completed recovery.
The original controller's in-memory failed count stays stale after independent recovery; use actual `case_state.json` and final collector. Once main dispatch drains, a no-retry `--resume` refresh can synchronize controller summary from disk without new calls.

Recovery invocation via wrapper:
`code/autodl_transport_recovery.py --base <formal base> --case implicit/mem0/114/r0 --workers 1`.
Without `--case`, inspect all registered cases; only eligible failures generate requests. Do not run duplicate controllers.

## Other live work

- Old-budget Travel dev: `results/development/autodl_travel_dev_v2`, exec86254/controllerPID213368 finished:11 complete,2failed. A-Mem failed under its old1000-token memory budget; dense failed at round7 after51 successful calls with an incomplete stream. All13 children loaded frozen old source before source transition. Core six cases complete. Old traces remain valid for their old config. Current source differs from that old freeze; do not run its recovery with changed generation source.
- New A-Mem16k Travel101: `results/development/autodl_amem_budget16k_dev`, initial exec56556 failed on a transport stream reconstruction at round7 memory_read after42 successful calls. Not a length failure. Recovery attempt1 through exec67138 finished complete:49 successfulLLM calls,8writes/7reads, original full-plan actor. Root has no active API recovery job. The helper permits this development family's changed scheduler/report hashes while requiring every actual generation module, provider, and graph to match its freeze; formal-family hashes remain fully strict.
- Agent `/root/travel_variant`: native A-Mem16k full369-turn conv check in `results/development/autodl_native_validation_20260918_v2/amem`, session28525. Old Mem0 PASS369/369+QA; old A-Mem1k FAIL44/369; old LightMem16k FAIL303/369. Full native checks are interface checks, not paper benchmark reproduction.
- LightMem same-request diagnostics: originalJSON mode1/2 looping; top_p1 also1/2 looping. No parameter search continues, original config retained.
- A-Mem16k adapts only memory calls on new provider. Exact development request needed1289 answer tokens and parsed5/5 neighbors; old1000 truncated. Actor/original routes unchanged;11 tests passed. Both native_limit and actual_limit logged. This differs from old provider's reasoning-mode budget failure.

## Completed results

MINJA: `results/real/minja_autodl_2026_09_18`, 8,400/8,400, validationPASS.
Trigger counts per360: ungated158, frequency_regime91, frequency_pooled91, random_matched93, oracle0, noop158, structure158.
Frequency-regime minus random ASR−0.56pp, 95% run-bootstrap[−6.11,+5.00].
True structure selected0 edges in all10 runs. Frequency localization63.9%precision vs poison prevalence60.4%; never call this graph recovery. Paired stats use10 independent writes, finite shared questionbank.
9,211 attempts including37 retries, 7,655,493 reported tokens, prices unknown.
Fixed run0 demo: `fixed_demo/index.html`, queriestest_10 andclean_test_0, repeat0. No cherry-picking or newAPI.

AgentPoison: `results/real/autodl_agentpoison_20260918`, complete352 trajectories, original criterionPASS.
Ungated9/72, noop6/72, gated0/72,3/3 blocks improved. Direct label-free localization1/2, frozencluster expansion2/2. Old modelFAIL preserved, split reused.
1,834 calls,0 API errors,1 native actor length retained. Input3,054,985/output106,269. Monetary price unknown, original zero cost fields explicitly only placeholders.
Clean retrievals unaffected0/24, so clean accuracy change is sampling variability.
Reports/provenance/label-stage audit complete.

## Remaining work

Current writing artifact: `docs/yujia-paper-outline-2026-09-18.md`,18 paragraphs with sentence sub-goals and evidence links (all18 references checked). Historical9/04 outline remains archived and links the new draft. The new draft explicitly distinguishes Travel's PCMCI+GRACE type graph fitted to training historical requirements, MINJA's regime-conditioned record estimator, and AgentPoison's frozen driver/cluster pipeline. Do not describe these as one learned graph or every branch as learning from generated actor traces. Abstract draft now has an updated evidence section and labels its old English text as an archive.

Finish main1,950 attempts and admissible transport recoveries; do not resample semantic failures. Obtain complete core/full reports if valid and separate completion/failure report otherwise.
Finish new-budget native/development runs. Update execution report, README/HANDOFF and abstract evidence with actual results. Do not reuse old39.55%, old tagged MINJA3/3, or claim one identical learned graph produced every result.
Main narrative must reflect whether learned edges add value beyond history lookup; MINJA's negative graph result cannot be hidden by frequency or AgentPoison outcomes.
