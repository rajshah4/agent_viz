# Laminar Parser Notes

## Scope of the first parser

The first Laminar integration targets **shared trace data**, not the full shared evaluation table UI.

Supported input shapes:

1. a combined payload with:
   - `trace`
   - `spans`
2. split responses from:
   - `/api/shared/traces/{trace_id}`
   - `/api/shared/traces/{trace_id}/spans`

## Why start at the trace layer

For `agent_viz`, the trace and span layer is the most useful level because it contains the trajectory needed for:

- timeline views
- action classification
- file navigation flow
- token and cost accumulation
- test and retry analysis

The shared evaluation endpoints are still useful for indexing and metadata, but the first parser should stay focused on reconstructing a single run.

## Observed Laminar signals

From the public Laminar shared UI and shipped client bundle, useful fields appear to include:

### Trace-level fields

- `id`
- `startTime`
- `endTime`
- `status`
- `traceType`
- `inputTokens`
- `outputTokens`
- `totalTokens`
- `inputCost`
- `outputCost`
- `totalCost`
- `metadata`

### Span-level fields

- `spanId`
- `parentSpanId`
- `name`
- `spanType`
- `startTime`
- `endTime`
- `status`
- `attributes`
- `inputTokens`
- `outputTokens`
- `totalTokens`
- `inputCost`
- `outputCost`
- `totalCost`
- `cacheReadInputTokens`
- `reasoningTokens`

## Mapping assumptions

Because public traces may vary by SDK and instrumentation setup, the parser uses heuristics:

- `spanType = LLM` maps to `EventType.LLM_CALL`
- tool-like spans plus file path hints map to `FILE_READ` or `FILE_EDIT`
- command or test hints map to `TEST_RUN` or `TOOL_CALL`
- name, tool name, command text, and attributes all contribute to action inference

## Prompt composition assumptions

Laminar traces may expose only part of the prompt composition directly.

Current approximation:

- `cached_prefix_tokens` <- `cacheReadInputTokens`
- `retrieved_context_tokens` <- retrieval-related token fields when present
- `replayed_context_tokens` <- replay or memory token fields when present
- `tool_output_tokens` <- tool output token fields when present
- `new_task_tokens` <- `inputTokens - known component tokens`

This is intentionally conservative and can be improved when richer trace exports are available.

## Next parser improvements

- support shared evaluation result rows once the public result payload is sampled reliably
- infer retries from repeated tool invocations and error spans, not only explicit names
- extract file paths from richer tool payload shapes
- compute patch-attempt groupings across related edit spans
