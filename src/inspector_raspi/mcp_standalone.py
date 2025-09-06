#!/usr/bin/env python3
"""
Minimal stdio-only MCP server for Raspberry Pi.

Goals:
- No HTTP server; all tools query the local system directly.
- Fast, robust, low-dependency. Works in VS Code Copilot Toolsets & Studio.

Implements JSON-RPC 2.0 over stdio with LSP-style Content-Length framing.

Tools provided:
- pi-health: quick OK with basic info
- pi-cpu-temp: CPU temperature in C
- pi-capabilities: binaries/devices/python libs presence
- pi-gpu-info: vcgencmd summary if available
- pi-usb-list: lsusb output or sysfs fallback
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import glob
import re


# ---------- JSON-RPC / LSP framing ----------

DEBUG = bool(os.getenv("RASPI_MCP_DEBUG"))


def _send(msg: Dict[str, Any]) -> None:
    data = json.dumps(msg, separators=(",", ":"), ensure_ascii=False).encode()
    sys.stdout.write(f"Content-Length: {len(data)}\r\n\r\n")
    sys.stdout.flush()
    sys.stdout.buffer.write(data)
    sys.stdout.flush()
    if DEBUG:
        try:
            sys.stderr.write(f"--> {msg.get('id')}: {msg.get('method') or 'result'}\n")
            sys.stderr.flush()
        except Exception:
            pass


def _read_message() -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        try:
            k, v = line.decode().split(":", 1)
        except ValueError:
            continue
        headers[k.strip().lower()] = v.strip()
    n = int(headers.get("content-length", "0"))
    if n <= 0:
        return None
    body = sys.stdin.buffer.read(n)
    try:
        msg = json.loads(body.decode())
        if DEBUG:
            try:
                sys.stderr.write(f"<-- {msg.get('id')}: {msg.get('method')}\n")
                sys.stderr.flush()
            except Exception:
                pass
        return msg
    except Exception:
        return None


def _ok(id_: int, result: Dict[str, Any]) -> None:
    _send({"jsonrpc": "2.0", "id": id_, "result": result})


def _err(id_: int, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


# ---------- Helpers for system queries ----------

def _run(cmd: List[str], timeout: float = 3.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


def _has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def _any_glob(paths: List[str]) -> bool:
    for p in paths:
        try:
            if glob.glob(p):
                return True
        except Exception:
            continue
    return False


def _read_cpu_temp() -> Optional[float]:
    # Prefer sysfs thermal zones
    zones = sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp"))
    for z in zones:
        try:
            raw = z.read_text().strip()
            if raw:
                val = int(raw)
                # values are usually millidegrees C
                if val > 1000:
                    return round(val / 1000.0, 1)
                return float(val)
        except Exception:
            pass
    # Fallback: vcgencmd measure_temp
    if _has_cmd("vcgencmd"):
        try:
            cp = _run(["vcgencmd", "measure_temp"])  # temp=45.6'C
            for part in cp.stdout.split("=")[-1:]:
                s = part.strip().rstrip("'C ")
                try:
                    return float(s)
                except Exception:
                    continue
        except Exception:
            pass
    return None


def _capabilities() -> Dict[str, bool]:
    # Binary checks
    bins = {
        "docker": _has_cmd("docker"),
        "ffmpeg": _has_cmd("ffmpeg"),
        "glxinfo": _has_cmd("glxinfo"),
        "lsb_release": _has_cmd("lsb_release"),
        "lsusb": _has_cmd("lsusb"),
        "v4l2_ctl": _has_cmd("v4l2-ctl"),
        "vcgencmd": _has_cmd("vcgencmd"),
        "vulkaninfo": _has_cmd("vulkaninfo"),
        "pip3": _has_cmd("pip3"),
    }
    # Device files
    devs = {
        "gpio_mem": Path("/dev/gpiomem").exists(),
        "i2c_dev": _any_glob(["/dev/i2c-*"]),
        "spi_dev": _any_glob(["/dev/spidev*"]),
        "video_dev": _any_glob(["/dev/video*", "/dev/v4l-subdev*"]),
        "thermal_zone": Path("/sys/class/thermal").exists(),
    }
    # Python libs (fast: check installed dists instead of importing heavy modules)
    py = {k: False for k in [
        "onnxruntime", "opencv_python", "openvino", "tensorflow", "tflite_runtime", "torch",
    ]}
    try:
        try:
            from importlib import metadata as _md  # Python 3.8+
        except Exception:  # pragma: no cover
            import importlib_metadata as _md  # type: ignore

        def has_dist(name: str) -> bool:
            try:
                return _md.version(name) is not None
            except Exception:
                return False

        py["onnxruntime"] = has_dist("onnxruntime")
        # OpenCV can be installed under multiple names; check common ones
        py["opencv_python"] = has_dist("opencv-python") or has_dist("opencv-python-headless")
        py["openvino"] = has_dist("openvino") or has_dist("openvino-dev")
        py["tensorflow"] = has_dist("tensorflow") or has_dist("tensorflow-cpu") or has_dist("tensorflow-lite")
        py["tflite_runtime"] = has_dist("tflite-runtime")
        py["torch"] = has_dist("torch")
    except Exception:
        pass

    # docker availability: require docker binary + socket
    if bins["docker"] and not Path("/var/run/docker.sock").exists():
        bins["docker"] = False

    out: Dict[str, bool] = {}
    out.update(bins)
    out.update(devs)
    out.update(py)
    return out


def _gpu_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {"vcgencmd": False}
    if _has_cmd("vcgencmd"):
        info["vcgencmd"] = True
        try:
            cp = _run(["vcgencmd", "get_mem", "gpu"])  # gpu=76M
            info["gpu_mem"] = cp.stdout.strip()
        except Exception as e:
            info["gpu_mem"] = f"error: {e}"
        try:
            cp = _run(["vcgencmd", "get_mem", "arm"])  # arm=xxxM
            info["arm_mem"] = cp.stdout.strip()
        except Exception as e:
            info["arm_mem"] = f"error: {e}"
        try:
            cp = _run(["vcgencmd", "version"])  # firmware version + build
            info["version"] = cp.stdout.strip()
        except Exception as e:
            info["version"] = f"error: {e}"
        try:
            cp = _run(["vcgencmd", "get_throttled"])  # bitmask
            info["throttled"] = cp.stdout.strip()
        except Exception:
            pass
    return info


def _usb_list() -> Dict[str, Any]:
    # Prefer lsusb
    if _has_cmd("lsusb"):
        try:
            cp = _run(["lsusb"])  # one device per line
            return {"lsusb": cp.stdout.strip().splitlines()}
        except Exception as e:
            return {"error": f"lsusb failed: {e}"}
    # Fallback to sysfs
    devices_root = Path("/sys/bus/usb/devices")
    items: List[Dict[str, str]] = []
    if devices_root.exists():
        for dev in devices_root.iterdir():
            try:
                vid = (dev / "idVendor").read_text().strip()
                pid = (dev / "idProduct").read_text().strip()
                mfg = (dev / "manufacturer").read_text().strip() if (dev / "manufacturer").exists() else ""
                prod = (dev / "product").read_text().strip() if (dev / "product").exists() else ""
                items.append({"device": dev.name, "vendor": vid, "product": pid, "manufacturer": mfg, "name": prod})
            except Exception:
                continue
    return {"sysfs": items}


# ---------- New Tool Helpers ----------

def _system_info() -> Dict[str, Any]:
    # CPU
    cpu: Dict[str, Any] = {}
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(errors="ignore")
        model = ""
        for line in cpuinfo.splitlines():
            if ":" in line:
                k, v = [p.strip() for p in line.split(":", 1)]
                if k.lower() in ("model name", "hardware", "model"):
                    model = v
        cpu["model"] = model
    except Exception:
        pass
    # Memory
    mem: Dict[str, Any] = {}
    try:
        meminfo = Path("/proc/meminfo").read_text(errors="ignore")
        m: Dict[str, int] = {}
        for line in meminfo.splitlines():
            parts = line.split(":", 1)
            if len(parts) != 2:
                continue
            key = parts[0]
            rest = parts[1].strip()
            val = rest.split()[0]
            try:
                m[key] = int(val) * 1024  # kB -> bytes
            except Exception:
                continue
        total = m.get("MemTotal")
        free = m.get("MemFree")
        cached = m.get("Cached")
        buffers = m.get("Buffers")
        avail = m.get("MemAvailable")
        used = None
        if total is not None and avail is not None:
            used = total - avail
        mem.update({"total": total, "available": avail, "used": used, "buffers": buffers, "cached": cached})
    except Exception:
        pass
    # Disk (root fs)
    disk: Dict[str, Any] = {}
    try:
        du = shutil.disk_usage("/")
        disk = {"total": du.total, "used": du.used, "free": du.free}
    except Exception:
        pass
    # OS/Python
    osinfo = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
    }
    # Network (summary)
    net: Dict[str, Any] = {"interfaces": []}
    try:
        ni = _net_interfaces()
        net = ni
    except Exception:
        pass
    # GPU
    gpu = _gpu_info()
    # Temps
    temps = {"cpu_celsius": _read_cpu_temp()}
    return {
        "cpu": cpu,
        "mem": mem,
        "disk": disk,
        "os": osinfo,
        "net": net,
        "gpu": gpu,
        "temps": temps,
    }


def _cpu_freq() -> Dict[str, Any]:
    base = Path("/sys/devices/system/cpu/cpu0/cpufreq")
    def read_int(p: Path) -> Optional[int]:
        try:
            return int(p.read_text().strip())
        except Exception:
            return None
    cur = read_int(base / "scaling_cur_freq")
    mn = read_int(base / "scaling_min_freq")
    mx = read_int(base / "scaling_max_freq")
    gov = None
    try:
        gov = (base / "scaling_governor").read_text().strip()
    except Exception:
        pass
    # Values are in kHz typically; convert to Hz if plausible
    def to_hz(x: Optional[int]) -> Optional[int]:
        if x is None:
            return None
        # If in kHz (< 10^7), convert to Hz
        return x * 1000 if x < 10_000_000 else x
    return {"cur_hz": to_hz(cur), "min_hz": to_hz(mn), "max_hz": to_hz(mx), "governor": gov}


def _throttle_status() -> Dict[str, Any]:
    flags: Dict[str, Any] = {
        "available": False,
        "raw": "",
        "flags": {},
    }
    if not _has_cmd("vcgencmd"):
        return flags
    try:
        cp = _run(["vcgencmd", "get_throttled"])  # e.g., throttled=0x0
        s = cp.stdout.strip()
        raw = s.split("=", 1)[-1]
        if raw.startswith("0x"):
            value = int(raw, 16)
        else:
            value = int(raw)
        def bit(n: int) -> bool:
            return bool(value & (1 << n))
        flags_map = {
            "under_voltage": bit(0),
            "freq_capped": bit(1),
            "throttled": bit(2),
            "soft_temp_limit": bit(3),
            "under_voltage_has_occurred": bit(16),
            "freq_capped_has_occurred": bit(17),
            "throttled_has_occurred": bit(18),
            "soft_temp_limit_has_occurred": bit(19),
        }
        return {"available": True, "raw": raw, "flags": flags_map}
    except Exception:
        return flags


def _camera_info() -> Dict[str, Any]:
    out: Dict[str, Any] = {"devices": []}
    if not _has_cmd("v4l2-ctl"):
        # List video devices crudely
        vids = sorted(glob.glob("/dev/video*"))
        return {"devices": [{"name": Path(p).name, "paths": [p]} for p in vids]}
    try:
        cp = _run(["v4l2-ctl", "--list-devices"], timeout=4.0)
        lines = cp.stdout.splitlines()
        cur_name = None
        paths: List[str] = []
        devices: List[Dict[str, Any]] = []
        for ln in lines + [""]:
            if ln.strip() == "":
                if cur_name and paths:
                    devices.append({"name": cur_name.strip(), "paths": paths[:]})
                cur_name, paths = None, []
                continue
            if not ln.startswith("\t") and not ln.startswith(" "):
                cur_name = ln
            else:
                p = ln.strip()
                if p:
                    paths.append(p)
        out["devices"] = devices
    except Exception:
        pass
    return out


def _v4l2_formats() -> Dict[str, Any]:
    devices = []
    devs = sorted(glob.glob("/dev/video*"))
    for d in devs:
        entry: Dict[str, Any] = {"device": d, "formats": []}
        if _has_cmd("v4l2-ctl"):
            try:
                cp = _run(["v4l2-ctl", "-d", d, "--list-formats-ext"], timeout=5.0)
                fmt_list: List[Dict[str, Any]] = []
                fourcc = None
                desc = None
                sizes: List[str] = []
                for line in cp.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Pixel Format:"):
                        # flush previous
                        if fourcc:
                            fmt_list.append({"fourcc": fourcc, "description": desc, "sizes": sizes[:]})
                            sizes = []
                        m = re.search(r"Pixel Format:\s*'([^']+)'\s*\(([^)]+)\)", line)
                        if m:
                            fourcc, desc = m.group(1), m.group(2)
                        else:
                            fourcc, desc = line.split(":", 1)[-1].strip(), None
                    elif line.startswith("Size:") and "Discrete" in line:
                        m = re.search(r"(\d+)x(\d+)", line)
                        if m:
                            sizes.append(f"{m.group(1)}x{m.group(2)}")
                if fourcc:
                    fmt_list.append({"fourcc": fourcc, "description": desc, "sizes": sizes[:]})
                entry["formats"] = fmt_list
            except Exception:
                pass
        devices.append(entry)
    return {"devices": devices}


def _net_interfaces() -> Dict[str, Any]:
    if _has_cmd("ip"):
        try:
            cp = _run(["ip", "-j", "addr"])  # JSON output
            data = json.loads(cp.stdout or "[]")
            out: List[Dict[str, Any]] = []
            for itf in data:
                addrs = []
                for a in itf.get("addr_info", []) or []:
                    fam = a.get("family")
                    addr = a.get("local")
                    if fam and addr:
                        addrs.append({"family": fam, "address": addr})
                out.append({"name": itf.get("ifname"), "mac": itf.get("address"), "addrs": addrs})
            return {"interfaces": out}
        except Exception:
            pass
    # Fallback: sysfs names only
    names = []
    try:
        for p in Path("/sys/class/net").iterdir():
            names.append(p.name)
    except Exception:
        pass
    return {"interfaces": [{"name": n, "mac": None, "addrs": []} for n in sorted(names)]}


def _wifi_status() -> Dict[str, Any]:
    info: Dict[str, Any] = {"available": False, "iface": "", "ssid": "", "quality": None, "bitrate": None}
    if not _has_cmd("iwgetid"):
        return info
    info["available"] = True
    try:
        cp = _run(["iwgetid"])  # e.g., wlan0  ESSID:"ssid"
        ln = cp.stdout.strip().splitlines()[0] if cp.stdout else ""
        if ln:
            parts = ln.split()
            if parts:
                info["iface"] = parts[0]
            m = re.search(r'ESSID:"([^"]*)"', ln)
            if m:
                info["ssid"] = m.group(1)
    except Exception:
        pass
    # quality/bitrate via iwconfig if present
    if _has_cmd("iwconfig") and info["iface"]:
        try:
            cp2 = _run(["iwconfig", info["iface"]])
            m = re.search(r"Link Quality=(\d+)/(\d+)", cp2.stdout or "")
            if m:
                num, den = int(m.group(1)), int(m.group(2))
                info["quality"] = round((num / max(1, den)) * 100)
            m2 = re.search(r"Bit Rate=(\S+)", cp2.stdout or "")
            if m2:
                info["bitrate"] = m2.group(1)
        except Exception:
            pass
    return info


def _dmesg_tail(lines: int = 200) -> Dict[str, Any]:
    try:
        cp = _run(["dmesg"])  # may require privileges on some systems
        all_lines = (cp.stdout or "").splitlines()
        return {"lines": all_lines[-max(1, int(lines)):]}
    except Exception as e:
        return {"lines": [], "error": str(e)}


def _services() -> Dict[str, Any]:
    if not _has_cmd("systemctl"):
        return {"available": False, "services": []}
    try:
        cp = _run(["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"])
        items: List[Dict[str, str]] = []
        for ln in (cp.stdout or "").splitlines():
            # Split by 2+ spaces to separate columns
            cols = re.split(r"\s{2,}", ln.strip())
            if not cols:
                continue
            unit = cols[0]
            desc = cols[-1] if len(cols) > 1 else ""
            items.append({"name": unit, "description": desc})
        return {"available": True, "services": items}
    except Exception as e:
        return {"available": True, "services": [], "error": str(e)}


def _i2c_scan() -> Dict[str, Any]:
    buses = sorted(glob.glob("/dev/i2c-*"))
    out: List[Dict[str, Any]] = []
    has_detect = _has_cmd("i2cdetect")
    for b in buses:
        entry: Dict[str, Any] = {"bus": b, "devices": []}
        if has_detect:
            # Bus number is suffix after '-'
            try:
                n = b.split("-")[-1]
                cp = _run(["i2cdetect", "-y", n], timeout=5.0)
                # Parse addresses where output not '--'
                addrs: List[str] = []
                for ln in (cp.stdout or "").splitlines():
                    ln = ln.strip()
                    if not ln or ln.startswith(" ") or not ":" in ln:
                        continue
                    parts = ln.split()
                    # skip row header like '00:'
                    for tok in parts[1:]:
                        if tok != "--" and tok != "--":
                            # tokens like '1a'
                            if re.fullmatch(r"[0-9a-fA-F]{2}", tok):
                                addrs.append(tok.lower())
                entry["devices"] = sorted(addrs)
            except Exception:
                pass
        out.append(entry)
    return {"buses": out}


# ----- USB tree and watch -----

def _usb_tree() -> Dict[str, Any]:
    if not _has_cmd("lsusb"):
        return {"available": False, "tree": []}
    try:
        if _has_cmd("lsusb"):
            # Try topology view; if not available, fall back to flat list
            if _has_cmd("lsusb"):
                cp = _run(["lsusb", "-t"])  # textual tree
                lines = (cp.stdout or "").splitlines()
                return {"available": True, "tree": lines}
    except Exception as e:
        return {"available": True, "tree": [], "error": str(e)}
    return {"available": False, "tree": []}


_USB_WATCH_STATE: Dict[str, Any] = {"token": 0, "snapshot": []}


def _usb_snapshot() -> List[str]:
    if _has_cmd("lsusb"):
        try:
            cp = _run(["lsusb"])  # one device per line
            return (cp.stdout or "").splitlines()
        except Exception:
            return []
    # Fallback to sysfs device names
    devices_root = Path("/sys/bus/usb/devices")
    items: List[str] = []
    if devices_root.exists():
        for dev in devices_root.iterdir():
            items.append(dev.name)
    return sorted(items)


def _usb_watch(reset: bool = False) -> Dict[str, Any]:
    global _USB_WATCH_STATE
    if reset or not _USB_WATCH_STATE.get("snapshot"):
        snap = _usb_snapshot()
        _USB_WATCH_STATE = {"token": 1, "snapshot": snap}
        return {"token": 1, "current": snap, "added": [], "removed": []}
    prev = _USB_WATCH_STATE.get("snapshot", [])
    cur = _usb_snapshot()
    added = [x for x in cur if x not in prev]
    removed = [x for x in prev if x not in cur]
    tok = int(_USB_WATCH_STATE.get("token", 1)) + 1
    _USB_WATCH_STATE = {"token": tok, "snapshot": cur}
    return {"token": tok, "current": cur, "added": added, "removed": removed}


# ---------- MCP Handlers ----------

def _initialize() -> Dict[str, Any]:
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {"name": "raspi-mcp", "version": "0.1.0"},
        "capabilities": {"tools": {"listChanged": True}},
    }


def _tools_list() -> Dict[str, Any]:
    tools = [
        {
            "name": "pi-health",
            "description": "Get MCP health",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-cpu-temp",
            "description": "Get CPU temperature (C)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-cpu-freq",
            "description": "CPU frequency and governor",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-capabilities",
            "description": "Get detected capabilities (binaries, devices, Python libs)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-throttle-status",
            "description": "Throttle flags from vcgencmd if available",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-system-info",
            "description": "Aggregate system snapshot (cpu/mem/disk/net/gpu/os/temps)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-gpu-info",
            "description": "GPU details using vcgencmd if available",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-camera-info",
            "description": "List V4L2 camera devices",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-v4l2-formats",
            "description": "Enumerate V4L2 pixel formats and discrete sizes per device",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-usb-list",
            "description": "List USB devices (lsusb or sysfs)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-usb-tree",
            "description": "USB topology tree (lsusb -t)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-usb-watch",
            "description": "Watch USB changes; optional {reset:bool} to reset baseline",
            "inputSchema": {
                "type": "object",
                "properties": {"reset": {"type": "boolean"}},
                "additionalProperties": False,
            },
        },
        {
            "name": "pi-net-interfaces",
            "description": "List network interfaces and addresses",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-wifi-status",
            "description": "Wi-Fi interface, SSID, link quality, bitrate (best-effort)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-dmesg-tail",
            "description": "Tail the kernel log; optional {lines:int} (default 200)",
            "inputSchema": {
                "type": "object",
                "properties": {"lines": {"type": "integer", "minimum": 1, "maximum": 5000}},
                "additionalProperties": False,
            },
        },
        {
            "name": "pi-services",
            "description": "List systemd services (if systemctl available)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-i2c-scan",
            "description": "Scan I2C buses for devices (best-effort)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-thermal-zones",
            "description": "List thermal zones and temperatures",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "pi-power",
            "description": "Core voltage and common clock rates (vcgencmd)",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    ]
    return {"tools": tools}


def _tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments") or {}
    # Normalize legacy dotted/camelCase names to hyphen-case expected here
    alias_map = {
        "pi.health": "pi-health",
        "pi.cpuTemp": "pi-cpu-temp",
        "pi.cpuFreq": "pi-cpu-freq",
        "pi.capabilities": "pi-capabilities",
        "pi.throttleStatus": "pi-throttle-status",
        "pi.systemInfo": "pi-system-info",
        "pi.gpuInfo": "pi-gpu-info",
        "pi.cameraInfo": "pi-camera-info",
        "pi.v4l2Formats": "pi-v4l2-formats",
        "pi.usbList": "pi-usb-list",
    "pi.usbTree": "pi-usb-tree",
    "pi.usbWatch": "pi-usb-watch",
        "pi.netInterfaces": "pi-net-interfaces",
        "pi.wifiStatus": "pi-wifi-status",
        "pi.dmesgTail": "pi-dmesg-tail",
        "pi.services": "pi-services",
        "pi.i2cScan": "pi-i2c-scan",
    "pi.thermalZones": "pi-thermal-zones",
    "pi.power": "pi-power",
    }
    if isinstance(name, str):
        name = alias_map.get(name, name)
    # Most tools take no arguments; pi-dmesg-tail optionally takes {lines}
    try:
        if name == "pi-health":
            res = {
                "status": "ok",
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "time": int(time.time()),
            }
        elif name == "pi-cpu-temp":
            t = _read_cpu_temp()
            res = {"celsius": t, "ok": t is not None}
        elif name == "pi-cpu-freq":
            res = _cpu_freq()
        elif name == "pi-capabilities":
            res = _capabilities()
        elif name == "pi-throttle-status":
            res = _throttle_status()
        elif name == "pi-system-info":
            res = _system_info()
        elif name == "pi-gpu-info":
            res = _gpu_info()
        elif name == "pi-camera-info":
            res = _camera_info()
        elif name == "pi-v4l2-formats":
            res = _v4l2_formats()
        elif name == "pi-usb-list":
            res = _usb_list()
        elif name == "pi-usb-tree":
            res = _usb_tree()
        elif name == "pi-usb-watch":
            res = _usb_watch(bool(args.get("reset", False)))
        elif name == "pi-net-interfaces":
            res = _net_interfaces()
        elif name == "pi-wifi-status":
            res = _wifi_status()
        elif name == "pi-dmesg-tail":
            lines = args.get("lines", 200)
            try:
                lines = int(lines)
            except Exception:
                lines = 200
            lines = max(1, min(5000, lines))
            res = _dmesg_tail(lines)
        elif name == "pi-services":
            res = _services()
        elif name == "pi-i2c-scan":
            res = _i2c_scan()
        elif name == "pi-thermal-zones":
            # Enumerate thermal zones with type & temp
            zones = []
            try:
                for z in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
                    t = None
                    try:
                        raw = (z / "temp").read_text().strip()
                        if raw:
                            val = int(raw)
                            t = round(val / 1000.0, 1) if val > 1000 else float(val)
                    except Exception:
                        pass
                    typ = (z / "type").read_text().strip() if (z / "type").exists() else ""
                    zones.append({"zone": z.name, "type": typ, "celsius": t})
            except Exception:
                pass
            res = {"zones": zones}
        elif name == "pi-power":
            info: Dict[str, Any] = {"available": _has_cmd("vcgencmd"), "volt": {}, "clocks": {}}
            if info["available"]:
                # Voltages
                for dom in ["core", "sdram_c", "sdram_i", "sdram_p"]:
                    try:
                        cp = _run(["vcgencmd", "measure_volts", dom])  # volt=1.2000V
                        s = (cp.stdout or "").strip()
                        m = re.search(r"volt=([0-9.]+)V", s)
                        if m:
                            info["volt"][dom] = float(m.group(1))
                    except Exception:
                        continue
                # Clocks (Hz)
                for clk in [
                    "arm",
                    "core",
                    "h264",
                    "isp",
                    "v3d",
                    "uart",
                    "pwm",
                    "emmc",
                    "pixel",
                    "hdmi",
                ]:
                    try:
                        cp = _run(["vcgencmd", "measure_clock", clk])  # frequency(48)=250000000
                        s = (cp.stdout or "").strip()
                        m = re.search(r"(\d+)$", s)
                        if m:
                            info["clocks"][clk] = int(m.group(1))
                    except Exception:
                        continue
            res = info
        else:
            raise ValueError(f"Unknown tool: {name}")
        return {
            "content": [{"type": "text", "text": json.dumps(res, separators=(",", ":"))}],
        }
    except Exception as e:
        raise RuntimeError(str(e))


def main() -> int:
    # Basic loop
    while True:
        msg = _read_message()
        if msg is None:
            break
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {}) or {}
        try:
            if method == "initialize":
                _ok(mid, _initialize())
            elif method == "tools/list":
                _ok(mid, _tools_list())
            elif method == "tools/call":
                _ok(mid, _tools_call(params))
            elif method == "shutdown":
                _ok(mid, {})
                break
            else:
                _err(mid, -32601, f"Method not found: {method}")
        except Exception as e:
            _err(mid, -32000, f"Server error: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
