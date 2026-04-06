# Product Thesis

`agent_viz` should not become a generic trace viewer.

Its job is to explain long-running coding-agent behavior in a way that makes inefficiency, convergence, and memory carry-forward obvious.

## What to borrow from generic trace tools

- practical ingestion patterns for nested spans and events
- convenient run navigation and filtering
- drill-down from run to step to raw event
- stable handling of timestamps, statuses, and tool boundaries

## What to avoid copying

- product framing centered on trace inspection alone
- data models that flatten away coding-specific progress signals
- dashboards that stop at token totals and latency
- interfaces that make it hard to compare many runs at once

## Distinctive thesis for agent_viz

The core question is not just "what happened in this trace?"

It is:

> Why did this agent spend time, tokens, and effort the way it did, and did that effort move the task closer to resolution?

That pushes the product toward:

1. action taxonomy
   - inspect
   - plan
   - edit
   - execute
   - retry
   - wait
   - finalize

2. prompt composition analysis
   - new task information
   - retrieved context
   - replayed prior state
   - cached prefix
   - tool output injected back in

3. progress-linked metrics
   - files read before first edit
   - edits before first passing test
   - tests and pass rate over time
   - unique files touched over time
   - token growth relative to concrete progress

4. cross-run comparison
   - heatmaps
   - funnels
   - efficiency scatter plots
   - repo navigation graphs

## First implementation principle

Start from a normalized event model and derived metrics, then build the first dashboard around those metrics.

That keeps trace ingestion replaceable while preserving the higher-level behavioral analysis layer.
