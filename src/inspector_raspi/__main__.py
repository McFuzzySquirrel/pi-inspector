import platform
import psutil
import subprocess
import json
from pathlib import Path
from typing import Optional
from flask import Flask, jsonify, request
import argparse

app = Flask(__name__)

def run_cmd(cmd: str, timeout: int = 5) -> Optional[str]:
    """Run a shell command and return stripped stdout, or None on error/timeout."""
    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode == 0:
            return completed.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None

def _read_os_release() -> dict:
    """Parse /etc/os-release into a dict, if available."""
    path = Path("/etc/os-release")
    if not path.exists():
        return {}
    data = {}
    try:
        for line in path.read_text().splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            # Strip surrounding quotes
            data[k] = v.strip().strip('"')
    except Exception:
        return {}
    return data

def _cpu_temperature_c() -> Optional[float]:
    """Get CPU temperature in Celsius via vcgencmd or thermal zone fallback."""
    out = run_cmd("vcgencmd measure_temp")
    if out and "temp=" in out:
        # Typical format: temp=48.0'C
        try:
            val = out.split("=")[1].split("'" )[0]
            return float(val)
        except Exception:
            pass
    # Fallback on Linux thermal zone (millidegrees)
    tz_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if tz_path.exists():
        try:
            milli = int(tz_path.read_text().strip())
            return round(milli / 1000.0, 1)
        except Exception:
            return None
    return None

def _device_tree_model() -> Optional[str]:
    p = Path("/proc/device-tree/model")
    if p.exists():
        try:
            return p.read_text(errors="ignore").strip("\x00\n ")
        except Exception:
            return None
    return None

def _cpu_revision() -> Optional[str]:
    out = run_cmd("grep -m1 '^Revision' /proc/cpuinfo | awk '{print $3}'")
    return out

def _cpu_serial_masked() -> Optional[str]:
    # Mask all but last 6 chars for privacy
    out = run_cmd("grep -m1 '^Serial' /proc/cpuinfo | awk '{print $3}'")
    if out and len(out) > 6:
        return f"***{out[-6:]}"
    return None

def _vcgencmd_get_throttled() -> Optional[str]:
    return run_cmd("vcgencmd get_throttled")

def _gpu_mem_split() -> dict:
    return {
        "gpu": run_cmd("vcgencmd get_mem gpu"),
        "arm": run_cmd("vcgencmd get_mem arm"),
    }

def _cpu_freq_mhz() -> Optional[float]:
    # Try sysfs first
    p = Path("/sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq")
    if p.exists():
        try:
            khz = int(p.read_text().strip())
            return round(khz / 1000.0, 1)
        except Exception:
            pass
    # Fallback vcgencmd
    out = run_cmd("vcgencmd measure_clock arm")
    if out and "frequency(48)=" in out:
        try:
            hz = int(out.split("=")[-1])
            return round(hz / 1_000_000.0, 1)
        except Exception:
            return None
    return None

def _video_devices() -> list:
    return [str(p) for p in sorted(Path("/dev").glob("video*"))]

def _wifi_ssid() -> Optional[str]:
    return run_cmd("iwgetid -r")

def _mac_addr(dev: str) -> Optional[str]:
    p = Path(f"/sys/class/net/{dev}/address")
    if p.exists():
        try:
            return p.read_text().strip()
        except Exception:
            return None
    return None

def _bt_present() -> bool:
    return Path("/sys/class/bluetooth").exists() or (run_cmd("hciconfig -a") is not None)

def _lsusb_summary(max_lines: int = 25) -> list:
    out = run_cmd("lsusb")
    if not out:
        return []
    lines = out.splitlines()
    return lines[:max_lines]

def _capabilities() -> dict:
    """Detect available tools and devices in a safe, quick way."""
    import shutil
    try:
        from importlib import metadata  # Python 3.8+
    except Exception:  # pragma: no cover
        import importlib_metadata as metadata  # type: ignore

    def has_dist(name: str) -> bool:
        try:
            return metadata.version(name) is not None
        except Exception:
            return False

    caps = {
        "vcgencmd": shutil.which("vcgencmd") is not None,
        "glxinfo": shutil.which("glxinfo") is not None,
        "vulkaninfo": shutil.which("vulkaninfo") is not None,
        "lsb_release": shutil.which("lsb_release") is not None,
        "lsusb": shutil.which("lsusb") is not None,
        "pip3": shutil.which("pip3") is not None,
        "thermal_zone": Path("/sys/class/thermal/thermal_zone0/temp").exists(),
        "i2c_dev": bool(list(Path("/dev").glob("i2c-*"))),
        "spi_dev": bool(list(Path("/dev").glob("spi*"))),
        "gpio_mem": Path("/dev/gpiomem").exists(),
        "video_dev": bool(list(Path("/dev").glob("video*"))),
        "libcamera": shutil.which("libcamera-hello") is not None or shutil.which("libcamera-still") is not None,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "v4l2_ctl": shutil.which("v4l2-ctl") is not None,
        "docker": shutil.which("docker") is not None,
        # Python packages
        "tflite_runtime": has_dist("tflite-runtime"),
        "onnxruntime": has_dist("onnxruntime"),
        "torch": has_dist("torch"),
        "tensorflow": has_dist("tensorflow") or has_dist("tensorflow-lite"),
        "openvino": has_dist("openvino") or has_dist("openvino-dev"),
        "opencv_python": has_dist("opencv-python"),
    }
    return caps

def get_system_info(fast: bool = False):
    # CPU & memory
    cpu_info = {
        "model": run_cmd("cat /proc/cpuinfo | grep 'Model' | head -1"),
        "arch": platform.machine(),
        "cores": psutil.cpu_count(logical=True),
    "features": run_cmd("cat /proc/cpuinfo | grep Features | head -1"),
    "revision": _cpu_revision(),
    "serial_masked": _cpu_serial_masked(),
    "current_freq_mhz": _cpu_freq_mhz(),
    }

    memory_info = {
        "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "swap_gb": round(psutil.swap_memory().total / (1024**3), 2)
    }

    storage_info = {
        "total_gb": round(psutil.disk_usage("/").total / (1024**3), 2),
        "free_gb": round(psutil.disk_usage("/").free / (1024**3), 2)
    }

    # GPU & video
    gpu_info = {
        "vcgencmd": run_cmd("vcgencmd version"),
        "glxinfo": run_cmd("glxinfo | grep 'OpenGL version'"),  # may need mesa-utils installed
        "gpu_mem": _gpu_mem_split(),
    }

    # OS & kernel
    os_info = {
        "kernel": run_cmd("uname -r"),
        "platform": platform.platform(),
    }
    # Prefer lsb_release if present, otherwise fallback to /etc/os-release
    name = run_cmd("lsb_release -si")
    version = run_cmd("lsb_release -sr")
    codename = run_cmd("lsb_release -sc")
    if name and version:
        os_info.update({"name": name, "version": version, "codename": codename})
    else:
        osv = _read_os_release()
        if osv:
            os_info.update({
                "name": osv.get("NAME"),
                "version": osv.get("VERSION_ID"),
                "codename": osv.get("VERSION_CODENAME") or osv.get("VERSION"),
                "id": osv.get("ID"),
                "pretty": osv.get("PRETTY_NAME"),
            })

    # Python & packages
    if fast:
        python_info = {
            "version": platform.python_version(),
            "packages": [],
            "packages_truncated": True,
        }
    else:
        pip_list = run_cmd("pip3 list --format=freeze")
        python_info = {
            "version": platform.python_version(),
            "packages": pip_list.splitlines()[:200] if pip_list else [],  # cap to avoid huge payloads
        }

    # Networking
    network_info = {
        "interfaces": list(psutil.net_if_addrs().keys()),
        "ip": run_cmd("hostname -I"),
        "wifi_ssid": _wifi_ssid(),
        "mac": {iface: _mac_addr(iface) for iface in ["eth0", "wlan0"] if _mac_addr(iface)},
        "bluetooth_present": _bt_present(),
    }

    # Peripherals
    peripherals_info = {
        "i2c": run_cmd("ls /dev/i2c-* 2>/dev/null"),
        "spi": run_cmd("ls /dev/spi* 2>/dev/null"),
        "gpio": run_cmd("ls /dev/gpiomem 2>/dev/null") is not None,
        "camera": run_cmd("vcgencmd get_camera"),
        "cpu_temp_c": _cpu_temperature_c(),
        "video_devices": _video_devices(),
    }

    # AI/ML
    if fast:
        ml_info = {"skipped": True}
    else:
        ml_info = {
            "tflite": run_cmd("pip3 show tflite-runtime"),
            "onnxruntime": run_cmd("pip3 show onnxruntime"),
            "torch": run_cmd("python3 -c 'import torch,sys;print(torch.__version__)'"),
            "opencv": run_cmd("python3 -c 'import cv2,sys;print(cv2.__version__)'"),
            "tensorflow": run_cmd("python3 -c 'import tensorflow as tf,sys;print(tf.__version__)'"),
            "openvino": run_cmd("python3 -c 'import openvino as ov,sys;print(ov.__version__)'"),
            # Detect Coral/Myriad/Google USB accelerators
            "coral_tpu": run_cmd("lsusb | grep -Ei 'Global Unichip|Movidius|Google'"),
        }

    # Board & power
    board_info = {
        "device_tree_model": _device_tree_model(),
        "throttled": _vcgencmd_get_throttled(),
    }

    return {
        "cpu": cpu_info,
        "memory": memory_info,
        "storage": storage_info,
        "gpu": gpu_info,
        "os": os_info,
        "python": python_info,
        "network": network_info,
        "peripherals": peripherals_info,
        "ml": ml_info,
        "board": board_info,
        "usb": {"lsusb": _lsusb_summary()},
    }

@app.route("/system-info", methods=["GET"])
def system_info():
    fast = str(request.args.get("fast", "")).lower() in {"1", "true", "yes"}
    return jsonify(get_system_info(fast=fast))

@app.route("/system-info-fast", methods=["GET"])
def system_info_fast():
    return jsonify(get_system_info(fast=True))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/cpu-temp", methods=["GET"])
def cpu_temp():
    return jsonify({"cpu_temp_c": _cpu_temperature_c()})

@app.route("/openapi.json", methods=["GET"])
def openapi_spec():
    """Serve the OpenAPI spec describing this local API."""
    spec_path = Path(__file__).with_name("openapi.json")
    if not spec_path.exists():
        return jsonify({
            "openapi": "3.0.3",
            "info": {"title": "Raspberry Pi Inspector API", "version": "0.1.0"},
            "paths": {"/system-info": {"get": {"summary": "System info"}}},
        })
    try:
        return jsonify(json.loads(spec_path.read_text()))
    except Exception:
        return jsonify({"error": "failed_to_load_spec"}), 500

@app.route("/version", methods=["GET"])
def version():
    try:
        try:
            from importlib import metadata  # Python 3.8+
        except Exception:  # pragma: no cover
            import importlib_metadata as metadata  # type: ignore
        ver = metadata.version("inspector-raspi")
    except Exception:
        ver = None
    return jsonify({
    "app": "inspector-raspi",
        "version": ver,
        "python": platform.python_version(),
    })

@app.route("/capabilities", methods=["GET"])
def capabilities():
    return jsonify(_capabilities())

def create_app() -> Flask:
    """Flask app factory for testing/embedding."""
    return app


def main():
    # Strictly local-only binding
    host = "127.0.0.1"
    # CLI takes precedence over env; default 5050
    parser = argparse.ArgumentParser(prog="inspector-raspi", description="Local Raspberry Pi environment inspector API")
    parser.add_argument("-p", "--port", type=int, help="Port to listen on (default from env or 5050)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Reduce startup/log output (silent stdout; suppress Werkzeug logs)")
    args = parser.parse_args()

    try:
        import os
        env_port = os.environ.get("PORT") or os.environ.get("INSPECTOR_PORT")
        port = args.port if args.port is not None else int(env_port) if env_port else 5050
    except Exception:
        port = args.port or 5050

    if not args.quiet:
        print(f"Starting Raspberry Pi Inspector on http://{host}:{port}/system-info")
    # Suppress Werkzeug logs if quiet
    if args.quiet:
        try:
            import logging
            logging.getLogger('werkzeug').setLevel(logging.ERROR)
        except Exception:
            pass
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()