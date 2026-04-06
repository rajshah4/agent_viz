from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.metrics import file_transition_edges, summarize_run
from agent_viz.models import (
    ActionType,
    EventSource,
    EventType,
    NormalizedEvent,
    PromptComposition,
    StepStatus,
)


class MetricsTestCase(unittest.TestCase):
    def test_summarize_run_aggregates_key_metrics(self) -> None:
        start = datetime(2026, 4, 5, 12, 0, 0)
        events = [
            NormalizedEvent(
                run_id="run-1",
                step_id="step-1",
                action_type=ActionType.INSPECT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_READ,
                status=StepStatus.SUCCESS,
                timestamp_start=start,
                timestamp_end=start + timedelta(seconds=2),
                file_paths=("src/app.py",),
                token_input=120,
                token_output=10,
                token_cached=40,
                prompt_composition=PromptComposition(
                    new_task_tokens=30,
                    retrieved_context_tokens=40,
                    replayed_context_tokens=20,
                    cached_prefix_tokens=10,
                    tool_output_tokens=20,
                ),
            ),
            NormalizedEvent(
                run_id="run-1",
                step_id="step-2",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=start + timedelta(seconds=3),
                timestamp_end=start + timedelta(seconds=5),
                file_paths=("src/app.py", "src/utils.py"),
                token_input=180,
                token_output=40,
                token_cached=50,
                prompt_composition=PromptComposition(
                    new_task_tokens=20,
                    retrieved_context_tokens=30,
                    replayed_context_tokens=70,
                    cached_prefix_tokens=20,
                    tool_output_tokens=40,
                ),
            ),
            NormalizedEvent(
                run_id="run-1",
                step_id="step-3",
                action_type=ActionType.EXECUTE,
                source=EventSource.TOOL,
                event_type=EventType.TEST_RUN,
                status=StepStatus.SUCCESS,
                timestamp_start=start + timedelta(seconds=6),
                timestamp_end=start + timedelta(seconds=8),
                tool_name="pytest",
                token_input=90,
                token_output=20,
                token_cached=30,
                test_count=3,
                tests_passed=3,
                tests_failed=0,
                prompt_composition=PromptComposition(
                    new_task_tokens=10,
                    retrieved_context_tokens=15,
                    replayed_context_tokens=60,
                    cached_prefix_tokens=25,
                    tool_output_tokens=20,
                ),
            ),
        ]

        summary = summarize_run(events)

        self.assertEqual(summary.run_id, "run-1")
        self.assertEqual(summary.total_steps, 3)
        self.assertEqual(summary.total_duration_ms, 8000)
        self.assertEqual(summary.wall_clock_duration_ms, 8000)
        self.assertEqual(summary.summed_event_duration_ms, 6000)
        self.assertEqual(summary.total_input_tokens, 390)
        self.assertEqual(summary.total_output_tokens, 70)
        self.assertEqual(summary.total_cached_tokens, 120)
        self.assertEqual(summary.total_file_reads, 1)
        self.assertEqual(summary.total_file_edits, 1)
        self.assertEqual(summary.total_tests_run, 3)
        self.assertEqual(summary.tests_passed, 3)
        self.assertEqual(summary.first_edit_step, "step-2")
        self.assertEqual(summary.first_execute_step, "step-3")
        self.assertEqual(summary.first_passing_test_step, "step-3")
        self.assertEqual(summary.unique_files_read, ("src/app.py",))
        self.assertEqual(summary.unique_files_edited, ("src/app.py", "src/utils.py"))
        self.assertTrue(summary.success)
        self.assertAlmostEqual(summary.cache_ratio, 120 / 510)
        self.assertAlmostEqual(summary.memory_inefficiency_ratio, 205 / 430)

    def test_file_transition_edges_tracks_navigation_flow(self) -> None:
        start = datetime(2026, 4, 5, 12, 0, 0)
        events = [
            NormalizedEvent(
                run_id="run-2",
                step_id="1",
                action_type=ActionType.INSPECT,
                event_type=EventType.FILE_READ,
                timestamp_start=start,
                file_paths=("a.py",),
            ),
            NormalizedEvent(
                run_id="run-2",
                step_id="2",
                action_type=ActionType.INSPECT,
                event_type=EventType.FILE_READ,
                timestamp_start=start + timedelta(seconds=1),
                file_paths=("b.py",),
            ),
            NormalizedEvent(
                run_id="run-2",
                step_id="3",
                action_type=ActionType.EDIT,
                event_type=EventType.FILE_EDIT,
                timestamp_start=start + timedelta(seconds=2),
                file_paths=("b.py", "c.py"),
            ),
        ]

        transitions = file_transition_edges(events)

        self.assertEqual(
            transitions,
            {
                ("a.py", "b.py"): 1,
                ("b.py", "b.py"): 1,
                ("b.py", "c.py"): 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
