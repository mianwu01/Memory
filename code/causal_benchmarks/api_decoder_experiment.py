"""Real-API value-decoder experiment for the four causal-memory tasks.

This experiment closes one precise T1 gap: it replaces the deterministic value
decoder with an OpenAI-compatible chat endpoint while holding an oracle/runtime
write mask fixed.  It does *not* claim end-to-end causal discovery.  Gold is
used only after a response has been parsed to score the reconstructed state.

The first frozen phase is a dev-only decoder gate with two contexts:
``oracle_context`` (runtime mechanism reads) and ``full_context``.  Test-arm
selection experiments are admitted only if this gate demonstrates that the
endpoint can execute the four task mechanisms reliably.
"""

from __future__ import annotations

import argparse
import copy
import concurrent.futures
import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import causal_formal, dynamic_search, dynamic_shopping, dynamic_travel
from .common import changed_nodes, runtime_view


SCHEMA = "causal-api-decoder/v1"
PROTOCOL_SCHEMA = "causal-api-decoder-protocol/v1"
LEDGER_SCHEMA = "causal-api-decoder-call/v1"
FAILURE_POLICY_REVISION = "causal-api-failure-policy/v2"
DEFAULT_BASE_URL = "https://bboluo.com/v1"
DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_TOKENS = 12000
TASKS = (
    ("dynamic_travel", dynamic_travel, 0),
    ("dynamic_shopping", dynamic_shopping, 1),
    ("dynamic_search", dynamic_search, 2),
    ("causal_formal", causal_formal, 3),
)
_IO_LOCK = threading.Lock()


SYSTEM_PROMPT = """You are a deterministic structured-state executor.
Apply the supplied intervention using the task rules and current context.
Return exactly one JSON object and no markdown or explanation.
Return one update for every ALLOWED_WRITE_NODE and no other node.
Cells not listed in updates inherit their old values.
The required schema is:
{"schema_version":"causal-api-decoder/v1","episode_id":"...","updates":[{"node":"...","value":null}]}
Use JSON booleans/null, preserve object fields exactly, and do not rename nodes."""


TRAVEL_CARD = """TRAVEL RULES
- transfer.end_hour = flight.arrival_hour + transfer.duration.
- If the attraction is unavailable it is cancelled and its end hour is null.
- Otherwise it stays scheduled when transfer ends at least one hour before its start.
- Otherwise, if flexible and transfer_end + 1 + duration <= 22, it is rescheduled and
  attraction.end_hour = transfer_end + 1 + duration; otherwise it is cancelled/null.
- Dinner readiness is max(transfer.end_hour, attraction.end_hour when non-null).
- If dinner is unavailable it is cancelled and its end hour is null.
- Otherwise it stays scheduled when readiness <= dinner.start_hour.
- Otherwise, if flexible and readiness + 1 + duration <= 24, it is rescheduled and
  dinner.end_hour = readiness + 1 + duration; otherwise it is cancelled/null.
- Hotel readiness is max(transfer.end_hour, dinner.end_hour when non-null).
- hotel.checkin_status is on_time when readiness <= deadline, late_allowed when later
  and late_checkin is true, and missed otherwise."""


SEARCH_CARD = """SEARCH/PROVENANCE RULES
- Only active, independent documents whose source trust is medium or high count.
- High-trust evidence weight is 3, medium-trust weight is 1, low trust is ignored.
- A support document adds its weight and a refute document subtracts it.
- Claim status is verified for score >= 2, disproved for score <= -2, unresolved otherwise.
- An answer is YES/NO/UNCERTAIN for verified/disproved/unresolved respectively.
- A brief is publish-confirmed/publish-correction/hold-for-review for YES/NO/UNCERTAIN.
- Every derived value has the exact shape {"kind":"<kind>","value":"<value>"}.
- A claim node must be {"kind":"claim","value":"verified|disproved|unresolved"}.
- An answer node must be {"kind":"answer","value":"YES|NO|UNCERTAIN"}.
- A brief node must be {"kind":"brief","value":"publish-confirmed|publish-correction|hold-for-review"}.
Never output a bare string for a claim, answer, or brief node."""


SHOPPING_RULES = """SHOPPING RULES
- Apply availability, price, or policy intervention first.
- Whenever a cart item is unavailable or becomes incompatible after propagation,
  replace it with the cheapest available compatible item in the same slot, ordered by
  (catalog price, product id). This rule applies to root and downstream repairs alike.
- CPU socket constrains motherboard and cooler; motherboard memory generation constrains
  memory; motherboard form, cooler height, and GPU length constrain case.
- PSU capacity must be at least CPU watts + GPU watts + 120.
- In strict display mode, monitor input must match GPU output; adapters_allowed accepts any.
- Repair in topological order; update cart.<slot> and price.<slot> together.
- subtotal_before_monitor sums all slot prices except monitor; total_spend adds monitor;
  remaining_budget = constraint.max_total - total_spend. Round money to two decimals.
- Under hard_cap, if total exceeds max_total, choose the cheapest compatible monitor and
  recompute the ledger. Every slot remains populated: never remove the monitor or set its
  price to zero. If the cheapest compatible monitor still exceeds max_total, keep it and
  report a negative remaining_budget. Flexible budget never forces a downgrade."""


FORMAL_CARD = """FORMAL NOTEBOOK RULES
The selected history records contain exact formulas. Apply the intervention to a primitive,
then recompute allowed lemma/theorem nodes in topological order. A gated twist/field parent
contributes only when its corresponding enabled axiom is true. Preserve integer and boolean
types exactly."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _text_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, path)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _IO_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"malformed {path}:{line_number}") from error
    return rows


def _travel_context(view: Mapping[str, Any], write_nodes: Sequence[str]) -> list[str]:
    parents: dict[str, set[str]] = {}
    for edge in dynamic_travel.GRAPH:
        parents.setdefault(str(edge["target"]), set()).add(str(edge["source"]))
    context = set(write_nodes)
    frontier = list(write_nodes)
    while frontier:
        node = frontier.pop()
        for parent in parents.get(node, set()):
            if parent not in context:
                context.add(parent)
                frontier.append(parent)
    return sorted(context & set(view["memory_state"]))


def _filter_edges(
    edges: Iterable[Mapping[str, Any]], context: Sequence[str]
) -> list[dict[str, Any]]:
    selected = set(context)
    return [
        copy.deepcopy(dict(edge))
        for edge in edges
        if str(edge.get("source")) in selected and str(edge.get("target")) in selected
    ]


def _shopping_runtime_resources(view: Mapping[str, Any]) -> dict[str, Any]:
    """Build an outcome-free catalog/availability snapshot for both arms.

    Candidate availability is a runtime tool resource, not a memory-selector
    outcome.  It is therefore held fixed across compact and full contexts.  We
    expose only entities whose availability cell exists in this runtime view,
    which preserves the held-out-entity split.
    """

    state = view["memory_state"]
    intervention = view["query"]["intervention"]
    availability = {
        node.split(".", 1)[1]: bool(value)
        for node, value in state.items()
        if node.startswith("availability.")
    }
    target = str(intervention["node"])
    if target.startswith("availability."):
        availability[target.split(".", 1)[1]] = bool(intervention["new_value"])
    catalog = {
        item_id: copy.deepcopy(dynamic_shopping.CATALOG[item_id])
        for item_id in sorted(availability)
    }
    return {
        "schema_version": "shopping-runtime-resources/v1",
        "availability_timing": "after_query_intervention",
        "catalog": catalog,
        "availability": availability,
    }


def _task_packet(
    label: str, episode: Mapping[str, Any], view: Mapping[str, Any]
) -> dict[str, Any]:
    pre = view["memory_state"]
    intervention = view["query"]["intervention"]
    if label == "dynamic_travel":
        intervened = copy.deepcopy(pre)
        intervened[str(intervention["node"])] = copy.deepcopy(intervention["new_value"])
        post = dynamic_travel._recompute(intervened)
        write = changed_nodes(pre, post)
        context = _travel_context(view, write)
        oracle_records: list[dict[str, Any]] = []
        full_records = list(view["history"])
        oracle_edges = _filter_edges(dynamic_travel.GRAPH, context)
        full_edges = copy.deepcopy(dynamic_travel.GRAPH)
        card = TRAVEL_CARD
    elif label == "dynamic_shopping":
        post, reads, _tool_queries = dynamic_shopping.simulate(pre, intervention)
        write = changed_nodes(pre, post)
        context = sorted((set(reads) | set(write)) & set(pre))
        oracle_records = []
        full_records = list(view["history"])
        graph = dynamic_shopping.dependency_graph(pre)
        oracle_edges = _filter_edges(graph["edges"], context)
        full_edges = copy.deepcopy(graph["edges"])
        card = SHOPPING_RULES
        runtime_resources = _shopping_runtime_resources(view)
    elif label == "dynamic_search":
        graph = dynamic_search.parse_runtime_graph(view["history"], pre)
        post = dynamic_search.simulate_post_state(pre, intervention, graph)
        write = changed_nodes(pre, post)
        reads = dynamic_search.required_reads(pre, intervention, graph)
        context = sorted((set(reads) | set(write)) & set(pre))
        oracle_records = [
            record
            for record in view["history"]
            if any(node in str(record.get("text", "")) for node in context)
        ]
        full_records = list(view["history"])
        oracle_edges = _filter_edges(graph, context)
        full_edges = copy.deepcopy(graph)
        card = SEARCH_CARD
    elif label == "causal_formal":
        task = str(view["task"])
        post = causal_formal.simulate(task, pre, intervention)
        write = changed_nodes(pre, post)
        # A value decoder needs both the primitive leaves and every unchanged
        # intermediate/formula on the active execution path.  Primitive-only
        # ``required_reads`` is sufficient for an executable solver that owns
        # the formulas, but not for a language model receiving notebook records.
        context = causal_formal._execution_context(task, post, write)
        oracle_records = [
            record for record in view["history"] if str(record.get("node")) in context
        ]
        full_records = list(view["history"])
        formal_edges = causal_formal._edge_records(causal_formal.SPECS[task])
        oracle_edges = _filter_edges(formal_edges, context)
        full_edges = copy.deepcopy(formal_edges)
        card = FORMAL_CARD
    else:  # pragma: no cover
        raise ValueError(label)

    if label != "dynamic_shopping":
        runtime_resources = None

    # This assertion is evaluator-side protocol validation.  Neither the gold
    # affected set nor post-state is copied into a case or prompt.
    if write != sorted(episode["gold"]["affected_nodes"]):
        raise AssertionError(f"runtime oracle disagrees with evaluator for {episode['episode_id']}")
    return {
        "write_nodes": write,
        "oracle_context_nodes": context,
        "runtime_post_state": post,
        "oracle_records": oracle_records,
        "full_records": full_records,
        "oracle_edges": oracle_edges,
        "full_edges": full_edges,
        "task_card": card,
        "runtime_resources": runtime_resources,
    }


def _prompt_payload(
    episode: Mapping[str, Any],
    view: Mapping[str, Any],
    packet: Mapping[str, Any],
    context_nodes: Sequence[str],
    arm: str,
) -> dict[str, Any]:
    state = view["memory_state"]
    if arm not in {"oracle_context", "full_context"}:
        raise ValueError(f"unknown context arm: {arm}")
    prefix = "oracle" if arm == "oracle_context" else "full"
    return {
        "episode_id": str(episode["episode_id"]),
        "task": str(view["task"]),
        "task_rules": packet["task_card"],
        "query": view["query"]["text"],
        "intervention": view["query"]["intervention"],
        "allowed_write_nodes": packet["write_nodes"],
        "current_context_state": {node: state[node] for node in context_nodes},
        "selected_memory_records": packet[f"{prefix}_records"],
        "selected_dependency_edges": packet[f"{prefix}_edges"],
        "runtime_resources": packet["runtime_resources"],
    }


def build_dev_smoke_cases(
    *,
    episodes: int = 120,
    seed: int = 17,
    limit_per_task: int = 12,
    task_families: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, Any]]]:
    """Build gold-free prompt cases and retain episodes only for later scoring."""

    cases: list[dict[str, Any]] = []
    evaluator_episodes: dict[str, Mapping[str, Any]] = {}
    selected_families = set(task_families or [label for label, _, _ in TASKS])
    unknown = selected_families - {label for label, _, _ in TASKS}
    if unknown:
        raise ValueError(f"unknown task families: {sorted(unknown)}")
    for label, module, offset in TASKS:
        if label not in selected_families:
            continue
        dataset = module.generate_dataset(episodes=episodes, seed=seed + offset)
        selected = [row for row in dataset if row["split"] == "dev"][:limit_per_task]
        if len(selected) < limit_per_task:
            raise ValueError(
                f"{label} has only {len(selected)} dev episodes; requested {limit_per_task}"
            )
        for episode_index, episode in enumerate(selected):
            view = runtime_view(episode, training=False)
            if "gold" in view or "observed_transition" in view:
                raise AssertionError("runtime projection leaked evaluator outcome")
            packet = _task_packet(label, episode, view)
            contexts = {
                "oracle_context": packet["oracle_context_nodes"],
                "full_context": sorted(view["memory_state"]),
            }
            evaluator_episodes[str(episode["episode_id"])] = episode
            for arm, context_nodes in contexts.items():
                payload = _prompt_payload(episode, view, packet, context_nodes, arm)
                request_id = f"{label}:{episode['episode_id']}:{arm}"
                cases.append(
                    {
                        "request_id": request_id,
                        "task_family": label,
                        "task": str(view["task"]),
                        "episode_id": str(episode["episode_id"]),
                        "arm": arm,
                        # The paired compact/full calls share a frozen seed so
                        # backend sampling noise is not confounded with context.
                        "decoder_seed": seed * 100_000 + offset * 1_000 + episode_index,
                        "write_nodes": list(packet["write_nodes"]),
                        "context_nodes": list(context_nodes),
                        "payload": payload,
                        "prompt_sha256": _digest(
                            {"system": SYSTEM_PROMPT, "user": _canonical(payload)}
                        ),
                    }
                )
    return cases, evaluator_episodes


def protocol_manifest(
    cases: Sequence[Mapping[str, Any]],
    *,
    episodes: int,
    seed: int,
    limit: int,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_retries: int = 3,
) -> dict[str, Any]:
    public_cases = [
        {
            key: copy.deepcopy(case[key])
            for key in (
                "request_id",
                "task_family",
                "task",
                "episode_id",
                "arm",
                "decoder_seed",
                "write_nodes",
                "context_nodes",
                "prompt_sha256",
            )
        }
        for case in cases
    ]
    task_families = sorted({str(case["task_family"]) for case in cases})
    required_task_families = sorted(label for label, _, _ in TASKS)
    full_gate_scope = (
        task_families == required_task_families
        and limit == 12
        and len(cases) == len(required_task_families) * 2 * limit
    )
    return {
        "schema": PROTOCOL_SCHEMA,
        "phase": "dev_decoder_gate" if full_gate_scope else "engineering_calibration",
        "frozen_date": "2026-08-31",
        "development_revision": 9,
        "failure_policy_revision": FAILURE_POLICY_REVISION,
        "experiment": "value_decoder_given_runtime_oracle_write_mask",
        "episodes_generated_per_task": episodes,
        "dataset_seed": seed,
        "dev_episodes_per_task": limit,
        "task_families": task_families,
        "arms": ["oracle_context", "full_context"],
        "runtime": {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "api_retries": api_retries,
            "response_format": "json_object",
        },
        "gold_access": "protocol assertion and post-generation scoring only; never prompt-visible",
        "outcome_isolation": "runtime_view(training=False)",
        "runtime_resource_policy": (
            "Outcome-free task resources are identical across context arms. Shopping "
            "receives the post-intervention availability snapshot and only catalog "
            "entities present in the runtime state; simulator tool-query outcomes are "
            "not disclosed."
        ),
        "decoder_gate": {
            "semantic_coverage_min": 1.0,
            "episode_success_min": 0.80,
            "rule": "both arms must meet both thresholds on every task before test API work",
        },
        "invalid_response_policy": (
            "Transport, empty, truncated, JSON-syntax, and type-level schema failures are "
            "retried with the identical prompt and decoder seed. Identity, node-name, "
            "duplicate-node, and exact update-node-set violations in otherwise structurally "
            "valid JSON are terminal semantic contract failures: they are scored once and "
            "never retried. Unresolved engineering failures reduce semantic coverage and "
            "are not semantic zeroes."
        ),
        "cases": public_cases,
        "case_manifest_sha256": _digest(public_cases),
    }


def _no_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class RetryableResponseError(ValueError):
    """An engineering-format failure covered by the frozen retry budget."""

    def __init__(self, message: str, *, failure_kind: str) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind


def _retryable_response_error(message: str, *, failure_kind: str) -> None:
    raise RetryableResponseError(message, failure_kind=failure_kind)


def parse_decoder_response(
    text: str,
    *,
    episode_id: str,
    write_nodes: Sequence[str],
    pre_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse one response with lossless syntax recovery and strict semantics.

    Markdown fences or non-JSON framing are removed deterministically.  Values,
    node names and object structure are never guessed or repaired by another
    model call, so a recovered response preserves the endpoint's exact answer.
    """

    stripped = text.strip()
    if not stripped:
        _retryable_response_error("empty response", failure_kind="empty")
    parse_mode = "direct_json"
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) < 3:
            _retryable_response_error(
                "empty fenced response", failure_kind="json_syntax"
            )
        stripped = "\n".join(lines[1:-1]).strip()
        if stripped.lower().startswith("json\n"):
            stripped = stripped[5:].strip()
        if not stripped:
            _retryable_response_error("empty fenced response", failure_kind="empty")
        parse_mode = "lossless_fence_unwrap"
    try:
        payload = json.loads(stripped, object_pairs_hook=_no_duplicate_object)
    except json.JSONDecodeError as error:
        first, last = stripped.find("{"), stripped.rfind("}")
        if first < 0 or last <= first or (first == 0 and last == len(stripped) - 1):
            raise RetryableResponseError(
                f"invalid JSON: {error.msg}", failure_kind="json_syntax"
            ) from error
        prefix, suffix = stripped[:first].strip(), stripped[last + 1 :].strip()
        if "{" in prefix or "}" in suffix:
            _retryable_response_error(
                "response contains ambiguous multiple JSON objects",
                failure_kind="json_syntax",
            )
        stripped = stripped[first : last + 1]
        parse_mode = "lossless_object_extract"
        try:
            payload = json.loads(stripped, object_pairs_hook=_no_duplicate_object)
        except (json.JSONDecodeError, ValueError) as nested_error:
            raise RetryableResponseError(
                f"invalid JSON: {str(nested_error)[:240]}",
                failure_kind="json_syntax",
            ) from nested_error
    except ValueError as error:
        raise RetryableResponseError(
            str(error), failure_kind="json_syntax"
        ) from error
    if not isinstance(payload, dict):
        _retryable_response_error(
            "top-level response must be an object", failure_kind="type_schema"
        )
    expected_keys = {"schema_version", "episode_id", "updates"}
    if set(payload) != expected_keys:
        _retryable_response_error(
            f"top-level keys must equal {sorted(expected_keys)}",
            failure_kind="type_schema",
        )
    if not isinstance(payload["schema_version"], str):
        _retryable_response_error(
            "schema_version must be a string", failure_kind="type_schema"
        )
    if not isinstance(payload["episode_id"], str):
        _retryable_response_error(
            "episode_id must be a string", failure_kind="type_schema"
        )
    if not isinstance(payload["updates"], list):
        _retryable_response_error("updates must be a list", failure_kind="type_schema")
    contract_errors: list[str] = []
    if payload["schema_version"] != SCHEMA:
        contract_errors.append("wrong schema_version")
    if payload["episode_id"] != episode_id:
        contract_errors.append("wrong episode_id")
    updates: dict[str, Any] = {}
    for row in payload["updates"]:
        if not isinstance(row, dict) or set(row) != {"node", "value"}:
            _retryable_response_error(
                "each update must contain exactly node and value",
                failure_kind="type_schema",
            )
        node = row["node"]
        if not isinstance(node, str):
            _retryable_response_error(
                "update node must be a string", failure_kind="type_schema"
            )
        if node not in pre_state:
            contract_errors.append(f"unknown state node: {node!r}")
        if node in updates:
            contract_errors.append(f"duplicate update node: {node}")
            continue
        value = row["value"]
        previous = pre_state.get(node)
        if node in pre_state and value is not None and previous is not None:
            if isinstance(previous, float) and isinstance(value, (int, float)) and not isinstance(value, bool):
                value = float(value)
            elif type(value) is not type(previous):
                _retryable_response_error(
                    f"type mismatch for {node}: {type(value).__name__} vs {type(previous).__name__}",
                    failure_kind="type_schema",
                )
        updates[node] = value
    if set(updates) != set(write_nodes):
        contract_errors.append(
            "update-node set does not exactly match allowed_write_nodes"
        )
    return {
        "updates": updates,
        "payload": payload,
        "parse_mode": parse_mode,
        "semantic_contract_valid": not contract_errors,
        "semantic_contract_errors": contract_errors,
    }


@dataclass(frozen=True)
class APIConfig:
    model: str
    base_url: str
    temperature: float = 0.0
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_seconds: float = 120.0
    retries: int = 3
    uncached_input_usd_per_million: float = 2.5
    cached_input_usd_per_million: float = 0.25
    output_usd_per_million: float = 10.0


def _call_api(
    case: Mapping[str, Any],
    config: APIConfig,
    ledger: Path,
    decoder_seed: int,
    response_validator: Callable[[str], Mapping[str, Any] | None] | None = None,
    prior_transport_events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    prior_transport_events = list(prior_transport_events)
    last_error = str(prior_transport_events[-1].get("error", "")) if prior_transport_events else ""
    last_failure_class = (
        str(prior_transport_events[-1].get("failure_class") or "transport")
        if prior_transport_events
        else "transport"
    )
    total_duration = sum(
        float(event.get("duration_seconds", 0.0)) for event in prior_transport_events
    )
    aggregate_usage = {
        "model_requested": config.model,
        "model_returned": "",
        "input_tokens": sum(int(event.get("input_tokens", 0)) for event in prior_transport_events),
        "cached_input_tokens": sum(
            int(event.get("cached_input_tokens", 0)) for event in prior_transport_events
        ),
        "output_tokens": sum(int(event.get("output_tokens", 0)) for event in prior_transport_events),
        "estimated_cost_usd": sum(
            float(event.get("estimated_cost_usd", 0.0)) for event in prior_transport_events
        ),
        "response_attempts": 0,
    }
    start_attempt = len(prior_transport_events) + 1
    for attempt in range(start_attempt, config.retries + 1):
        started = time.time()
        try:
            response = client.chat.completions.create(
                model=config.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _canonical(case["payload"])},
                ],
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                top_p=1,
                seed=decoder_seed,
                response_format={"type": "json_object"},
            )
            elapsed = time.time() - started
            total_duration += elapsed
            usage = response.usage
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = int(getattr(details, "cached_tokens", 0) or 0)
            cost = (
                (input_tokens - cached_tokens)
                * config.uncached_input_usd_per_million
                + cached_tokens * config.cached_input_usd_per_million
                + output_tokens * config.output_usd_per_million
            ) / 1_000_000
            finish_reason = str(response.choices[0].finish_reason or "")
            content = response.choices[0].message.content or ""
            incomplete_error = ""
            failure_class = "none"
            semantic_contract_errors: list[str] = []
            if not content.strip():
                incomplete_error = (
                    "EmptyResponse: "
                    f"finish_reason={finish_reason or 'missing'}, "
                    "empty_content=True"
                )
                failure_class = "empty"
            elif finish_reason != "stop":
                incomplete_error = (
                    "TruncatedCompletion: "
                    f"finish_reason={finish_reason or 'missing'}, "
                    "empty_content=False"
                )
                failure_class = "truncated"
            elif response_validator is not None:
                try:
                    validation = response_validator(content)
                    if validation is not None:
                        semantic_contract_errors = list(
                            validation.get("semantic_contract_errors", [])
                        )
                        if semantic_contract_errors:
                            failure_class = "semantic_contract"
                except RetryableResponseError as error:
                    failure_class = error.failure_kind
                    incomplete_error = (
                        f"EngineeringResponseError[{failure_class}]: "
                        f"{str(error)[:240]}"
                    )
                except ValueError as error:
                    # Backward-compatible validators may still raise plain
                    # ValueError for a structural/type-level schema failure.
                    failure_class = "type_schema"
                    incomplete_error = (
                        "EngineeringResponseError[type_schema]: "
                        f"{str(error)[:240]}"
                    )
            event = {
                "schema": LEDGER_SCHEMA,
                "failure_policy_revision": FAILURE_POLICY_REVISION,
                "request_id": case["request_id"],
                "attempt": attempt,
                "prompt_sha256": case["prompt_sha256"],
                "model_requested": config.model,
                "model_returned": str(response.model or ""),
                "decoder_seed": decoder_seed,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": cost,
                "duration_seconds": elapsed,
                "finish_reason": finish_reason,
                "response_sha256": _text_digest(content),
                "error": incomplete_error,
                "failure_class": failure_class,
                "semantic_contract_errors": semantic_contract_errors,
            }
            _append_jsonl(ledger, event)
            aggregate_usage["input_tokens"] += input_tokens
            aggregate_usage["cached_input_tokens"] += cached_tokens
            aggregate_usage["output_tokens"] += output_tokens
            aggregate_usage["estimated_cost_usd"] += cost
            aggregate_usage["response_attempts"] += 1
            aggregate_usage["model_returned"] = str(response.model or "")
            if incomplete_error:
                last_error = incomplete_error
                last_failure_class = failure_class
                if attempt < config.retries:
                    time.sleep(min(2 ** (attempt - 1), 20))
                    continue
                return {
                    "text": content,
                    "usage": aggregate_usage,
                    "api_attempts": attempt,
                    "api_duration_seconds": total_duration,
                    "error": last_error,
                    "failure_class": failure_class,
                }
            return {
                "text": content,
                "usage": aggregate_usage,
                "api_attempts": attempt,
                "api_duration_seconds": total_duration,
                "error": "",
                "failure_class": failure_class,
            }
        except Exception as error:  # transport/rate-limit/5xx; no parse retry
            elapsed = time.time() - started
            total_duration += elapsed
            last_error = f"{type(error).__name__}: {str(error)[:240]}"
            last_failure_class = "transport"
            _append_jsonl(
                ledger,
                {
                    "schema": LEDGER_SCHEMA,
                    "failure_policy_revision": FAILURE_POLICY_REVISION,
                    "request_id": case["request_id"],
                    "attempt": attempt,
                    "prompt_sha256": case["prompt_sha256"],
                    "model_requested": config.model,
                    "decoder_seed": decoder_seed,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "duration_seconds": elapsed,
                    "finish_reason": "error",
                    "response_sha256": "",
                    "error": last_error,
                    "failure_class": "transport",
                    "semantic_contract_errors": [],
                },
            )
            if attempt < config.retries:
                time.sleep(min(2 ** (attempt - 1), 20))
    return {
        "text": "",
        "usage": aggregate_usage,
        "api_attempts": config.retries,
        "api_duration_seconds": total_duration,
        "error": last_error,
        "failure_class": last_failure_class,
    }


def _execute_case(
    case: Mapping[str, Any],
    evaluator_episodes: Mapping[str, Mapping[str, Any]],
    *,
    config: APIConfig,
    ledger: Path,
    decoder_seed: int,
    prior_transport_events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    episode = evaluator_episodes[str(case["episode_id"])]
    def validate_response(text: str) -> Mapping[str, Any]:
        return parse_decoder_response(
            text,
            episode_id=str(case["episode_id"]),
            write_nodes=case["write_nodes"],
            pre_state=episode["memory_state"],
        )

    response = _call_api(
        case,
        config,
        ledger,
        decoder_seed,
        response_validator=validate_response,
        prior_transport_events=prior_transport_events,
    )
    parse_error = ""
    parsed: dict[str, Any] | None = None
    if not response["error"]:
        try:
            parsed = parse_decoder_response(
                response["text"],
                episode_id=str(case["episode_id"]),
                write_nodes=case["write_nodes"],
                pre_state=episode["memory_state"],
            )
        except ValueError as error:
            parse_error = str(error)[:300]
    semantic_contract_valid = (
        bool(parsed["semantic_contract_valid"]) if parsed is not None else None
    )
    semantic_contract_errors = (
        list(parsed["semantic_contract_errors"]) if parsed is not None else []
    )
    post = copy.deepcopy(episode["memory_state"])
    if parsed is not None:
        post.update(
            {
                node: value
                for node, value in parsed["updates"].items()
                if node in post
            }
        )
    gold_post = episode["gold"]["post_state"]
    write_nodes = list(case["write_nodes"])
    value_accuracy = sum(
        node in parsed["updates"]
        and parsed["updates"][node] == gold_post[node]
        for node in write_nodes
    ) / max(1, len(write_nodes)) if parsed is not None else None
    semantic_contract_failure = bool(
        parsed is not None and not semantic_contract_valid
    )
    failure_class = (
        str(response.get("failure_class") or "engineering")
        if response["error"]
        else "semantic_contract" if semantic_contract_failure else "none"
    )
    return {
        "schema": "causal-api-decoder-result/v1",
        "failure_policy_revision": FAILURE_POLICY_REVISION,
        "request_id": str(case["request_id"]),
        "task_family": case["task_family"],
        "task": case["task"],
        "episode_id": case["episode_id"],
        "arm": case["arm"],
        "prompt_sha256": case["prompt_sha256"],
        "decoder_seed": decoder_seed,
        "write_nodes": write_nodes,
        "context_nodes": list(case["context_nodes"]),
        "api_error": response["error"],
        "parse_error": parse_error,
        "json_valid": parsed is not None,
        "parse_mode": parsed["parse_mode"] if parsed is not None else None,
        "semantic_scored": parsed is not None,
        "semantic_contract_valid": semantic_contract_valid,
        "semantic_contract_failure": semantic_contract_failure,
        "semantic_contract_errors": semantic_contract_errors,
        "engineering_failure": bool(response["error"]),
        "engineering_failure_kind": failure_class if response["error"] else None,
        "failure_class": failure_class,
        "write_value_accuracy": value_accuracy,
        "episode_success": (
            bool(semantic_contract_valid and post == gold_post)
            if parsed is not None
            else None
        ),
        "updates": parsed["updates"] if parsed is not None else None,
        "raw_response": response["text"],
        "usage": response["usage"],
        "api_attempts": response["api_attempts"],
        "api_duration_seconds": response["api_duration_seconds"],
    }


def _run_cases(
    cases: Sequence[Mapping[str, Any]],
    evaluator_episodes: Mapping[str, Mapping[str, Any]],
    *,
    config: APIConfig,
    ledger: Path,
    results_jsonl: Path,
    workers: int = 1,
) -> list[dict[str, Any]]:
    rows = _read_jsonl(results_jsonl)
    expected = {str(case["request_id"]): case for case in cases}
    if len(expected) != len(cases):
        raise ValueError("case manifest contains duplicate request ids")
    completed: dict[str, dict[str, Any]] = {}
    for row in rows:
        request_id = str(row.get("request_id", ""))
        if request_id not in expected:
            raise ValueError(f"results contain unexpected request id: {request_id!r}")
        if request_id in completed:
            raise ValueError(f"results contain duplicate request id: {request_id}")
        case = expected[request_id]
        if row.get("schema") != "causal-api-decoder-result/v1":
            raise ValueError(f"wrong result schema for {request_id}")
        if row.get("prompt_sha256") != case["prompt_sha256"]:
            raise ValueError(f"stale prompt hash for {request_id}")
        if row.get("decoder_seed") != case["decoder_seed"]:
            raise ValueError(f"stale decoder seed for {request_id}")
        usage = row.get("usage") or {}
        if usage and usage.get("model_requested") != config.model:
            raise ValueError(f"stale model result for {request_id}")
        completed[request_id] = row
    prior_by_request: dict[str, list[dict[str, Any]]] = {}
    for event in _read_jsonl(ledger):
        request_id = str(event.get("request_id", ""))
        if request_id not in expected:
            raise ValueError(f"ledger contains unexpected request id: {request_id!r}")
        case = expected[request_id]
        if event.get("schema") != LEDGER_SCHEMA:
            raise ValueError(f"wrong ledger schema for {request_id}")
        if event.get("prompt_sha256") != case["prompt_sha256"]:
            raise ValueError(f"stale ledger prompt hash for {request_id}")
        if event.get("decoder_seed") != case["decoder_seed"]:
            raise ValueError(f"stale ledger seed for {request_id}")
        if event.get("model_requested") != config.model:
            raise ValueError(f"stale ledger model for {request_id}")
        prior_by_request.setdefault(request_id, []).append(event)
    for request_id, events in prior_by_request.items():
        events.sort(key=lambda event: int(event.get("attempt", 0)))
        attempts = [int(event.get("attempt", 0)) for event in events]
        if attempts != list(range(1, len(events) + 1)):
            raise ValueError(f"non-contiguous preflight ledger attempts for {request_id}")
        if len(events) > config.retries:
            raise ValueError(f"preflight retry budget exceeded for {request_id}")
        if request_id not in completed:
            if any(str(event.get("finish_reason", "")) != "error" for event in events):
                raise ValueError(
                    f"orphan API response for {request_id}; fail closed instead of reissuing"
                )
            if len(events) >= config.retries:
                raise ValueError(f"transport retry budget exhausted for {request_id}")
    pending = [
        (index, case)
        for index, case in enumerate(cases)
        if str(case["request_id"]) not in completed
    ]

    def run_one(item: tuple[int, Mapping[str, Any]]) -> dict[str, Any]:
        _index, case = item
        return _execute_case(
            case,
            evaluator_episodes,
            config=config,
            ledger=ledger,
            decoder_seed=int(case["decoder_seed"]),
            prior_transport_events=prior_by_request.get(str(case["request_id"]), ()),
        )

    if workers <= 1:
        generated = map(run_one, pending)
    else:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        generated = executor.map(run_one, pending)
    try:
        for row in generated:
            _append_jsonl(results_jsonl, row)
            completed[str(row["request_id"])] = row
    finally:
        if workers > 1:
            executor.shutdown(wait=True)
    return [completed[str(case["request_id"])] for case in cases]


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return sum(values) / len(values) if values else None


def _engineering_failure_kind(api_error: str) -> str | None:
    """Infer a bounded category for legacy rows without additive v1 fields."""

    if not api_error:
        return None
    if "[json_syntax]" in api_error:
        return "json_syntax"
    if "[type_schema]" in api_error or "SchemaValidationError" in api_error:
        return "type_schema"
    if api_error.startswith("EmptyResponse"):
        return "empty"
    if api_error.startswith(("TruncatedCompletion", "IncompleteCompletion")):
        return "truncated"
    return "transport"


def _api_error_is_semantic_contract(api_error: str) -> bool:
    if not api_error:
        return False
    return any(
        marker in api_error
        for marker in (
            "update-node set does not exactly match allowed_write_nodes",
            "wrong episode_id",
            "wrong schema_version",
            "unknown state node",
            "duplicate update node",
        )
    )


def _ledger_failure_class(event: Mapping[str, Any]) -> str:
    """Classify additive and legacy ledger events without response recovery."""

    recorded = event.get("failure_class")
    if isinstance(recorded, str) and recorded:
        return recorded
    error = str(event.get("error", ""))
    if not error:
        return "none"
    semantic_markers = (
        "update-node set does not exactly match allowed_write_nodes",
        "wrong episode_id",
        "wrong schema_version",
        "unknown state node",
        "duplicate update node",
    )
    if any(marker in error for marker in semantic_markers):
        return "semantic_contract"
    if error.startswith(("EmptyResponse",)):
        return "empty"
    if error.startswith(("IncompleteCompletion", "TruncatedCompletion")):
        return "truncated"
    if "invalid JSON" in error or "does not contain a JSON object" in error:
        return "json_syntax"
    if "SchemaValidationError" in error or "[type_schema]" in error:
        return "type_schema"
    if str(event.get("finish_reason", "")) == "error":
        return "transport"
    return "type_schema"


def audit_and_rescore(
    rows: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    evaluator_episodes: Mapping[str, Mapping[str, Any]],
    ledger_rows: Sequence[Mapping[str, Any]],
    config: APIConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Reparse raw outputs and bind protocol, results, scoring, and usage ledger.

    The returned rows contain evaluator-recomputed metrics.  Stored metric
    fields are never trusted.  Any identity, score, response, model, attempt or
    usage mismatch makes the audit incomplete and therefore blocks the gate.
    """

    expected = {str(case["request_id"]): case for case in cases}
    errors: list[str] = []
    if len(expected) != len(cases):
        errors.append("protocol contains duplicate request ids")

    result_by_id: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        request_id = str(row.get("request_id", ""))
        if request_id in result_by_id:
            errors.append(f"duplicate result:{request_id}")
        result_by_id[request_id] = row
        if request_id not in expected:
            errors.append(f"unexpected result:{request_id}")

    ledger_by_id: dict[str, list[Mapping[str, Any]]] = {}
    for event in ledger_rows:
        request_id = str(event.get("request_id", ""))
        ledger_by_id.setdefault(request_id, []).append(event)
        if request_id not in expected:
            errors.append(f"unexpected ledger event:{request_id}")

    rescored: list[dict[str, Any]] = []
    for request_id, case in expected.items():
        row = result_by_id.get(request_id)
        if row is None:
            errors.append(f"missing result:{request_id}")
            continue
        episode = evaluator_episodes[str(case["episode_id"])]
        identity = {
            "schema": "causal-api-decoder-result/v1",
            "request_id": request_id,
            "task_family": case["task_family"],
            "task": case["task"],
            "episode_id": case["episode_id"],
            "arm": case["arm"],
            "prompt_sha256": case["prompt_sha256"],
            "decoder_seed": case["decoder_seed"],
            "write_nodes": list(case["write_nodes"]),
            "context_nodes": list(case["context_nodes"]),
        }
        for key, value in identity.items():
            if row.get(key) != value:
                errors.append(f"result identity mismatch:{request_id}:{key}")
        if (
            "failure_policy_revision" in row
            and row.get("failure_policy_revision") != FAILURE_POLICY_REVISION
        ):
            errors.append(f"result failure policy mismatch:{request_id}")

        recorded_api_error = str(row.get("api_error", ""))
        raw_response = row.get("raw_response")
        if not isinstance(raw_response, str):
            errors.append(f"raw response is not text:{request_id}")
            raw_response = ""
        parsed: dict[str, Any] | None = None
        deterministic_parse_error = ""
        try:
            parsed = parse_decoder_response(
                raw_response,
                episode_id=str(case["episode_id"]),
                write_nodes=case["write_nodes"],
                pre_state=episode["memory_state"],
            )
        except ValueError as error:
            deterministic_parse_error = str(error)[:300]
        reclassified_legacy_semantic_error = bool(
            parsed is not None
            and not parsed["semantic_contract_valid"]
            and _api_error_is_semantic_contract(recorded_api_error)
        )
        if reclassified_legacy_semantic_error:
            errors.append(
                f"semantic response recorded as engineering failure:{request_id}"
            )
        api_error = "" if reclassified_legacy_semantic_error else recorded_api_error
        scorable = not api_error and parsed is not None
        post = copy.deepcopy(episode["memory_state"])
        if scorable:
            post.update(
                {
                    node: value
                    for node, value in parsed["updates"].items()
                    if node in post
                }
            )
        gold_post = episode["gold"]["post_state"]
        write_nodes = list(case["write_nodes"])
        value_accuracy = (
            sum(
                node in parsed["updates"]
                and parsed["updates"][node] == gold_post[node]
                for node in write_nodes
            )
            / max(1, len(write_nodes))
            if scorable
            else None
        )
        semantic_contract_valid = (
            bool(parsed["semantic_contract_valid"]) if scorable else None
        )
        semantic_contract_errors = (
            list(parsed["semantic_contract_errors"]) if scorable else []
        )
        semantic_contract_failure = bool(
            scorable and not semantic_contract_valid
        )
        engineering_failure_kind = _engineering_failure_kind(api_error)
        failure_class = (
            engineering_failure_kind
            if api_error
            else "semantic_contract" if semantic_contract_failure else "none"
        )
        legacy_derived = {
            "parse_error": deterministic_parse_error if not api_error else "",
            "json_valid": scorable,
            "parse_mode": parsed["parse_mode"] if scorable else None,
            "semantic_scored": scorable,
            "write_value_accuracy": value_accuracy,
            "episode_success": (
                bool(semantic_contract_valid and post == gold_post)
                if scorable
                else None
            ),
            "updates": parsed["updates"] if scorable else None,
        }
        additive_derived = {
            "semantic_contract_valid": semantic_contract_valid,
            "semantic_contract_failure": semantic_contract_failure,
            "semantic_contract_errors": semantic_contract_errors,
            "engineering_failure": bool(api_error),
            "engineering_failure_kind": engineering_failure_kind,
            "failure_class": failure_class,
        }
        for key, value in legacy_derived.items():
            if row.get(key) != value:
                errors.append(f"stored score mismatch:{request_id}:{key}")
        # The classifier fields are additive to the v1 row schema.  Historical
        # v1 rows remain auditable; newly generated rows must bind them.
        for key, value in additive_derived.items():
            if key in row and row.get(key) != value:
                errors.append(f"stored classification mismatch:{request_id}:{key}")

        events = sorted(
            ledger_by_id.get(request_id, []), key=lambda event: int(event.get("attempt", 0))
        )
        if not events:
            errors.append(f"missing ledger:{request_id}")
        attempts = [int(event.get("attempt", 0)) for event in events]
        if attempts != list(range(1, len(events) + 1)):
            errors.append(f"non-contiguous ledger attempts:{request_id}")
        if len(events) > config.retries:
            errors.append(f"retry budget exceeded:{request_id}")
        for event in events:
            if event.get("schema") != LEDGER_SCHEMA:
                errors.append(f"ledger schema mismatch:{request_id}")
            if event.get("prompt_sha256") != case["prompt_sha256"]:
                errors.append(f"ledger prompt mismatch:{request_id}")
            if event.get("decoder_seed") != case["decoder_seed"]:
                errors.append(f"ledger seed mismatch:{request_id}")
            if event.get("model_requested") != config.model:
                errors.append(f"ledger requested model mismatch:{request_id}")
            if (
                "failure_policy_revision" in event
                and event.get("failure_policy_revision") != FAILURE_POLICY_REVISION
            ):
                errors.append(f"ledger failure policy mismatch:{request_id}")
            finish_reason = str(event.get("finish_reason", ""))
            response_sha256 = event.get("response_sha256")
            if finish_reason == "error":
                if response_sha256 != "":
                    errors.append(f"transport event has response hash:{request_id}")
            elif not isinstance(response_sha256, str) or len(response_sha256) != 64:
                errors.append(f"response hash missing:{request_id}")
        for event in events[:-1]:
            if not event.get("error"):
                errors.append(f"successful nonfinal attempt:{request_id}")
            if _ledger_failure_class(event) == "semantic_contract":
                errors.append(f"semantic response was retried:{request_id}")
        response_events = [
            event for event in events if str(event.get("finish_reason", "")) != "error"
        ]
        returned_models = {
            str(event.get("model_returned", ""))
            for event in response_events
            if event.get("model_returned")
        }
        if response_events and returned_models != {config.model}:
            errors.append(f"ledger returned model mismatch:{request_id}")
        if events:
            final_has_error = bool(events[-1].get("error"))
            if final_has_error != bool(api_error):
                errors.append(f"ledger/result final status mismatch:{request_id}")
            if str(events[-1].get("finish_reason", "")) != "error" and events[-1].get(
                "response_sha256"
            ) != _text_digest(raw_response):
                errors.append(f"final response hash mismatch:{request_id}")
            recorded_failure_class = _ledger_failure_class(events[-1])
            if recorded_failure_class != failure_class:
                errors.append(f"ledger failure class mismatch:{request_id}")

        expected_usage = {
            "model_requested": config.model,
            "model_returned": config.model if response_events else "",
            "input_tokens": sum(int(event.get("input_tokens", 0)) for event in events),
            "cached_input_tokens": sum(
                int(event.get("cached_input_tokens", 0)) for event in events
            ),
            "output_tokens": sum(int(event.get("output_tokens", 0)) for event in events),
            "estimated_cost_usd": sum(
                float(event.get("estimated_cost_usd", 0.0)) for event in events
            ),
            "response_attempts": len(response_events),
        }
        usage = row.get("usage")
        if not isinstance(usage, dict):
            errors.append(f"missing aggregate usage:{request_id}")
            usage = {}
        for key, value in expected_usage.items():
            observed = usage.get(key)
            if isinstance(value, float):
                matches = isinstance(observed, (int, float)) and abs(float(observed) - value) < 1e-9
            else:
                matches = observed == value
            if not matches:
                errors.append(f"aggregate usage mismatch:{request_id}:{key}")
        if row.get("api_attempts") != (attempts[-1] if attempts else 0):
            errors.append(f"attempt count mismatch:{request_id}")
        expected_duration = sum(float(event.get("duration_seconds", 0.0)) for event in events)
        observed_duration = row.get("api_duration_seconds")
        if not isinstance(observed_duration, (int, float)) or abs(
            float(observed_duration) - expected_duration
        ) >= 1e-9:
            errors.append(f"duration mismatch:{request_id}")

        canonical = copy.deepcopy(dict(row))
        canonical["failure_policy_revision"] = FAILURE_POLICY_REVISION
        canonical["api_error"] = api_error
        if reclassified_legacy_semantic_error:
            canonical["recorded_api_error"] = recorded_api_error
        canonical.update(identity)
        canonical.update(legacy_derived)
        canonical.update(additive_derived)
        rescored.append(canonical)

    missing_ledgers = sorted(set(expected) - set(ledger_by_id))
    total_cost = sum(
        float(event.get("estimated_cost_usd", 0.0)) for event in ledger_rows
    )
    report = {
        "complete": not errors and len(rescored) == len(expected),
        "protocol_cases": len(expected),
        "results": len(result_by_id),
        "ledger_events": len(ledger_rows),
        "missing_ledger_request_ids": missing_ledgers,
        "errors": errors,
        "ledger_total_estimated_cost_usd": total_cost,
        "scoring_source": "raw_response reparsed; state metrics recomputed against evaluator gold",
    }
    return rescored, report


def summarize(
    rows: Sequence[Mapping[str, Any]],
    protocol: Mapping[str, Any],
    config: APIConfig,
    integrity_audit: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected_cases = {
        str(case["request_id"]): case for case in protocol.get("cases", [])
    }
    received: dict[str, Mapping[str, Any]] = {}
    duplicate_ids: list[str] = []
    for row in rows:
        request_id = str(row.get("request_id", ""))
        if request_id in received:
            duplicate_ids.append(request_id)
        received[request_id] = row
    missing_ids = sorted(set(expected_cases) - set(received))
    unexpected_ids = sorted(set(received) - set(expected_cases))
    mismatched_ids = sorted(
        request_id
        for request_id in set(expected_cases) & set(received)
        if received[request_id].get("prompt_sha256")
        != expected_cases[request_id].get("prompt_sha256")
        or received[request_id].get("task_family")
        != expected_cases[request_id].get("task_family")
        or received[request_id].get("arm") != expected_cases[request_id].get("arm")
        or received[request_id].get("decoder_seed")
        != expected_cases[request_id].get("decoder_seed")
    )
    manifest_complete = not (
        missing_ids or unexpected_ids or duplicate_ids or mismatched_ids
    ) and len(received) == len(expected_cases)
    expected_groups: dict[tuple[str, str], list[str]] = {}
    for request_id, case in expected_cases.items():
        expected_groups.setdefault(
            (str(case["task_family"]), str(case["arm"])), []
        ).append(request_id)
    matrix = {}
    for (task, arm), request_ids in sorted(expected_groups.items()):
        items = [received[request_id] for request_id in request_ids if request_id in received]
        valid = [row for row in items if row["semantic_scored"]]
        unresolved_engineering = [
            row for row in items if not bool(row.get("semantic_scored"))
        ]
        semantic_contract_failures = [
            row
            for row in valid
            if row.get("semantic_contract_failure") is True
            or row.get("failure_class") == "semantic_contract"
            or row.get("semantic_contract_valid") is False
        ]
        expected_count = len(request_ids)
        group_missing = sorted(set(request_ids) - set(received))
        matrix.setdefault(task, {})[arm] = {
            "calls_expected": expected_count,
            "calls_received": len(items),
            "calls_missing": len(group_missing),
            "missing_request_ids": group_missing,
            "received_coverage": (
                len(items) / expected_count if expected_count else None
            ),
            "semantic_rows": len(valid),
            "semantic_coverage": (
                len(valid) / expected_count if expected_count else None
            ),
            "raw_json_validity": sum(
                row.get("parse_mode") == "direct_json" for row in items
            ) / len(items) if items else None,
            "raw_json_validity_received_only": sum(
                row.get("parse_mode") == "direct_json" for row in items
            ) / len(items) if items else None,
            "losslessly_recovered_responses": sum(
                row.get("parse_mode") in {
                    "lossless_fence_unwrap",
                    "lossless_object_extract",
                }
                for row in items
            ),
            "write_value_accuracy_valid_only": _mean(valid, "write_value_accuracy"),
            "episode_success_valid_only": _mean(valid, "episode_success"),
            "input_tokens": sum(int(row.get("usage", {}).get("input_tokens", 0)) for row in items),
            "cached_input_tokens": sum(
                int(row.get("usage", {}).get("cached_input_tokens", 0)) for row in items
            ),
            "output_tokens": sum(int(row.get("usage", {}).get("output_tokens", 0)) for row in items),
            "estimated_cost_usd": sum(
                float(row.get("usage", {}).get("estimated_cost_usd", 0.0)) for row in items
            ),
            "api_duration_seconds": sum(
                float(row.get("api_duration_seconds", 0.0)) for row in items
            ),
            "unresolved_engineering_rows": sorted(
                str(row["request_id"]) for row in unresolved_engineering
            ),
            "unresolved_engineering_failures": len(unresolved_engineering),
            "semantic_contract_failure_rows": sorted(
                str(row["request_id"]) for row in semantic_contract_failures
            ),
            "semantic_contract_failures": len(semantic_contract_failures),
            # Legacy aliases remain for readers of the additive v1 summary.
            "unresolved_parse_failures": len(unresolved_engineering),
            "api_failures": sum(bool(row.get("api_error")) for row in items),
        }
    gate = protocol["decoder_gate"]
    task_pass = {
        task: all(
            row["semantic_coverage"] is not None
            and row["semantic_coverage"] >= gate["semantic_coverage_min"]
            and row["episode_success_valid_only"] is not None
            and row["episode_success_valid_only"] >= gate["episode_success_min"]
            for row in arms.values()
        )
        for task, arms in matrix.items()
    }
    required_tasks = {label for label, _, _ in TASKS}
    expected_groups = {
        (task, arm): 12
        for task in required_tasks
        for arm in ("oracle_context", "full_context")
    }
    observed_groups = {
        (task, arm): int(values["calls_expected"])
        for task, arms in matrix.items()
        for arm, values in arms.items()
    }
    full_gate_scope = (
        protocol.get("phase") == "dev_decoder_gate"
        and set(protocol.get("task_families", [])) == required_tasks
        and protocol.get("dev_episodes_per_task") == 12
        and observed_groups == expected_groups
    )
    expected_received_rows = [
        received[request_id]
        for request_id in expected_cases
        if request_id in received
    ]
    unresolved_engineering_ids = sorted(
        str(row["request_id"])
        for row in expected_received_rows
        if not bool(row.get("semantic_scored"))
    )
    semantic_contract_failure_ids = sorted(
        str(row["request_id"])
        for row in expected_received_rows
        if bool(row.get("semantic_scored"))
        and (
            row.get("semantic_contract_failure") is True
            or row.get("failure_class") == "semantic_contract"
            or row.get("semantic_contract_valid") is False
        )
    )
    semantic_rows = sum(
        bool(row.get("semantic_scored")) for row in expected_received_rows
    )
    return {
        "schema": "causal-api-decoder-summary/v1",
        "failure_policy_revision": FAILURE_POLICY_REVISION,
        "protocol_case_manifest_sha256": protocol["case_manifest_sha256"],
        "model_requested": config.model,
        "base_url": config.base_url,
        "matrix": matrix,
        "manifest_audit": {
            "complete": manifest_complete,
            "calls_expected": len(expected_cases),
            "calls_received_unique": len(received),
            "missing_request_ids": missing_ids,
            "unexpected_request_ids": unexpected_ids,
            "duplicate_request_ids": sorted(set(duplicate_ids)),
            "mismatched_request_ids": mismatched_ids,
        },
        "coverage": {
            "calls_expected": len(expected_cases),
            "calls_received": len(expected_received_rows),
            "calls_missing": len(missing_ids),
            "received_coverage": (
                len(expected_received_rows) / len(expected_cases)
                if expected_cases
                else None
            ),
            "semantic_rows": semantic_rows,
            "semantic_coverage": (
                semantic_rows / len(expected_cases) if expected_cases else None
            ),
        },
        "failure_classification": {
            "missing_request_ids": missing_ids,
            "unresolved_engineering_request_ids": unresolved_engineering_ids,
            "semantic_contract_failure_request_ids": semantic_contract_failure_ids,
            "unresolved_engineering_rows": len(unresolved_engineering_ids),
            "semantic_contract_failures": len(semantic_contract_failure_ids),
        },
        "integrity_audit": copy.deepcopy(
            dict(integrity_audit or {"complete": False, "errors": ["not supplied"]})
        ),
        "full_gate_scope_audit": {
            "complete": full_gate_scope,
            "required": "4 task families x 2 context arms x 12 dev episodes = 96 calls",
            "protocol_phase": protocol.get("phase"),
            "observed_expected_calls": sum(observed_groups.values()),
        },
        "task_decoder_gate_pass": task_pass,
        "all_task_decoder_gates_pass": (
            manifest_complete
            and full_gate_scope
            and bool(integrity_audit and integrity_audit.get("complete"))
            and bool(task_pass)
            and all(task_pass.values())
        ),
        "failure_accounting": (
            "Transport, empty, truncated, JSON-syntax, and type-schema failures consume "
            "the frozen retry budget; unresolved rows reduce coverage and are never zero-"
            "filled. Valid structurally typed JSON with an identity/node-set contract "
            "violation is scored once as an endpoint semantic failure and is not retried."
        ),
        "claim_boundary": (
            "This is a real-API value decoder conditioned on a runtime-oracle write mask "
            "and runtime-oracle execution context/active-ancestor closure. It is not "
            "end-to-end learned causal discovery or impact selection evidence."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--limit-per-task", type=int, default=12)
    parser.add_argument(
        "--task-family",
        action="append",
        choices=[label for label, _, _ in TASKS],
        help="restrict an engineering calibration to one or more task families",
    )
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--api-retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--results-jsonl", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    cases, evaluator_episodes = build_dev_smoke_cases(
        episodes=args.episodes,
        seed=args.seed,
        limit_per_task=args.limit_per_task,
        task_families=args.task_family,
    )
    generated_protocol = protocol_manifest(
        cases,
        episodes=args.episodes,
        seed=args.seed,
        limit=args.limit_per_task,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        api_retries=args.api_retries,
    )
    if args.prepare_only:
        if args.protocol.exists():
            existing = json.loads(args.protocol.read_text())
            if existing != generated_protocol:
                raise SystemExit("refusing to overwrite a different frozen protocol")
        else:
            _atomic_json(args.protocol, generated_protocol)
        print(json.dumps({
            "protocol": str(args.protocol),
            "cases": len(cases),
            "case_manifest_sha256": generated_protocol["case_manifest_sha256"],
        }, indent=2))
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not configured")
    if not args.protocol.is_file():
        raise SystemExit("frozen --protocol is required before API execution")
    frozen_protocol = json.loads(args.protocol.read_text())
    if frozen_protocol != generated_protocol:
        raise SystemExit("runtime cases do not match frozen protocol")
    for required in (args.results_jsonl, args.ledger, args.summary):
        if required is None:
            raise SystemExit("--results-jsonl, --ledger and --summary are required for API execution")
    config = APIConfig(
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        retries=args.api_retries,
    )
    order = list(cases)
    random.Random(args.seed + 991).shuffle(order)
    rows = _run_cases(
        order,
        evaluator_episodes,
        config=config,
        ledger=args.ledger,
        results_jsonl=args.results_jsonl,
        workers=args.workers,
    )
    rescored_rows, integrity_audit = audit_and_rescore(
        rows,
        order,
        evaluator_episodes,
        _read_jsonl(args.ledger),
        config,
    )
    report = summarize(
        rescored_rows,
        frozen_protocol,
        config,
        integrity_audit=integrity_audit,
    )
    _atomic_json(args.summary, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
