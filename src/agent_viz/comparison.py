from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
from typing import Any

from .metrics import summarize_run
from .models import ActionType, EventType, NormalizedEvent

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

OVERHEAD_COLORS = {
    "persistence_lookup": "#7F8CFF",
    "persistence_write": "#4C78A8",
    "orchestration": "#B279A2",
    "unknown_internal": "#6C6F7D",
}


def build_multi_run_comparison_data(
    runs: dict[str, list[NormalizedEvent]] | list[tuple[str, list[NormalizedEvent]]],
) -> dict[str, Any]:
    normalized_runs = _normalize_runs(runs)
    if not normalized_runs:
        raise ValueError("build_multi_run_comparison_data requires at least one run")

    summaries: list[dict[str, Any]] = []
    action_keys: set[str] = set()
    visible_action_keys: set[str] = set()
    overhead_keys: set[str] = set()

    for label, events in normalized_runs:
        summary = summarize_run(events)
        llm_steps = sum(1 for event in events if event.event_type == EventType.LLM_CALL)
        unique_files = sorted({path for event in events for path in event.touched_files})
        total_actions = max(sum(summary.action_counts.values()), 1)
        non_overhead_events = [event for event in events if event.action_type != ActionType.OVERHEAD]
        non_overhead_counts = Counter(event.action_type.value for event in non_overhead_events)
        visible_total = max(sum(non_overhead_counts.values()), 1)
        dominant_action = max(summary.action_counts.items(), key=lambda item: item[1])[0] if summary.action_counts else None
        overhead_counts = Counter(
            _classify_overhead_event(event) for event in events if event.action_type == ActionType.OVERHEAD
        )
        run_details = _derive_run_details(events, summary)
        action_keys.update(summary.action_counts)
        visible_action_keys.update(non_overhead_counts)
        overhead_keys.update(overhead_counts)

        summaries.append(
            {
                "label": label,
                "run_id": summary.run_id,
                "success": summary.success,
                "success_num": 1 if summary.success else 0,
                "total_steps": summary.total_steps,
                "total_duration_ms": summary.total_duration_ms,
                "total_input_tokens": summary.total_input_tokens,
                "total_output_tokens": summary.total_output_tokens,
                "total_cached_tokens": summary.total_cached_tokens,
                "total_tests_run": summary.total_tests_run,
                "tests_passed": summary.tests_passed,
                "tests_failed": summary.tests_failed,
                "cache_ratio": summary.cache_ratio,
                "carry_forward_ratio": summary.memory_inefficiency_ratio,
                "memory_inefficiency_ratio": summary.memory_inefficiency_ratio,
                "wait_time_ratio": summary.wait_time_ratio,
                "dominant_action": dominant_action,
                "llm_steps": llm_steps,
                "unique_files": unique_files,
                "unique_files_count": len(unique_files),
                "action_counts": dict(summary.action_counts),
                "action_shares": {
                    action: summary.action_counts.get(action, 0) / total_actions
                    for action in summary.action_counts
                },
                "visible_action_counts": dict(non_overhead_counts),
                "visible_action_shares": {
                    action: non_overhead_counts.get(action, 0) / visible_total
                    for action in non_overhead_counts
                },
                "overhead_counts": dict(overhead_counts),
                **run_details,
            }
        )

    ordered_actions = sorted(action_keys)
    ordered_visible_actions = sorted(visible_action_keys)
    ordered_overhead = sorted(overhead_keys)

    action_breakdown = _build_action_rows(summaries, ordered_actions, counts_key="action_counts")
    visible_action_breakdown = _build_action_rows(
        summaries,
        ordered_visible_actions,
        counts_key="visible_action_counts",
    )
    overhead_breakdown = _build_action_rows(
        summaries,
        ordered_overhead,
        counts_key="overhead_counts",
    )
    burden_breakdown = [
        {"label": row["label"], "metric": "files_before_first_edit", "value": row["files_read_before_first_edit_count"]}
        for row in summaries
    ] + [
        {"label": row["label"], "metric": "edits_before_first_pass", "value": row["edits_before_first_pass"]}
        for row in summaries
    ] + [
        {"label": row["label"], "metric": "tests_before_first_pass", "value": row["tests_before_first_pass"]}
        for row in summaries
    ] + [
        {"label": row["label"], "metric": "tests_after_first_pass", "value": row["tests_after_first_pass"]}
        for row in summaries
    ] + [
        {"label": row["label"], "metric": "max_retry_burst", "value": row["max_retry_burst"]}
        for row in summaries
    ]

    success_count = sum(1 for row in summaries if row["success"])
    average_cache_ratio = sum(row["cache_ratio"] for row in summaries) / len(summaries)
    average_carry_forward_ratio = sum(row["carry_forward_ratio"] for row in summaries) / len(summaries)
    average_files_before_first_edit = sum(row["files_read_before_first_edit_count"] for row in summaries) / len(summaries)
    average_tests_before_first_pass = sum(row["tests_before_first_pass"] for row in summaries) / len(summaries)

    return {
        "runs": summaries,
        "action_breakdown": action_breakdown,
        "visible_action_breakdown": visible_action_breakdown,
        "overhead_breakdown": overhead_breakdown,
        "burden_breakdown": burden_breakdown,
        "action_palette": ACTION_COLORS,
        "overhead_palette": OVERHEAD_COLORS,
        "summary": {
            "run_count": len(summaries),
            "success_count": success_count,
            "average_cache_ratio": average_cache_ratio,
            "average_carry_forward_ratio": average_carry_forward_ratio,
            "average_files_before_first_edit": average_files_before_first_edit,
            "average_tests_before_first_pass": average_tests_before_first_pass,
        },
    }


def render_multi_run_comparison(
    runs: dict[str, list[NormalizedEvent]] | list[tuple[str, list[NormalizedEvent]]],
    output_path: str | Path,
    *,
    title: str | None = None,
) -> Path:
    data = build_multi_run_comparison_data(runs)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_build_comparison_html(data, title=title), encoding="utf-8")
    return output


def _normalize_runs(
    runs: dict[str, list[NormalizedEvent]] | list[tuple[str, list[NormalizedEvent]]],
) -> list[tuple[str, list[NormalizedEvent]]]:
    if isinstance(runs, dict):
        items = list(runs.items())
    else:
        items = list(runs)
    return [(str(label), list(events)) for label, events in items if events]


def _ordered_events(events: list[NormalizedEvent]) -> list[NormalizedEvent]:
    return sorted(
        events,
        key=lambda event: (
            event.timestamp_start.isoformat() if event.timestamp_start else "",
            event.step_id,
        ),
    )


def _derive_run_details(events: list[NormalizedEvent], summary: Any) -> dict[str, Any]:
    ordered_events = _ordered_events(events)
    file_counter = Counter(path for event in ordered_events for path in event.touched_files)
    module_counter = Counter(_module_label(path) for path in file_counter)

    first_edit_index: int | None = None
    first_pass_index: int | None = None
    tests_before_first_pass = 0
    edits_before_first_pass = 0
    unique_files_read_before_first_edit: set[str] = set()
    max_retry_burst = 0
    retry_burst = 0

    for index, event in enumerate(ordered_events, start=1):
        if first_edit_index is None and event.action_type == ActionType.EDIT:
            first_edit_index = index

        if first_edit_index is None and event.event_type == EventType.FILE_READ:
            unique_files_read_before_first_edit.update(event.touched_files)

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

    files_before_first_edit_count = len(unique_files_read_before_first_edit)
    tests_after_first_pass = summary.total_tests_run - tests_before_first_pass if first_pass_index is not None else 0

    return {
        "step_of_first_edit": first_edit_index,
        "step_of_first_pass": first_pass_index,
        "files_read_before_first_edit": sorted(unique_files_read_before_first_edit),
        "files_read_before_first_edit_count": files_before_first_edit_count,
        "edits_before_first_pass": edits_before_first_pass,
        "tests_before_first_pass": tests_before_first_pass,
        "tests_after_first_pass": tests_after_first_pass,
        "max_retry_burst": max_retry_burst,
        "retry_density": summary.retry_count / max(summary.total_steps, 1),
        "top_files": [
            {"label": path, "count": count}
            for path, count in file_counter.most_common(4)
        ],
        "top_modules": [
            {"label": module, "count": count}
            for module, count in module_counter.most_common(4)
        ],
    }


def _module_label(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "<unknown>"
    if parts[0] in {"src", "tests", "test", "lib"} and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _build_action_rows(
    summaries: list[dict[str, Any]],
    actions: list[str],
    *,
    counts_key: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in summaries:
        counts = row[counts_key]
        total = max(sum(counts.values()), 1)
        for action in actions:
            rows.append(
                {
                    "label": row["label"],
                    "run_id": row["run_id"],
                    "action": action,
                    "count": counts.get(action, 0),
                    "share": counts.get(action, 0) / total,
                }
            )
    return rows


def _classify_overhead_event(event: NormalizedEvent) -> str:
    if event.tool_name == "local_file_store":
        laminar_path = event.metadata.get("laminar_path") or []
        leaf = laminar_path[-1] if laminar_path else ""
        if leaf.endswith(".list") or leaf.endswith(".get") or leaf.endswith(".read"):
            return "persistence_lookup"
        if leaf.endswith(".write") or leaf.endswith(".put") or leaf.endswith(".save"):
            return "persistence_write"
        return "orchestration"
    if event.tool_name in {"task_tracker", "finish", "think"}:
        return "orchestration"
    return "unknown_internal"


def _build_focus_cards(runs: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for row in runs:
        top_modules = "".join(
            f"<li><span>{escape(item['label'])}</span><strong>{item['count']}</strong></li>"
            for item in row["top_modules"]
        ) or "<li><span>—</span><strong>0</strong></li>"
        top_files = "".join(
            f"<li><span>{escape(item['label'])}</span><strong>{item['count']}</strong></li>"
            for item in row["top_files"]
        ) or "<li><span>—</span><strong>0</strong></li>"
        cards.append(
            "<article class=\"focus-card\">"
            f"<h3>{escape(row['label'])}</h3>"
            f"<p class=\"focus-meta\">first edit step: {row['step_of_first_edit'] or '—'} · files before edit: {row['files_read_before_first_edit_count']} · edits before first pass: {row['edits_before_first_pass']} · tests before first pass: {row['tests_before_first_pass']}</p>"
            "<div class=\"focus-columns\">"
            f"<div><h4>Top modules</h4><ul class=\"focus-list\">{top_modules}</ul></div>"
            f"<div><h4>Top files</h4><ul class=\"focus-list\">{top_files}</ul></div>"
            "</div>"
            "</article>"
        )
    return "".join(cards)


def _build_comparison_html(data: dict[str, Any], *, title: str | None) -> str:
    summary = data["summary"]
    runs = data["runs"]
    document_title = title or "agent_viz — run comparison"
    payload_json = json.dumps(data, indent=2)

    cards = [
        ("Runs", str(summary["run_count"])),
        ("Successes", f"{summary['success_count']}/{summary['run_count']}"),
        ("Avg cache ratio", f"{summary['average_cache_ratio']:.1%}"),
        ("Avg carry-forward ratio", f"{summary['average_carry_forward_ratio']:.1%}"),
        ("Avg files before first edit", f"{summary['average_files_before_first_edit']:.1f}"),
        ("Avg tests before first pass", f"{summary['average_tests_before_first_pass']:.1f}"),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="card-label">{escape(label)}</div><div class="card-value">{escape(value)}</div></div>'
        for label, value in cards
    )
    rows_html = "".join(
        "<tr>"
        f"<td>{escape(row['label'])}</td>"
        f"<td>{escape(row['run_id'])}</td>"
        f"<td>{'yes' if row['success'] else 'no'}</td>"
        f"<td>{row['total_input_tokens']:,}</td>"
        f"<td>{row['total_output_tokens']:,}</td>"
        f"<td>{row['files_read_before_first_edit_count']}</td>"
        f"<td>{row['edits_before_first_pass']}</td>"
        f"<td>{row['tests_before_first_pass']}</td>"
        f"<td>{row['tests_after_first_pass']}</td>"
        f"<td>{row['max_retry_burst']}</td>"
        f"<td>{row['carry_forward_ratio']:.1%}</td>"
        "</tr>"
        for row in runs
    )
    focus_cards_html = _build_focus_cards(runs)

    glossary_rows = [
        (
            "Action mix",
            "Normalized share of classified events within a run. The top chart includes internal runtime work; the second chart removes overhead so visible coding behavior is easier to compare.",
        ),
        (
            "Overhead",
            "Internal harness/runtime work rather than direct repo work. In these traces it is mostly LocalFileStore persistence activity, split into persistence lookups and writes when possible.",
        ),
        (
            "Files before first edit",
            "Distinct files explicitly read before the first edit step. Lower is usually better, because it means the run searched less before committing to an edit.",
        ),
        (
            "Edits before first pass",
            "Number of edit steps before the first passing test. Lower is usually better; a low search count with many edits suggests the run committed quickly but not cleanly.",
        ),
        (
            "Tests before first pass",
            "Tests consumed before the first passing signal. For failed runs, this falls back to total tests run before the trace ended. Lower is usually better.",
        ),
        (
            "Tests after first pass",
            "Additional tests run after the first passing signal. Lower is better, because it suggests less verification churn after the patch was already plausible.",
        ),
        (
            "Max retry burst",
            "Longest consecutive burst of explicit retry or wait steps. Lower is usually better.",
        ),
        (
            "Carry-forward ratio",
            "Share of attributed prompt tokens coming from replayed context plus cached prefix tokens. Higher values mean more prior state is being carried forward into each LLM call.",
        ),
    ]
    glossary_html = "".join(
        f'<div class="glossary-row"><div class="glossary-term">{escape(term)}</div><div class="glossary-text">{escape(text)}</div></div>'
        for term, text in glossary_rows
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
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); }
    .page { max-width: 1460px; margin: 0 auto; padding: 24px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 20px; }
    .card, .panel, .focus-card { background: linear-gradient(180deg, var(--panel), var(--panel-soft)); border: 1px solid var(--border); border-radius: 16px; }
    .card { padding: 14px; min-height: 90px; }
    .card-label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
    .card-value { font-size: 24px; font-weight: 650; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
    .panel { padding: 14px; }
    .panel h2 { margin: 0 0 6px; font-size: 18px; }
    .panel p { margin: 0 0 12px; color: var(--muted); font-size: 14px; }
    .chart { width: 100%; height: 420px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 10px 12px; border-top: 1px solid rgba(154, 166, 209, 0.12); font-size: 14px; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
    .focus-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
    .focus-card { padding: 14px; }
    .focus-card h3 { margin: 0 0 8px; font-size: 16px; }
    .focus-meta { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
    .focus-columns { display: grid; grid-template-columns: 1fr; gap: 12px; }
    .focus-columns h4 { margin: 0 0 8px; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .focus-list { list-style: none; margin: 0; padding: 0; }
    .focus-list li { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-top: 1px solid rgba(154, 166, 209, 0.12); font-size: 13px; }
    .focus-list li:first-child { border-top: 0; padding-top: 0; }
    .glossary-row { display: grid; grid-template-columns: 190px 1fr; gap: 14px; padding: 10px 0; border-top: 1px solid rgba(154, 166, 209, 0.12); }
    .glossary-row:first-child { border-top: 0; padding-top: 0; }
    .glossary-term { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
    .glossary-text { font-size: 14px; line-height: 1.45; }
    @media (min-width: 980px) {
      .grid.two { grid-template-columns: 1fr 1fr; }
      .focus-columns { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"page\">
    <h1>__TITLE__</h1>
    <p style=\"margin:0 0 20px;color:#9aa6d1;\">Compare multiple runs under the same harness contract: success, token spend, carry-forward, and straightforward lower-is-better search and verification burdens.</p>
    <div class=\"cards\">__CARDS__</div>
    <div class=\"grid two\">
      <section class=\"panel\">
        <h2>Success versus token spend</h2>
        <p>Each point is one run, sized by total steps and colored by cache ratio. Hover for output tokens, tests before first pass, and files before first edit.</p>
        <div id=\"success-scatter\" class=\"chart\"></div>
      </section>
      <section class=\"panel\">
        <h2>Action mix per run</h2>
        <p>Normalized action shares across all classified events, including runtime overhead.</p>
        <div id=\"action-mix\" class=\"chart\"></div>
      </section>
    </div>
    <div class=\"grid two\">
      <section class=\"panel\">
        <h2>Visible action mix per run</h2>
        <p>Same mix after removing overhead, which makes exploration, editing, testing, and finalization easier to compare.</p>
        <div id=\"visible-action-mix\" class=\"chart\"></div>
      </section>
      <section class=\"panel\">
        <h2>Overhead breakdown per run</h2>
        <p>Subdivides overhead into persistence lookups, persistence writes, orchestration, and unknown internal work.</p>
        <div id=\"overhead-breakdown\" class=\"chart\"></div>
      </section>
    </div>
    <div class=\"grid two\">
      <section class=\"panel\">
        <h2>Search burden versus test burden</h2>
        <p>X-axis is files before the first edit; Y-axis is tests before the first pass or run end. Marker size tracks total steps and color tracks carry-forward ratio.</p>
        <div id=\"burden-scatter\" class=\"chart\"></div>
      </section>
      <section class=\"panel\">
        <h2>Direct burden metrics per run</h2>
        <p>Grouped bars show files before first edit, edits before first pass, tests before first pass, tests after first pass, and retry bursts. Lower is usually better.</p>
        <div id=\"burden-bars\" class=\"chart\"></div>
      </section>
    </div>
    <section class=\"panel\">
      <h2>Run focus snapshots</h2>
      <p>Top modules and files help distinguish runs that share the same benchmark pattern but work in different areas of the repo.</p>
      <div class=\"focus-grid\">__FOCUS_CARDS__</div>
    </section>
    <section class=\"panel\">
      <h2>Run summary table</h2>
      <p>Compact per-run metrics using direct lower-is-better search and verification counts.</p>
      <table>
        <thead>
          <tr><th>Label</th><th>Run ID</th><th>Success</th><th>Input tokens</th><th>Output tokens</th><th>Files before first edit</th><th>Edits before first pass</th><th>Tests before first pass</th><th>Tests after first pass</th><th>Max retry burst</th><th>Carry-forward ratio</th></tr>
        </thead>
        <tbody>__ROWS__</tbody>
      </table>
    </section>
    <section class=\"panel\">
      <h2>Metric glossary</h2>
      <p>Definitions for the comparison charts and table metrics.</p>
      __GLOSSARY__
    </section>
  </div>
  <script>
    const comparisonData = __PAYLOAD__;

    function buildSuccessScatter() {
      const rows = comparisonData.runs;
      Plotly.newPlot('success-scatter', [{
        type: 'scatter',
        mode: 'markers+text',
        x: rows.map((row) => row.total_input_tokens),
        y: rows.map((row) => row.success_num),
        text: rows.map((row) => row.label),
        textposition: 'top center',
        marker: {
          size: rows.map((row) => Math.max(12, Math.min(40, 12 + Math.sqrt(row.total_steps)))),
          color: rows.map((row) => row.cache_ratio),
          colorscale: 'Viridis',
          showscale: true,
          colorbar: { title: 'cache ratio' },
          line: { color: '#edf1ff', width: 0.8 },
        },
        customdata: rows.map((row) => [row.run_id, row.total_steps, row.total_output_tokens, row.carry_forward_ratio, row.tests_before_first_pass, row.files_read_before_first_edit_count, row.edits_before_first_pass]),
        hovertemplate: '<b>%{text}</b><br>run=%{customdata[0]}<br>input tokens=%{x}<br>output tokens=%{customdata[2]}<br>success=%{y}<br>steps=%{customdata[1]}<br>carry-forward ratio=%{customdata[3]:.2%}<br>tests before first pass=%{customdata[4]}<br>files before first edit=%{customdata[5]}<br>edits before first pass=%{customdata[6]}<extra></extra>',
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { title: 'input tokens', gridcolor: '#2b3355' },
        yaxis: { title: 'success', tickmode: 'array', tickvals: [0, 1], ticktext: ['no', 'yes'], gridcolor: '#2b3355' },
        margin: { l: 70, r: 50, t: 16, b: 48 },
      }, { responsive: true });
    }

    function buildStackedBar(elementId, rows, palette) {
      const actions = [...new Set(rows.map((row) => row.action))];
      const labels = [...new Set(rows.map((row) => row.label))];
      const traces = actions.map((action) => {
        const filtered = rows.filter((row) => row.action === action);
        return {
          type: 'bar',
          name: action,
          x: filtered.map((row) => row.label),
          y: filtered.map((row) => row.share),
          marker: { color: palette[action] || '#888' },
          hovertemplate: `${action}: %{y:.1%}<extra></extra>`,
        };
      });
      Plotly.newPlot(elementId, traces, {
        barmode: 'stack',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { categoryorder: 'array', categoryarray: labels },
        yaxis: { title: 'share of steps', tickformat: '.0%', gridcolor: '#2b3355' },
        margin: { l: 70, r: 24, t: 16, b: 48 },
        legend: { orientation: 'h' },
      }, { responsive: true });
    }

    function buildBurdenScatter() {
      const rows = comparisonData.runs;
      Plotly.newPlot('burden-scatter', [{
        type: 'scatter',
        mode: 'markers+text',
        x: rows.map((row) => row.files_read_before_first_edit_count),
        y: rows.map((row) => row.tests_before_first_pass),
        text: rows.map((row) => row.label),
        textposition: 'top center',
        marker: {
          size: rows.map((row) => Math.max(12, Math.min(40, 12 + Math.sqrt(row.total_steps)))),
          color: rows.map((row) => row.carry_forward_ratio),
          colorscale: 'Plasma',
          showscale: true,
          colorbar: { title: 'carry-forward' },
          line: { color: '#edf1ff', width: 0.8 },
        },
        customdata: rows.map((row) => [row.max_retry_burst, row.edits_before_first_pass, row.tests_after_first_pass]),
        hovertemplate: '<b>%{text}</b><br>files before first edit=%{x}<br>tests before first pass=%{y}<br>edits before first pass=%{customdata[1]}<br>tests after first pass=%{customdata[2]}<br>max retry burst=%{customdata[0]}<extra></extra>',
      }], {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        xaxis: { title: 'files before first edit', gridcolor: '#2b3355' },
        yaxis: { title: 'tests before first pass', gridcolor: '#2b3355' },
        margin: { l: 70, r: 50, t: 16, b: 48 },
      }, { responsive: true });
    }

    function buildBurdenBars() {
      const rows = comparisonData.burden_breakdown;
      const metrics = [...new Set(rows.map((row) => row.metric))];
      const traces = metrics.map((metric) => {
        const filtered = rows.filter((row) => row.metric === metric);
        return {
          type: 'bar',
          name: metric.replaceAll('_', ' '),
          x: filtered.map((row) => row.label),
          y: filtered.map((row) => row.value),
          hovertemplate: `${metric.replaceAll('_', ' ')}: %{y}<extra></extra>`,
        };
      });
      Plotly.newPlot('burden-bars', traces, {
        barmode: 'group',
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#edf1ff' },
        yaxis: { title: 'count', gridcolor: '#2b3355' },
        margin: { l: 70, r: 24, t: 16, b: 48 },
        legend: { orientation: 'h' },
      }, { responsive: true });
    }

    buildSuccessScatter();
    buildStackedBar('action-mix', comparisonData.action_breakdown, comparisonData.action_palette);
    buildStackedBar('visible-action-mix', comparisonData.visible_action_breakdown, comparisonData.action_palette);
    buildStackedBar('overhead-breakdown', comparisonData.overhead_breakdown, comparisonData.overhead_palette);
    buildBurdenScatter();
    buildBurdenBars();
  </script>
</body>
</html>
"""

    return (
        template.replace("__TITLE__", escape(document_title))
        .replace("__CARDS__", cards_html)
        .replace("__ROWS__", rows_html)
        .replace("__FOCUS_CARDS__", focus_cards_html)
        .replace("__GLOSSARY__", glossary_html)
        .replace("__PAYLOAD__", payload_json)
    )
