from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    INSPECT = "inspect"
    PLAN = "plan"
    EDIT = "edit"
    EXECUTE = "execute"
    RETRY = "retry"
    WAIT = "wait"
    OVERHEAD = "overhead"
    FINALIZE = "finalize"


class EventSource(str, Enum):
    MODEL = "model"
    TOOL = "tool"
    RUNTIME = "runtime"
    RETRIEVAL = "retrieval"
    SYSTEM = "system"


class EventType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FILE_READ = "file_read"
    FILE_EDIT = "file_edit"
    TEST_RUN = "test_run"
    MESSAGE = "message"
    RETRY = "retry"
    WAIT = "wait"


class StepStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PromptComposition:
    new_task_tokens: int = 0
    retrieved_context_tokens: int = 0
    replayed_context_tokens: int = 0
    cached_prefix_tokens: int = 0
    tool_output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.new_task_tokens
            + self.retrieved_context_tokens
            + self.replayed_context_tokens
            + self.cached_prefix_tokens
            + self.tool_output_tokens
        )

    @property
    def memory_load_tokens(self) -> int:
        return self.replayed_context_tokens + self.cached_prefix_tokens


@dataclass(frozen=True)
class NormalizedEvent:
    run_id: str
    step_id: str
    action_type: ActionType
    source: EventSource = EventSource.RUNTIME
    event_type: EventType = EventType.MESSAGE
    status: StepStatus = StepStatus.UNKNOWN
    timestamp_start: datetime | None = None
    timestamp_end: datetime | None = None
    duration_ms: int | None = None
    parent_step_id: str | None = None
    tool_name: str | None = None
    file_paths: tuple[str, ...] = ()
    token_input: int = 0
    token_output: int = 0
    token_cached: int = 0
    cost_usd: float = 0.0
    test_count: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    prompt_composition: PromptComposition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_paths", tuple(self.file_paths))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def resolved_duration_ms(self) -> int:
        if self.duration_ms is not None:
            return self.duration_ms
        if self.timestamp_start is not None and self.timestamp_end is not None:
            delta = self.timestamp_end - self.timestamp_start
            return max(int(delta.total_seconds() * 1000), 0)
        return 0

    @property
    def touched_files(self) -> tuple[str, ...]:
        return self.file_paths

    @property
    def total_tokens(self) -> int:
        return self.token_input + self.token_output


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    total_steps: int
    total_duration_ms: int
    wall_clock_duration_ms: int
    summed_event_duration_ms: int
    total_input_tokens: int
    total_output_tokens: int
    total_cached_tokens: int
    total_cost_usd: float
    total_tool_calls: int
    total_file_reads: int
    total_file_edits: int
    total_tests_run: int
    tests_passed: int
    tests_failed: int
    unique_files_read: tuple[str, ...]
    unique_files_edited: tuple[str, ...]
    action_counts: dict[str, int]
    action_duration_ms: dict[str, int]
    first_edit_step: str | None = None
    first_execute_step: str | None = None
    first_passing_test_step: str | None = None
    retry_count: int = 0
    wait_time_ratio: float = 0.0
    cache_ratio: float = 0.0
    memory_inefficiency_ratio: float = 0.0
    success: bool = False
