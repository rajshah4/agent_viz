from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen
import re

from .laminar import parse_laminar_trace_responses
from .models import NormalizedEvent

LAMINAR_BASE_URL = "https://laminar.sh"
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
HYDRATE_SPAN_NAMES = {"litellm.completion"}


JsonFetcher = Callable[[str], Any]


def extract_laminar_trace_id(reference: str) -> str:
    text = reference.strip()
    if not text:
        raise ValueError("Laminar reference cannot be empty")
    if TRACE_ID_PATTERN.fullmatch(text):
        return text

    parsed = urlparse(text)
    query_trace_ids = parse_qs(parsed.query).get("traceId")
    if query_trace_ids:
        trace_id = query_trace_ids[0].strip()
        if TRACE_ID_PATTERN.fullmatch(trace_id):
            return trace_id

    path_parts = [part for part in parsed.path.split("/") if part]
    for index, part in enumerate(path_parts[:-1]):
        if part == "traces":
            candidate = path_parts[index + 1]
            if TRACE_ID_PATTERN.fullmatch(candidate):
                return candidate

    raise ValueError(f"Could not extract a Laminar trace ID from: {reference}")


def build_laminar_shared_api_urls(
    reference: str,
    *,
    base_url: str = LAMINAR_BASE_URL,
) -> tuple[str, str]:
    trace_id = extract_laminar_trace_id(reference)
    normalized_base = base_url.rstrip("/")
    return (
        f"{normalized_base}/api/shared/traces/{trace_id}",
        f"{normalized_base}/api/shared/traces/{trace_id}/spans",
    )


def fetch_laminar_trace_responses(
    reference: str,
    *,
    base_url: str = LAMINAR_BASE_URL,
    timeout: float = 30.0,
    fetch_json: JsonFetcher | None = None,
    hydrate_spans: bool = True,
    max_workers: int = 8,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    trace_url, spans_url = build_laminar_shared_api_urls(reference, base_url=base_url)
    trace_id = extract_laminar_trace_id(reference)
    loader = fetch_json or (lambda url: _fetch_json(url, timeout=timeout))

    trace_response = loader(trace_url)
    spans_response = loader(spans_url)

    if not isinstance(trace_response, dict):
        raise ValueError("Laminar trace endpoint did not return an object")
    if not isinstance(spans_response, list):
        raise ValueError("Laminar spans endpoint did not return a list")

    spans = [span for span in spans_response if isinstance(span, dict)]
    if hydrate_spans and spans:
        spans = hydrate_laminar_spans(
            trace_id,
            spans,
            base_url=base_url,
            timeout=timeout,
            fetch_json=loader,
            max_workers=max_workers,
        )
    return trace_response, spans


def hydrate_laminar_spans(
    trace_id: str,
    spans: list[dict[str, Any]],
    *,
    base_url: str = LAMINAR_BASE_URL,
    timeout: float = 30.0,
    fetch_json: JsonFetcher | None = None,
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    loader = fetch_json or (lambda url: _fetch_json(url, timeout=timeout))
    normalized_base = base_url.rstrip("/")
    hydrated_by_id = {
        str(span.get("spanId") or span.get("id") or index): dict(span)
        for index, span in enumerate(spans)
    }

    candidates = [
        span for span in spans if _should_hydrate_span(span)
    ]
    if not candidates:
        return [dict(span) for span in spans]

    def fetch_detail(span: dict[str, Any]) -> tuple[str, Any]:
        span_id = str(span.get("spanId") or span.get("id") or "")
        url = f"{normalized_base}/api/shared/traces/{trace_id}/spans/{span_id}"
        return span_id, loader(url)

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        futures = [executor.submit(fetch_detail, span) for span in candidates]
        for future in as_completed(futures):
            try:
                span_id, detailed = future.result()
            except Exception:
                continue
            if not isinstance(detailed, dict):
                continue
            base_span = hydrated_by_id.get(span_id, {})
            hydrated_by_id[span_id] = _merge_span_records(base_span, detailed)

    return [hydrated_by_id[str(span.get("spanId") or span.get("id") or index)] for index, span in enumerate(spans)]


def load_laminar_trace(
    reference: str,
    *,
    base_url: str = LAMINAR_BASE_URL,
    timeout: float = 30.0,
    fetch_json: JsonFetcher | None = None,
    hydrate_spans: bool = True,
    max_workers: int = 8,
) -> list[NormalizedEvent]:
    trace_response, spans_response = fetch_laminar_trace_responses(
        reference,
        base_url=base_url,
        timeout=timeout,
        fetch_json=fetch_json,
        hydrate_spans=hydrate_spans,
        max_workers=max_workers,
    )
    return parse_laminar_trace_responses(trace_response, spans_response)


def save_laminar_trace_payload(
    reference: str,
    output_path: str | Path,
    *,
    base_url: str = LAMINAR_BASE_URL,
    timeout: float = 30.0,
    fetch_json: JsonFetcher | None = None,
    hydrate_spans: bool = True,
    max_workers: int = 8,
) -> Path:
    trace_response, spans_response = fetch_laminar_trace_responses(
        reference,
        base_url=base_url,
        timeout=timeout,
        fetch_json=fetch_json,
        hydrate_spans=hydrate_spans,
        max_workers=max_workers,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"trace": trace_response, "spans": spans_response}, indent=2),
        encoding="utf-8",
    )
    return output


def _should_hydrate_span(span: dict[str, Any]) -> bool:
    name = str(span.get("name") or "")
    span_type = str(span.get("spanType") or "").upper()
    return (
        span_type == "LLM"
        or name in HYDRATE_SPAN_NAMES
        or name.endswith("Action")
    )


def _merge_span_records(base: dict[str, Any], detailed: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(detailed)
    for key in ("attributes", "input", "output", "aggregatedMetrics"):
        base_value = base.get(key)
        detail_value = detailed.get(key)
        if isinstance(base_value, dict) and isinstance(detail_value, dict):
            combined = dict(base_value)
            combined.update(detail_value)
            merged[key] = combined
        elif detail_value is None and base_value is not None:
            merged[key] = base_value
    return merged


def _fetch_json(url: str, *, timeout: float) -> Any:
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)
