from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.laminar import parse_laminar_trace_payload, parse_laminar_trace_responses
from agent_viz.metrics import summarize_run
from agent_viz.models import ActionType, EventSource, EventType, StepStatus


class LaminarParserTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fixture_path = PROJECT_ROOT / "examples" / "laminar_shared_trace.json"
        self.payload = json.loads(fixture_path.read_text())

    def test_parse_laminar_trace_payload_maps_span_types_and_metrics(self) -> None:
        events = parse_laminar_trace_payload(self.payload)

        self.assertEqual(len(events), 5)
        self.assertEqual(events[0].event_type, EventType.FILE_READ)
        self.assertEqual(events[0].action_type, ActionType.INSPECT)
        self.assertEqual(events[0].tool_name, "view")
        self.assertEqual(events[0].file_paths, ("src/agent.py",))

        self.assertEqual(events[1].event_type, EventType.LLM_CALL)
        self.assertEqual(events[1].action_type, ActionType.PLAN)
        self.assertEqual(events[1].source, EventSource.MODEL)
        self.assertEqual(events[1].prompt_composition.cached_prefix_tokens, 50)
        self.assertEqual(events[1].prompt_composition.new_task_tokens, 50)

        self.assertEqual(events[2].event_type, EventType.FILE_EDIT)
        self.assertEqual(events[2].action_type, ActionType.EDIT)
        self.assertEqual(events[2].file_paths, ("src/agent.py", "tests/test_parser.py"))

        self.assertEqual(events[3].event_type, EventType.TEST_RUN)
        self.assertEqual(events[3].action_type, ActionType.EXECUTE)
        self.assertEqual(events[3].test_count, 4)
        self.assertEqual(events[3].tests_passed, 4)
        self.assertEqual(events[3].tests_failed, 0)

        self.assertEqual(events[4].action_type, ActionType.FINALIZE)
        self.assertEqual(events[4].status, StepStatus.SUCCESS)

    def test_parse_laminar_trace_responses_accepts_split_payloads(self) -> None:
        events = parse_laminar_trace_responses(self.payload["trace"], self.payload["spans"])
        self.assertEqual([event.step_id for event in events], [
            "span-read",
            "span-plan",
            "span-edit",
            "span-test",
            "span-final",
        ])


    def test_parse_hydrated_openshands_spans_detects_paths_tests_and_overhead(self) -> None:
        payload = {
            "trace": {"id": "trace-hydrated", "status": "success"},
            "spans": [
                {
                    "spanId": "span-overhead",
                    "name": "LocalFileStore.write",
                    "spanType": "TOOL",
                    "status": "success",
                    "startTime": "2026-02-17T12:40:00Z",
                    "endTime": "2026-02-17T12:40:00.100000Z",
                    "input": {"path": "base_state.json", "contents": "{}"},
                },
                {
                    "spanId": "span-llm",
                    "name": "litellm.completion",
                    "spanType": "LLM",
                    "status": "success",
                    "startTime": "2026-02-17T12:40:01Z",
                    "endTime": "2026-02-17T12:40:02Z",
                    "inputTokens": 500,
                    "outputTokens": 40,
                    "attributes": {
                        "gen_ai.usage.cache_read_input_tokens": 120,
                        "gen_ai.completion.0.tool_calls.0.name": "file_editor",
                        "gen_ai.completion.0.tool_calls.0.arguments": "{\"command\": \"view\", \"path\": \"/workspace/repo/src/app.py\"}",
                    },
                    "input": [
                        {"role": "system", "content": [{"type": "text", "text": "system prompt"}]},
                        {"role": "user", "content": [{"type": "text", "text": "fix the bug"}]},
                        {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "I will inspect the file."},
                                {
                                    "type": "tool_call",
                                    "name": "file_editor",
                                    "id": "tool-1",
                                    "arguments": {"command": "view", "path": "/workspace/repo/src/app.py"},
                                },
                            ],
                        },
                        {"role": "tool", "content": [{"type": "text", "text": "def buggy():\n    pass"}]},
                    ],
                    "output": [
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_call",
                                    "name": "file_editor",
                                    "id": "tool-2",
                                    "arguments": {"command": "view", "path": "/workspace/repo/src/app.py"},
                                }
                            ],
                        }
                    ],
                },
                {
                    "spanId": "span-read",
                    "name": "FileEditorAction",
                    "spanType": "TOOL",
                    "status": "success",
                    "startTime": "2026-02-17T12:40:03Z",
                    "endTime": "2026-02-17T12:40:03.100000Z",
                    "input": {"action": {"command": "view", "path": "/workspace/repo/src/app.py", "kind": "FileEditorAction"}},
                    "output": {
                        "command": "view",
                        "path": "/workspace/repo/src/app.py",
                        "content": [{"type": "text", "text": "1\tdef buggy():\n2\t    pass"}],
                    },
                },
                {
                    "spanId": "span-edit",
                    "name": "FileEditorAction",
                    "spanType": "TOOL",
                    "status": "success",
                    "startTime": "2026-02-17T12:40:04Z",
                    "endTime": "2026-02-17T12:40:04.100000Z",
                    "input": {"action": {"command": "str_replace", "path": "/workspace/repo/src/app.py", "old_str": "pass", "new_str": "return 1", "kind": "FileEditorAction"}},
                    "output": {"command": "str_replace", "path": "/workspace/repo/src/app.py"},
                },
                {
                    "spanId": "span-test",
                    "name": "TerminalAction",
                    "spanType": "TOOL",
                    "status": "success",
                    "startTime": "2026-02-17T12:40:05Z",
                    "endTime": "2026-02-17T12:40:06Z",
                    "input": {"action": {"command": "cd /workspace/repo && python -m pytest tests/test_app.py -v", "kind": "TerminalAction"}},
                    "output": {
                        "content": [
                            {
                                "type": "text",
                                "text": "tests/test_app.py::test_bug PASSED\n================ 3 passed, 1 failed in 0.12s ================",
                            }
                        ]
                    },
                },
            ],
        }

        events = parse_laminar_trace_payload(payload)

        self.assertEqual(events[0].action_type, ActionType.OVERHEAD)
        self.assertEqual(events[0].source, EventSource.RUNTIME)

        self.assertEqual(events[1].event_type, EventType.LLM_CALL)
        self.assertEqual(events[1].tool_name, "file_editor")
        self.assertEqual(events[1].prompt_composition.cached_prefix_tokens, 120)
        self.assertGreater(events[1].prompt_composition.new_task_tokens, 0)
        self.assertGreater(events[1].prompt_composition.replayed_context_tokens, 0)
        self.assertGreater(events[1].prompt_composition.tool_output_tokens, 0)

        self.assertEqual(events[2].event_type, EventType.FILE_READ)
        self.assertEqual(events[2].file_paths, ("/workspace/repo/src/app.py",))

        self.assertEqual(events[3].event_type, EventType.FILE_EDIT)
        self.assertEqual(events[3].action_type, ActionType.EDIT)

        self.assertEqual(events[4].event_type, EventType.TEST_RUN)
        self.assertEqual(events[4].test_count, 4)
        self.assertEqual(events[4].tests_passed, 3)
        self.assertEqual(events[4].tests_failed, 1)

        summary = summarize_run(events)
        self.assertEqual(summary.total_file_reads, 1)
        self.assertEqual(summary.total_file_edits, 1)
        self.assertEqual(summary.total_tests_run, 4)
        self.assertIn("overhead", summary.action_counts)

    def test_parser_output_can_be_summarized(self) -> None:
        summary = summarize_run(parse_laminar_trace_payload(self.payload))

        self.assertEqual(summary.run_id, "trace-demo-001")
        self.assertEqual(summary.total_steps, 5)
        self.assertEqual(summary.total_file_reads, 1)
        self.assertEqual(summary.total_file_edits, 1)
        self.assertEqual(summary.total_tests_run, 4)
        self.assertEqual(summary.tests_passed, 4)
        self.assertEqual(summary.first_edit_step, "span-edit")
        self.assertEqual(summary.first_execute_step, "span-test")
        self.assertEqual(summary.first_passing_test_step, "span-test")
        self.assertTrue(summary.success)


if __name__ == "__main__":
    unittest.main()
