# Workspace migration snapshot (2026-09-16)

This document is the entry point for continuing the project in another workspace. The
commit containing this file freezes the current source, protocols, reports, generated
artifacts, raw event records, accounting ledgers, partial-run status, and portable
memory stores. Use branch `claude/artifact-ordering-inzyf3` and record the checked-out
commit with `git rev-parse HEAD` before resuming any paid run.

## Current experiment state

The authoritative narrative status is [HANDOFF.md](HANDOFF.md), with the most recent
short report in [yujia-progress-2026-09-15.md](yujia-progress-2026-09-15.md). The
important boundaries at migration time are:

- `faithful_memory_aiaaa_v2` is stopped, not running in the background. The provider
  returned `403 INSUFFICIENT_BALANCE`; the TokenRhythm backup returned the equivalent
  `402`. Its frozen readiness artifact reports 5/16 development gates passed and the
  formal campaign remains 0/100.
- The completed v2 Travel gates are `noGcompact_101` and `query_only_101`. The remaining
  eight Travel arms did not complete. For native LoCoMo, Mem0 reached 102/369 history
  writes, A-Mem 31/369, and LightMem reached 369/369 writes before its offline update
  was interrupted; none of the three completed native QA.
- Do not restart an old supervisor or overwrite a failed directory. Once the account
  works again, first run a minimal generation probe, then register new technical
  recovery directories for the eleven failed gates. The scheduler's stop-on-failure
  amendment and all partial stores/events are preserved under
  `results/development/faithful_memory_aiaaa_v2/`.
- The earlier `p2_recent_baselines_tokenrhythm_v5` ten-arm run over IDs 111/112/113 is
  complete but explicitly exploratory. Its immutable combined view is
  `results/real/p2_recent_baselines_tokenrhythm_v5_completed/`; the original interrupted
  summary and its registered recovery remain separately preserved.
- The redesigned deterministic causal benchmarks, simulation v2, real-API six-arm v1,
  hidden-routing v2 audit, and the associated negative/partial verdicts are preserved.
  Hidden-mechanism v3 is a preregistration only and still awaits external double-check;
  it must not be described as an executed experiment.
- The 2026-09-14/15 meeting materials, figures, PDFs, bilingual outline, cost snapshots,
  and offline update bundle are committed with this snapshot. No message was sent to
  Yujia by this workspace.

Machine-readable resume anchors:

```text
results/development/faithful_memory_aiaaa_v2/readiness.json
results/development/faithful_memory_aiaaa_v2/campaign_state.json
results/development/faithful_memory_aiaaa_v2/dispatch_failure_policy_amendment.json
results/real/p2_recent_baselines_tokenrhythm_v5/recovery_state.json
results/real/p2_recent_baselines_tokenrhythm_v5_completed/result_view_manifest.json
```

## What the Git snapshot contains

The snapshot intentionally includes unfinished implementations as source files, not
only polished entry points. In particular it contains:

- `code/arena_recent_*.py` and the paired tests for the recent-memory campaign,
  recovery, reporting, delivery, and budget accounting;
- `code/faithful_*.py`, relay transport, acceptance/reporting tools, tests, and both
  dependency lists for the fidelity remediation;
- `code/causal_benchmarks/`, simulation/story audits, the API experiment tools, and all
  corresponding generated result trees;
- every non-ignored result/config/event/status/ledger artifact, including portable
  Qdrant SQLite databases needed to inspect partial runs;
- current manuscript sources, meeting slides, exported PDFs/PNGs/HTML, and handoff
  documents.

At snapshot validation time there were 1,001 previously untracked migration candidates
totalling about 228 MB. The largest single file was 17.2 MB, so no GitHub large-file
exception or Git LFS dependency is required.

## Deliberately excluded local state

These exclusions are intentional and must not be recovered by force-adding them:

- `deepseek_apikey.md` and `.env`: live credentials. Create a new local ignored
  credential file in the destination workspace; never copy a key into Git or a report.
- `.tmp/`: virtual environments, caches, temporary compilations, and disposable
  execution state. Rebuild environments from `code/requirements-recent-memory.txt` and
  `code/requirements-faithful-memory.txt`.
- `benchmarks/`: independent upstream Git checkouts. Recreate them at the pins below.
- `*.log`: verbose process/LaTeX logs. Authoritative raw model events, API errors,
  accounting, statuses, and reports are retained in JSON/JSONL/CSV. The logs contain no
  unique resume state.
- `results/**/.lock`: host-local Qdrant ownership markers. Copying them can incorrectly
  make a portable store appear busy; the SQLite database files themselves are included.

## Upstream checkout pins

The ignored benchmark directories were clean at audit time. Reclone each repository and
checkout the exact commit:

| local directory | upstream | commit |
|---|---|---|
| `benchmarks/AgenticMemory-paper` | `https://github.com/WujiangXu/AgenticMemory.git` | `0c8039f28fdcc08189a23c07a3437d9d2482f9c2` |
| `benchmarks/AgentPoison` | `https://github.com/AI-secure/AgentPoison.git` | `7236bf43148211918fd6b84d862495525798ab3c` |
| `benchmarks/A-mem` | `https://github.com/agiresearch/A-mem.git` | `ceffb860f0712bbae97b184d440df62bc910ca8d` |
| `benchmarks/LightMem` | `https://github.com/zjunlp/LightMem.git` | `8449d574df6bae1bdf3314a1564da65e2f37e046` |
| `benchmarks/mem0` | `https://github.com/mem0ai/mem0.git` | `c7ee362aff94a369af70f13f2b4f853f6793ff4c` |
| `benchmarks/mem0-memory-benchmarks` | `https://github.com/mem0ai/memory-benchmarks.git` | `4b61c5d31b9c668a12b4f5e78064248a02c82d2b` |
| `benchmarks/MemoryArena` | `https://github.com/ZexueHe/MemoryArena.git` | `6cd9de14b71915e39ac742a20dc33785e14b6aab` |
| `benchmarks/MINJA` | `https://github.com/dsh3n77/MINJA.git` | `a3ec8da0f7740b3fe629f6706e1c14296ee6861d` |

## Destination-workspace acceptance

After cloning and recreating the environment/checkouts, run the offline acceptance
suite before making API calls:

```bash
python3 -m compileall -q code
PYTHONPATH=code python3 -m unittest discover -s code -p 'test_*.py' -v
python3 -m json.tool \
  results/development/faithful_memory_aiaaa_v2/readiness.json >/dev/null
```

The migration source passed compilation and all 122 discovered unit tests on Python
3.10.16. The JSON check only confirms that the frozen blocked-state record is readable;
it is not authorization to resume paid work. Do not invoke `faithful_acceptance.py`
until every required development gate is complete: it creates a new acceptance record
and is intentionally fail-closed on the current partial state.

Before a paid recovery, also verify the destination branch and local credential route:

```bash
git status --short --branch
git rev-parse HEAD
python3 code/run_with_local_deepseek.py -- python3 -c 'print("route wrapper loaded")'
```

Do not run the full campaign merely to test the wrapper. Follow the recovery policy in
the current handoff and write into new directories so the committed partial evidence
remains immutable.
