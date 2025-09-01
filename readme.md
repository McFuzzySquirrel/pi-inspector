Raspberry Pi Inspector
======================

If you’re looking to build applications that run on a Raspberry Pi, this can help. It’s a local-only API and a VS Code extension that let GitHub Copilot Chat and Agent Modes understand your Pi’s live environment so suggestions align with your actual hardware and OS.

Quick start (TL;DR)
-------------------
1) Install (isolated):
```bash
pipx install .
```

2) Start on demand (minimal background time):
```bash
systemd-run --user --unit=pi-inspector --same-dir ~/.local/bin/inspector-raspi -p 5050
```

3) Verify locally:
```bash
curl -s http://127.0.0.1:5050/health
```

4) Use it:
- VS Code: install the VSIX under `extensions/pi-inspector/`, then run “Pi Inspector: Health”.
- MCP: run `python3 scripts/mcp_roundtrip.py --port 5050 --tool pi.systemInfo`.

What’s inside
-------------
- A Flask API (loopback-only by default) exposing endpoints like `/health`, `/system-info`, `/cpu-temp`, and an OpenAPI spec.
- A VS Code extension that calls the API and optionally registers tools for Copilot Agent Mode.
- A minimal MCP (Model Context Protocol) server (stdio) that proxies to the API so non-Copilot agents can use the same tools.

Usage
-----
Recommended (minimal resources, on-demand): pipx + user systemd

1) Install once with pipx (isolated, keeps system Python clean):

```bash
sudo apt-get update
sudo apt-get install -y pipx
pipx ensurepath
cd "$(pwd)"  # repo root
pipx install .
```

2) Start/stop on demand (no background when not in use):

Quick transient unit (no files):
```bash
systemd-run --user --unit=pi-inspector --same-dir ~/.local/bin/inspector-raspi -p 5050
# stop later
systemctl --user stop pi-inspector.service
```

Optional helper scripts:
```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/pi-inspector-start <<'EOF'
#!/usr/bin/env bash
exec systemd-run --user --unit=pi-inspector --same-dir "$HOME/.local/bin/inspector-raspi" -p 5050
EOF
chmod +x ~/.local/bin/pi-inspector-start

cat > ~/.local/bin/pi-inspector-stop <<'EOF'
#!/usr/bin/env bash
exec systemctl --user stop pi-inspector.service
EOF
chmod +x ~/.local/bin/pi-inspector-stop

# usage
pi-inspector-start
pi-inspector-stop
```

3) Call endpoints:

```bash
curl -s http://127.0.0.1:5050/health
curl -s http://127.0.0.1:5050/cpu-temp
curl -s http://127.0.0.1:5050/system-info | jq .
curl -s http://127.0.0.1:5050/openapi.json | jq .
```

Alternative ways to run (if you don’t want pipx):
- As a module: `python -m inspector_raspi -p 5050`
- With a venv:
	```bash
	python3 -m venv .venv
	source .venv/bin/activate
	pip install -e .
	inspector-raspi -p 5050
	```

MCP server (portable tools for other agents)
--------------------------------------------
The MCP server is a tiny stdio process that exposes the same tools and proxies them to the local HTTP API. It only runs when a client launches it and is otherwise idle—no background service needed.

- Install (already included when you `pipx install .`): provides `inspector-raspi-mcp`.
- Tools exposed: `pi.health`, `pi.cpuTemp`, `pi.systemInfo`, `pi.capabilities`.
- Port selection: `--port 5050` or environment `INSPECTOR_PORT`/`PORT`.

Run a quick smoke (manual):
```bash
# Launch and keep attached (it waits for MCP JSON-RPC messages on stdin)
inspector-raspi-mcp --port 5050
# Press Ctrl+C to exit
```

Example client configuration (Claude Desktop tool window or generic MCP client):
```json
{
	"mcpServers": {
		"pi-inspector": {
			"command": "inspector-raspi-mcp",
			"args": ["--port", "5050"],
			"env": { "INSPECTOR_PORT": "5050" }
		}
	}
}
```

Try it (roundtrip test):
```bash
# In one terminal: ensure the HTTP API is running locally
inspector-raspi -p 5050

# In another terminal: run the stdio roundtrip test
python3 scripts/mcp_roundtrip.py --port 5050 --tool pi.systemInfo
```

VS Code user-level MCP config (Toolsets):
Create `~/.config/Code/User/mcp.json` with:
```json
{
	"servers": {
		"pi-inspector": {
			"type": "stdio",
			"command": "/home/<user>/.local/bin/inspector-raspi-mcp",
			"args": ["--port", "5050"],
			"env": { "INSPECTOR_PORT": "5050" }
		}
	},
	"inputs": []
}
```
Then restart VS Code. The MCP server will be spawned on demand by Toolsets, keeping resource usage minimal.

Notes:
- Ensure the HTTP API is running (see Usage above). The MCP server simply proxies to it.
- Because MCP uses stdio, you do not need systemd for it; your client will spawn it on demand, keeping resource usage minimal.

Configure
---------
- -p/--port CLI flag takes precedence.
- PORT or INSPECTOR_PORT env var can change the port.
- Binding is restricted to 127.0.0.1 by default.

Copilot Agent Mode
------------------
- Use the VS Code extension to auto-register tools when supported by your VS Code/Copilot build (e.g., `pi.health`, `pi.systemInfo`).
- Alternatively, register http://127.0.0.1:5050/openapi.json as a tool spec so the agent can call `/health`, `/cpu-temp`, `/system-info` directly.

OpenAPI tool registration (generic agent example):
```json
{
	"tools": [
		{
			"name": "pi-inspector",
			"type": "openapi",
			"openapi": { "url": "http://127.0.0.1:5050/openapi.json" },
			"server": { "url": "http://127.0.0.1:5050" },
			"auth": { "type": "none" }
		}
	]
}
```
Notes:
- Ensure the API is running locally and only bound to 127.0.0.1.
- Many agent platforms accept an OpenAPI tool source; adapt the field names to your platform’s schema.

VS Code Extension
-----------------
- Build/package in `extensions/pi-inspector` and install the `.vsix`.
- Commands available via the Command Palette:
	- Pi Inspector: Health (`piInspector.health`)
	- Pi Inspector: Capabilities (`piInspector.capabilities`)
- Configuration: `piInspector.port` (defaults to 5050)

Copilot Chat participant (@PiInspector)
--------------------------------------
- After installing the VSIX, you can type `@PiInspector` in Copilot Chat and ask: `capabilities`, `health`, `cpu temp`, or `system info`.
- If it doesn’t appear, check the extension Output channel for a note about chat API availability.

Install from VSIX
-----------------
1. Open VS Code and go to the Extensions view (Ctrl/Cmd+Shift+X).
2. Click the “…” menu, then “Install from VSIX…”.
3. Pick `pi-inspector-<version>.vsix` from `extensions/pi-inspector/`.
4. Reload if prompted.
