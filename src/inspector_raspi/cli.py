#!/usr/bin/env python3
"""
Simple CLI helpers to call inspector-raspi functionality without MCP framing.

Commands:
  - raspi-capabilities: print JSON capabilities to stdout
"""
from __future__ import annotations

import json
import sys

from .mcp_standalone import _capabilities  # reuse the same implementation


def capabilities_cmd() -> int:
    try:
        caps = _capabilities()
        sys.stdout.write(json.dumps(caps, separators=(",", ":")) + "\n")
        return 0
    except Exception as e:
        sys.stderr.write(f"error: {e}\n")
        return 1

if __name__ == "__main__":  # manual run: python -m inspector_raspi.cli
    raise SystemExit(capabilities_cmd())
