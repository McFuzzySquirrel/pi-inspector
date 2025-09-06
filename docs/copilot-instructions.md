Pi Inspector – Agent Instructions
=================================

Purpose
-------
Guidance for GitHub Copilot Chat/Agent (and other agents) to interact with this Raspberry Pi safely and effectively using the local Pi Inspector API/MCP tools.

Snapshot of current capabilities (2025-09-05)
---------------------------------------------
From GET /capabilities:

- Available: ffmpeg, i2c_dev, spi_dev, v4l2_ctl, video_dev, vcgencmd, vulkaninfo, lsb_release, lsusb, pip3, thermal_zone
- Not available: docker, libcamera, glxinfo, gpio_mem, onnxruntime, opencv_python, openvino, tensorflow, tflite_runtime, torch

Agent operating rules
---------------------
- Always query capabilities first: use one of these tools and cache results per chat turn:
  - pi.capabilities (MCP) or GET /capabilities (OpenAPI)
- Keep it local-only: do not make external network calls; prefer loopback resources and shell tools.
- Be resource-aware: suggest lightweight options first; avoid heavy installs unless explicitly requested.
- Prefer existing tools based on capabilities:
  - If vcgencmd is present: use it for CPU temp, clocks, throttling.
  - If video_dev and v4l2_ctl are present but libcamera is absent: use V4L2 (/dev/videoX) instead of libcamera.
  - If ffmpeg is present: prefer ffmpeg for capture/transcode tasks.
  - If vulkaninfo is present and glxinfo is absent: avoid GLX/OpenGL instructions; consider headless or Vulkan where relevant.
  - Docker is not available: avoid Docker-based instructions; use system packages or Python venv.
- Confirm installations: if a package/tool is missing, propose the minimal commands and clearly separate optional steps.
- Privacy: do not exfiltrate device identifiers; mask serials (Inspector already masks CPU serial).

Tools and how to call them
--------------------------
- OpenAPI tool (local HTTP): base http://127.0.0.1:5051 (workspace default)
  - GET /health → { status }
  - GET /cpu-temp → { cpu_temp_c }
  - GET /capabilities → { ...booleans }
  - GET /system-info → rich system JSON
- MCP tools (stdio server inspector-raspi-mcp):
  - pi-health, pi-cpu-temp, pi-system-info, pi-capabilities, pi-gpu-info, pi-camera-info, pi-usb-list, pi-usb-watch
  - pi-usb-watch returns { devices[], added[], removed[], changed, count, timestamp, ttl_hint_seconds }

Response pattern for the agent
------------------------------
1) Call pi-capabilities (or /capabilities) and, if needed, pi-system-info for details.
2) Summarize relevant facts in 1–2 bullets.
3) Provide the minimal, local-first solution (short steps or code). Avoid external deps unless requested.
4) Offer optional next steps (e.g., install a package) clearly marked.

Quick examples
--------------
- CPU temperature (Python using thermal zone fallback):
  ```python
  from pathlib import Path
  # Pi Inspector – Minimal Agent Instructions (stdio-only)

  Purpose
  - Use local Raspberry Pi diagnostics safely via the stdio MCP server `raspi-mcp`.
  - No HTTP server, no OpenAPI, no curl. Everything goes through MCP tools.

  Golden rules
  - Detect first, act second: call `pi-capabilities` at the start; call `pi-system-info` only when needed.
  - Gate suggestions by capabilities: only propose steps that work now; if something missing clearly unlocks the goal, suggest the smallest optional install.
  - Local-first and lightweight: prefer built-ins and existing tools. Avoid heavy installs unless the user asks.
  - Ask only when essential: otherwise make a reasonable assumption, state it, proceed.
  - Output style: keep answers short with concrete steps; end with a “Try this” action.

  MCP server
  - Name: pi-inspector
  - Type: stdio
  - Command: `raspi-mcp`

  Available tools
  - Health/CPU: `pi-health`, `pi-cpu-temp`, `pi-cpu-freq`, `pi-throttle-status`
  - Capabilities/System: `pi-capabilities`, `pi-system-info`
  - GPU/Power: `pi-gpu-info`, `pi-power`
  - Cameras: `pi-camera-info`, `pi-v4l2-formats`
  - USB: `pi-usb-list`, `pi-usb-tree`, `pi-usb-watch`
  - Network: `pi-net-interfaces`, `pi-wifi-status`
  - Logs/Services: `pi-dmesg-tail` (args: `lines`, `reset`), `pi-services`
  - I2C/Thermal: `pi-i2c-scan`, `pi-thermal-zones`

  Capability gates (examples)
  - If `vcgencmd` is available: use it for temps/throttle/power; else read from `/sys/class/thermal/*`.
  - If `video_dev` and `v4l2_ctl` exist and libcamera is absent: use V4L2 `/dev/video*` instead of libcamera.
  - If `ffmpeg` is available: prefer it for capture/transcode; otherwise suggest installing it (optional).
  - If `docker` is unavailable: avoid Docker-based approaches; use system packages or venv.

  Example flows
  - “List USB devices” → call `pi-usb-list` → return JSON and highlight key devices.
  - “Tail dmesg 20 lines” → call `pi-dmesg-tail` with `{ "lines": 20 }`.
  - “Watch USB then reset” → call `pi-usb-watch`, later call with `{ "reset": true }`.
  - “Show camera formats” → call `pi-v4l2-formats`; if missing `v4l2-ctl`, suggest `sudo apt-get install -y v4l-utils` (optional).

  Suggested installs (only when they unlock the request)
  - System tools (apt): ffmpeg, v4l2-ctl (v4l-utils), usbutils, i2c-tools, wireless-tools, vulkan-tools
  - Python libs (pip in venv): opencv-python-headless, onnxruntime, tflite-runtime, torch (device/arch-dependent)

  Safety & privacy
  - Stay on-device. Don’t exfiltrate unique identifiers. Ask before changing system state or installing.

  Maintenance
  - Owner: @mcfuzzysquirrel
  - Last updated: 2025-09-06
- "If vcgencmd exists, get throttle flags; otherwise read temps from thermal zones and report only what’s available."
