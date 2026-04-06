# Dashboard Spec

## Objective

Create a compact dashboard that explains long-running coding agent behavior at three levels at once:

1. whole-run overview
2. step-level prompt and action composition
3. progress toward resolution

The dashboard should help answer whether the agent is converging, looping, or simply carrying too much state forward.

## Primary entities

### Run
A full agent attempt on one task or issue.

### Step
A single model turn, tool call, grouped reasoning span, or other atomic unit in the trace.

### Event
A timestamped record emitted by the runtime, model, or tooling layer.

## Normalized event schema

Each raw trace record should be mapped into a normalized event with fields like:

- `run_id`
- `step_id`
- `parent_step_id`
- `timestamp_start`
- `timestamp_end`
- `duration_ms`
- `source` — model, tool, runtime, retrieval, system
- `event_type` — llm_call, tool_call, tool_result, file_read, file_edit, test_run, message, retry, wait
- `action_type` — inspect, plan, edit, execute, retry, wait, finalize
- `tool_name`
- `file_path`
- `token_input`
- `token_output`
- `token_cached`
- `cost_usd`
- `status` — success, error, timeout, interrupted
- `test_count`
- `tests_passed`
- `tests_failed`
- `metadata`

## Derived metrics

### Run-level metrics

- total duration
- total steps
- total input tokens
- total output tokens
- total cached tokens
- total tool calls
- total file reads
- total file edits
- total tests run
- first edit step
- first test step
- first passing test step
- unique files read
- unique files edited
- retry count
- wait time ratio
- cache ratio
- success flag

### Efficiency metrics

- **localization efficiency** = time or steps to first relevant edit
- **repair efficiency** = edits before first plausible patch
- **verification efficiency** = tests after first plausible patch until final pass
- **memory inefficiency** = replayed context / total prompt context after localization

### Step-level prompt composition

For each LLM call, estimate prompt input shares:

- new task info
- newly retrieved context
- replayed prior context
- cached prefix
- injected tool output

## Recommended charts

### 1. Whole-run stacked timeline

**Purpose:** show where time or token volume went.

- x-axis: wall-clock time or step number
- y-axis: duration, tokens, or cost
- stack/color: inspect, plan, edit, execute, retry, wait

**Questions answered**
- Was the run mostly exploration, execution, or recovery?
- Did retries dominate the second half of the run?

### 2. Prompt composition chart per step

**Purpose:** show what each model call was made of.

- one stacked bar per LLM step
- segments:
  - new task info
  - retrieved context
  - replayed context
  - cached prefix
  - tool output injected back in

**Questions answered**
- Is the agent rereading or replaying too much?
- Does prompt growth eventually become mostly carry-forward?

### 3. Cumulative progress plot

**Purpose:** compare spending versus progress.

Suggested lines:
- cumulative input tokens
- cumulative output tokens
- cumulative cached tokens
- cumulative tests run
- cumulative tests passed
- cumulative unique files touched

**Questions answered**
- Are tokens rising without equivalent progress?
- Did the agent converge after localization or keep wandering?

### 4. Per-step heatmap across runs

**Purpose:** compare many runs quickly.

- rows: runs
- columns: steps
- color: dominant action type, token volume, or error state

**Questions answered**
- Which runs are short and decisive?
- Which runs fall into retry spirals or exploration-heavy loops?

### 5. Repo navigation graph

**Purpose:** show whether the agent narrows onto relevant files.

- nodes: files or tools
- edges: transitions between successive file touches or tool calls
- optional node size: number of visits
- optional edge weight: transition count

**Questions answered**
- Did the agent focus on a small file cluster?
- Did it bounce broadly around the repo?

### 6. Funnel chart

**Purpose:** summarize effort reduction from exploration to resolution.

Suggested stages:
- files discovered
- files opened
- files edited
- tests run
- candidate fixes attempted
- successful resolution

## Minimal viable dashboard

If building the first version quickly, start with:

1. whole-run stacked timeline
2. prompt composition per step
3. cumulative progress plot
4. cross-run heatmap

## Data requirements

To make the first version useful, the trace source should expose or allow reconstruction of:

- timestamps
- model call boundaries
- prompt and completion token counts
- tool invocation boundaries
- tool outputs
- file paths touched
- command execution outcomes
- test outcomes
- retry or error markers

## Open questions

- How should we infer `action_type` when traces are incomplete?
- Can prompt segments be measured exactly, or only approximated?
- What counts as a `plausible patch` before tests pass?
- How should multi-file edits be grouped into patch attempts?
