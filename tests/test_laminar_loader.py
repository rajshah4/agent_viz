from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.laminar_loader import (
    build_laminar_shared_api_urls,
    extract_laminar_trace_id,
    fetch_laminar_trace_responses,
    load_laminar_trace,
)


class LaminarLoaderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        fixture_path = PROJECT_ROOT / "examples" / "laminar_shared_trace.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.trace_response = payload["trace"]
        self.spans_response = payload["spans"]

    def test_extract_laminar_trace_id_accepts_raw_trace_id(self) -> None:
        trace_id = "537db26f-50c3-7350-1a28-dfdf1a349f66"
        self.assertEqual(extract_laminar_trace_id(trace_id), trace_id)

    def test_extract_laminar_trace_id_accepts_shared_eval_url_with_trace_query(self) -> None:
        reference = (
            "https://laminar.sh/shared/evals/c97e4a45-8a14-428f-8eac-f77ef6eb75a8"
            "?traceId=537db26f-50c3-7350-1a28-dfdf1a349f66"
            "&datapointId=5ccd7459-f332-4234-9e74-08946800a41c"
            "&spanId=00000000-0000-0000-67ef-a3041a16198b"
        )
        self.assertEqual(
            extract_laminar_trace_id(reference),
            "537db26f-50c3-7350-1a28-dfdf1a349f66",
        )

    def test_build_laminar_shared_api_urls_uses_extracted_trace_id(self) -> None:
        trace_url, spans_url = build_laminar_shared_api_urls(
            "https://laminar.sh/shared/traces/537db26f-50c3-7350-1a28-dfdf1a349f66"
        )
        self.assertEqual(
            trace_url,
            "https://laminar.sh/api/shared/traces/537db26f-50c3-7350-1a28-dfdf1a349f66",
        )
        self.assertEqual(
            spans_url,
            "https://laminar.sh/api/shared/traces/537db26f-50c3-7350-1a28-dfdf1a349f66/spans",
        )

    def test_fetch_and_load_can_use_injected_fetcher(self) -> None:
        responses = {
            "https://laminar.sh/api/shared/traces/537db26f-50c3-7350-1a28-dfdf1a349f66": self.trace_response,
            "https://laminar.sh/api/shared/traces/537db26f-50c3-7350-1a28-dfdf1a349f66/spans": self.spans_response,
        }

        def fake_fetch(url: str):
            return responses[url]

        trace_response, spans_response = fetch_laminar_trace_responses(
            "537db26f-50c3-7350-1a28-dfdf1a349f66",
            fetch_json=fake_fetch,
        )
        events = load_laminar_trace(
            "537db26f-50c3-7350-1a28-dfdf1a349f66",
            fetch_json=fake_fetch,
        )

        self.assertEqual(trace_response["id"], "trace-demo-001")
        self.assertEqual(len(spans_response), 5)
        self.assertEqual(len(events), 5)
        self.assertEqual(events[0].run_id, "trace-demo-001")


    def test_fetch_laminar_trace_responses_hydrates_selected_spans(self) -> None:
        trace_id = "537db26f-50c3-7350-1a28-dfdf1a349f66"
        bulk_spans = [
            {
                "spanId": "span-llm",
                "name": "litellm.completion",
                "spanType": "LLM",
                "status": "success",
            },
            {
                "spanId": "span-read",
                "name": "FileEditorAction",
                "spanType": "TOOL",
                "status": "success",
            },
            {
                "spanId": "span-other",
                "name": "LocalFileStore.list",
                "spanType": "TOOL",
                "status": "success",
            },
        ]
        responses = {
            f"https://laminar.sh/api/shared/traces/{trace_id}": {"id": "trace-demo-002", "status": "success"},
            f"https://laminar.sh/api/shared/traces/{trace_id}/spans": bulk_spans,
            f"https://laminar.sh/api/shared/traces/{trace_id}/spans/span-llm": {
                "spanId": "span-llm",
                "name": "litellm.completion",
                "spanType": "LLM",
                "input": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
            },
            f"https://laminar.sh/api/shared/traces/{trace_id}/spans/span-read": {
                "spanId": "span-read",
                "name": "FileEditorAction",
                "spanType": "TOOL",
                "input": {"action": {"command": "view", "path": "/workspace/repo/file.py", "kind": "FileEditorAction"}},
            },
        }
        seen_urls: list[str] = []

        def fake_fetch(url: str):
            seen_urls.append(url)
            return responses[url]

        _, hydrated_spans = fetch_laminar_trace_responses(
            trace_id,
            fetch_json=fake_fetch,
        )

        self.assertIn(f"https://laminar.sh/api/shared/traces/{trace_id}/spans/span-llm", seen_urls)
        self.assertIn(f"https://laminar.sh/api/shared/traces/{trace_id}/spans/span-read", seen_urls)
        self.assertEqual(hydrated_spans[0]["input"][0]["role"], "user")
        self.assertEqual(hydrated_spans[1]["input"]["action"]["path"], "/workspace/repo/file.py")
        self.assertNotIn("input", hydrated_spans[2])


if __name__ == "__main__":
    unittest.main()
