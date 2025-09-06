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

Use with a virtualenv (venv)
----------------------------
If you prefer an isolated venv instead of pipx:

```bash
# In your project directory on the Pi
python3 -m venv .venv
source .venv/bin/activate

# Option A: install from GitHub (read-only)
pip install git+https://github.com/McFuzzySquirrel/pi-inspector.git@feature/mcp-stdio-tools-and-tests

# Option B: working copy (editable)
pip install -e .

# Verify the CLI is on PATH (should point to .venv/bin)
which raspi-mcp

# Self-test
raspi-mcp-selftest
```

VS Code MCP config with a venv
-------------------------------
If VS Code doesn’t see your venv PATH, point to the venv explicitly. Either of these works:

1) Call the entry script from your venv
```jsonc
{
	"servers": {
		"pi-inspector": {
			"type": "stdio",
			"command": "/absolute/path/to/your/project/.venv/bin/raspi-mcp"
		}
	}
}
```

2) Use python -m to launch the module with your venv’s Python
```jsonc
{
	"servers": {
		"pi-inspector": {
			"type": "stdio",
			"command": "/absolute/path/to/your/project/.venv/bin/python",
			"args": ["-m", "inspector_raspi.mcp_standalone"]
		}
	}
}
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

Fresh Pi? Troubleshooting & feedback
-----------------------------------
- First run `raspi-mcp-selftest`. If it fails, re-run with debug:
	- RASPI_MCP_DEBUG=1 raspi-mcp-selftest
- Then open an issue with:
	- Pi model and OS (cat /etc/os-release)
	- Python version (python3 --version)
	- Self-test output (and debug run if used)
	- Any optional packages installed
- Issues: https://github.com/McFuzzySquirrel/pi-inspector/issues

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
