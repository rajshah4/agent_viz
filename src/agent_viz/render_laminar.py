from __future__ import annotations

import argparse
from pathlib import Path

from .dashboard import render_single_run_dashboard
from .laminar_loader import extract_laminar_trace_id, load_laminar_trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a single-run dashboard from a Laminar shared trace reference.",
    )
    parser.add_argument(
        "reference",
        help="Laminar shared trace URL, shared eval URL with traceId, or raw trace ID.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output HTML file path. Defaults to ./laminar_trace_<trace_id>.html",
    )
    parser.add_argument(
        "--title",
        help="Optional dashboard title override.",
    )
    args = parser.parse_args(argv)

    trace_id = extract_laminar_trace_id(args.reference)
    output_path = Path(args.output).expanduser().resolve() if args.output else Path.cwd() / f"laminar_trace_{trace_id}.html"
    events = load_laminar_trace(args.reference)
    title = args.title or f"Laminar Trace {trace_id[:8]}"
    rendered = render_single_run_dashboard(events, output_path, title=title)
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
