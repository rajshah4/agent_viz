# agent_viz

Visual analytics for understanding how coding agents behave on long-running tasks.

**Live gallery:** https://rajshah4.github.io/agent_viz/  
**Reading guide:** [`docs/dashboard_reading_guide.md`](./docs/dashboard_reading_guide.md)  
**Product framing:** [`docs/product_thesis.md`](./docs/product_thesis.md)

`agent_viz` turns agent traces into compact visual explanations of what happened during a run, where time and tokens went, and whether the run was converging or just getting heavier.

The current showcased traces come from the [OpenHands Index](https://huggingface.co/spaces/OpenHands/openhands-index). The immediate focus is shared Laminar traces and similar coding-agent trajectories, but the product goal is broader: make long agent runs legible to humans.

## What these dashboards are for

The dashboards are designed to answer questions like:

- Was the run mostly reading, editing, testing, retrying, or waiting?
- How quickly did the agent localize the right files?
- Did failing tests lead to productive repair or more wandering?
- Did passing tests actually end the run?
- Was prompt growth driven by fresh context or by carry-forward?
- How much of the trajectory was real repo work versus harness or runtime overhead?

## Visualization highlights

### Behavior and burden summary

A compact front page for the run:

- duration, tokens, and carry-forward ratio
- files before first edit
- edits before first pass
- tests before first pass
- tests after first pass
- max retry burst

This is the quickest way to tell whether a run looks efficient, expensive, or churn-heavy.

### Harness lane occupancy

A wall-clock view of which layer held the run over time:

- `controller`
- `model`
- `workspace`
- `runtime`

This makes it easy to see whether the run was dominated by prompting, repo work, orchestration churn, or hidden overhead.

### Lane summary and handoffs

A compressed summary of the lane view, plus a Sankey showing how control moved between layers.

Useful for spotting:

- many short controller bursts
- long workspace bursts of focused repo work
- long model bursts from repeated or heavy LLM calls
- runtime activity that is larger than expected

### Feedback to next meaningful move heatmap

A dense view of what happened after each feedback category, using collapsed outcome labels instead of raw `execute`.

Typical columns include:

- `edit`
- `file content`
- `test failure`
- `test pass`
- `shell output`
- `shell error`
- `retry`
- `wait`
- `finalize`

This helps show whether failures lead to repair, whether reads lead to edits, and whether success usually ends the run.

### Anchor flow views

Two related Sankey views explain post-action behavior:

- **All anchors overview** - one dense combined map across `inspect`, `edit`, `test failure`, and `test pass`
- **Selected anchor: next two meaningful moves** - a cleaner selector-based view for one anchor at a time

These views collapse routine execution into visible outcomes so the flow emphasizes what the agent learned or did next.

### Prompt makeup per LLM call

A normalized stacked bar chart showing whether each prompt was mostly:

- fresh task ask
- fresh repo/tool context
- replayed prior context
- cached prefix reuse
- tool output added

This is useful for seeing when prompts stop getting smarter and start getting heavier.

### File transition graph and cumulative progress

Together these show whether the run narrowed onto a small file cluster and whether growing token spend translated into visible progress.

Useful for spotting:

- search-heavy wandering
- concentrated repair around a small module cluster
- verification churn after a plausible fix already exists
- token growth without corresponding tests passed or convergence

## What a good run versus a bad run often looks like

### Productive repair loop

Common signs:

- low files-before-first-edit
- `test failure` to `edit` is prominent
- `test pass` to `finalize` is visible
- workspace activity dominates more than controller churn

### Search-heavy wandering

Common signs:

- high files-before-first-edit
- repeated `file content` to `file content`
- broad file transitions instead of a tight cluster
- unique files touched rises while progress stays flat

### Verification churn

Common signs:

- many tests before or after first pass
- post-edit flows keep returning to `test failure`
- workspace bursts stay large while progress is flat

### Harness or runtime overhead

Common signs:

- controller or runtime lanes consume a surprising share of time
- burst count is high in controller
- retries, waits, or persistence activity are unusually visible

## Open the dashboards

### GitHub Pages gallery

- Gallery landing page: https://rajshah4.github.io/agent_viz/
- Curated comparison view: [`agent_viz_compare_four_live.html`](./agent_viz_compare_four_live.html)
- Single trace: [`laminar_trace_39f38cb4.html`](./laminar_trace_39f38cb4.html)
- Single trace: [`laminar_trace_537db26f.html`](./laminar_trace_537db26f.html)
- Single trace: [`laminar_trace_67ade002.html`](./laminar_trace_67ade002.html)
- Single trace: [`laminar_trace_9c186814.html`](./laminar_trace_9c186814.html)

## Learn how to read the charts

- [`docs/dashboard_reading_guide.md`](./docs/dashboard_reading_guide.md) - chart-by-chart explanation and interpretation tips
- [`docs/dashboard_spec.md`](./docs/dashboard_spec.md) - compact dashboard and metric spec
- [`docs/product_thesis.md`](./docs/product_thesis.md) - what this should borrow from trace viewers and what it should avoid
- [`docs/laminar_parser.md`](./docs/laminar_parser.md) - Laminar parser scope, assumptions, and observed fields

## Project layout

- `src/agent_viz/dashboard.py` - single-run dashboard data builder and HTML renderer
- `src/agent_viz/comparison.py` - multi-run comparison data builder and HTML renderer
- `src/agent_viz/laminar.py` - Laminar trace parsing into normalized events
- `src/agent_viz/laminar_loader.py` - fetch shared Laminar traces from IDs or URLs
- `src/agent_viz/metrics.py` - run summaries, burden metrics, and file transitions
- `tests/test_dashboard.py` - dashboard data and rendering coverage

## Local rendering, if you want it

The README is intentionally showcase-first, but local rendering is straightforward when needed.

Render a single Laminar reference:

```bash
cd /Users/rajiv.shah/Code/agent_viz
PYTHONPATH=src python3 -m agent_viz.render_laminar '<laminar_reference>' -o /tmp/agent_viz_single.html
```

Render a comparison dashboard:

```bash
cd /Users/rajiv.shah/Code/agent_viz
PYTHONPATH=src python3 -m agent_viz.render_compare '<laminar_ref_1>' '<laminar_ref_2>' -o /tmp/agent_viz_compare.html
```
