# AGENTS.md

## Repository purpose

This repository is for analyzing long-running coding agent traces and building visuals that explain agent behavior over time.

Primary target questions:
- where time, tokens, and cost go during a run
- how much state is replayed across steps
- whether exploration, editing, and verification are efficient
- how successful and unsuccessful runs differ

## Current state

Initial Python scaffold is in place.

Current implemented artifacts:
- `src/agent_viz/models.py` for normalized event and summary data models
- `src/agent_viz/metrics.py` for run summary and file-transition derivation
- `src/agent_viz/laminar.py` for first-pass Laminar shared trace parsing
- `src/agent_viz/laminar_loader.py` for loading shared Laminar traces from URLs or IDs
- `src/agent_viz/dashboard.py` for single-run dashboard data prep and HTML rendering
- `src/agent_viz/render_laminar.py` for CLI rendering from Laminar references
- `tests/test_metrics.py`, `tests/test_laminar_parser.py`, `tests/test_laminar_loader.py`, and `tests/test_dashboard.py` for lightweight validation
- `docs/product_thesis.md` for positioning versus generic trace viewers
- `docs/laminar_parser.md` for parser scope and assumptions

## Working conventions

- Keep the first implementation centered on a normalized event model.
- Prefer a small number of clear charts over a large dashboard.
- Focus on action categories that are legible to humans: inspect, plan, edit, execute, retry, wait, finalize.
- Separate raw trace ingestion from metric derivation and visualization.
- Keep examples trace-source-agnostic, but Laminar-style traces are the first concrete target.

## Useful next artifacts

- broader Laminar compatibility from more sampled real traces
- richer efficiency metrics beyond the current run summary
- multi-run comparison prototype
- direct shared-trace loading helpers
- additional trace fixtures for different agent runtimes

## Notes for future sessions

- Shared eval URLs with `traceId=...` can now be rendered directly via the Laminar loader.
- Laminar loading now hydrates detailed LLM and action spans to recover prompt messages, file paths, and terminal test summaries from public shared traces.
- Internal `LocalFileStore.*` spans are treated as `overhead` rather than repo edits/reads.
- Single-run dashboard now includes a compact behavior-and-burden summary with direct lower-is-better metrics such as files before first edit, edits before first pass, tests before first pass, tests after first pass, and max retry burst.
- Single-run dashboard includes harness-oriented teaching views: a burden bar chart, wall-clock harness lane occupancy, lane summary plus layer handoffs, feedback-to-next-action Sankey, control-event timeline, and a clickable step anatomy inspector.
- Prompt composition in single-run dashboards is now shown as a 100%-stacked `prompt makeup per LLM call` chart with clearer labels for fresh task ask, fresh repo/tool context, replayed prior context, cached prefix reuse, and tool output added.
- Single-run file transition graphs are now filtered to the most-touched files so the main repo navigation path stays readable on long traces.
- Prompt makeup charts now use compact `LLM N` x-labels with only a sparse subset of tick labels shown; detailed step references move into hover text to avoid overlap on long runs.
- File transition Sankey nodes now display short file names (falling back to the last two path segments when basenames collide) while keeping full paths in hover text.
- `Harness steering events` replaces the older control-events wording and only shows harness-side actions like plan updates, retries, waits, interruptions, and finish.
- Single-run dashboards now stop at `cumulative progress`; the experimental verification-lag/focused-window section was removed because it was not as useful as the core views.
- Derived test counts are only inferred for actual test commands and `test_run` events; file reads and other non-test spans should not create fake test spikes.



- Duration is now split in single-run dashboards: `wall-clock duration` is first observed start to last observed end, while `summed event duration` adds step durations and can exceed wall-clock when spans overlap or nest.

- Feedback-to-next-action transitions skip intermediate `plan` and `overhead` steps so the chart reflects material next actions like `execute`, `edit`, and `finalize`.
- Multi-run comparisons are available via `agent-viz-compare` / `python -m agent_viz.render_compare` and now include token/burden scatter, action mix, visible action mix, overhead breakdown, direct burden bars, and per-run focus snapshots.
- Comparison dashboard now uses the UI term `carry-forward ratio` instead of `memory inefficiency`; it is defined as replayed-context tokens plus cached-prefix tokens divided by total attributed prompt-composition tokens.
- `Unique files` in comparison views means distinct file paths touched in reads or edits, not total repo files and not a created-vs-modified breakdown.
- Overhead is now subdivided in comparisons; for current OpenHands Laminar traces it is mostly `LocalFileStore.list` and `LocalFileStore.write`, shown as persistence lookups and persistence writes.
- Comparison dashboards now emphasize direct lower-is-better burden metrics instead of abstract ratios: files before first edit, edits before first pass, tests before first pass, tests after first pass, and max retry burst.
- For failed runs, `tests before first pass` falls back to total tests run before the trace ended; this keeps the metric easy to compare across success and failure cases.
- The comparison page includes run focus snapshots showing top modules and top files, which is useful when same-benchmark traces have similar action mixes but touch different code areas.
- GitHub Pages publishing is intentionally minimal: a hand-written root `index.html` plus `.github/workflows/deploy-pages.yml`, which copies a curated set of standalone HTML dashboards into `_site`; update both files together when changing the showcase.





- The first spec lives in `docs/dashboard_spec.md`.
- README captures the initial product direction and key visual ideas.
