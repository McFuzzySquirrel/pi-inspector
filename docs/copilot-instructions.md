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
- OpenAPI tool (local HTTP): base http://127.0.0.1:5050
  - GET /health → { status }
  - GET /cpu-temp → { cpu_temp_c }
  - GET /capabilities → { ...booleans }
  - GET /system-info → rich system JSON
- MCP tools (stdio server inspector-raspi-mcp):
  - pi.health, pi.cpuTemp, pi.systemInfo, pi.capabilities

Response pattern for the agent
------------------------------
1) Call pi.capabilities (or /capabilities) and, if needed, pi.systemInfo for details.
2) Summarize relevant facts in 1–2 bullets.
3) Provide the minimal, local-first solution (short steps or code). Avoid external deps unless requested.
4) Offer optional next steps (e.g., install a package) clearly marked.

Quick examples
--------------
- CPU temperature (Python using thermal zone fallback):
  ```python
  from pathlib import Path
  p = Path('/sys/class/thermal/thermal_zone0/temp')
  print(round(int(p.read_text().strip())/1000.0, 1))
  ```
- CPU temperature (shell):
  ```bash
  vcgencmd measure_temp || awk '{print $1/1000}' /sys/class/thermal/thermal_zone0/temp
  ```
- List video devices with V4L2:
  ```bash
  ls -1 /dev/video* 2>/dev/null || true
  v4l2-ctl --all --device=/dev/video0 2>/dev/null | sed -n '1,40p'
  ```
- Record 5s video from /dev/video0 with ffmpeg:
  ```bash
  ffmpeg -f v4l2 -framerate 30 -i /dev/video0 -t 5 out.mp4
  ```

Operational notes
-----------------
- The API binds to 127.0.0.1 by default; keep it local for privacy.
- Start on demand to minimize footprint: `systemd-run --user --unit=pi-inspector --same-dir ~/.local/bin/inspector-raspi -p 5050`.
- For MCP, VS Code Toolsets can auto-launch inspector-raspi-mcp; the API must be running first.

Prompts the agent can use
-------------------------
- "Check pi capabilities, then propose a local-only way to capture a snapshot from the first camera device. Avoid libcamera."
- "Verify if ffmpeg is available; if yes, give a minimal command to transcode a video to H.264."
- "Confirm whether any ML runtimes are installed; if none, suggest the smallest runtime to run a MobileNet and how to install it, but keep it optional."
