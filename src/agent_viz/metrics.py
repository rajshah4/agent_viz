from __future__ import annotations

from collections import Counter

from .models import ActionType, EventType, NormalizedEvent, RunSummary, StepStatus


def summarize_run(events: list[NormalizedEvent]) -> RunSummary:
    if not events:
        raise ValueError("summarize_run requires at least one event")

    ordered_events = sorted(
        events,
        key=lambda event: (
            event.timestamp_start.isoformat() if event.timestamp_start else "",
            event.step_id,
        ),
    )

    action_counts: Counter[str] = Counter()
    action_duration_ms: Counter[str] = Counter()
    unique_files_read: set[str] = set()
    unique_files_edited: set[str] = set()

    total_input_tokens = 0
    total_output_tokens = 0
    total_cached_tokens = 0
    total_cost_usd = 0.0
    total_tool_calls = 0
    total_file_reads = 0
    total_file_edits = 0
    total_tests_run = 0
    tests_passed = 0
    tests_failed = 0
    retry_count = 0
    wait_duration_ms = 0
    summed_event_duration_ms = 0
    prompt_memory_tokens = 0
    prompt_total_tokens = 0
    first_timestamp = None
    last_timestamp_end_ms = None

    first_edit_step: str | None = None
    first_execute_step: str | None = None
    first_passing_test_step: str | None = None

    for event in ordered_events:
        action_key = event.action_type.value
        duration_ms = event.resolved_duration_ms
        action_counts[action_key] += 1
        action_duration_ms[action_key] += duration_ms
        summed_event_duration_ms += duration_ms
        total_input_tokens += event.token_input
        total_output_tokens += event.token_output
        total_cached_tokens += event.token_cached
        total_cost_usd += event.cost_usd
        total_tests_run += event.test_count
        tests_passed += event.tests_passed
        tests_failed += event.tests_failed

        if event.timestamp_start is not None:
            if first_timestamp is None or event.timestamp_start < first_timestamp:
                first_timestamp = event.timestamp_start
            event_end_ms = int(event.timestamp_start.timestamp() * 1000) + duration_ms
            if last_timestamp_end_ms is None or event_end_ms > last_timestamp_end_ms:
                last_timestamp_end_ms = event_end_ms

        if event.prompt_composition is not None:
            prompt_memory_tokens += event.prompt_composition.memory_load_tokens
            prompt_total_tokens += event.prompt_composition.total_tokens

        if event.event_type == EventType.TOOL_CALL:
            total_tool_calls += 1
        if event.event_type == EventType.FILE_READ:
            total_file_reads += 1
            unique_files_read.update(event.touched_files)
        if event.event_type == EventType.FILE_EDIT:
            total_file_edits += 1
            unique_files_edited.update(event.touched_files)
        if event.action_type == ActionType.RETRY or event.event_type == EventType.RETRY:
            retry_count += 1
        if event.action_type == ActionType.WAIT:
            wait_duration_ms += duration_ms

        if first_edit_step is None and event.action_type == ActionType.EDIT:
            first_edit_step = event.step_id
        if first_execute_step is None and event.action_type == ActionType.EXECUTE:
            first_execute_step = event.step_id
        if first_passing_test_step is None and event.tests_passed > 0:
            first_passing_test_step = event.step_id

    wall_clock_duration_ms = 0
    if first_timestamp is not None and last_timestamp_end_ms is not None:
        wall_clock_duration_ms = max(last_timestamp_end_ms - int(first_timestamp.timestamp() * 1000), 0)

    token_input_base = total_input_tokens + total_cached_tokens
    cache_ratio = total_cached_tokens / token_input_base if token_input_base else 0.0
    wait_time_ratio = (
        wait_duration_ms / summed_event_duration_ms if summed_event_duration_ms else 0.0
    )
    memory_inefficiency_ratio = (
        prompt_memory_tokens / prompt_total_tokens if prompt_total_tokens else 0.0
    )
    success = first_passing_test_step is not None and tests_failed == 0

    return RunSummary(
        run_id=ordered_events[0].run_id,
        total_steps=len(ordered_events),
        total_duration_ms=wall_clock_duration_ms,
        wall_clock_duration_ms=wall_clock_duration_ms,
        summed_event_duration_ms=summed_event_duration_ms,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cached_tokens=total_cached_tokens,
        total_cost_usd=round(total_cost_usd, 6),
        total_tool_calls=total_tool_calls,
        total_file_reads=total_file_reads,
        total_file_edits=total_file_edits,
        total_tests_run=total_tests_run,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        unique_files_read=tuple(sorted(unique_files_read)),
        unique_files_edited=tuple(sorted(unique_files_edited)),
        action_counts=dict(action_counts),
        action_duration_ms=dict(action_duration_ms),
        first_edit_step=first_edit_step,
        first_execute_step=first_execute_step,
        first_passing_test_step=first_passing_test_step,
        retry_count=retry_count,
        wait_time_ratio=wait_time_ratio,
        cache_ratio=cache_ratio,
        memory_inefficiency_ratio=memory_inefficiency_ratio,
        success=success,
    )


def file_transition_edges(events: list[NormalizedEvent]) -> dict[tuple[str, str], int]:
    ordered_events = sorted(
        events,
        key=lambda event: (
            event.timestamp_start.isoformat() if event.timestamp_start else "",
            event.step_id,
        ),
    )

    visited_paths: list[str] = []
    for event in ordered_events:
        visited_paths.extend(event.touched_files)

    if len(visited_paths) < 2:
        return {}

    transitions: Counter[tuple[str, str]] = Counter()
    for source, destination in zip(visited_paths, visited_paths[1:]):
        transitions[(source, destination)] += 1
    return dict(transitions)
