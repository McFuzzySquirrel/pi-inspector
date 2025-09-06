#!/usr/bin/env python3
from __future__ import annotations

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
    # Read LSP-style headers
    while True:
        line = proc.stdout.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        # Be tolerant of casing/spacing
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


def _recv_until_id(proc: subprocess.Popen, target_id: int, max_scans: int = 8) -> Optional[Dict[str, Any]]:
    for _ in range(max_scans):
        msg = _recv_message(proc)
        if msg is None:
            return None
        if msg.get("id") == target_id:
            return msg
    return None


def test_mcp_stdio_end_to_end():
    # Launch the real stdio-only MCP server as a module
    env = os.environ.copy()
    # Keep debug off by default to avoid noisy stderr in CI
    env.pop("RASPI_MCP_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        # initialize
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        init = _recv_until_id(proc, 1)
        assert init and "result" in init
        assert init["result"]["serverInfo"]["name"] == "raspi-mcp"

        # tools/list
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tlist = _recv_until_id(proc, 2)
        assert tlist and "result" in tlist
        names = {t["name"] for t in tlist["result"]["tools"]}
        assert {"pi-health", "pi-cpu-temp", "pi-capabilities"}.issubset(names)

        # tools/call: pi-capabilities
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "pi-capabilities", "arguments": {}},
            },
        )
        call = _recv_until_id(proc, 3)
        assert call and "result" in call
        content = call["result"]["content"][0]
        assert content["type"] == "text"
        caps = json.loads(content["text"])  # should be a JSON dict
        assert isinstance(caps, dict)
        # Basic keys expected on a Pi-like system (don’t enforce exact values)
        for key in ["lsusb", "v4l2_ctl", "vcgencmd", "thermal_zone"]:
            assert key in caps

        # shutdown
        _send(proc, {"jsonrpc": "2.0", "id": 4, "method": "shutdown", "params": {}})
        shut = _recv_until_id(proc, 4)
        assert shut and "result" in shut
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def _call_tool(name: str, arguments: dict | None = None):
    env = os.environ.copy()
    env.pop("RASPI_MCP_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert _recv_until_id(proc, 1)
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            },
        )
        msg = _recv_until_id(proc, 2)
        assert msg and "result" in msg
        content = msg["result"]["content"][0]
        data = json.loads(content["text"])  # dict
        return data
    finally:
        try:
            _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
            _recv_until_id(proc, 3)
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def test_mcp_tool_cpu_freq():
    data = _call_tool("pi-cpu-freq")
    assert set(["cur_hz", "min_hz", "max_hz", "governor"]).issubset(data.keys())


def test_mcp_tool_throttle_status():
    data = _call_tool("pi-throttle-status")
    assert "available" in data and "flags" in data
    if data["available"]:
        for k in [
            "under_voltage",
            "freq_capped",
            "throttled",
            "soft_temp_limit",
            "under_voltage_has_occurred",
        ]:
            assert k in data["flags"]


def test_mcp_tool_system_info():
    data = _call_tool("pi-system-info")
    for k in ["cpu", "mem", "disk", "os", "net", "gpu", "temps"]:
        assert k in data


def test_mcp_tool_camera_info():
    data = _call_tool("pi-camera-info")
    assert "devices" in data and isinstance(data["devices"], list)


def test_mcp_tool_v4l2_formats():
    data = _call_tool("pi-v4l2-formats")
    assert "devices" in data and isinstance(data["devices"], list)


def test_mcp_tool_net_interfaces():
    data = _call_tool("pi-net-interfaces")
    assert "interfaces" in data and isinstance(data["interfaces"], list)


def test_mcp_tool_wifi_status():
    data = _call_tool("pi-wifi-status")
    assert "available" in data


def test_mcp_tool_dmesg_tail():
    data = _call_tool("pi-dmesg-tail", {"lines": 10})
    assert "lines" in data and isinstance(data["lines"], list)
    assert len(data["lines"]) <= 10


def test_mcp_tool_services():
    data = _call_tool("pi-services")
    assert "available" in data and "services" in data


def test_mcp_tool_i2c_scan():
    data = _call_tool("pi-i2c-scan")
    assert "buses" in data and isinstance(data["buses"], list)


def test_mcp_tool_usb_tree():
    data = _call_tool("pi-usb-tree")
    assert "available" in data and "tree" in data
    if data["available"]:
        assert isinstance(data["tree"], list)


def test_mcp_tool_usb_watch():
    # Reset baseline
    data1 = _call_tool("pi-usb-watch", {"reset": True})
    assert "token" in data1 and "current" in data1
    # Next call should return token+1 and possibly empty deltas
    data2 = _call_tool("pi-usb-watch")
    assert data2.get("token", 0) >= data1.get("token", 0)
    assert all(k in data2 for k in ["current", "added", "removed"])  # shape


def test_mcp_tool_thermal_zones():
    data = _call_tool("pi-thermal-zones")
    assert "zones" in data and isinstance(data["zones"], list)


def test_mcp_tool_power():
    data = _call_tool("pi-power")
    assert "available" in data and "volt" in data and "clocks" in data


def test_mcp_tool_health():
    env = os.environ.copy()
    env.pop("RASPI_MCP_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert _recv_until_id(proc, 1)

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "pi-health", "arguments": {}},
            },
        )
        msg = _recv_until_id(proc, 2)
        assert msg and "result" in msg
        content = msg["result"]["content"][0]
        data = json.loads(content["text"])  # dict
        assert isinstance(data, dict)
        for key in ["status", "platform", "python", "time"]:
            assert key in data
        assert data["status"] == "ok"

        _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        assert _recv_until_id(proc, 3)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def test_mcp_tool_cpu_temp():
    env = os.environ.copy()
    env.pop("RASPI_MCP_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert _recv_until_id(proc, 1)

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "pi-cpu-temp", "arguments": {}},
            },
        )
        msg = _recv_until_id(proc, 2)
        assert msg and "result" in msg
        content = msg["result"]["content"][0]
        data = json.loads(content["text"])  # dict like {"celsius": <float|null>, "ok": <bool>}
        assert isinstance(data, dict)
        assert "ok" in data and isinstance(data["ok"], bool)
        assert "celsius" in data  # may be None on some systems

        _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        assert _recv_until_id(proc, 3)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def test_mcp_tool_gpu_info():
    env = os.environ.copy()
    env.pop("RASPI_MCP_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert _recv_until_id(proc, 1)

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "pi-gpu-info", "arguments": {}},
            },
        )
        msg = _recv_until_id(proc, 2)
        assert msg and "result" in msg
        content = msg["result"]["content"][0]
        info = json.loads(content["text"])  # dict
        assert isinstance(info, dict)
        # Always expect a boolean vcgencmd key; additional fields are optional
        assert "vcgencmd" in info and isinstance(info["vcgencmd"], bool)
        if info["vcgencmd"]:
            # If vcgencmd is available, commonly present keys
            for k in ["gpu_mem", "arm_mem", "version"]:
                assert k in info

        _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        assert _recv_until_id(proc, 3)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


def test_mcp_tool_usb_list():
    env = os.environ.copy()
    env.pop("RASPI_MCP_DEBUG", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "inspector_raspi.mcp_standalone"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert _recv_until_id(proc, 1)

        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "pi-usb-list", "arguments": {}},
            },
        )
        msg = _recv_until_id(proc, 2)
        assert msg and "result" in msg
        content = msg["result"]["content"][0]
        data = json.loads(content["text"])  # dict
        assert isinstance(data, dict)
        # Either lsusb output (list of lines) or sysfs fallback (list of dicts)
        if "lsusb" in data:
            assert isinstance(data["lsusb"], list)
        elif "sysfs" in data:
            assert isinstance(data["sysfs"], list)
        else:
            # At least one key should exist
            assert False, f"unexpected usb payload keys: {list(data.keys())}"

        _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}})
        assert _recv_until_id(proc, 3)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            proc.kill()
