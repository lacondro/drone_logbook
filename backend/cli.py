"""CLI to parse a single log and dump the summary as JSON (M1 verification)."""
from __future__ import annotations

import json
import sys

from parsers import parse_log


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python cli.py <logfile> [--no-track]", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        result = parse_log(path)
    except Exception as e:  # noqa: BLE001 - CLI top-level: report and exit non-zero
        print(json.dumps({"parse_status": "error", "parse_error": f"{type(e).__name__}: {e}"}, indent=2))
        return 1
    if "--no-track" in argv:
        if result.get("track_geojson"):
            result["track_geojson"] = f"<LineString {len(result['track_geojson']['coordinates'])} pts>"
    if "--no-msgs" in argv:
        result["logged_messages"] = f"<{len(result.get('logged_messages', []))} messages>"
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
