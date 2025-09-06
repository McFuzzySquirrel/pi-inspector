#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

TOOLS = [
    "pi-health",
    "pi-cpu-temp",
    "pi-cpu-freq",
    "pi-capabilities",
    "pi-throttle-status",
    "pi-system-info",
    "pi-gpu-info",
    "pi-camera-info",
    "pi-v4l2-formats",
    "pi-usb-list",
    "pi-usb-tree",
    "pi-usb-watch",
    "pi-net-interfaces",
    "pi-wifi-status",
    "pi-dmesg-tail",
    "pi-services",
    "pi-i2c-scan",
    "pi-thermal-zones",
    "pi-power",
]


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
        parts = line.decode(errors="replace").split(":", 1)
        if len(parts) != 2:
            continue
        k, v = parts
        headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length", "0"))
    if n <= 0:
        return None
    body = proc.stdout.read(n)
    return json.loads(body.decode())


def _recv_until_id(proc: subprocess.Popen, target_id: int, max_scans: int = 20) -> Optional[Dict[str, Any]]:
    for _ in range(max_scans):
        msg = _recv_message(proc)
        if msg is None:
            return None
        if msg.get("id") == target_id:
            return msg
    return None


def main(argv: list[str] | None = None) -> int:
    # Keep debug off for clean output
    env = os.environ.copy()
    env.pop("RASPI_MCP_DEBUG", None)

    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    failures: list[str] = []
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        init = _recv_until_id(proc, 1)
        if not init or "result" not in init:
            print("FAIL: initialize", file=sys.stderr)
            return 2

        # tools/list sanity
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tlist = _recv_until_id(proc, 2)
        available = set()
        if tlist and "result" in tlist:
            available = {t.get("name") for t in tlist["result"].get("tools", [])}

        # Call each tool
        msg_id = 10
        for tool in TOOLS:
            msg_id += 1
            _send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "method": "tools/call",
                    "params": {"name": tool, "arguments": {"lines": 5} if tool == "pi-dmesg-tail" else {}},
                },
            )
            resp = _recv_until_id(proc, msg_id)
            if not resp or "result" not in resp:
                failures.append(tool)
                continue
            try:
                content = resp["result"]["content"][0]
                json.loads(content.get("text", "{}"))
            except Exception:
                failures.append(tool)

        # shutdown
        _send(proc, {"jsonrpc": "2.0", "id": 999, "method": "shutdown", "params": {}})
        _recv_until_id(proc, 999)

    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()

    # Report summary
    missing = [t for t in TOOLS if t not in available]
    if missing:
        print("WARN: tools missing from server:", ", ".join(sorted(missing)))

    if failures:
        print("FAIL: tools with errors:", ", ".join(sorted(failures)))
        return 1

    print("PASS: MCP server OK; all tool calls returned JSON")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
