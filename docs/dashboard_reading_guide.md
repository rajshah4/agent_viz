# Dashboard Reading Guide

This guide explains what each single-run dashboard visualization is trying to show, how to read it, and what kinds of agent behavior it is useful for spotting.

The dashboard is not meant to be a generic trace viewer. It is meant to help answer a few practical questions quickly:

- where the run spent time and effort
- whether the agent localized the right code area efficiently
- whether post-edit behavior was productive or repetitive
- whether the harness, model, workspace, or runtime held the run
- whether tokens and tests translated into visible progress

## How to read the page overall

A good default reading order is:

1. **Behavior and burden summary** for the headline signals
2. **Search / edit / verify burden** for direct lower-is-better counts
3. **Harness lane occupancy** and **Lane summary and handoffs** for where control sat over time
4. **Feedback → next meaningful move heatmap** plus the anchor flow views for reaction patterns
5. **Prompt makeup per LLM call** and **Cumulative progress** for prompt growth versus progress
6. **File transition graph** and **Step anatomy** for detailed investigation

## A note on interpretation

These visuals are derived from normalized events and heuristics. They are very useful, but they are still summaries.

A few important examples:

- `finalize` means the run appeared to conclude or submit an answer, not necessarily the literal last raw event.
- `file content` means the run appears to have read file contents rather than listing a directory.
- routine `execute` spans are collapsed into outcomes in the anchor views and in the feedback heatmap, so the charts emphasize what the execution revealed rather than the existence of a command.
- overlapping spans can make some time-based lane shares add to more than 100% across lanes.

## Chart-by-chart guide

### Behavior and burden summary

**What it is**

A compact set of headline metrics for the run, including duration, tokens, carry-forward ratio, and lower-is-better burden counts.

**How to read it**

Use it as the dashboard's front page. It should tell you whether the run was short or long, prompt-heavy or tool-heavy, and whether the search and verification burden looks low or high.

**Useful for spotting**

- expensive runs that did not make much progress
- runs that replayed too much prior context
- runs that needed many files, edits, or tests before reaching a pass

### Search / edit / verify burden

**What it is**

A direct bar chart for:

- files before first edit
- edits before first pass
- tests before first pass
- tests after first pass
- max retry burst

**How to read it**

Smaller is usually better. The point is not to reduce everything to one score, but to make search burden and verification burden visible without abstraction.

**Useful for spotting**

- slow localization before the first concrete patch
- repair churn before the first plausible fix
- excessive verification after the run already had a passing test
- retry spirals driven by harness behavior

### Harness lane occupancy

**What it is**

A wall-clock view of which lane held the run over time:

- `controller`
- `model`
- `workspace`
- `runtime`

Each horizontal bar is a burst of consecutive events in the same lane.

**How to read it**

Read it as the movie of the run. Look for long uninterrupted stretches, rapid alternation, or lanes that dominate large parts of the trajectory.

**Useful for spotting**

- long model-heavy stretches where prompting dominates
- long workspace-heavy stretches of reading, editing, or testing
- controller churn from retries, waits, or repeated steering
- runtime overhead that is surprisingly visible relative to actual work

### Lane summary and handoffs

**What it is**

A compressed summary of the lane occupancy view plus a Sankey of transitions between lane bursts.

Each lane row reports:

- active time
- share of full run time
- event count and event share
- median event duration
- longest burst
- burst count

The handoff Sankey counts transitions like `controller → model` or `workspace → controller` between consecutive bursts.

**How to read it**

Think of this section as the box score for the lane timeline.

- **active time** shows how much wall-clock time the lane was active after merging overlaps within that lane
- **event count** shows how often that lane appeared
- **median event duration** shows the typical event size in that lane
- **longest burst** shows the longest uninterrupted stretch that lane held control
- **burst count** shows how fragmented or chopped up the lane was

The Sankey below answers: after one lane held the run, which lane tended to take over next?

**Useful for spotting**

- many short controller bursts, which often mean orchestration churn
- long model bursts, which can mean large or repeated LLM calls
- long workspace bursts, which often mean sustained repo work or test loops
- non-trivial runtime time, which can reveal hidden overhead
- repeated `workspace → controller → model → workspace` cycles, which often indicate the normal think-act-observe loop
- unusual handoff patterns that suggest excessive harness mediation or persistence activity

### Feedback → next meaningful move heatmap

**What it is**

A matrix of feedback categories on the y-axis versus the next meaningful move on the x-axis.

Typical x-axis categories include:

- `edit`
- `file content`
- `repo listing`
- `test failure`
- `test pass`
- `shell output`
- `shell error`
- `retry`
- `wait`
- `finalize`

Routine `execute` spans are collapsed into their observed outcomes so the heatmap focuses on what the run learned or did next.

**How to read it**

Read across a row to see what the run usually did after a given kind of observation.

Examples:

- if `test failure` mostly maps to `edit`, the run usually responds directly to failing tests
- if `file content` often maps to `file content`, the run may be staying in inspection mode
- if `test pass` often maps to `finalize`, the run is often able to stop cleanly after success

**Useful for spotting**

- whether failures are leading to repair or to more searching
- whether passing tests reliably terminate the run
- whether file reads usually convert into edits or just more reads
- whether shell errors lead to retries, waits, or deeper inspection

### All anchors overview

**What it is**

A dense Sankey that combines all supported anchors in one chart:

- `inspect`
- `edit`
- `test failure`
- `test pass`

From each anchor, it shows the next two meaningful nodes.

**How to read it**

Use it as an overview, not the most precise explanation. Hovering and highlighting are helpful here. The chart is intentionally dense so you can see the overall balance of branches across all anchor types at once.

**Useful for spotting**

- the dominant post-anchor pathways in the whole run
- whether edit-centered behavior overwhelms the rest of the flow
- whether successful branches are visible but small relative to failed ones
- whether the run has many distinct recovery branches or just one main loop

### Selected anchor: next two meaningful moves

**What it is**

A selector-driven Sankey that lets you isolate one anchor at a time.

Available anchors:

- `inspect`
- `edit`
- `test failure`
- `test pass`

The view skips `plan` and `overhead`, collapses routine `execute` spans into observed outcomes, and allows `finalize` as an endpoint but not as a starting anchor.

**How to read it**

Use this when the combined overview is too dense. It answers one crisp question at a time, such as:

- after inspect, what happened next?
- after edit, what came back?
- after test failure, what recovery path followed?
- after test pass, did the run finish or keep going?

**Useful for spotting**

- whether edits usually lead to failure, pass, or more inspection
- whether failures lead straight to edits or detours through file reads
- whether test passes cleanly terminate the run
- whether different anchor types have very different branch structures

### Run timeline

**What it is**

A time-ordered chart of individual events colored by dominant action type.

**How to read it**

Use it to recover sequence and pacing. Unlike the lane views, this chart is event-level rather than lane-level.

**Useful for spotting**

- exactly where long waits or retries occurred
- late-stage bursts of testing or editing
- whether the run had one concentrated repair phase or many scattered ones

### Prompt makeup per LLM call

**What it is**

A 100%-stacked view of prompt composition for each LLM call.

Segments include:

- fresh task ask
- fresh repo/tool context
- replayed prior context
- cached prefix reuse
- tool output added

**How to read it**

Each bar is normalized, so the question is composition, not absolute size. Hover to see raw token counts.

**Useful for spotting**

- prompts that become dominated by carry-forward rather than fresh context
- heavy reliance on cached prefixes
- moments where tool output suddenly becomes a large prompt component

### File transition graph (top files)

**What it is**

A Sankey of movement between the most-touched files in the run.

**How to read it**

Use it to understand whether the run converged onto a small cluster of files or wandered broadly. Node labels are shortened for readability, but hover text preserves the full paths.

**Useful for spotting**

- tight concentration around one module or file cluster
- repeated bouncing between a few files during repair
- broad repo wandering before localization

### Harness steering events

**What it is**

A view of harness-side steering actions only, such as plan updates, retries, waits, interruptions, and finish.

**How to read it**

This is not ordinary coding work. It is a lens into how much the harness itself was steering or reacting.

**Useful for spotting**

- retry storms
- waiting/idling periods
- interruptions and restarts
- finish behavior that looks delayed or repeated

### Step anatomy

**What it is**

A drill-down inspector for one selected step, showing command details, prompt information, feedback, file paths, and control metadata.

**How to read it**

Use it when a summary chart raises a question and you want the exact step-level evidence behind it.

**Useful for spotting**

- what command or file read produced a surprising branch in another chart
- whether a test failure was broad or narrow
- what the prompt looked like at a key turning point

### Cumulative progress

**What it is**

A set of cumulative lines over the trajectory, including token counts and progress proxies like tests passed and unique files touched.

**How to read it**

Compare spending curves against progress curves.

- rising tokens with flat tests passed may mean churn
- rising files touched without progress may mean wandering
- stable files with increasing tests passed may mean focused convergence

**Useful for spotting**

- long runs that keep spending without solving
- convergence after localization
- late-stage churn after a plausible fix already exists

## A few recurring behavioral patterns

### Productive repair loop

Common signs:

- low files-before-first-edit
- moderate edit/test burden
- `test failure → edit` is prominent
- `test pass → finalize` is visible
- workspace dominates more than controller or runtime

### Search-heavy wandering

Common signs:

- high files-before-first-edit
- file transition graph is broad rather than focused
- `file content → file content` or `repo listing → file content` is common
- unique files touched keeps climbing without much test progress

### Verification churn

Common signs:

- many tests before or after first pass
- post-edit flows keep cycling through `test failure`
- workspace bursts are long but progress is flat
- cumulative tests rise faster than tests passed

### Harness or runtime overhead

Common signs:

- controller or runtime lanes consume a surprising share of the run
- burst count is high in controller
- handoffs are very dense
- visible waits, retries, or persistence-heavy behavior

## When to trust which chart most

- For **sequence**, trust the **Run timeline** and **Step anatomy**.
- For **where time sat**, trust **Harness lane occupancy** and **Lane summary**.
- For **search and verification efficiency**, trust **Behavior and burden summary** plus **Search / edit / verify burden**.
- For **reaction patterns**, trust the **Feedback heatmap** and **anchor flow** views.
- For **prompt growth**, trust **Prompt makeup per LLM call** and **Cumulative progress**.

## Suggested workflow for reviewing a run

1. Start with the summary cards and burden chart.
2. Check lane occupancy and lane summary to see where time really went.
3. Use the feedback heatmap and anchor views to understand the post-observation control loop.
4. Use prompt makeup and cumulative progress to decide whether the run was converging or just getting heavier.
5. Use the file graph, timeline, and step inspector to investigate specific turns.
