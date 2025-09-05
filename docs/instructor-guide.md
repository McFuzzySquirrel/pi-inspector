Instructor Guide: Pi Inspector (All‑in‑One MCP)
===============================================

Purpose
-------
Help participants get a working local MCP setup quickly using the all‑in‑one server that embeds the API (no separate API process).

Audience & Requirements
-----------------------
- Linux (Debian/Ubuntu/Raspberry Pi OS)
- Python 3.9+ and internet connectivity to GitHub
- Optional: VS Code with GitHub Copilot/Toolsets to exercise MCP UI

10‑Minute Setup (Recommended: pipx)
-----------------------------------
1) Install pipx (once per machine):
```bash
sudo apt-get update && sudo apt-get install -y pipx
pipx ensurepath
```

2) Install Pi Inspector from GitHub:
```bash
pipx install git+https://github.com/McFuzzySquirrel/pi-inspector.git@feature/mcp-first
```

3) Run the all‑in‑one MCP (spawns API quietly):
```bash
inspector-raspi-mcp-all --port 5051
# Leave it running (it communicates over stdio with the client)
```

4) VS Code MCP wiring (user‑level):
Create `~/.config/Code/User/mcp.json`:
```json
{
  "servers": {
    "pi-inspector": {
      "type": "stdio",
      "command": "/home/$(whoami)/.local/bin/inspector-raspi-mcp-all",
      "args": ["--port", "5051"],
      "env": { "INSPECTOR_PORT": "5051" }
    }
  }
}
```
Reload VS Code; Copilot/Toolsets will auto‑launch the server on demand.

Alternative (venv install)
--------------------------
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install git+https://github.com/McFuzzySquirrel/pi-inspector.git@feature/mcp-first
inspector-raspi-mcp-all --port 5051
```

Validate
--------
- Quick API check (served by the embedded API):
```bash
curl -s http://127.0.0.1:5051/health
```
- Roundtrip (from repo clone, optional):
```bash
python scripts/mcp_roundtrip.py --port 5051 --tool pi.usbList
```
- In Copilot Chat: ask to list tools, or run `pi.usbList`, then run `pi.usbWatch` twice.

Common Issues & Fixes
---------------------
- Port already in use: pick a different port (e.g., 5053) and update both `--port` and `INSPECTOR_PORT` in mcp.json.
- `command not found`: ensure pipx is on PATH (`pipx ensurepath`; re‑open the terminal) or use the venv option.
- Copilot “auto‑configure tools” prompts: trust the workspace and set auto‑configure to Always in Settings.
- No output from MCP and API unreachable: verify `curl http://127.0.0.1:<port>/health` and keep port values consistent.

Stop/Cleanup
------------
- Press Ctrl+C in the terminal running `inspector-raspi-mcp-all`.
- To be thorough, ensure no listeners remain (should not persist):
```bash
ss -ltnp | awk 'NR==1 || /:505[0-5]/'
```

Notes
-----
- The all‑in‑one server avoids unsolicited stdout and auto‑detects JSON‑RPC framing.
- No Node/npm required. Python is required on the host running the MCP.
- For advanced use, the non‑embedded server `inspector-raspi-mcp` can proxy to an externally‑run API.
