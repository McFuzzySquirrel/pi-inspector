#!/usr/bin/env python3
"""
Minimal MCP client roundtrip tester for inspector-raspi-mcp.

This launches the MCP server (module or console) over stdio, sends:
  - initialize
  - tools/list
    - tools/call (default: pi-health)
  - shutdown
and prints the responses.

Usage:
    python3 scripts/mcp_roundtrip.py --port 5050 --tool pi-health

Notes:
  - Ensure the HTTP API is running on 127.0.0.1:<port> beforehand.
  - You can choose how to launch the server: module (-m) or the console script.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional


def _send(proc: subprocess.Popen, msg: Dict[str, Any]) -> None:
    data = json.dumps(msg).encode()
    proc.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
    proc.stdin.write(data)
    proc.stdin.flush()


def _recv_message(proc: subprocess.Popen) -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    while True:
        line = proc.stdout.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        k, v = line.decode().split(":", 1)
        headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length", "0"))
    if n <= 0:
        return None
    body = proc.stdout.read(n)
    return json.loads(body.decode())


def _recv_until_id(proc: subprocess.Popen, target_id: int, max_scans: int = 8) -> Optional[Dict[str, Any]]:
    for _ in range(max_scans):
        msg = _recv_message(proc)
        if msg is None:
            return None
        # Print notifications for visibility, but keep waiting for the matching id
        if "id" not in msg:
            print("notification:", msg)
            continue
        if msg.get("id") == target_id:
            return msg
        # Unexpected id, keep scanning a few messages
        print("skipped message:", msg)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MCP roundtrip tester for inspector-raspi")
    ap.add_argument("--port", type=int, default=int(os.getenv("INSPECTOR_PORT", os.getenv("PORT", 5050))), help="Local inspector API port")
    ap.add_argument("--tool", type=str, default="pi-health", help="Tool to call: pi-health | pi-cpu-temp | pi-system-info | pi-capabilities | pi-usb-list | pi-usb-watch | pi-gpu-info | pi-camera-info")
    ap.add_argument("--args", type=str, default="{}", help='JSON object of tool arguments, e.g., {"reset":true} for pi-usb-watch')
    ap.add_argument("--repeat", type=int, default=1, help="Call the tool N times (useful for watch tools).")
    ap.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between repeated tool calls.")
    ap.add_argument("--launch", choices=["module", "command"], default="command", help="How to launch server: console command (default) or Python module")
    args = ap.parse_args(argv)

    # Launch the MCP server on stdio
    if args.launch == "module":
        cmd = [sys.executable, "-m", "inspector_raspi.mcp_server", "--port", str(args.port)]
    else:
        cmd = ["inspector-raspi-mcp", "--port", str(args.port)]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # If the process exits immediately, surface stderr to help diagnose (e.g., missing module)
    import time
    time.sleep(0.05)
    if proc.poll() is not None:
        err = (proc.stderr.read() or b"").decode(errors="replace")
        print("Server exited early. Stderr:\n" + err)
        return 1

    # initialize
    _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    print("initialize:", _recv_until_id(proc, 1))

    # tools/list
    _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    print("tools/list:", _recv_until_id(proc, 2))

    # tools/call (possibly repeated)
    try:
        tool_args = json.loads(args.args)
        if not isinstance(tool_args, dict):
            raise ValueError("--args must be a JSON object")
    except Exception as e:
        print(f"Invalid --args JSON: {e}")
        return 2

    for i in range(1, max(1, args.repeat) + 1):
        call_id = 2 + i + 1  # ensure unique IDs after tools/list
        _send(proc, {"jsonrpc": "2.0", "id": call_id, "method": "tools/call", "params": {"name": args.tool, "arguments": tool_args}})
        print(f"tools/call {args.tool} [{i}/{args.repeat}]:", _recv_until_id(proc, call_id))
        if i < args.repeat:
            import time as _t
            _t.sleep(max(0.0, args.sleep))

    # shutdown
    _send(proc, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
    print("shutdown:", _recv_until_id(proc, 4))

    try:
        proc.terminate()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
