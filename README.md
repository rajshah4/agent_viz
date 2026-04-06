# agent_viz

Visual analytics for understanding how coding agents behave on long-running tasks.

## Goal

`agent_viz` is a small workspace for turning agent traces into visuals that explain what happened during a run, where time and tokens went, and whether the agent was making progress or just replaying state.

The immediate use case is analyzing traces like Laminar eval traces and similar trajectories from OpenHands Index or older SWE-bench-style runs.

## Core questions

- Was a run mostly reading, reasoning, editing, testing, retrying, or waiting?
- How much context was newly acquired versus replayed from earlier steps?
- How quickly did the agent localize the right files?
- How many edits and tests happened before the first plausible fix?
- When do tokens keep increasing without corresponding progress?

## Initial dashboard ideas

1. **Run timeline / stacked ribbon**
   - read / inspect
   - plan / reason
   - edit / patch
   - test / execute
   - retry / recover
   - idle / wait / tool overhead

2. **Prompt composition per step**
   - new task info
   - retrieved repo or tool context
   - replayed prior context
   - cached prefix
   - injected tool output

3. **Progress charts**
   - files read before first edit
   - edits before first passing test
   - tests run over time
   - pass rate over time
   - unique files touched over time

4. **Cross-run comparison views**
   - per-step heatmap across many runs
   - success vs total tokens scatter plot
   - localization and verification efficiency summaries

## Current scaffold

- `pyproject.toml` — lightweight Python package config
- `src/agent_viz/models.py` — normalized events, prompt composition, run summary models
- `src/agent_viz/metrics.py` — run summarization and file-transition utilities
- `src/agent_viz/laminar.py` — first-pass Laminar shared trace parser
- `src/agent_viz/laminar_loader.py` — fetch shared Laminar traces from trace IDs or URLs
- `src/agent_viz/comparison.py` — multi-run comparison data builder and HTML renderer
- `src/agent_viz/dashboard.py` — single-run dashboard data builder and HTML renderer
- `src/agent_viz/render_compare.py` — CLI for rendering multi-run comparisons from Laminar references
- `src/agent_viz/render_laminar.py` — CLI for rendering dashboards from Laminar references
- `examples/laminar_shared_trace.json` — example Laminar-style trace payload
- `examples/render_example_dashboard.py` — helper script to render the example dashboard
- `tests/test_metrics.py` — metric unit coverage
- `tests/test_laminar_parser.py` — Laminar parsing coverage
- `tests/test_laminar_loader.py` — shared URL and fetch-flow coverage
- `tests/test_dashboard.py` — dashboard data and rendering coverage
- `docs/dashboard_spec.md` — compact dashboard and metrics spec
- `docs/product_thesis.md` — what to borrow from trace viewers and what to avoid copying
- `docs/laminar_parser.md` — parser assumptions, scope, and observed fields
- `AGENTS.md` — repository memory and working conventions

## Current parser entry points

- `parse_laminar_trace_payload(payload)`
- `parse_laminar_trace_responses(trace_response, spans_response)`

The parser currently targets shared Laminar trace data and converts spans into `NormalizedEvent` records using heuristics for action type, event type, file touches, tests, and prompt composition.

## Current dashboard entry points

- `build_single_run_dashboard_data(events)`
- `render_single_run_dashboard(events, output_path, title=None)`

The single-run dashboard now renders a standalone HTML file with teaching-oriented harness views:

1. behavior and burden summary, with direct lower-is-better counts
2. search / edit / verify burden bar chart
3. harness lane occupancy over wall-clock time
4. lane summary and layer-to-layer handoffs
5. feedback-to-next-action Sankey flow
6. run timeline by action type
7. normalized prompt makeup per LLM call
8. control-event timeline
9. step anatomy inspector
10. cumulative progress lines
11. top-file transition Sankey graph

To render the included example dashboard:

```bash
cd /Users/rajiv.shah/Code/agent_viz
python3 examples/render_example_dashboard.py
```

You can also pass a custom output path:

```bash
python3 examples/render_example_dashboard.py /tmp/agent_viz_dashboard.html
```

## Render directly from a Laminar URL

Supported inputs:

- shared trace URL: `https://laminar.sh/shared/traces/<trace_id>`
- shared eval URL with `traceId=...`
- raw trace ID

Example using the trace URL you shared:

```bash
cd /Users/rajiv.shah/Code/agent_viz
PYTHONPATH=src python3 -m agent_viz.render_laminar 'https://laminar.sh/shared/evals/c97e4a45-8a14-428f-8eac-f77ef6eb75a8?traceId=537db26f-50c3-7350-1a28-dfdf1a349f66&datapointId=5ccd7459-f332-4234-9e74-08946800a41c&spanId=00000000-0000-0000-67ef-a3041a16198b' -o /tmp/laminar_trace_live.html
```

If installed as a package, you can also use:

```bash
agent-viz-laminar '<laminar_reference>' -o /tmp/laminar_trace_live.html
```

The Laminar loader now hydrates detailed LLM and action spans when available, which improves:

- file path extraction for `FileEditorAction`
- test-run detection and pass/fail parsing for `TerminalAction`
- prompt carry-forward attribution from hydrated LLM message history
- the single-run dashboard now shows both `wall-clock duration` (first observed start to last observed end) and `summed event duration` (sum of step durations), since nested or overlapping spans can make the latter larger than the former

- separation of internal Laminar/OpenHands persistence activity into an `overhead` action bucket


## Included generated dashboards

This repo also includes committed HTML artifacts you can open directly from the repository:

- Single trace: [`laminar_trace_39f38cb4.html`](./laminar_trace_39f38cb4.html)
- Single trace: [`laminar_trace_537db26f.html`](./laminar_trace_537db26f.html)
- Single trace: [`laminar_trace_67ade002.html`](./laminar_trace_67ade002.html)
- Single trace: [`laminar_trace_9c186814.html`](./laminar_trace_9c186814.html)
- Comparison view: [`agent_viz_compare.html`](./agent_viz_compare.html)
- Comparison view (two live traces): [`agent_viz_compare_two_live.html`](./agent_viz_compare_two_live.html)
- Comparison view (four live traces): [`agent_viz_compare_four_live.html`](./agent_viz_compare_four_live.html)


## Compare multiple runs

You can also render a lightweight comparison dashboard across multiple Laminar references:

```bash
cd /Users/rajiv.shah/Code/agent_viz
PYTHONPATH=src python3 -m agent_viz.render_compare '<laminar_ref_1>' '<laminar_ref_2>' -o /tmp/agent_viz_compare.html
```

If installed as a package:

```bash
agent-viz-compare '<laminar_ref_1>' '<laminar_ref_2>' -o /tmp/agent_viz_compare.html
```

The comparison view currently includes:

- success vs token spend, with output tokens plus search/test burden details in hover tooltips
- normalized action mix per run
- visible action mix per run, excluding overhead
- overhead breakdown per run (for example, LocalFileStore lookups vs writes)
- search burden vs test burden scatter
- direct burden bars for files before first edit, edits before first pass, tests before first pass, tests after first pass, and retry bursts
- top modules / top files snapshots for each run
- compact run summary table for same-harness comparisons
- on-page glossary definitions for files before first edit, edits before first pass, tests before first pass, tests after first pass, max retry burst, and carry-forward ratio

## Likely next steps

1. Improve Laminar field extraction against more real shared traces and SDK variants.
2. Add clearer repair-quality metrics beyond the current search and verification burden counts.
3. Add small multiples and heatmaps for comparing many runs.
4. Add stronger controller-state metrics such as retries-to-success, finish attempts, and stop-condition markers.

## First-pass action taxonomy

- `inspect`
- `plan`
- `edit`
- `execute`
- `retry`
- `wait`
- `finalize`

This taxonomy can be refined later as real trace data is sampled.
