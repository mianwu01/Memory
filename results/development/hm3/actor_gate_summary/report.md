# Flash thinking actor qualification

Development only; fixed seed 80, first 10 cases, 3 independent calls each. This is not a structure experiment or a comparison with historical non-thinking runs.

| version | correct / 30 | stable cases / 10 | truncations | thinking observed | gate |
|---|---:|---:|---:|---:|---|
| actor_gate_flash_thinking_v1 | 29 | 9 | 0 | 30/30 | PASS |

## Every frozen case

| case | actor_gate_flash_thinking_v1 |
|---|---:|
| travel-s80-dev-000 | 3/3 |
| travel-s80-dev-001 | 3/3 |
| travel-s80-dev-002 | 3/3 |
| travel-s80-dev-003 | 3/3 |
| travel-s80-dev-004 | 3/3 |
| travel-s80-dev-005 | 2/3 |
| travel-s80-dev-006 | 3/3 |
| travel-s80-dev-007 | 3/3 |
| travel-s80-dev-008 | 3/3 |
| travel-s80-dev-009 | 3/3 |

Fresh responses: 30; input/output tokens: 188178/604164.
Legacy-rate scenario: $6.3180; not an actual invoice.

The initial literal-ID gate failed because returned IDs differed only in case. The post-run acceptance report uses casefold for model identity; original IDs and the literal decision remain in JSON. See actor-gate-model-id-amendment-2026-09-22.md. No API responses were repeated.

Gate 2 is not passed. No discovery or audit calls were started. See native-task-screen-2026-09-22.md.
