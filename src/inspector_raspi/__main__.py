import platform
import psutil
import subprocess
import json
from pathlib import Path
from typing import Optional
from flask import Flask, jsonify
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
        "lsb_release": shutil.which("lsb_release") is not None,
        "lsusb": shutil.which("lsusb") is not None,
        "pip3": shutil.which("pip3") is not None,
        "thermal_zone": Path("/sys/class/thermal/thermal_zone0/temp").exists(),
        "i2c_dev": bool(list(Path("/dev").glob("i2c-*"))),
        "spi_dev": bool(list(Path("/dev").glob("spi*"))),
        "gpio_mem": Path("/dev/gpiomem").exists(),
        # Python packages
        "tflite_runtime": has_dist("tflite-runtime"),
        "onnxruntime": has_dist("onnxruntime"),
    }
    return caps

def get_system_info():
    # CPU & memory
    cpu_info = {
        "model": run_cmd("cat /proc/cpuinfo | grep 'Model' | head -1"),
        "arch": platform.machine(),
        "cores": psutil.cpu_count(logical=True),
        "features": run_cmd("cat /proc/cpuinfo | grep Features | head -1")
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
        "glxinfo": run_cmd("glxinfo | grep 'OpenGL version'")  # may need mesa-utils installed
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
    pip_list = run_cmd("pip3 list --format=freeze")
    python_info = {
        "version": platform.python_version(),
        "packages": pip_list.splitlines()[:200] if pip_list else [],  # cap to avoid huge payloads
    }

    # Networking
    network_info = {
        "interfaces": list(psutil.net_if_addrs().keys()),
        "ip": run_cmd("hostname -I")
    }

    # Peripherals
    peripherals_info = {
        "i2c": run_cmd("ls /dev/i2c-* 2>/dev/null"),
        "spi": run_cmd("ls /dev/spi* 2>/dev/null"),
        "gpio": run_cmd("ls /dev/gpiomem 2>/dev/null") is not None,
        "camera": run_cmd("vcgencmd get_camera"),
        "cpu_temp_c": _cpu_temperature_c(),
    }

    # AI/ML
    ml_info = {
        "tflite": run_cmd("pip3 show tflite-runtime"),
        "onnxruntime": run_cmd("pip3 show onnxruntime"),
        "coral_tpu": run_cmd("lsusb | grep 'Global Unichip Corp.'")  # Coral USB accelerator
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
        "ml": ml_info
    }

@app.route("/system-info", methods=["GET"])
def system_info():
    return jsonify(get_system_info())

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
    args = parser.parse_args()

    try:
        import os
        env_port = os.environ.get("PORT") or os.environ.get("INSPECTOR_PORT")
        port = args.port if args.port is not None else int(env_port) if env_port else 5050
    except Exception:
        port = args.port or 5050

    print(f"Starting Raspberry Pi Inspector on http://{host}:{port}/system-info")
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()