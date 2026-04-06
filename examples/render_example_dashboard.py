from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from agent_viz.dashboard import render_single_run_dashboard
from agent_viz.laminar import parse_laminar_trace_payload


def main() -> int:
    fixture_path = PROJECT_ROOT / "examples" / "laminar_shared_trace.json"
    output_path = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) > 1
        else PROJECT_ROOT / "examples" / "laminar_single_run_dashboard.html"
    )

    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    events = parse_laminar_trace_payload(payload)
    render_single_run_dashboard(events, output_path, title="Laminar Example Run")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
