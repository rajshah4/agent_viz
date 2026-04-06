from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.dashboard import build_single_run_dashboard_data, render_single_run_dashboard
from agent_viz.laminar import parse_laminar_trace_payload


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
        self.assertEqual(data["feedback_next_action"]["nodes"][0]["kind"], "feedback")
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
        self.assertIn("Feedback to next action", html)
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
