Raspberry Pi MCP (raspi-mcp)
=============================

Minimal, stdio-only MCP server that lets Copilot/Agent clients query your Raspberry Pi locally over stdio. No HTTP, no ports. Works great with VS Code Copilot Toolsets & Studio.

What you get
------------
- Local-only tools: health, temps, capabilities, GPU, USB, camera, network, services, power, more
- Zero-config server start: client launches `raspi-mcp` on demand
- Safe fallbacks: runs on bare installs, enriches with optional packages

Quickstart (pipx)
-----------------
```bash
sudo apt-get update && sudo apt-get install -y pipx
pipx ensurepath
pipx install git+https://github.com/McFuzzySquirrel/pi-inspector.git
```

Self-test (on the Pi)
---------------------
```bash
raspi-mcp-selftest
```
You should see: `PASS: MCP server OK; all tool calls returned JSON`.

Add to VS Code (MCP config)
---------------------------
Create `~/.config/Code/User/mcp.json` (Linux) with:
```jsonc
{
	"servers": {
		"pi-inspector": {
			"type": "stdio",
			"command": "raspi-mcp"
		}
	}
}
```
Reload VS Code. In Copilot Chat or Toolsets, run a tool like: `pi-capabilities`.

Optional packages (recommended)
-------------------------------
```bash
sudo apt-get install -y usbutils v4l-utils ffmpeg vulkan-tools i2c-tools wireless-tools iproute2
```

CLI helpers
-----------
- `raspi-mcp` – start the stdio MCP server (clients launch this automatically)
- `raspi-capabilities` – print capabilities JSON directly (no MCP framing)
- `raspi-mcp-selftest` – run all tools via MCP and report PASS/FAIL

Develop (this repo)
-------------------
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -q
```

License
-------
MIT
