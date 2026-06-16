"""Log parsers: dispatch by file content (magic bytes), not extension."""
from __future__ import annotations

from . import common


def parse_log(path: str) -> dict:
    """Parse a flight log, returning a summary dict.

    Detection is by magic bytes so a ``.bin`` file is correctly routed to either
    the PX4 ULog or ArduPilot DataFlash parser. Parser-level problems are
    surfaced as ``parse_status``; only an unrecognised/unreadable file raises.
    """
    stack = common.detect_stack(path)
    if stack == "px4":
        from . import px4_parser
        return px4_parser.parse(path)
    if stack == "ardupilot":
        from . import ardupilot_parser
        return ardupilot_parser.parse(path)
    raise ValueError("unrecognised log format (not a PX4 ULog or ArduPilot DataFlash log)")
