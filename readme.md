Raspberry Pi Inspector
======================
(Note: still rough around the edges, but easy to try.)

If you’re building apps for Raspberry Pi, this gives you a local-only API, a VS Code extension, and an MCP server so Copilot Chat/Agent Modes (and other MCP clients) understand your Pi’s actual hardware/OS.

Two-minute quickstart (VS Code)
-------------------------------
This repo includes ready-to-run tasks and a VSIX.

1) Install (editable) inside a venv
	- Run the VS Code task: “Install (editable)”

2) Start the API quietly in the background
	- Run: “Run Pi Inspector API (5051)”
	- This uses `--quiet` and port 5051 to avoid conflicts; it’s hidden by default.

3) Verify
```bash
curl -s http://127.0.0.1:5051/health
```

4) Use it
	- VS Code extension: install the `.vsix` from `extensions/pi-inspector/`, then run “Pi Inspector: Health” or “Pi Inspector: Capabilities”.
	- Copilot (MCP): Copilot will launch the MCP server on demand; no terminal needed.

Quickstart: MCP (all-in-one, no separate API)
--------------------------------------------
If you only want the MCP and don’t want to run the API separately, use the all-in-one server.

Install (pipx recommended):
```bash
sudo apt-get update && sudo apt-get install -y pipx
pipx ensurepath
pipx install git+https://github.com/McFuzzySquirrel/pi-inspector.git
```

VS Code user MCP config (`~/.config/Code/User/mcp.json`):
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
Reload VS Code; Copilot/Toolsets will auto-launch it when needed.

Optional CLI smoke-test:
```bash
inspector-raspi-mcp-all --port 5051
# In another terminal (repo optional):
python scripts/mcp_roundtrip.py --port 5051 --tool pi-usb-list
```

CLI quickstart (no VS Code required)
------------------------------------
Option A: pipx (isolated)
```bash
pipx install .
inspector-raspi --port 5051 --quiet &
curl -s http://127.0.0.1:5051/health
```

Option B: venv
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
inspector-raspi --port 5051 --quiet &
curl -s http://127.0.0.1:5051/health
```

Optional (systemd-run on demand):
```bash
systemd-run --user --unit=pi-inspector --same-dir ~/.local/bin/inspector-raspi --port 5051 --quiet
```

What’s inside
-------------
- A Flask API (loopback-only by default) exposing endpoints like `/health`, `/system-info`, `/cpu-temp`, and an OpenAPI spec.
- A VS Code extension that calls the API and optionally registers tools for Copilot Agent Mode.
- A minimal MCP (Model Context Protocol) server (stdio) that proxies to the API so non-Copilot agents can use the same tools.
- Agent usage guide: see `docs/copilot-instructions.md` for model-facing guidance and examples.

MCP-first track
---------------
We maintain an "MCP-first" branch focused on making MCP the default integration for local Pi development:

- Branch: `feature/mcp-first`
- Proposal and roadmap: `docs/mcp-first-proposal.md`
- To try it locally:
	```bash
	git switch feature/mcp-first
	```

Usage
-----
Recommended (minimal resources, on-demand): VS Code tasks or pipx

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
systemd-run --user --unit=pi-inspector --same-dir ~/.local/bin/inspector-raspi -p 5051
# stop later
systemctl --user stop pi-inspector.service
```

Optional helper scripts:
```bash
mkdir -p ~/.local/bin
cat > ~/.local/bin/pi-inspector-start <<'EOF'
#!/usr/bin/env bash
exec systemd-run --user --unit=pi-inspector --same-dir "$HOME/.local/bin/inspector-raspi" -p 5051
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
curl -s http://127.0.0.1:${PORT:-5051}/health
curl -s http://127.0.0.1:${PORT:-5051}/cpu-temp
curl -s http://127.0.0.1:${PORT:-5051}/system-info | jq .
curl -s http://127.0.0.1:${PORT:-5051}/openapi.json | jq .
```

Alternative ways to run (if you don’t want pipx):
- As a module: `python -m inspector_raspi -p ${PORT:-5051}`
- With a venv:
	```bash
	python3 -m venv .venv
	source .venv/bin/activate
	pip install -e .
	inspector-raspi -p ${PORT:-5051} --quiet
	```

Quiet mode and ports
--------------------
- `--quiet` hides the startup print and reduces Werkzeug logs.
- Default port is 5050. You can change with `--port`, or env vars `INSPECTOR_PORT`/`PORT`.
- In this workspace, VS Code tasks use 5051 by default and set the env so Copilot-launched MCP instances hit the right port.

USB quick checks (hot-plug)
---------------------------
- List devices via MCP: `pi-usb-list` (summary from `lsusb`).
- Watch for changes: `pi-usb-watch` returns current devices plus added/removed since the last call in this session.
	- Optional arg: `{ "reset": true }` to reseed the snapshot.
	- TTL hint ~3s (system info cache), so very fast plug/unplug may take a moment to reflect.

MCP server (portable tools for other agents)
--------------------------------------------
The MCP server is a tiny stdio process that exposes the same tools and proxies them to the local HTTP API. It only runs when a client launches it and is otherwise idle—no background service needed.

- Install (already included when you `pipx install .`): provides `inspector-raspi-mcp` and `inspector-raspi-mcp-all`.
- Tools exposed: `pi-health`, `pi-cpu-temp`, `pi-system-info`, `pi-capabilities`, `pi-gpu-info`, `pi-camera-info`, `pi-usb-list`, `pi-usb-watch`.
	- Note: hyphen-case is the canonical naming; legacy dotted names (e.g., `pi.health`, `pi.usbList`) are accepted as aliases.
- Port selection: `--port 5051` (workspace default) or environment `INSPECTOR_PORT`/`PORT`.

Run a quick smoke (manual):
```bash
# Launch and keep attached (it waits for MCP JSON-RPC messages on stdin)
inspector-raspi-mcp --port 5051
# Press Ctrl+C to exit
```

All-in-one MCP (no separate API process):
```bash
# Spawns the API quietly on a free local port (prefers 5051) and serves MCP over stdio
inspector-raspi-mcp-all --port 5051
# Use in VS Code by pointing the MCP server command to inspector-raspi-mcp-all
```

Example client configuration (Claude Desktop tool window or generic MCP client):
```json
{
	"mcpServers": {
		"pi-inspector": {
			"command": "inspector-raspi-mcp-all",
			"args": ["--port", "5051"],
			"env": { "INSPECTOR_PORT": "5051", "PORT": "5051" }
		}
	}
}
```

Try it (roundtrip test):
```bash
# In one terminal: ensure the HTTP API is running locally on 5051
inspector-raspi -p 5051 --quiet

# In another terminal: run stdio roundtrip tests
python3 scripts/mcp_roundtrip.py --port 5051 --tool pi-system-info
python3 scripts/mcp_roundtrip.py --port 5051 --tool pi-usb-list
python3 scripts/mcp_roundtrip.py --port 5051 --tool pi-usb-watch --args '{"reset": true}' --repeat 2 --sleep 0.5
```

VS Code user-level MCP config (Toolsets):
Create `~/.config/Code/User/mcp.json` with:
```json
{
	"servers": {
		"pi-inspector": {
			"type": "stdio",
			"command": "/home/<user>/.local/bin/inspector-raspi-mcp",
			"args": ["--port", "5051"],
			"env": { "INSPECTOR_PORT": "5051", "PORT": "5051" }
		}
	},
	"inputs": []
}
```
Then restart VS Code. The MCP server will be spawned on demand by Toolsets, keeping resource usage minimal.

No prompts (auto-config)
------------------------
To skip the "auto-configure tools for this chat" banner every time:
- Trust the workspace (Command Palette → "Workspaces: Manage Workspace Trust" → Trust).
- Open Settings and search for "Auto Configure Tools"; set it to Always.
- When the banner appears, choose the "Always auto-configure" or "Don't ask again" option.

Notes:
- Ensure the HTTP API is running (see Usage above). The MCP server simply proxies to it.
- Because MCP uses stdio, you do not need systemd for it; your client will spawn it on demand, keeping resource usage minimal.

Troubleshooting
---------------
- Port already in use: start on a different port (e.g., 5051) or stop the other process.
- No output but API unreachable: ensure it binds to 127.0.0.1 and your curl uses the same port.
- MCP parse warnings or hangs: the server now avoids unsolicited output and auto-detects framing; restart your client if it cached an older binary.
- VS Code extension can’t fetch: check the Output channel “Pi Inspector” for notes about fetch polyfill or port mismatch.

Configure
---------
- API binary (`inspector-raspi`):
	- Flags: `-p/--port`, `-q/--quiet`
	- Env: `INSPECTOR_PORT` or `PORT` to set the port when flags aren’t provided
	- Notes: binds to 127.0.0.1 only; use shell redirection to silence output: `inspector-raspi -p 5051 --quiet >/dev/null 2>&1 &`

- MCP (stdio) proxy (`inspector-raspi-mcp`):
	- Flag: `--port` (API port to call)
	- Env: `INSPECTOR_PORT`/`PORT` (API port), `MCP_HTTP_TIMEOUT` (default 6.0s), `MCP_DEBUG=1` (stderr trace)

- All-in-one MCP (`inspector-raspi-mcp-all`):
	- Flags: `--port` (preferred API port to bind), `--no-wait` (don’t wait on `/health`)
	- Env: `INSPECTOR_PORT`/`PORT` (preferred API port), `MCP_HTTP_TIMEOUT` (default 6.0s), `MCP_DEBUG=1` (stderr trace)
	- Stdout is protocol-only; occasional diagnostics go to stderr. To fully silence: `inspector-raspi-mcp-all --port 5051 >/dev/null 2>&1 &`

How to set env vars (binary installs):
- One-off shell prefix: `INSPECTOR_PORT=5051 MCP_DEBUG=1 inspector-raspi-mcp-all --port 5051`
- Persist for current shell: `export INSPECTOR_PORT=5051; export MCP_HTTP_TIMEOUT=8`
- VS Code Toolsets (MCP) user config (`~/.config/Code/User/mcp.json`):
	```json
	{
		"servers": {
			"pi-inspector": {
				"type": "stdio",
				"command": "/home/<user>/.local/bin/inspector-raspi-mcp-all",
				"args": ["--port", "5051"],
				"env": { "INSPECTOR_PORT": "5051", "MCP_HTTP_TIMEOUT": "8" }
			}
		}
	}
	```
- systemd-run transient (no terminal noise):
	```bash
	systemd-run --user --unit=pi-inspector --same-dir \
		env INSPECTOR_PORT=5051 MCP_HTTP_TIMEOUT=8 \
		~/.local/bin/inspector-raspi-mcp-all --port 5051
	```

Timeouts and performance notes:
- `/system-info` can take a few seconds on a cold run. MCP calls use a 6s default timeout.
- Increase via `MCP_HTTP_TIMEOUT` if you see tool failures on first call.

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
