from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from statistics import median
from typing import Any

from .metrics import file_transition_edges, summarize_run
from .models import ActionType, EventType, NormalizedEvent, StepStatus

ACTION_COLORS = {
    "inspect": "#4C78A8",
    "plan": "#F58518",
    "edit": "#54A24B",
    "execute": "#E45756",
    "retry": "#B279A2",
    "wait": "#9D755D",
    "overhead": "#6C6F7D",
    "finalize": "#72B7B2",
}

PROMPT_COLORS = {
    "new_task_tokens": "#4C78A8",
    "retrieved_context_tokens": "#F58518",
    "replayed_context_tokens": "#E45756",
    "cached_prefix_tokens": "#72B7B2",
    "tool_output_tokens": "#54A24B",
}

HARNESS_LANE_COLORS = {
    "controller": "#B279A2",
    "model": "#F58518",
    "workspace": "#4C78A8",
    "runtime": "#6C6F7D",
}

LANE_ORDER = ("controller", "model", "workspace", "runtime")



def _derive_burden_metrics(events: list[NormalizedEvent]) -> dict[str, int | None | list[str]]:
    first_edit_index: int | None = None
    first_pass_index: int | None = None
    tests_before_first_pass = 0
    edits_before_first_pass = 0
    files_before_first_edit: set[str] = set()
    retry_burst = 0
    max_retry_burst = 0

    for index, event in enumerate(events, start=1):
        if first_edit_index is None and event.action_type == ActionType.EDIT:
            first_edit_index = index

        if first_edit_index is None and event.event_type == EventType.FILE_READ:
            files_before_first_edit.update(event.touched_files)

        if first_pass_index is None:
            tests_before_first_pass += event.test_count
            if event.action_type == ActionType.EDIT:
                edits_before_first_pass += 1
            if event.tests_passed > 0:
                first_pass_index = index

        if event.action_type in {ActionType.RETRY, ActionType.WAIT}:
            retry_burst += 1
            max_retry_burst = max(max_retry_burst, retry_burst)
        else:
            retry_burst = 0

    tests_after_first_pass = (
        max(sum(event.test_count for event in events) - tests_before_first_pass, 0)
        if first_pass_index is not None
        else 0
    )

    return {
        "first_edit_index": first_edit_index,
        "first_pass_index": first_pass_index,
        "files_before_first_edit": sorted(files_before_first_edit),
        "files_before_first_edit_count": len(files_before_first_edit),
        "edits_before_first_pass": edits_before_first_pass,
        "tests_before_first_pass": tests_before_first_pass,
        "tests_after_first_pass": tests_after_first_pass,
        "max_retry_burst": max_retry_burst,
    }



def build_single_run_dashboard_data(events: list[NormalizedEvent]) -> dict[str, Any]:
    if not events:
        raise ValueError("build_single_run_dashboard_data requires at least one event")

    ordered_events = _ordered_events(events)
    summary = summarize_run(ordered_events)
    base_time = _base_timestamp(ordered_events)

    timeline_rows: list[dict[str, Any]] = []
    cumulative_rows: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []
    control_rows: list[dict[str, Any]] = []
    step_details: list[dict[str, Any]] = []
    unique_files_seen: set[str] = set()
    cumulative_input_tokens = 0
    cumulative_output_tokens = 0
    cumulative_cached_tokens = 0
    cumulative_tests_run = 0
    cumulative_tests_passed = 0

    for index, event in enumerate(ordered_events, start=1):
        start_ms = _milliseconds_since(base_time, event.timestamp_start)
        duration_ms = event.resolved_duration_ms
        lane = _event_lane(event)
        feedback_category = _feedback_category(event)
        observation_excerpt = _observation_excerpt(event)
        control_tags = _control_tags(event)
        unique_files_seen.update(event.touched_files)
        cumulative_input_tokens += event.token_input
        cumulative_output_tokens += event.token_output
        cumulative_cached_tokens += event.token_cached
        cumulative_tests_run += event.test_count
        cumulative_tests_passed += event.tests_passed

        timeline_row = {
            "step_id": event.step_id,
            "step_index": index,
            "action_type": event.action_type.value,
            "event_type": event.event_type.value,
            "status": event.status.value,
            "lane": lane,
            "start_ms": start_ms,
            "duration_ms": duration_ms,
            "end_ms": start_ms + duration_ms,
            "token_input": event.token_input,
            "token_output": event.token_output,
            "token_cached": event.token_cached,
            "cost_usd": event.cost_usd,
            "files": list(event.touched_files),
            "tool_name": event.tool_name,
            "feedback_category": feedback_category,
            "control_tags": control_tags,
            "label": _event_label(event, index),
        }
        timeline_rows.append(timeline_row)

        if lane == "controller" or control_tags:
            control_rows.append(dict(timeline_row))

        cumulative_rows.append(
            {
                "step_id": event.step_id,
                "step_index": index,
                "label": f"{index}: {event.step_id}",
                "cumulative_input_tokens": cumulative_input_tokens,
                "cumulative_output_tokens": cumulative_output_tokens,
                "cumulative_cached_tokens": cumulative_cached_tokens,
                "cumulative_tests_run": cumulative_tests_run,
                "cumulative_tests_passed": cumulative_tests_passed,
                "cumulative_unique_files": len(unique_files_seen),
            }
        )

        if (
            event.event_type == EventType.LLM_CALL
            and event.prompt_composition is not None
            and event.prompt_composition.total_tokens > 0
        ):
            prompt_index = len(prompt_rows) + 1
            prompt_rows.append(
                {
                    "step_id": event.step_id,
                    "step_index": index,
                    "prompt_index": prompt_index,
                    "label": f"LLM {prompt_index}",
                    "detail_label": f"LLM {prompt_index} · step {index}",
                    "new_task_tokens": event.prompt_composition.new_task_tokens,
                    "retrieved_context_tokens": event.prompt_composition.retrieved_context_tokens,
                    "replayed_context_tokens": event.prompt_composition.replayed_context_tokens,
                    "cached_prefix_tokens": event.prompt_composition.cached_prefix_tokens,
                    "tool_output_tokens": event.prompt_composition.tool_output_tokens,
                    "total_tokens": event.prompt_composition.total_tokens,
                }
            )

        step_details.append(
            {
                "step_id": event.step_id,
                "step_index": index,
                "label": _event_label(event, index),
                "lane": lane,
                "action_type": event.action_type.value,
                "event_type": event.event_type.value,
                "status": event.status.value,
                "source": event.source.value,
                "tool_name": event.tool_name,
                "command": _event_command(event),
                "files": list(event.touched_files),
                "feedback_category": feedback_category,
                "control_tags": control_tags,
                "duration_ms": duration_ms,
                "token_input": event.token_input,
                "token_output": event.token_output,
                "token_cached": event.token_cached,
                "cost_usd": event.cost_usd,
                "test_count": event.test_count,
                "tests_passed": event.tests_passed,
                "tests_failed": event.tests_failed,
                "observation_excerpt": observation_excerpt,
                "prompt_composition": {
                    "new_task_tokens": event.prompt_composition.new_task_tokens,
                    "retrieved_context_tokens": event.prompt_composition.retrieved_context_tokens,
                    "replayed_context_tokens": event.prompt_composition.replayed_context_tokens,
                    "cached_prefix_tokens": event.prompt_composition.cached_prefix_tokens,
                    "tool_output_tokens": event.prompt_composition.tool_output_tokens,
                    "total_tokens": event.prompt_composition.total_tokens,
                }
                if event.prompt_composition is not None
                else None,
            }
        )

    action_counts = Counter(row["action_type"] for row in timeline_rows)
    lane_counts = Counter(row["lane"] for row in timeline_rows)
    control_tag_counts = Counter(tag for row in control_rows for tag in row["control_tags"])
    tool_counts = Counter(event.tool_name for event in ordered_events if event.tool_name)
    file_touch_counts = Counter(path for event in ordered_events for path in event.touched_files)
    transitions = file_transition_edges(ordered_events)
    filtered_transitions = _filter_top_file_transitions(transitions, file_touch_counts, max_files=8)
    transition_graph = _build_transition_graph(filtered_transitions)
    feedback_graph = _build_feedback_action_graph(ordered_events)
    lane_occupancy_rows, lane_summary_rows, lane_handoff_graph = _build_lane_views(
        timeline_rows,
        total_run_duration_ms=summary.wall_clock_duration_ms,
    )
    burden_metrics = _derive_burden_metrics(ordered_events)
    burden_rows = [
        {"metric": "files before first edit", "value": burden_metrics["files_before_first_edit_count"]},
        {"metric": "edits before first pass", "value": burden_metrics["edits_before_first_pass"]},
        {"metric": "tests before first pass", "value": burden_metrics["tests_before_first_pass"]},
        {"metric": "tests after first pass", "value": burden_metrics["tests_after_first_pass"]},
        {"metric": "max retry burst", "value": burden_metrics["max_retry_burst"]},
    ]
    dominant_lane = (
        max(lane_summary_rows, key=lambda row: row["active_wall_clock_ms"])["lane"]
        if lane_summary_rows
        else (lane_counts.most_common(1)[0][0] if lane_counts else None)
    )

    return {
        "run_id": summary.run_id,
        "summary": {
            "run_id": summary.run_id,
            "success": summary.success,
            "total_steps": summary.total_steps,
            "total_duration_ms": summary.total_duration_ms,
            "wall_clock_duration_ms": summary.wall_clock_duration_ms,
            "summed_event_duration_ms": summary.summed_event_duration_ms,
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "total_cached_tokens": summary.total_cached_tokens,
            "total_cost_usd": summary.total_cost_usd,
            "total_tests_run": summary.total_tests_run,
            "tests_passed": summary.tests_passed,
            "tests_failed": summary.tests_failed,
            "cache_ratio": summary.cache_ratio,
            "carry_forward_ratio": summary.memory_inefficiency_ratio,
            "memory_inefficiency_ratio": summary.memory_inefficiency_ratio,
            "wait_time_ratio": summary.wait_time_ratio,
            "first_edit_step": summary.first_edit_step,
            "first_execute_step": summary.first_execute_step,
            "first_passing_test_step": summary.first_passing_test_step,
            "unique_files_read": list(summary.unique_files_read),
            "unique_files_edited": list(summary.unique_files_edited),
            "files_before_first_edit": burden_metrics["files_before_first_edit"],
            "files_before_first_edit_count": burden_metrics["files_before_first_edit_count"],
            "edits_before_first_pass": burden_metrics["edits_before_first_pass"],
            "tests_before_first_pass": burden_metrics["tests_before_first_pass"],
            "tests_after_first_pass": burden_metrics["tests_after_first_pass"],
            "max_retry_burst": burden_metrics["max_retry_burst"],
            "first_edit_index": burden_metrics["first_edit_index"],
            "first_pass_index": burden_metrics["first_pass_index"],
            "dominant_action": action_counts.most_common(1)[0][0] if action_counts else None,
            "dominant_lane": dominant_lane,
            "llm_steps": sum(1 for event in ordered_events if event.event_type == EventType.LLM_CALL),
            "lane_summary": lane_summary_rows,
            "test_run_events": sum(1 for event in ordered_events if event.event_type == EventType.TEST_RUN),
            "controller_events": len(control_rows),
            "top_control_events": [{"name": name, "count": count} for name, count in control_tag_counts.most_common(5)],
            "top_tools": [{"name": name, "count": count} for name, count in tool_counts.most_common(5)],
            "top_files": [{"path": path, "count": count} for path, count in file_touch_counts.most_common(8)],
        },
        "action_palette": ACTION_COLORS,
        "prompt_palette": PROMPT_COLORS,
        "lane_palette": HARNESS_LANE_COLORS,
        "timeline": timeline_rows,
        "lane_occupancy": lane_occupancy_rows,
        "lane_summary": lane_summary_rows,
        "lane_handoffs": lane_handoff_graph,
        "control_timeline": control_rows,
        "step_details": step_details,
        "prompt_composition": prompt_rows,
        "cumulative_progress": cumulative_rows,
        "feedback_next_action": feedback_graph,
        "file_transitions": transition_graph,
        "burden_metrics": burden_rows,
        "action_counts": dict(action_counts),
        "lane_counts": dict(lane_counts),
    }


def render_single_run_dashboard(
    events: list[NormalizedEvent],
    output_path: str | Path,
    *,
    title: str | None = None,
) -> Path:
    dashboard_data = build_single_run_dashboard_data(events)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html = _build_dashboard_html(dashboard_data, title=title)
    output.write_text(html, encoding="utf-8")
    return output


def _ordered_events(events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    return sorted(
        events,
        key=lambda event: (
            event.timestamp_start.isoformat() if event.timestamp_start else "",
            event.step_id,
        ),
    )


def _base_timestamp(events: list[NormalizedEvent]) -> datetime:
    for event in events:
        if event.timestamp_start is not None:
            return event.timestamp_start
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _milliseconds_since(base_time: datetime, value: datetime | None) -> int:
    if value is None:
        return 0
    return max(int((value - base_time).total_seconds() * 1000), 0)


def _event_label(event: NormalizedEvent, step_index: int) -> str:
    files = ", ".join(event.touched_files[:3])
    suffix = f" — {files}" if files else ""
    return f"{step_index}: {event.action_type.value}/{event.event_type.value}{suffix}"


def _build_transition_graph(
    transitions: dict[tuple[str, str], int],
) -> dict[str, list[dict[str, Any]]]:
    node_index: dict[str, int] = {}
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    all_paths = {path for edge in transitions for path in edge}
    basenames = Counter(_short_path_label(path) for path in all_paths)
    duplicate_basenames = {name for name, count in basenames.items() if count > 1}

    def display_label(path: str) -> str:
        return _short_path_label(path, duplicate_basenames)

    def get_index(path: str) -> int:
        if path not in node_index:
            node_index[path] = len(nodes)
            nodes.append({"id": path, "label": display_label(path), "full_label": path})
        return node_index[path]

    for (source, target), weight in sorted(transitions.items()):
        links.append(
            {
                "source": get_index(source),
                "target": get_index(target),
                "value": weight,
                "label": f"{display_label(source)} → {display_label(target)}",
                "full_label": f"{source} → {target}",
            }
        )

    return {"nodes": nodes, "links": links}


def _filter_top_file_transitions(
    transitions: dict[tuple[str, str], int],
    file_touch_counts: Counter[str],
    *,
    max_files: int = 8,
) -> dict[tuple[str, str], int]:
    top_files = {path for path, _count in file_touch_counts.most_common(max_files)}
    filtered = {
        edge: weight
        for edge, weight in transitions.items()
        if edge[0] in top_files and edge[1] in top_files
    }
    return filtered or transitions




def _build_feedback_action_graph(events: list[NormalizedEvent]) -> dict[str, list[dict[str, Any]]]:
    transitions: Counter[tuple[str, str]] = Counter()
    ordered_events = _ordered_events(events)
    for index, event in enumerate(ordered_events[:-1]):
        feedback_category = _feedback_category(event)
        if not feedback_category:
            continue
        next_action = _next_visible_action(ordered_events, start_index=index + 1)
        if not next_action:
            continue
        transitions[(feedback_category, next_action)] += 1

    node_index: dict[str, int] = {}
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    def get_index(label: str, kind: str) -> int:
        key = f"{kind}:{label}"
        if key not in node_index:
            node_index[key] = len(nodes)
            nodes.append({"id": key, "label": label, "kind": kind})
        return node_index[key]

    for (source, target), weight in sorted(transitions.items()):
        links.append(
            {
                "source": get_index(source, "feedback"),
                "target": get_index(target, "action"),
                "value": weight,
                "label": f"{source} → {target}",
            }
        )

    return {"nodes": nodes, "links": links}


def _build_lane_views(
    timeline_rows: list[dict[str, Any]],
    *,
    total_run_duration_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    if not timeline_rows:
        return [], [], {"nodes": [], "links": []}

    lane_intervals: dict[str, list[tuple[int, int]]] = defaultdict(list)
    lane_event_durations: dict[str, list[int]] = defaultdict(list)
    lane_event_counts: Counter[str] = Counter()
    bursts: list[dict[str, Any]] = []
    current_burst: dict[str, Any] | None = None

    for row in timeline_rows:
        lane = row["lane"]
        lane_event_counts[lane] += 1
        lane_event_durations[lane].append(row["duration_ms"])
        lane_intervals[lane].append((row["start_ms"], row["end_ms"]))

        if current_burst is not None and current_burst["lane"] == lane:
            current_burst["end_ms"] = max(current_burst["end_ms"], row["end_ms"])
            current_burst["duration_ms"] = current_burst["end_ms"] - current_burst["start_ms"]
            current_burst["step_end"] = row["step_index"]
            current_burst["event_count"] += 1
            current_burst["last_label"] = row["label"]
        else:
            if current_burst is not None:
                bursts.append(current_burst)
            current_burst = {
                "lane": lane,
                "start_ms": row["start_ms"],
                "end_ms": row["end_ms"],
                "duration_ms": row["duration_ms"],
                "step_start": row["step_index"],
                "step_end": row["step_index"],
                "event_count": 1,
                "first_label": row["label"],
                "last_label": row["label"],
            }
    if current_burst is not None:
        bursts.append(current_burst)

    lane_summary_rows: list[dict[str, Any]] = []
    total_events = len(timeline_rows)
    lane_order = [lane for lane in LANE_ORDER if lane in lane_event_counts] + [
        lane for lane in sorted(lane_event_counts) if lane not in LANE_ORDER
    ]
    for lane in lane_order:
        merged_intervals = _merge_intervals(lane_intervals[lane])
        active_wall_clock_ms = sum(end - start for start, end in merged_intervals)
        burst_durations = [burst["duration_ms"] for burst in bursts if burst["lane"] == lane]
        lane_summary_rows.append(
            {
                "lane": lane,
                "event_count": lane_event_counts[lane],
                "event_share": lane_event_counts[lane] / total_events if total_events else 0.0,
                "active_wall_clock_ms": active_wall_clock_ms,
                "wall_share": active_wall_clock_ms / total_run_duration_ms if total_run_duration_ms else 0.0,
                "median_event_duration_ms": int(median(lane_event_durations[lane])) if lane_event_durations[lane] else 0,
                "longest_burst_ms": max(burst_durations) if burst_durations else 0,
                "burst_count": len(burst_durations),
            }
        )

    handoff_counts: Counter[tuple[str, str]] = Counter()
    for source, target in zip(bursts, bursts[1:]):
        if source["lane"] == target["lane"]:
            continue
        handoff_counts[(source["lane"], target["lane"])] += 1

    return bursts, lane_summary_rows, _build_simple_sankey(handoff_counts)


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not intervals:
        return []
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _build_simple_sankey(
    transitions: Counter[tuple[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    node_index: dict[str, int] = {}
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    def get_index(label: str) -> int:
        if label not in node_index:
            node_index[label] = len(nodes)
            nodes.append({"id": label, "label": label})
        return node_index[label]

    for (source, target), weight in sorted(transitions.items()):
        links.append(
            {
                "source": get_index(source),
                "target": get_index(target),
                "value": weight,
                "label": f"{source} → {target}",
            }
        )

    return {"nodes": nodes, "links": links}


def _next_visible_action(events: list[NormalizedEvent], *, start_index: int) -> str | None:
    for event in events[start_index:]:
        if event.action_type in {ActionType.OVERHEAD, ActionType.PLAN}:
            continue
        return event.action_type.value
    return None


def _event_lane(event: NormalizedEvent) -> str:
    if event.action_type == ActionType.OVERHEAD or event.tool_name == "local_file_store":
        return "runtime"
    if event.tool_name in {"task_tracker", "think", "finish"} or event.action_type in {
        ActionType.RETRY,
        ActionType.WAIT,
        ActionType.FINALIZE,
    }:
        return "controller"
    if event.event_type == EventType.LLM_CALL:
        return "model"
    return "workspace"


def _feedback_category(event: NormalizedEvent) -> str | None:
    if event.action_type == ActionType.OVERHEAD or event.event_type == EventType.LLM_CALL:
        return None
    if event.status in {StepStatus.ERROR, StepStatus.TIMEOUT, StepStatus.INTERRUPTED}:
        return "tool error"
    if event.event_type == EventType.TEST_RUN:
        if event.tests_failed:
            return "test failure"
        if event.tests_passed and not event.tests_failed:
            return "test pass"
        return "test output"
    if event.event_type == EventType.FILE_READ:
        return "repo listing" if any(_is_directory_like(path) for path in event.touched_files) else "file content"
    if event.event_type == EventType.FILE_EDIT:
        return "edit result"
    if event.tool_name == "terminal":
        excerpt = _observation_excerpt(event).lower()
        return "shell error" if any(token in excerpt for token in ["traceback", "error", "failed"]) else "shell output"
    if event.tool_name in {"task_tracker", "think", "finish"}:
        return "controller update"
    return None


def _control_tags(event: NormalizedEvent) -> list[str]:
    tags: list[str] = []
    if event.tool_name == "task_tracker":
        tags.append("plan_update")
    if event.tool_name == "think":
        tags.append("reasoning_note")
    if event.tool_name == "finish" or event.action_type == ActionType.FINALIZE:
        tags.append("finish")
    if event.action_type == ActionType.WAIT:
        tags.append("wait")
    if event.action_type == ActionType.RETRY or event.event_type == EventType.RETRY:
        tags.append("retry")
    if event.status == StepStatus.TIMEOUT:
        tags.append("timeout")
    if event.status == StepStatus.INTERRUPTED:
        tags.append("interrupted")
    return tags


def _event_command(event: NormalizedEvent) -> str | None:
    command = event.metadata.get("command")
    return str(command) if command else None


def _observation_excerpt(event: NormalizedEvent) -> str:
    values = _collect_strings(event.metadata.get("output"))
    if not values:
        return ""
    merged = "\n".join(value.strip() for value in values if value.strip())
    if len(merged) <= 320:
        return merged
    return f"{merged[:317]}..."


def _collect_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for nested in value.values():
            strings.extend(_collect_strings(nested))
        return strings
    if isinstance(value, list):
        strings: list[str] = []
        for nested in value:
            strings.extend(_collect_strings(nested))
        return strings
    return []


def _is_directory_like(path: str) -> bool:
    stripped = path.rstrip("/")
    leaf = stripped.rsplit("/", 1)[-1]
    return "." not in leaf


def _short_path_label(path: str, duplicate_basenames: set[str] | None = None) -> str:
    stripped = path.rstrip("/")
    if not stripped:
        return path
    parts = [part for part in stripped.split("/") if part]
    if not parts:
        return path
    basename = parts[-1]
    if duplicate_basenames and basename in duplicate_basenames and len(parts) >= 2:
        return "/".join(parts[-2:])
    return basename

def _build_dashboard_html(dashboard_data: dict[str, Any], *, title: str | None) -> str:
    summary = dashboard_data["summary"]
    document_title = title or f"agent_viz — {summary['run_id']}"
    payload_json = json.dumps(dashboard_data, indent=2)

    cards = [
        ("Run", summary["run_id"]),
        ("Success", "yes" if summary["success"] else "no"),
        ("Steps", str(summary["total_steps"])),
        ("Wall-clock duration", _format_duration(summary["wall_clock_duration_ms"])),
        ("Summed event duration", _format_duration(summary["summed_event_duration_ms"])),
        ("Input tokens", f"{summary['total_input_tokens']:,}"),
        ("Output tokens", f"{summary['total_output_tokens']:,}"),
        ("Carry-forward ratio", f"{summary['carry_forward_ratio']:.1%}"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="card-label">{escape(label)}</div><div class="card-value">{escape(value)}</div></div>'
        for label, value in cards
    )
    top_tools_text = ", ".join(
        f"{item['name']} ({item['count']})" for item in summary.get("top_tools", [])
    ) or "—"
    top_files_text = ", ".join(
        f"{item['path']} ({item['count']})" for item in summary.get("top_files", [])[:5]
    ) or "—"
    top_control_text = ", ".join(
        f"{item['name']} ({item['count']})" for item in summary.get("top_control_events", [])
    ) or "—"
    highlights = [
        ("Dominant action", str(summary.get("dominant_action") or "—")),
        ("Dominant lane by time", str(summary.get("dominant_lane") or "—")),
        ("LLM steps", str(summary.get("llm_steps", 0))),
        ("Verification gap episodes", str(summary.get("verification_gap_episodes", 0))),
        ("Max verification gap", str(summary.get("max_verification_gap", 0))),
        ("Test run events", str(summary.get("test_run_events", 0))),
        ("Controller events", str(summary.get("controller_events", 0))),
        ("Files before first edit", str(summary.get("files_before_first_edit_count", 0))),
        ("Edits before first pass", str(summary.get("edits_before_first_pass", 0))),
        ("Tests before first pass", str(summary.get("tests_before_first_pass", 0))),
        ("Tests after first pass", str(summary.get("tests_after_first_pass", 0))),
        ("Max retry burst", str(summary.get("max_retry_burst", 0))),
        ("Duration note", "Wall-clock uses first start to last observed end; summed event duration adds step durations and can exceed wall-clock when spans overlap."),
        ("Top control events", top_control_text),
        ("Top tools", top_tools_text),
        ("Top files", top_files_text),
    ]
    highlights_html = "".join(
        f'<div class="detail-row"><div class="detail-label">{escape(label)}</div><div class="detail-value">{escape(value)}</div></div>'
        for label, value in highlights
    )
    lane_glossary = [
        {"label": "Controller", "color": HARNESS_LANE_COLORS["controller"], "value": "Harness orchestration around the main solve loop. Examples: retry, wait, finish, finalize, task updates."},
        {"label": "Model", "color": HARNESS_LANE_COLORS["model"], "value": "LLM call spans: prompt-in, model-out, and prompt carry-forward effects. Example: one model response that sets up the next tool action."},
        {"label": "Workspace", "color": HARNESS_LANE_COLORS["workspace"], "value": "Task-facing work such as reading files, editing code, and ordinary terminal/tool actions. Examples: open file, patch code, run tests."},
        {"label": "Runtime", "color": HARNESS_LANE_COLORS["runtime"], "value": "Internal overhead and persistence activity rather than task-solving work. Examples: LocalFileStore and harness plumbing."},
        {"label": "Active time", "color": "#72B7B2", "value": "Union of observed wall-clock intervals for a lane, so overlapping events within the same lane are merged instead of double-counted."},
        {"label": "Burst", "color": "#54A24B", "value": "A consecutive same-lane stretch in observed event order, shown as one occupancy bar segment."},
        {"label": "Handoff", "color": "#E45756", "value": "One lane burst followed by the next lane burst in trace order. The Sankey width shows how often that transition happened."},
    ]
    lane_glossary_html = "".join(
        '<div class="detail-row"><div class="detail-label"><span style="display:inline-block;width:10px;height:10px;border-radius:999px;margin-right:8px;background:'
        + escape(item["color"])
        + ';vertical-align:middle;"></span>'
        + escape(item["label"])
        + '</div><div class="detail-value">'
        + escape(item["value"])
        + '</div></div>'
        for item in lane_glossary
    )

    template = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>__TITLE__</title>
  <script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f1220;
      --panel: #171b2e;
      --panel-soft: #11162a;
      --border: #2b3355;
      --text: #edf1ff;
      --muted: #9aa6d1;
      --accent: #72b7b2;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); }
    .page { max-width: 1380px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 30px; }
    p.lead { margin: 0 0 20px; color: var(--muted); }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .card { background: linear-gradient(180deg, var(--panel), var(--panel-soft)); border: 1px solid var(--border); border-radius: 14px; padding: 14px; min-height: 90px; }
    .card-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
    .card-value { font-size: 24px; font-weight: 650; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
    .panel { background: linear-gradient(180deg, var(--panel), var(--panel-soft)); border: 1px solid var(--border); border-radius: 16px; padding: 14px; }
    .panel h2 { margin: 0 0 6px; font-size: 18px; }
    .panel p { margin: 0 0 12px; color: var(--muted); font-size: 14px; }
    .details-grid { display: grid; grid-template-columns: 1fr; gap: 10px 20px; }
    .detail-row { display: grid; grid-template-columns: 170px 1fr; gap: 14px; padding: 10px 0; border-top: 1px solid rgba(154, 166, 209, 0.12); }
    .detail-row:first-child { border-top: 0; padding-top: 0; }
    .detail-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
    .detail-value { font-size: 14px; line-height: 1.45; }
    .selector { width: 100%; background: #0f1220; color: var(--text); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; }
    .step-detail { display: grid; gap: 12px; }
    .step-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
    .step-chip { background: rgba(114, 183, 178, 0.08); border: 1px solid rgba(114, 183, 178, 0.18); border-radius: 12px; padding: 10px 12px; }
    .step-chip-label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
    .step-chip-value { font-size: 14px; line-height: 1.4; word-break: break-word; }
    pre.step-pre { margin: 0; padding: 12px; border-radius: 12px; background: #0f1220; border: 1px solid var(--border); color: var(--text); font-size: 12px; white-space: pre-wrap; word-break: break-word; }
    .chart { width: 100%; height: 420px; }
    .chart.short { height: 360px; }
    @media (min-width: 1100px) {
      .grid.two { grid-template-columns: 1fr 1fr; }
      .details-grid { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"page\">
    <h1>__TITLE__</h1>
    <p class=\"lead\">Single-run dashboard for agent behavior: harness activity, prompt carry-forward, and direct search, edit, and test burden.</p>
    <div class=\"cards\">__CARDS__</div>
    <section class=\"panel\">
      <h2>Behavior and burden summary</h2>
      <p>Compact signals for long-run dynamics, with direct lower-is-better search and verification counts.</p>
      <div class=\"details-grid\">__HIGHLIGHTS__</div>
    </section>
    <div class=\"grid\">
      <section class=\"panel\">
        <h2>Search / edit / verify burden</h2>
        <p>Direct counts for files before the first edit, edits before the first pass, tests before the first pass, tests after the first pass, and retry bursts. Lower is usually better.</p>
        <div id=\"burden-summary\" class=\"chart short\"></div>
      </section>
      <div class=\"grid two\">
        <section class=\"panel\">
          <h2>Harness lane occupancy</h2>
          <p>Wall-clock bursts for controller, model, workspace, and runtime so you can see which layer actually held the run over time.</p>
          <div id=\"harness-loop\" class=\"chart short\"></div>
        </section>
        <section class=\"panel\">
          <h2>Feedback to next action</h2>
          <p>How observations like file content or test failures route into the next chosen action.</p>
          <div id=\"feedback-next-action\" class=\"chart short\"></div>
        </section>
      </div>
      <section class=\"panel\">
        <h2>Lane summary and handoffs</h2>
        <p>Observed active time, burst lengths, and layer-to-layer handoffs. Active-time shares are relative to full run time and can overlap when layers were active concurrently.</p>
        <h3 style=\"margin:0 0 8px;font-size:15px;color:#edf1ff;\">How lane timing works</h3>
        <div class=\"details-grid\">__LANE_GLOSSARY__</div>
        <div id=\"lane-summary\" class=\"details-grid\" style=\"margin-top:14px;\"></div>
        <div id=\"lane-handoffs\" class=\"chart short\"></div>
      </section>
      <section class=\"panel\">
        <h2>Run timeline</h2>
        <p>Each bar shows one event positioned by time, colored by dominant action type.</p>
        <div id=\"timeline\" class=\"chart\"></div>
      </section>
      <div class=\"grid two\">
        <section class=\"panel\">
          <h2>Prompt makeup per LLM call</h2>
          <p>Each bar is normalized to 100% so you can see whether a prompt was mostly fresh task/context, replayed prior context, cached prefix reuse, or tool output. Hover for raw token counts.</p>
          <div id=\"prompt-composition\" class=\"chart short\"></div>
        </section>
        <section class=\"panel\">
          <h2>File transition graph (top files)</h2>
          <p>Observed movement between the most-touched files in the run, filtered down so the main repo navigation path stays readable.</p>
          <div id=\"file-transitions\" class=\"chart short\"></div>
        </section>
      </div>
      <div class=\"grid two\">
        <section class=\"panel\">
          <h2>Harness steering events</h2>
          <p>Only the harness-side steering actions: plan updates, retries, waits, interruptions, and finish. This is not ordinary file reading, editing, or testing work.</p>
          <div id=\"control-timeline\" class=\"chart short\"></div>
        </section>
        <section class=\"panel\">
          <h2>Step anatomy</h2>
          <p>Click a chart row or choose a step to inspect the exact command, feedback, prompt, and control metadata.</p>
          <select id=\"step-selector\" class=\"selector\"></select>
          <div id=\"step-detail\" class=\"step-detail\"></div>
        </section>
      </div>
      <section class=\"panel\">
        <h2>Cumulative progress</h2>
        <p>Tokens and progress measures over the trajectory, useful for spotting churn versus convergence.</p>
        <div id=\"cumulative-progress\" class=\"chart\"></div>
      </section>
    </div>
  </div>
  <script>
    const dashboardData = __PAYLOAD__;

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function shortPathLabel(path) {
      const parts = String(path ?? '').split('/').filter(Boolean);
      return parts.length ? parts[parts.length - 1] : String(path ?? '');
    }

    function countSummary(items, labelKey = 'name') {
      if (!items || !items.length) {
        return '—';
      }
      return items.map((item) => `${escapeHtml(item[labelKey])} (${item.count})`).join(', ');
    }

    function formatSeconds(value) {
      return `${value.toFixed(2)}s`;
    }

    function formatPercent(value) {
      return `${(value * 100).toFixed(1)}%`;
    }

    function selectStep(stepIndex) {
      const selector = document.getElementById('step-selector');
      if (selector) {
        selector.value = String(stepIndex);
      }
      renderStepDetail(stepIndex);
    }

    function renderStepDetail(stepIndex) {
      const detail = dashboardData.step_details.find((row) => row.step_index === stepIndex) || dashboardData.step_details[0];
      if (!detail) {
        return;
      }
      const prompt = detail.prompt_composition;
      const chips = [
        ['lane', detail.lane],
        ['action', detail.action_type],
        ['event', detail.event_type],
        ['tool', detail.tool_name || '—'],
        ['status', detail.status],
        ['duration', formatSeconds(detail.duration_ms / 1000)],
        ['feedback', detail.feedback_category || '—'],
        ['control', detail.control_tags.length ? detail.control_tags.join(', ') : '—'],
        ['tests', `${detail.tests_passed}/${detail.test_count} passed`],
        ['tokens', `${detail.token_input} in / ${detail.token_output} out / ${detail.token_cached} cached`],
      ];
      if (detail.files.length) {
        chips.push(['files', detail.files.join(', ')]);
      }
      const chipsHtml = chips.map(([label, value]) => `
        <div class="step-chip">
          <div class="step-chip-label">${escapeHtml(label)}</div>
          <div class="step-chip-value">${escapeHtml(value)}</div>
        </div>
      `).join('');
      const promptHtml = prompt ? `
        <div>
          <div class="step-chip-label">prompt composition</div>
          <pre class="step-pre">new=${prompt.new_task_tokens}\nretrieved=${prompt.retrieved_context_tokens}\nreplayed=${prompt.replayed_context_tokens}\ncached=${prompt.cached_prefix_tokens}\ntool_output=${prompt.tool_output_tokens}\ntotal=${prompt.total_tokens}</pre>
        </div>
      ` : '';
      const commandHtml = detail.command ? `
        <div>
          <div class="step-chip-label">command</div>
          <pre class="step-pre">${escapeHtml(detail.command)}</pre>
        </div>
      ` : '';
      const observationHtml = detail.observation_excerpt ? `
        <div>
          <div class="step-chip-label">observation</div>
          <pre class="step-pre">${escapeHtml(detail.observation_excerpt)}</pre>
        </div>
      ` : '';
      document.getElementById('step-detail').innerHTML = `
        <div class="step-grid">${chipsHtml}</div>
        ${promptHtml}
        ${commandHtml}
        ${observationHtml}
      `;
    }

    function initStepSelector() {
      const selector = document.getElementById('step-selector');
      selector.innerHTML = dashboardData.step_details.map((detail) => `
        <option value="${detail.step_index}">${escapeHtml(detail.label)}</option>
      `).join('');
      selector.addEventListener('change', (event) => {
        selectStep(Number(event.target.value));
      });
      if (dashboardData.step_details.length) {
        selectStep(dashboardData.step_details[0].step_index);
      }
    }


    function wireStepClicks(elementId) {
      const node = document.getElementById(elementId);
      if (!node || typeof node.on !== 'function') {
        return;
      }
      node.on('plotly_click', (event) => {
        const customdata = event?.points?.[0]?.customdata;
        const stepIndex = Array.isArray(customdata) ? Number(customdata[0]) : Number(customdata);
        if (!Number.isNaN(stepIndex)) {
          selectStep(stepIndex);
        }
      });
    }

    function buildHarnessLoop() {
      const rows = dashboardData.lane_occupancy;
      const lanePalette = dashboardData.lane_palette;
      if (!rows.length) {
        document.getElementById('harness-loop').innerHTML = '<div style="padding:24px;color:#9aa6d1;">No timed lane occupancy was detected.</div>';
        return;
      }
      const laneOrder = dashboardData.lane_summary.map((row) => row.lane);
      const traces = laneOrder.filter((lane) => rows.some((row) => row.lane === lane)).map((lane) => {
        const filtered = rows.filter((row) => row.lane === lane);
        return {
          type: 'bar',
          orientation: 'h',
          name: lane,
          y: filtered.map(() => lane),
          x: filtered.map((row) => row.duration_ms / 1000),
          base: filtered.map((row) => row.start_ms / 1000),
          marker: {
            color: lanePalette[lane] || '#888',
            opacity: 0.85,
            line: { color: '#edf1ff', width: 0.8 },
          },
          customdata: filtered.map((row) => [row.step_start, row.step_end, row.event_count, row.first_label, row.last_label, row.duration_ms]),
          hovertemplate: '<b>' + lane + '</b><br>start=%{base:.2f}s<br>duration=%{x:.2f}s<br>steps=%{customdata[0]}–%{customdata[1]}<br>events in burst=%{customdata[2]}<br>first=%{customdata[3]}<br>last=%{customdata[4]}<extra></extra>',
        };
      });
      Plotly.newPlot('harness-loop', traces, {
        barmode: 'overlay',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { title: 'seconds since run start', gridcolor: '#2b3355' },
        yaxis: { title: 'harness layer', automargin: true, categoryorder: 'array', categoryarray: laneOrder },
        margin: { l: 110, r: 24, t: 16, b: 48 },
        legend: { orientation: 'h' },
      }, { responsive: true });
      wireStepClicks('harness-loop');
    }

    function buildLaneSummary() {
      const rows = dashboardData.lane_summary;
      const host = document.getElementById('lane-summary');
      if (!rows.length) {
        host.innerHTML = '<div style="padding:12px 0;color:#9aa6d1;">No lane summary is available yet.</div>';
        return;
      }
      host.innerHTML = rows.map((row) => `
        <div class="detail-row">
          <div class="detail-label">${escapeHtml(row.lane)}</div>
          <div class="detail-value">active ${formatSeconds(row.active_wall_clock_ms / 1000)} • ${formatPercent(row.wall_share)} of run • ${row.event_count} events (${formatPercent(row.event_share)}) • median event ${formatSeconds(row.median_event_duration_ms / 1000)} • longest burst ${formatSeconds(row.longest_burst_ms / 1000)} • ${row.burst_count} bursts</div>
        </div>
      `).join('');
    }

    function buildLaneHandoffs() {
      const graph = dashboardData.lane_handoffs;
      if (!graph.nodes.length || !graph.links.length) {
        document.getElementById('lane-handoffs').innerHTML = '<div style="padding:24px;color:#9aa6d1;">Not enough lane changes were observed to show handoffs yet.</div>';
        return;
      }
      Plotly.newPlot('lane-handoffs', [{
        type: 'sankey',
        arrangement: 'snap',
        node: {
          pad: 18,
          thickness: 18,
          line: { color: '#2b3355', width: 1 },
          label: graph.nodes.map((node) => node.label),
          color: graph.nodes.map((node) => dashboardData.lane_palette[node.label] || '#888'),
        },
        link: {
          source: graph.links.map((link) => link.source),
          target: graph.links.map((link) => link.target),
          value: graph.links.map((link) => link.value),
          label: graph.links.map((link) => link.label),
          color: 'rgba(114,183,178,0.45)',
        },
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        margin: { l: 16, r: 16, t: 16, b: 16 },
      }, { responsive: true });
    }

    function buildFeedbackNextAction() {
      const graph = dashboardData.feedback_next_action;
      if (!graph.nodes.length || !graph.links.length) {
        document.getElementById('feedback-next-action').innerHTML = '<div style="padding:24px;color:#9aa6d1;">Not enough observable feedback transitions yet.</div>';
        return;
      }
      Plotly.newPlot('feedback-next-action', [{
        type: 'sankey',
        arrangement: 'snap',
        node: {
          pad: 18,
          thickness: 18,
          line: { color: '#2b3355', width: 1 },
          label: graph.nodes.map((node) => node.label),
          color: graph.nodes.map((node) => node.kind === 'feedback' ? '#4C78A8' : '#F58518'),
        },
        link: {
          source: graph.links.map((link) => link.source),
          target: graph.links.map((link) => link.target),
          value: graph.links.map((link) => link.value),
          label: graph.links.map((link) => link.label),
          color: 'rgba(114,183,178,0.45)',
        },
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        margin: { l: 16, r: 16, t: 16, b: 16 },
      }, { responsive: true });
    }

    function buildControlTimeline() {
      const rows = dashboardData.control_timeline;
      if (!rows.length) {
        document.getElementById('control-timeline').innerHTML = '<div style="padding:24px;color:#9aa6d1;">No harness steering events such as retry, wait, or finish were detected.</div>';
        return;
      }
      const points = rows.map((row) => ({
        ...row,
        primary_tag: row.control_tags.length ? row.control_tags[0] : row.action_type,
        all_tags: row.control_tags.length ? row.control_tags.join(', ') : row.action_type,
      }));
      Plotly.newPlot('control-timeline', [{
        type: 'scatter',
        mode: 'markers',
        x: points.map((row) => row.start_ms / 1000),
        y: points.map((row) => row.primary_tag),
        marker: {
          color: points.map((row) => dashboardData.action_palette[row.action_type] || '#B279A2'),
          size: 14,
          line: { color: '#edf1ff', width: 0.8 },
        },
        customdata: points.map((row) => [row.step_index, row.label, row.all_tags, row.action_type, row.status]),
        hovertemplate: '<b>%{customdata[1]}</b><br>steering event=%{y}<br>all tags=%{customdata[2]}<br>action=%{customdata[3]}<br>status=%{customdata[4]}<extra></extra>',
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { title: 'seconds since run start', gridcolor: '#2b3355' },
        yaxis: { title: 'steering event', automargin: true },
        margin: { l: 150, r: 24, t: 16, b: 48 },
      }, { responsive: true });
      wireStepClicks('control-timeline');
    }

    function buildBurdenSummary() {
      const rows = dashboardData.burden_metrics;
      Plotly.newPlot('burden-summary', [{
        type: 'bar',
        x: rows.map((row) => row.metric),
        y: rows.map((row) => row.value),
        marker: {
          color: ['#4C78A8', '#54A24B', '#E45756', '#72B7B2', '#B279A2'],
          line: { color: '#edf1ff', width: 0.8 },
        },
        hovertemplate: '%{x}: %{y}<extra></extra>',
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { automargin: true },
        yaxis: { title: 'count', gridcolor: '#2b3355' },
        margin: { l: 60, r: 24, t: 16, b: 80 },
      }, { responsive: true });
    }

    function buildTimeline() {
      const rows = dashboardData.timeline;
      const palette = dashboardData.action_palette;
      const traces = [];
      const actionTypes = [...new Set(rows.map((row) => row.action_type))];
      actionTypes.forEach((action) => {
        const filtered = rows.filter((row) => row.action_type === action);
        traces.push({
          type: 'bar',
          orientation: 'h',
          name: action,
          y: filtered.map((row) => row.label),
          x: filtered.map((row) => row.duration_ms / 1000),
          base: filtered.map((row) => row.start_ms / 1000),
          marker: { color: palette[action] || '#888' },
          customdata: filtered.map((row) => [row.step_index, row.step_id, row.event_type, row.status, row.token_input, row.token_output, row.token_cached, row.cost_usd, row.lane]),
          hovertemplate: '<b>%{y}</b><br>step=%{customdata[1]}<br>lane=%{customdata[8]}<br>event=%{customdata[2]}<br>status=%{customdata[3]}<br>duration=%{x:.2f}s<br>input=%{customdata[4]}<br>output=%{customdata[5]}<br>cached=%{customdata[6]}<br>cost=$%{customdata[7]:.5f}<extra></extra>',
        });
      });
      Plotly.newPlot('timeline', traces, {
        barmode: 'stack',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { title: 'seconds since run start', gridcolor: '#2b3355' },
        yaxis: { automargin: true, categoryorder: 'array', categoryarray: rows.map((row) => row.label).reverse() },
        margin: { l: 200, r: 24, t: 16, b: 48 },
        legend: { orientation: 'h' },
      }, { responsive: true });
      wireStepClicks('timeline');
    }

    function buildPromptComposition() {
      const rows = dashboardData.prompt_composition;
      const palette = dashboardData.prompt_palette;
      const labels = rows.map((row) => row.label);
      const maxTickLabels = 6;
      const tickIndexes = labels.length <= maxTickLabels
        ? labels.map((_, index) => index)
        : [...new Set(Array.from({ length: maxTickLabels }, (_, position) => Math.round((position * (labels.length - 1)) / (maxTickLabels - 1))))];
      const tickValues = tickIndexes.map((index) => labels[index]);
      const tickText = tickIndexes.map((index) => labels[index]);
      const series = [
        ['new_task_tokens', 'fresh task ask'],
        ['retrieved_context_tokens', 'fresh repo/tool context'],
        ['replayed_context_tokens', 'replayed prior context'],
        ['cached_prefix_tokens', 'cached prefix reuse'],
        ['tool_output_tokens', 'tool output added'],
      ];
      const traces = series.map(([key, label]) => ({
        type: 'bar',
        name: label,
        x: labels,
        y: rows.map((row) => row.total_tokens ? (row[key] / row.total_tokens) * 100 : 0),
        marker: { color: palette[key] || '#888' },
        customdata: rows.map((row) => [row.step_index, row.step_id, row[key], row.total_tokens, row.detail_label]),
        hovertemplate: '<b>%{customdata[4]}</b><br>' + label + ': %{customdata[2]} tokens<br>share=%{y:.1f}%<br>total prompt=%{customdata[3]} tokens<extra></extra>',
      }));
      Plotly.newPlot('prompt-composition', traces, {
        barmode: 'stack',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { automargin: true, tickangle: 0, tickmode: 'array', tickvals: tickValues, ticktext: tickText },
        yaxis: { title: 'share of prompt (%)', gridcolor: '#2b3355', ticksuffix: '%' },
        margin: { l: 70, r: 24, t: 16, b: 90 },
        legend: { orientation: 'h' },
      }, { responsive: true });
      wireStepClicks('prompt-composition');
    }

    function buildCumulativeProgress() {
      const rows = dashboardData.cumulative_progress;
      const labels = rows.map((row) => row.label);
      const maxTickLabels = 6;
      const tickIndexes = labels.length <= maxTickLabels
        ? labels.map((_, index) => index)
        : [...new Set(Array.from({ length: maxTickLabels }, (_, position) => Math.round((position * (labels.length - 1)) / (maxTickLabels - 1))))];
      const tickValues = tickIndexes.map((index) => labels[index]);
      const tickText = tickIndexes.map((index) => `step ${rows[index].step_index}`);
      const traces = [
        ['cumulative_input_tokens', 'input tokens', '#4C78A8', 'y1'],
        ['cumulative_output_tokens', 'output tokens', '#F58518', 'y1'],
        ['cumulative_cached_tokens', 'cached tokens', '#72B7B2', 'y1'],
        ['cumulative_tests_run', 'tests run', '#E45756', 'y2'],
        ['cumulative_tests_passed', 'tests passed', '#54A24B', 'y2'],
        ['cumulative_unique_files', 'unique files', '#B279A2', 'y2'],
      ].map(([key, label, color, yaxis]) => ({
        type: 'scatter',
        mode: 'lines+markers',
        name: label,
        x: labels,
        y: rows.map((row) => row[key]),
        line: { color, width: 3 },
        marker: { color, size: 7 },
        customdata: rows.map((row) => [row.step_index, row.step_id, row.label]),
        yaxis,
        hovertemplate: '<b>%{customdata[2]}</b><br>' + label + ': %{y}<extra></extra>',
      }));
      Plotly.newPlot('cumulative-progress', traces, {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { automargin: true, tickmode: 'array', tickvals: tickValues, ticktext: tickText },
        yaxis: { title: 'tokens', gridcolor: '#2b3355' },
        yaxis2: { title: 'progress counts', overlaying: 'y', side: 'right' },
        margin: { l: 70, r: 70, t: 16, b: 90 },
        legend: { orientation: 'h' },
      }, { responsive: true });
      wireStepClicks('cumulative-progress');
    }


    function buildFileTransitions() {
      const graph = dashboardData.file_transitions;
      if (!graph.nodes.length || !graph.links.length) {
        document.getElementById('file-transitions').innerHTML = '<div style="padding:24px;color:#9aa6d1;">Not enough file transitions yet.</div>';
        return;
      }
      Plotly.newPlot('file-transitions', [{
        type: 'sankey',
        arrangement: 'snap',
        node: {
          pad: 18,
          thickness: 18,
          line: { color: '#2b3355', width: 1 },
          label: graph.nodes.map((node) => node.label),
          customdata: graph.nodes.map((node) => node.full_label || node.label),
          hovertemplate: '<b>%{label}</b><br>full path=%{customdata}<extra></extra>',
          color: '#4C78A8',
        },
        link: {
          source: graph.links.map((link) => link.source),
          target: graph.links.map((link) => link.target),
          value: graph.links.map((link) => link.value),
          label: graph.links.map((link) => link.label),
          customdata: graph.links.map((link) => link.full_label || link.label),
          hovertemplate: '<b>%{label}</b><br>full path flow=%{customdata}<br>count=%{value}<extra></extra>',
          color: 'rgba(114,183,178,0.45)',
        },
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        margin: { l: 16, r: 16, t: 16, b: 16 },
      }, { responsive: true });
    }

    initStepSelector();
    buildBurdenSummary();
    buildHarnessLoop();
    buildLaneSummary();
    buildLaneHandoffs();
    buildFeedbackNextAction();
    buildTimeline();
    buildPromptComposition();
    buildControlTimeline();
    buildCumulativeProgress();
    buildFileTransitions();
  </script>
</body>
</html>
"""
    return (
        template.replace("__TITLE__", escape(document_title))
        .replace("__CARDS__", cards_html)
        .replace("__HIGHLIGHTS__", highlights_html)
        .replace("__LANE_GLOSSARY__", lane_glossary_html)
        .replace("__PAYLOAD__", payload_json)
    )


def _format_duration(duration_ms: int) -> str:
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.1f}s"
