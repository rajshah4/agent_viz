from __future__ import annotations

import argparse
from pathlib import Path

from .comparison import render_multi_run_comparison
from .laminar_loader import extract_laminar_trace_id, load_laminar_trace


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a multi-run comparison dashboard from Laminar shared trace references.",
    )
    parser.add_argument(
        "references",
        nargs="+",
        help="Laminar shared trace URLs, shared eval URLs with traceId, or raw trace IDs.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output HTML file path. Defaults to ./laminar_compare.html",
    )
    parser.add_argument(
        "--title",
        help="Optional dashboard title override.",
    )
    args = parser.parse_args(argv)

    runs: list[tuple[str, list]] = []
    for reference in args.references:
        trace_id = extract_laminar_trace_id(reference)
        label = trace_id[:8]
        runs.append((label, load_laminar_trace(reference)))

    output_path = Path(args.output).expanduser().resolve() if args.output else Path.cwd() / "laminar_compare.html"
    rendered = render_multi_run_comparison(runs, output_path, title=args.title or "Laminar run comparison")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
