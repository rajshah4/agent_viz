from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.dashboard import build_single_run_dashboard_data, render_single_run_dashboard
from agent_viz.laminar import parse_laminar_trace_payload
from agent_viz.models import ActionType, EventSource, EventType, NormalizedEvent, StepStatus


class DashboardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fixture_path = PROJECT_ROOT / "examples" / "laminar_shared_trace.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.events = parse_laminar_trace_payload(payload)

    def test_build_single_run_dashboard_data_returns_chart_ready_structures(self) -> None:
        data = build_single_run_dashboard_data(self.events)

        self.assertEqual(data["run_id"], "trace-demo-001")
        self.assertEqual(data["summary"]["total_steps"], 5)
        self.assertEqual(len(data["timeline"]), 5)
        self.assertEqual(len(data["prompt_composition"]), 2)
        self.assertEqual(data["prompt_composition"][0]["label"], "LLM 1")
        self.assertEqual(len(data["cumulative_progress"]), 5)
        self.assertEqual(len(data["step_details"]), 5)
        self.assertEqual(len(data["burden_metrics"]), 5)
        self.assertEqual(data["timeline"][0]["start_ms"], 0)
        self.assertEqual(data["timeline"][0]["lane"], "workspace")
        self.assertEqual(data["timeline"][3]["event_type"], "test_run")
        self.assertEqual(data["step_details"][1]["lane"], "model")
        self.assertTrue(data["lane_occupancy"])
        self.assertEqual(data["lane_occupancy"][0]["lane"], "workspace")
        self.assertEqual(data["lane_summary"][0]["lane"], "controller")
        self.assertTrue(data["lane_handoffs"]["links"])
        self.assertTrue(data["feedback_action_heatmap"]["feedback_labels"])
        self.assertTrue(data["feedback_action_heatmap"]["action_labels"])
        self.assertEqual(data["anchor_follow_through"]["default_anchor"], "edit")
        self.assertTrue(data["anchor_follow_through"]["overview_graph"]["links"])
        self.assertTrue(data["anchor_follow_through"]["graphs"]["edit"]["nodes"])
        self.assertTrue(data["anchor_follow_through"]["graphs"]["edit"]["links"])
        self.assertIn("inspect", {option["key"] for option in data["anchor_follow_through"]["options"]})
        self.assertEqual(data["cumulative_progress"][-1]["cumulative_tests_passed"], 4)
        self.assertEqual(data["summary"]["files_before_first_edit_count"], 1)
        self.assertEqual(data["summary"]["edits_before_first_pass"], 1)
        self.assertEqual(data["summary"]["tests_before_first_pass"], 4)
        self.assertEqual(data["summary"]["tests_after_first_pass"], 0)
        self.assertEqual(data["summary"]["max_retry_burst"], 0)
        self.assertIn("carry_forward_ratio", data["summary"])
        self.assertTrue(data["file_transitions"]["nodes"])
        self.assertTrue(data["file_transitions"]["links"])
        self.assertNotIn("/", data["file_transitions"]["nodes"][0]["label"])

    def test_anchor_follow_through_supports_multiple_selected_starts(self) -> None:
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-1",
                action_type=ActionType.INSPECT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_READ,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time,
                timestamp_end=base_time + timedelta(seconds=1),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-2",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=2),
                timestamp_end=base_time + timedelta(seconds=3),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-3",
                action_type=ActionType.EXECUTE,
                source=EventSource.TOOL,
                event_type=EventType.TEST_RUN,
                status=StepStatus.ERROR,
                timestamp_start=base_time + timedelta(seconds=4),
                timestamp_end=base_time + timedelta(seconds=5),
                test_count=1,
                tests_failed=1,
                tool_name="terminal",
                metadata={"output": "1 failed"},
            ),
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-4",
                action_type=ActionType.INSPECT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_READ,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=6),
                timestamp_end=base_time + timedelta(seconds=7),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-5",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=8),
                timestamp_end=base_time + timedelta(seconds=9),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-6",
                action_type=ActionType.EXECUTE,
                source=EventSource.TOOL,
                event_type=EventType.TEST_RUN,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=10),
                timestamp_end=base_time + timedelta(seconds=11),
                test_count=1,
                tests_passed=1,
                tool_name="terminal",
                metadata={"output": "1 passed"},
            ),
            NormalizedEvent(
                run_id="trace-anchor-follow-through",
                step_id="step-7",
                action_type=ActionType.FINALIZE,
                source=EventSource.SYSTEM,
                event_type=EventType.MESSAGE,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=12),
                timestamp_end=base_time + timedelta(seconds=13),
                tool_name="finish",
            ),
        ]

        flow_payload = build_single_run_dashboard_data(events)["anchor_follow_through"]
        flow_data = flow_payload["graphs"]
        edit_labels = {link["label"] for link in flow_data["edit"]["links"]}
        inspect_labels = {link["label"] for link in flow_data["inspect"]["links"]}
        failure_labels = {link["label"] for link in flow_data["test_failure"]["links"]}
        pass_labels = {link["label"] for link in flow_data["test_pass"]["links"]}
        overview_labels = {link["label"] for link in flow_payload["overview_graph"]["links"]}

        self.assertIn("edit → test failure", edit_labels)
        self.assertIn("test failure → file content", edit_labels)
        self.assertNotIn("edit → execute", edit_labels)
        self.assertIn("inspect → edit", inspect_labels)
        self.assertIn("edit → test failure", inspect_labels)
        self.assertIn("test failure → file content", failure_labels)
        self.assertIn("file content → edit", failure_labels)
        self.assertIn("test pass → finalize", pass_labels)
        self.assertIn("inspect → edit", overview_labels)
        self.assertIn("edit → test failure", overview_labels)
        self.assertIn("test pass → finalize", overview_labels)
        self.assertFalse(flow_data["test_pass"]["nodes"][0]["label"] == "finalize")

    def test_anchor_follow_through_uses_single_finalize_sink(self) -> None:
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [
            NormalizedEvent(
                run_id="trace-anchor-finalize-sink",
                step_id="step-1",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time,
                timestamp_end=base_time + timedelta(seconds=1),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-anchor-finalize-sink",
                step_id="step-2",
                action_type=ActionType.FINALIZE,
                source=EventSource.SYSTEM,
                event_type=EventType.MESSAGE,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=2),
                timestamp_end=base_time + timedelta(seconds=3),
                tool_name="finish",
            ),
            NormalizedEvent(
                run_id="trace-anchor-finalize-sink",
                step_id="step-3",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=4),
                timestamp_end=base_time + timedelta(seconds=5),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-anchor-finalize-sink",
                step_id="step-4",
                action_type=ActionType.EXECUTE,
                source=EventSource.TOOL,
                event_type=EventType.TEST_RUN,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=6),
                timestamp_end=base_time + timedelta(seconds=7),
                test_count=1,
                tests_passed=1,
                tool_name="terminal",
                metadata={"output": "1 passed"},
            ),
            NormalizedEvent(
                run_id="trace-anchor-finalize-sink",
                step_id="step-5",
                action_type=ActionType.FINALIZE,
                source=EventSource.SYSTEM,
                event_type=EventType.MESSAGE,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=8),
                timestamp_end=base_time + timedelta(seconds=9),
                tool_name="finish",
            ),
        ]

        flow_payload = build_single_run_dashboard_data(events)["anchor_follow_through"]
        edit_graph = flow_payload["graphs"]["edit"]
        overview_graph = flow_payload["overview_graph"]

        edit_finalize_nodes = [node for node in edit_graph["nodes"] if node["label"] == "finalize"]
        overview_finalize_nodes = [node for node in overview_graph["nodes"] if node["label"] == "finalize"]

        self.assertEqual(len(edit_finalize_nodes), 1)
        self.assertEqual(edit_finalize_nodes[0]["stage"], 2)
        self.assertEqual(len(overview_finalize_nodes), 1)
        self.assertEqual(overview_finalize_nodes[0]["stage"], 2)
        self.assertIn("edit → finalize", {link["label"] for link in edit_graph["links"]})
        self.assertIn("test pass → finalize", {link["label"] for link in overview_graph["links"]})

    def test_feedback_action_heatmap_counts_next_actions_by_category(self) -> None:
        base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = [
            NormalizedEvent(
                run_id="trace-feedback-heatmap",
                step_id="step-1",
                action_type=ActionType.INSPECT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_READ,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time,
                timestamp_end=base_time + timedelta(seconds=1),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-feedback-heatmap",
                step_id="step-2",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=2),
                timestamp_end=base_time + timedelta(seconds=3),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
            NormalizedEvent(
                run_id="trace-feedback-heatmap",
                step_id="step-3",
                action_type=ActionType.EXECUTE,
                source=EventSource.TOOL,
                event_type=EventType.TEST_RUN,
                status=StepStatus.ERROR,
                timestamp_start=base_time + timedelta(seconds=4),
                timestamp_end=base_time + timedelta(seconds=5),
                test_count=1,
                tests_failed=1,
                tool_name="terminal",
                metadata={"output": "1 failed"},
            ),
            NormalizedEvent(
                run_id="trace-feedback-heatmap",
                step_id="step-4",
                action_type=ActionType.EDIT,
                source=EventSource.TOOL,
                event_type=EventType.FILE_EDIT,
                status=StepStatus.SUCCESS,
                timestamp_start=base_time + timedelta(seconds=6),
                timestamp_end=base_time + timedelta(seconds=7),
                file_paths=("/workspace/app.py",),
                tool_name="file_editor",
            ),
        ]

        heatmap = build_single_run_dashboard_data(events)["feedback_action_heatmap"]
        row_index = {label: index for index, label in enumerate(heatmap["feedback_labels"])}
        col_index = {label: index for index, label in enumerate(heatmap["action_labels"])}

        self.assertNotIn("execute", heatmap["action_labels"])
        self.assertEqual(heatmap["z"][row_index["file content"]][col_index["edit"]], 1)
        self.assertEqual(heatmap["z"][row_index["edit result"]][col_index["test failure"]], 1)
        self.assertEqual(heatmap["z"][row_index["test failure"]][col_index["edit"]], 1)


    def test_render_single_run_dashboard_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "dashboard.html"
            rendered = render_single_run_dashboard(self.events, output_path, title="Fixture Dashboard")
            html = rendered.read_text(encoding="utf-8")

        self.assertEqual(rendered, output_path)
        self.assertIn("Fixture Dashboard", html)
        self.assertIn("Plotly", html)
        self.assertIn("trace-demo-001", html)
        self.assertIn("Single-run dashboard for agent behavior", html)
        self.assertIn("Behavior and burden summary", html)
        self.assertIn("Search / edit / verify burden", html)
        self.assertIn("Carry-forward ratio", html)
        self.assertIn("Wall-clock duration", html)
        self.assertIn("Summed event duration", html)
        self.assertIn("Harness lane occupancy", html)
        self.assertIn("Lane summary and handoffs", html)
        self.assertIn("How lane timing works", html)
        self.assertIn("Controller", html)
        self.assertIn("Handoff", html)
        self.assertIn("Dominant lane by time", html)
        self.assertIn("Feedback → next meaningful move heatmap", html)
        self.assertIn("All anchors overview", html)
        self.assertIn("Selected anchor: next two meaningful moves", html)
        self.assertIn("anchor-flow-selector", html)
        self.assertIn("Prompt makeup per LLM call", html)
        self.assertIn("fresh repo/tool context", html)
        self.assertIn("File transition graph (top files)", html)
        self.assertIn("Harness steering events", html)
        self.assertIn("plan updates, retries, waits, interruptions, and finish", html)
        self.assertIn("Step anatomy", html)
        self.assertIn("Cumulative progress", html)
        self.assertNotIn("Verification lag", html)


if __name__ == "__main__":
    unittest.main()
