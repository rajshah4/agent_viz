from __future__ import annotations

from dataclasses import replace
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.comparison import build_multi_run_comparison_data, render_multi_run_comparison
from agent_viz.laminar import parse_laminar_trace_payload


class ComparisonTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fixture_path = PROJECT_ROOT / "examples" / "laminar_shared_trace.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        run_a = parse_laminar_trace_payload(payload)
        run_b = [
            replace(
                event,
                run_id="trace-demo-002",
                token_input=event.token_input + 10,
                token_cached=event.token_cached + 5,
            )
            for event in run_a
        ]
        self.runs = [("run-a", run_a), ("run-b", run_b)]

    def test_build_multi_run_comparison_data_returns_run_rows(self) -> None:
        data = build_multi_run_comparison_data(self.runs)

        self.assertEqual(data["summary"]["run_count"], 2)
        self.assertEqual(len(data["runs"]), 2)
        self.assertTrue(data["action_breakdown"])
        self.assertTrue(data["visible_action_breakdown"])
        self.assertIn("overhead_breakdown", data)
        self.assertTrue(data["burden_breakdown"])
        self.assertEqual(data["runs"][0]["label"], "run-a")
        self.assertIn("dominant_action", data["runs"][0])
        self.assertIn("carry_forward_ratio", data["runs"][0])
        self.assertIn("files_read_before_first_edit_count", data["runs"][0])
        self.assertIn("edits_before_first_pass", data["runs"][0])
        self.assertIn("tests_before_first_pass", data["runs"][0])
        self.assertIn("tests_after_first_pass", data["runs"][0])
        self.assertIn("top_files", data["runs"][0])
        self.assertGreaterEqual(data["summary"]["average_cache_ratio"], 0)
        self.assertGreaterEqual(data["summary"]["average_carry_forward_ratio"], 0)
        self.assertGreaterEqual(data["summary"]["average_files_before_first_edit"], 0)
        self.assertGreaterEqual(data["summary"]["average_tests_before_first_pass"], 0)

    def test_render_multi_run_comparison_writes_html(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "comparison.html"
            rendered = render_multi_run_comparison(self.runs, output_path, title="Harness Comparison")
            html = rendered.read_text(encoding="utf-8")

        self.assertEqual(rendered, output_path)
        self.assertIn("Harness Comparison", html)
        self.assertIn("Success versus token spend", html)
        self.assertIn("Action mix per run", html)
        self.assertIn("Visible action mix per run", html)
        self.assertIn("Overhead breakdown per run", html)
        self.assertIn("Search burden versus test burden", html)
        self.assertIn("Direct burden metrics per run", html)
        self.assertIn("Run focus snapshots", html)
        self.assertIn("Metric glossary", html)
        self.assertIn("Carry-forward ratio", html)
        self.assertIn("Edits before first pass", html)
        self.assertIn("run-a", html)
        self.assertIn("run-b", html)


if __name__ == "__main__":
    unittest.main()
