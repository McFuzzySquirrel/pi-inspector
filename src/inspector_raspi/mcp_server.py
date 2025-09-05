"""
Minimal MCP (Model Context Protocol) server over stdio that proxies tools to the
local Raspberry Pi Inspector HTTP API. Implements a tiny subset of MCP using
JSON-RPC 2.0 framed with Content-Length headers (LSP-style framing).

Tools exposed:
- pi.health -> GET /health
- pi.cpuTemp -> GET /cpu-temp
- pi.systemInfo -> GET /system-info
- pi.capabilities -> GET /capabilities
- pi.gpuInfo -> extract GPU-related fields from /system-info
- pi.cameraInfo -> summarize camera/video info from /system-info and /capabilities

Note: MCP servers are typically launched on-demand by the client over stdio;
this process is intentionally lightweight and idle when not in use.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple


JSON = Dict[str, Any]


def _now_ms() -> int:
    return int(time.time() * 1000)


class StdioJsonRpc:
    def __init__(self, inp: io.BufferedReader, out: io.BufferedWriter) -> None:
        self._in = inp
        self._out = out

    def _read_headers(self) -> Optional[Dict[str, str]]:
        headers: Dict[str, str] = {}
        line_parts: list[bytes] = []
        while True:
            line = self._in.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            line_parts.append(line)
            if len(line_parts) > 64:  # guard against header abuse
                raise RuntimeError("Too many header lines")
        for raw in line_parts:
            try:
                s = raw.decode("utf-8").strip()
                if not s:
                    continue
                k, v = s.split(":", 1)
                headers[k.strip().lower()] = v.strip()
            except Exception:
                continue
        return headers

    def _read_message(self) -> Optional[JSON]:
        headers = self._read_headers()
        if headers is None:
            return None
        length_s = headers.get("content-length")
        if not length_s:
            return None
        try:
            length = int(length_s)
        except ValueError:
            return None
        if length < 0 or length > 1_000_000:
            raise RuntimeError("Invalid Content-Length")
        body = self._in.read(length)
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None

    def _send(self, payload: JSON) -> None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
        self._out.write(header)
        self._out.write(data)
        self._out.flush()

    def send_result(self, id_val: Any, result: Any) -> None:
        self._send({"jsonrpc": "2.0", "id": id_val, "result": result})

    def send_error(self, id_val: Any, code: int, message: str, data: Any = None) -> None:
        err: JSON = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        self._send({"jsonrpc": "2.0", "id": id_val, "error": err})

    def send_notification(self, method: str, params: Any = None) -> None:
        msg: JSON = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def serve(self, handler: "McpHandler") -> None:
        # Minimal handshake notification
        self.send_notification("$/serverStarted", {"ts": _now_ms()})
        while True:
            msg = self._read_message()
            if msg is None:
                break
            mid = msg.get("id")
            method = msg.get("method")
            params = msg.get("params", {})
            try:
                if method == "initialize":
                    res = handler.on_initialize(params)
                    self.send_result(mid, res)
                elif method == "tools/list":
                    res = handler.on_tools_list(params)
                    self.send_result(mid, res)
                elif method == "tools/call":
                    res = handler.on_tools_call(params)
                    self.send_result(mid, res)
                elif method in ("shutdown", "exit"):
                    self.send_result(mid, {})
                    break
                else:
                    self.send_error(mid, -32601, f"Method not found: {method}")
            except Exception as e:
                self.send_error(mid, -32000, "Server error", {"message": str(e)})


class McpHandler:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache: Dict[str, Tuple[float, Any]] = {}

    def _http_json_cached(self, path: str, ttl: float = 3.0) -> Any:
        url = f"{self.base_url}{path}"
        now = time.time()
        hit = self._cache.get(url)
        if hit and (now - hit[0]) <= ttl:
            return hit[1]
        data = _http_json(url)
        self._cache[url] = (now, data)
        return data

    def on_initialize(self, params: JSON) -> JSON:
        return {
            "protocolVersion": "2024-11-05",  # nominal; clients usually only need capabilities
            "serverInfo": {"name": "inspector-raspi-mcp", "version": "0.1.0"},
            "capabilities": {
                "tools": {"listChanged": True}
            },
        }

    def on_tools_list(self, params: JSON) -> JSON:
        # Minimal JSON Schemas (empty objects)
        empty_obj = {"type": "object", "properties": {}, "additionalProperties": False}
        return {
            "tools": [
                {"name": "pi.health", "description": "Get inspector health", "inputSchema": empty_obj},
                {"name": "pi.cpuTemp", "description": "Get CPU temperature (C)", "inputSchema": empty_obj},
                {"name": "pi.systemInfo", "description": "Get full system information", "inputSchema": empty_obj},
                {"name": "pi.capabilities", "description": "Get detected capabilities", "inputSchema": empty_obj},
                {"name": "pi.gpuInfo", "description": "GPU details extracted from system info", "inputSchema": empty_obj},
                {"name": "pi.cameraInfo", "description": "Camera/video device summary from system info and capabilities", "inputSchema": empty_obj},
            ]
        }

    def on_tools_call(self, params: JSON) -> JSON:
        name = params.get("name")
        if not isinstance(name, str):
            raise ValueError("Invalid tool name")

        if name in {"pi.health", "pi.cpuTemp", "pi.systemInfo", "pi.capabilities"}:
            path = {
                "pi.health": "/health",
                "pi.cpuTemp": "/cpu-temp",
                "pi.systemInfo": "/system-info",
                "pi.capabilities": "/capabilities",
            }[name]
            data = self._http_json_cached(path)
        elif name == "pi.gpuInfo":
            sysinfo = self._http_json_cached("/system-info")
            data = sysinfo.get("gpu", {}) if isinstance(sysinfo, dict) else {}
        elif name == "pi.cameraInfo":
            sysinfo = self._http_json_cached("/system-info")
            caps = self._http_json_cached("/capabilities")
            peripherals = sysinfo.get("peripherals", {}) if isinstance(sysinfo, dict) else {}
            data = {
                "video_devices": peripherals.get("video_devices", []),
                "camera_status": peripherals.get("camera"),
                "v4l2_ctl": bool(caps.get("v4l2_ctl", False)) if isinstance(caps, dict) else False,
                "libcamera": bool(caps.get("libcamera", False)) if isinstance(caps, dict) else False,
            }
        else:
            raise ValueError(f"Unknown tool: {name}")

        content = [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]
        return {"content": content}


def _http_json(url: str, timeout: float = 2.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 (local API only)
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        if "json" in ctype or text.startswith("{") or text.startswith("["):
            return json.loads(text)
        return {"raw": text}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Minimal MCP server for inspector-raspi (stdio)")
    p.add_argument("--port", type=int, default=int(os.getenv("INSPECTOR_PORT", os.getenv("PORT", 5050))), help="Local inspector API port")
    args = p.parse_args(argv)
    base_url = f"http://127.0.0.1:{args.port}"

    handler = McpHandler(base_url)
    rpc = StdioJsonRpc(sys.stdin.buffer, sys.stdout.buffer)
    try:
        rpc.serve(handler)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        # Best-effort error to stderr; MCP clients read stdout only.
        sys.stderr.write(f"MCP server error: {e}\n")
        sys.stderr.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
