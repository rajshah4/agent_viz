from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import re
from typing import Any

from .models import (
    ActionType,
    EventSource,
    EventType,
    NormalizedEvent,
    PromptComposition,
    StepStatus,
)

LLM_SPAN_TYPES = {"LLM", "GENERATION", "MODEL"}
TOOL_SPAN_TYPES = {"TOOL", "FUNCTION", "FUNCTION_CALL"}
RETRIEVAL_HINTS = {"retrieve", "retrieval", "search", "grep", "find", "lookup"}
INSPECT_HINTS = {"read", "open", "view", "inspect", "cat", "list", "search", "grep", "find"}
EDIT_HINTS = {"edit", "write", "patch", "replace", "insert", "apply", "rewrite", "create"}
EXECUTE_HINTS = {"test", "pytest", "exec", "execute", "run", "bash", "shell", "command", "python", "make", "pip install"}
TEST_COMMAND_HINTS = {
    "pytest",
    "py.test",
    "python -m pytest",
    "python -m unittest",
    "unittest",
    "tox",
    "nose",
    "go test",
    "cargo test",
    "npm test",
    "pnpm test",
    "yarn test",
}
RETRY_HINTS = {"retry", "recover", "backoff", "rerun"}
WAIT_HINTS = {"wait", "sleep", "poll", "pause"}
OVERHEAD_HINTS = {"localfilestore", "base_state.json"}
FINALIZE_HINTS = {"submit", "final", "answer", "complete", "done", "finish"}
FILE_EDITOR_READ_COMMANDS = {"view"}
FILE_EDITOR_EDIT_COMMANDS = {"create", "str_replace", "insert", "undo_edit"}
FILE_EXTENSION_PATTERN = re.compile(
    r"(^|/|\\)([^/\\]+\.(py|js|ts|tsx|jsx|json|yml|yaml|toml|ini|md|txt|sh|rb|go|rs|java|c|cpp|h|hpp|ipynb|rst))$",
    re.IGNORECASE,
)
TEST_SUMMARY_PATTERN = re.compile(r"(?:(\d+) failed)?(?:, )?(?:(\d+) passed)?(?:, )?(?:(\d+) skipped)?(?:, )?(?:(\d+) deselected)?", re.IGNORECASE)


def parse_laminar_trace_payload(payload: Mapping[str, Any]) -> list[NormalizedEvent]:
    trace = _ensure_mapping(payload.get("trace"))
    spans_value = payload.get("spans")
    spans = [span for span in spans_value if isinstance(span, Mapping)] if isinstance(spans_value, Sequence) and not isinstance(spans_value, (str, bytes, bytearray)) else []

    if not trace and "data" in payload and isinstance(payload["data"], Mapping):
        nested = payload["data"]
        trace = _ensure_mapping(nested.get("trace"))
        spans_value = nested.get("spans")
        spans = [span for span in spans_value if isinstance(span, Mapping)] if isinstance(spans_value, Sequence) and not isinstance(spans_value, (str, bytes, bytearray)) else spans

    if not trace and not spans:
        raise ValueError("Laminar payload must contain a trace object or spans list")

    trace_id = str(
        _first_non_null(
            trace.get("id") if trace else None,
            trace.get("traceId") if trace else None,
            payload.get("traceId"),
            payload.get("run_id"),
            "laminar-run",
        )
    )
    trace_status = _coerce_status(_first_non_null(trace.get("status") if trace else None, payload.get("status")))

    events = [
        _parse_span(span, trace_id=trace_id, trace_status=trace_status)
        for span in spans
    ]
    events.sort(key=lambda event: ((event.timestamp_start or datetime.min.replace(tzinfo=timezone.utc)).timestamp(), event.step_id))

    if events:
        return events

    return [
        NormalizedEvent(
            run_id=trace_id,
            step_id=trace_id,
            action_type=ActionType.FINALIZE if trace_status == StepStatus.SUCCESS else ActionType.PLAN,
            source=EventSource.RUNTIME,
            event_type=EventType.MESSAGE,
            status=trace_status,
            timestamp_start=_parse_datetime(_first_non_null(trace.get("startTime"), trace.get("createdAt"))),
            timestamp_end=_parse_datetime(_first_non_null(trace.get("endTime"), trace.get("updatedAt"))),
            token_input=_coerce_int(_find_value(trace, "inputTokens", "promptTokens")),
            token_output=_coerce_int(_find_value(trace, "outputTokens", "completionTokens")),
            token_cached=_coerce_int(_find_value(trace, "cacheReadInputTokens", "cachedInputTokens")),
            cost_usd=_coerce_float(_find_value(trace, "totalCost", "costUsd")),
            metadata={"laminar_trace": dict(trace)},
        )
    ]


def parse_laminar_trace_responses(
    trace_response: Mapping[str, Any],
    spans_response: Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> list[NormalizedEvent]:
    trace = _ensure_mapping(trace_response.get("trace") if isinstance(trace_response, Mapping) else None) or _ensure_mapping(trace_response)
    if isinstance(spans_response, Mapping):
        raw_spans = spans_response.get("spans")
    else:
        raw_spans = spans_response
    payload = {"trace": trace, "spans": raw_spans}
    return parse_laminar_trace_payload(payload)


def _parse_span(span: Mapping[str, Any], *, trace_id: str, trace_status: StepStatus) -> NormalizedEvent:
    attributes = _ensure_mapping(span.get("attributes"))
    name = str(_first_non_null(span.get("name"), span.get("spanId"), "span"))
    span_type = str(_first_non_null(span.get("spanType"), span.get("type"), "DEFAULT"))
    tool_name = _extract_tool_name(span, attributes)
    command = _extract_command(span, attributes)
    file_paths = tuple(_extract_file_paths(span, attributes, command=command))
    observation_text = _extract_observation_text(span)
    status = _coerce_status(_first_non_null(span.get("status"), attributes.get("status"), trace_status.value))

    input_tokens = _coerce_int(
        _find_value(span, "inputTokens", "promptTokens", "tokenInput", "gen_ai.usage.input_tokens")
    )
    cached_tokens = _coerce_int(
        _find_value(
            span,
            "cacheReadInputTokens",
            "cachedInputTokens",
            "cachedPrefixTokens",
            "cachedTokens",
            "gen_ai.usage.cache_read_input_tokens",
        )
    )
    output_tokens = _coerce_int(
        _find_value(span, "outputTokens", "completionTokens", "tokenOutput", "gen_ai.usage.output_tokens")
    )
    total_cost = _coerce_float(_find_value(span, "totalCost", "costUsd", "gen_ai.usage.cost"))
    if not total_cost:
        total_cost = _coerce_float(_find_value(span, "inputCost", "gen_ai.usage.input_cost")) + _coerce_float(
            _find_value(span, "outputCost", "gen_ai.usage.output_cost")
        )

    prompt = _extract_prompt_composition(
        span,
        attributes,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
    )
    event_type = _infer_event_type(
        name=name,
        span_type=span_type,
        tool_name=tool_name,
        command=command,
        file_paths=file_paths,
        attributes=attributes,
        observation_text=observation_text,
    )
    action_type = _infer_action_type(
        name=name,
        span_type=span_type,
        tool_name=tool_name,
        command=command,
        file_paths=file_paths,
        event_type=event_type,
        status=status,
        observation_text=observation_text,
    )
    source = _infer_source(
        span_type=span_type,
        name=name,
        tool_name=tool_name,
        attributes=attributes,
    )

    tests_passed = _coerce_int(_find_value(span, "testsPassed", "passedTests", "passCount"))
    tests_failed = _coerce_int(_find_value(span, "testsFailed", "failedTests", "failCount"))
    test_count = _coerce_int(_find_value(span, "testCount", "testsRun", "numTests"))
    derived_passed = derived_failed = derived_total = 0
    if event_type == EventType.TEST_RUN or _looks_like_test_command(command or ""):
        derived_passed, derived_failed, derived_total = _extract_test_results(command, observation_text)
    if not tests_passed:
        tests_passed = derived_passed
    if not tests_failed:
        tests_failed = derived_failed
    if not test_count and derived_total:
        test_count = derived_total
    if not test_count and (tests_passed or tests_failed):
        test_count = tests_passed + tests_failed
    if event_type == EventType.TEST_RUN and not test_count:
        test_count = 1

    metadata = {
        "laminar_span_id": _first_non_null(span.get("spanId"), span.get("id"), name),
        "laminar_span_type": span_type,
        "laminar_path": _find_value(attributes, "lmnr.span.path", "spanPath", "path"),
        "command": command,
    }
    if span.get("input") is not None:
        metadata["input"] = span.get("input")
    if span.get("output") is not None:
        metadata["output"] = span.get("output")
    if attributes:
        metadata["attributes"] = dict(attributes)

    return NormalizedEvent(
        run_id=trace_id,
        step_id=str(_first_non_null(span.get("spanId"), span.get("id"), name)),
        parent_step_id=_coerce_optional_str(_first_non_null(span.get("parentSpanId"), span.get("parentId"))),
        action_type=action_type,
        source=source,
        event_type=event_type,
        status=status,
        timestamp_start=_parse_datetime(_first_non_null(span.get("startTime"), span.get("start_time"), span.get("createdAt"))),
        timestamp_end=_parse_datetime(_first_non_null(span.get("endTime"), span.get("end_time"), span.get("updatedAt"))),
        tool_name=tool_name,
        file_paths=file_paths,
        token_input=input_tokens,
        token_output=output_tokens,
        token_cached=cached_tokens,
        cost_usd=total_cost,
        test_count=test_count,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        prompt_composition=prompt,
        metadata=metadata,
    )


def _infer_event_type(
    *,
    name: str,
    span_type: str,
    tool_name: str | None,
    command: str | None,
    file_paths: tuple[str, ...],
    attributes: Mapping[str, Any],
    observation_text: str,
) -> EventType:
    text = _joined_text(name, span_type, tool_name, command, observation_text, _find_value(attributes, "operation", "kind"))
    if _is_internal_overhead_span(name=name, command=command, file_paths=file_paths):
        return EventType.TOOL_CALL
    if span_type.upper() in LLM_SPAN_TYPES:
        return EventType.LLM_CALL
    if tool_name == "file_editor":
        action_command = _normalize_action_command(command)
        if action_command in FILE_EDITOR_READ_COMMANDS:
            return EventType.FILE_READ
        if action_command in FILE_EDITOR_EDIT_COMMANDS:
            return EventType.FILE_EDIT
    if tool_name == "terminal" and _looks_like_test_command(text):
        return EventType.TEST_RUN
    if _has_hint(text, WAIT_HINTS):
        return EventType.WAIT
    if _has_hint(text, RETRY_HINTS):
        return EventType.RETRY
    if file_paths and _has_hint(text, EDIT_HINTS):
        return EventType.FILE_EDIT
    if file_paths and _has_hint(text, INSPECT_HINTS | RETRIEVAL_HINTS):
        return EventType.FILE_READ
    if _looks_like_test_command(text) or _find_value(attributes, "testsPassed", "testsFailed", "testCount") is not None:
        return EventType.TEST_RUN
    if tool_name or span_type.upper() in TOOL_SPAN_TYPES:
        return EventType.TOOL_CALL
    return EventType.MESSAGE


def _infer_action_type(
    *,
    name: str,
    span_type: str,
    tool_name: str | None,
    command: str | None,
    file_paths: tuple[str, ...],
    event_type: EventType,
    status: StepStatus,
    observation_text: str,
) -> ActionType:
    text = _joined_text(name, tool_name, command, observation_text)
    if _is_internal_overhead_span(name=name, command=command, file_paths=file_paths):
        return ActionType.OVERHEAD
    if tool_name == "finish":
        return ActionType.FINALIZE
    if span_type.upper() in LLM_SPAN_TYPES:
        return ActionType.FINALIZE if _has_hint(text, FINALIZE_HINTS) else ActionType.PLAN
    if tool_name in {"task_tracker", "think"}:
        return ActionType.PLAN
    if event_type == EventType.FILE_EDIT:
        return ActionType.EDIT
    if event_type == EventType.FILE_READ:
        return ActionType.INSPECT
    if event_type == EventType.TEST_RUN:
        return ActionType.EXECUTE
    if _has_hint(text, WAIT_HINTS):
        return ActionType.WAIT
    if _has_hint(text, RETRY_HINTS) or (status in {StepStatus.ERROR, StepStatus.TIMEOUT} and _looks_like_test_command(text)):
        return ActionType.RETRY
    if _has_hint(text, FINALIZE_HINTS):
        return ActionType.FINALIZE
    if _has_hint(text, EDIT_HINTS):
        return ActionType.EDIT
    if tool_name == "terminal" or _has_hint(text, EXECUTE_HINTS):
        return ActionType.EXECUTE
    if _has_hint(text, INSPECT_HINTS | RETRIEVAL_HINTS):
        return ActionType.INSPECT
    if tool_name:
        return ActionType.EXECUTE
    return ActionType.PLAN


def _infer_source(
    *,
    span_type: str,
    name: str,
    tool_name: str | None,
    attributes: Mapping[str, Any],
) -> EventSource:
    normalized_span_type = span_type.upper()
    if _is_internal_overhead_span(name=name, command=None, file_paths=()):
        return EventSource.RUNTIME
    if normalized_span_type in LLM_SPAN_TYPES:
        return EventSource.MODEL
    if _has_hint(_joined_text(name, tool_name), RETRIEVAL_HINTS) or _find_value(attributes, "retrievedContextTokens", "retrievalTokens") is not None:
        return EventSource.RETRIEVAL
    if tool_name or normalized_span_type in TOOL_SPAN_TYPES:
        return EventSource.TOOL
    return EventSource.RUNTIME


def _extract_prompt_composition(
    span: Mapping[str, Any],
    attributes: Mapping[str, Any],
    *,
    input_tokens: int,
    cached_tokens: int,
) -> PromptComposition:
    prompt_messages = span.get("input")
    if isinstance(prompt_messages, Sequence) and not isinstance(prompt_messages, (str, bytes, bytearray)):
        estimated = _estimate_prompt_from_messages(prompt_messages, input_tokens=input_tokens, cached_tokens=cached_tokens)
        if estimated is not None:
            return estimated

    total_input = input_tokens
    retrieved = _coerce_int(_find_value(span, "retrievedContextTokens", "retrievalTokens"))
    replayed = _coerce_int(_find_value(span, "replayedContextTokens", "memoryTokens", "carryForwardTokens"))
    cached = cached_tokens
    tool_output = _coerce_int(_find_value(span, "toolOutputTokens", "observationTokens"))
    new_task = max(total_input - (retrieved + replayed + cached + tool_output), 0)
    return PromptComposition(
        new_task_tokens=new_task,
        retrieved_context_tokens=retrieved,
        replayed_context_tokens=replayed,
        cached_prefix_tokens=cached,
        tool_output_tokens=tool_output,
    )


def _extract_tool_name(span: Mapping[str, Any], attributes: Mapping[str, Any]) -> str | None:
    tool_call = _extract_tool_call_payload(span, attributes)
    if tool_call.get("name"):
        return _coerce_optional_str(tool_call.get("name"))

    action_payload = _extract_action_payload(span)
    action_kind = _coerce_optional_str(_first_non_null(action_payload.get("kind"), action_payload.get("name")))
    if action_kind == "FileEditorAction":
        return "file_editor"
    if action_kind == "TerminalAction":
        return "terminal"
    if action_kind == "TaskTrackerAction":
        return "task_tracker"
    if action_kind == "ThinkAction":
        return "think"
    if action_kind == "FinishAction":
        return "finish"
    if str(span.get("name") or "").startswith("LocalFileStore."):
        return "local_file_store"

    value = _first_non_null(
        _find_value(attributes, "toolName", "tool", "tool_name"),
        _find_value(span, "toolName", "tool", "tool_name"),
    )
    return _coerce_optional_str(value)


def _extract_command(span: Mapping[str, Any], attributes: Mapping[str, Any]) -> str | None:
    action_payload = _extract_action_payload(span)
    tool_call = _extract_tool_call_payload(span, attributes)
    output_payload = _ensure_mapping(span.get("output"))
    value = _first_non_null(
        action_payload.get("command"),
        output_payload.get("command"),
        tool_call.get("command"),
        _find_value(attributes, "command", "cmd", "shellCommand", "argv"),
        _find_value(span, "command", "cmd", "shellCommand", "argv"),
    )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        joined = " ".join(str(item) for item in value)
        return joined or None
    return _coerce_optional_str(value)


def _extract_file_paths(
    span: Mapping[str, Any],
    attributes: Mapping[str, Any],
    *,
    command: str | None,
) -> list[str]:
    action_payload = _extract_action_payload(span)
    tool_call = _extract_tool_call_payload(span, attributes)
    output_payload = _ensure_mapping(span.get("output"))
    candidates: list[str] = []

    for source in (action_payload, output_payload, tool_call, attributes, span):
        for key in ("path", "filePath", "file", "files", "paths", "filePaths", "targetFile", "targetPath"):
            value = _find_value(source, key)
            candidates.extend(_extract_path_like_strings(value))

    if command and not candidates:
        candidates.extend(_extract_path_like_strings(command))
    if not candidates:
        candidates.extend(_extract_path_like_strings(_extract_observation_text(span)))

    deduped: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip()
        if normalized and normalized not in deduped and not _is_internal_state_path(normalized):
            deduped.append(normalized)
    return deduped




def _extract_action_payload(span: Mapping[str, Any]) -> Mapping[str, Any]:
    input_payload = _ensure_mapping(span.get("input"))
    action_payload = _ensure_mapping(input_payload.get("action"))
    return action_payload or input_payload


def _extract_tool_call_payload(span: Mapping[str, Any], attributes: Mapping[str, Any]) -> Mapping[str, Any]:
    output_payload = span.get("output")
    if isinstance(output_payload, Sequence) and not isinstance(output_payload, (str, bytes, bytearray)):
        for item in output_payload:
            if isinstance(item, Mapping):
                for content_item in item.get("content", []):
                    if isinstance(content_item, Mapping) and content_item.get("type") == "tool_call":
                        arguments = content_item.get("arguments")
                        parsed = _parse_json_like(arguments)
                        if isinstance(parsed, Mapping):
                            return {"name": content_item.get("name"), **parsed}
                        return {"name": content_item.get("name"), "arguments": arguments}

    tool_name = _coerce_optional_str(
        _find_value(attributes, "gen_ai.completion.0.tool_calls.0.name", "toolCallName")
    )
    arguments = _find_value(attributes, "gen_ai.completion.0.tool_calls.0.arguments", "toolCallArguments")
    parsed_arguments = _parse_json_like(arguments)
    if tool_name and isinstance(parsed_arguments, Mapping):
        return {"name": tool_name, **parsed_arguments}
    if tool_name:
        return {"name": tool_name, "arguments": arguments}
    return {}


def _extract_observation_text(span: Mapping[str, Any]) -> str:
    output_payload = span.get("output")
    strings = [text.strip() for text in _walk_strings(output_payload) if str(text).strip()]
    return "\n".join(strings)


def _extract_test_results(command: str | None, observation_text: str) -> tuple[int, int, int]:
    text = observation_text.lower()
    passed = _extract_named_count(text, "passed")
    failed = _extract_named_count(text, "failed")
    skipped = _extract_named_count(text, "skipped")
    total = passed + failed + skipped
    if total:
        return passed, failed, total
    if _looks_like_test_command(command or ""):
        return 0, 0, 1
    return 0, 0, 0


def _estimate_prompt_from_messages(
    messages: Sequence[Any],
    *,
    input_tokens: int,
    cached_tokens: int,
) -> PromptComposition | None:
    uncached_tokens = max(input_tokens - cached_tokens, 0)
    if not messages:
        return None

    weights = {
        "new_task": 0,
        "tool_output": 0,
        "replayed": 0,
    }
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        role = str(message.get("role") or "").lower()
        weight = sum(len(text) for text in _walk_strings(message.get("content")))
        if role == "user":
            weights["new_task"] += weight
        elif role == "tool":
            weights["tool_output"] += weight
        else:
            weights["replayed"] += weight

    allocated = _allocate_token_buckets(uncached_tokens, weights)
    return PromptComposition(
        new_task_tokens=allocated["new_task"],
        retrieved_context_tokens=0,
        replayed_context_tokens=allocated["replayed"],
        cached_prefix_tokens=min(cached_tokens, input_tokens),
        tool_output_tokens=allocated["tool_output"],
    )


def _allocate_token_buckets(total_tokens: int, weights: Mapping[str, int]) -> dict[str, int]:
    if total_tokens <= 0:
        return {key: 0 for key in weights}
    total_weight = sum(max(weight, 0) for weight in weights.values())
    if total_weight <= 0:
        return {key: (total_tokens if index == 0 else 0) for index, key in enumerate(weights)}

    raw_allocations = {
        key: total_tokens * max(weight, 0) / total_weight
        for key, weight in weights.items()
    }
    allocated = {key: int(value) for key, value in raw_allocations.items()}
    remainder = total_tokens - sum(allocated.values())
    for key, _ in sorted(raw_allocations.items(), key=lambda item: item[1] - int(item[1]), reverse=True):
        if remainder <= 0:
            break
        allocated[key] += 1
        remainder -= 1
    return allocated


def _normalize_action_command(command: str | None) -> str:
    return str(command or "").strip().lower()


def _looks_like_test_command(text: str) -> bool:
    lowered = text.lower()
    return any(hint in lowered for hint in TEST_COMMAND_HINTS)


def _extract_named_count(text: str, label: str) -> int:
    match = re.search(rf"(\d+)\s+{re.escape(label)}", text, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _is_internal_overhead_span(*, name: str, command: str | None, file_paths: Sequence[str]) -> bool:
    lowered_name = name.lower()
    if any(hint in lowered_name for hint in OVERHEAD_HINTS):
        return True
    if any(_is_internal_state_path(path) for path in file_paths):
        return True
    lowered_command = str(command or "").lower()
    return any(hint in lowered_command for hint in OVERHEAD_HINTS)


def _is_internal_state_path(path: str) -> bool:
    normalized = path.strip().strip('"\'')
    return normalized in {"events", "base_state.json"} or normalized.endswith("/base_state.json")


def _parse_json_like(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (Mapping, list)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None

def _extract_path_like_strings(value: Any) -> list[str]:
    paths: list[str] = []
    for text in _walk_strings(value):
        for token in re.split(r"\s+|,|;|\(|\)|\[|\]|\{|\}|\"|'", text):
            candidate = token.strip()
            if _looks_like_file_path(candidate):
                paths.append(candidate)
    return paths


def _walk_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        results: list[str] = []
        for item in value.values():
            results.extend(_walk_strings(item))
        return results
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        results: list[str] = []
        for item in value:
            results.extend(_walk_strings(item))
        return results
    return []


def _looks_like_file_path(value: str) -> bool:
    if not value or value.startswith("http://") or value.startswith("https://"):
        return False
    if value.startswith(("./", "../", "/")):
        return True
    return bool(FILE_EXTENSION_PATTERN.search(value))


def _find_value(data: Mapping[str, Any] | None, *candidate_keys: str) -> Any:
    if not isinstance(data, Mapping):
        return None
    normalized_candidates = {_normalize_key(key) for key in candidate_keys}
    for key, value in data.items():
        if _normalize_key(str(key)) in normalized_candidates:
            return value
    for value in data.values():
        if isinstance(value, Mapping):
            nested = _find_value(value, *candidate_keys)
            if nested is not None:
                return nested
    return None


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(normalized), tz=timezone.utc)
        except ValueError:
            return None


def _coerce_status(value: Any) -> StepStatus:
    text = str(value or "").strip().lower()
    if text in {"success", "ok", "completed", "complete", "passed"}:
        return StepStatus.SUCCESS
    if text in {"error", "failed", "failure"}:
        return StepStatus.ERROR
    if text in {"timeout", "timed_out"}:
        return StepStatus.TIMEOUT
    if text in {"cancelled", "canceled", "interrupted", "aborted"}:
        return StepStatus.INTERRUPTED
    return StepStatus.UNKNOWN


def _coerce_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(str(value))
    except ValueError:
        return 0


def _coerce_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _ensure_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _joined_text(*values: Any) -> str:
    return " ".join(str(value).lower() for value in values if value)


def _has_hint(text: str, hints: set[str]) -> bool:
    return any(hint in text for hint in hints)
