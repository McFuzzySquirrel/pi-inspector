Raspberry Pi Inspector
======================

If you’re looking to build applications that run on a Raspberry Pi, this can help. It’s a local-only API and a VS Code extension that let GitHub Copilot Chat and Agent Modes understand your Pi’s live environment so suggestions align with your actual hardware and OS.

What’s inside
-------------
- A Flask API (loopback-only by default) exposing endpoints like `/health`, `/system-info`, `/cpu-temp`, and an OpenAPI spec.
- A VS Code extension that calls the API and optionally registers tools for Copilot Agent Mode.

Usage
-----
1. Create a venv and install deps:
	- python3 -m venv .venv
	- source .venv/bin/activate
	- pip install -e .

2. Run the server (loopback only):
	- inspector-raspi
	- inspector-raspi -p 5052  # override port via CLI

3. Call endpoints:
	- http://127.0.0.1:5050/health
	- http://127.0.0.1:5050/cpu-temp
	- http://127.0.0.1:5050/system-info
	- http://127.0.0.1:5050/openapi.json

Configure
---------
- -p/--port CLI flag takes precedence.
- PORT or INSPECTOR_PORT env var can change the port.
- Binding is restricted to 127.0.0.1 by default.

Copilot Agent Mode
------------------
- Use the VS Code extension to auto-register tools when supported by your VS Code/Copilot build (e.g., `pi.health`, `pi.systemInfo`).
- Alternatively, register http://127.0.0.1:5050/openapi.json as a tool spec so the agent can call `/health`, `/cpu-temp`, `/system-info` directly.

VS Code Extension
-----------------
- Build/package in `extensions/pi-inspector` and install the `.vsix`.
- Commands available via the Command Palette:
	- Pi Inspector: Health (`piInspector.health`)
	- Pi Inspector: Capabilities (`piInspector.capabilities`)
- Configuration: `piInspector.port` (defaults to 5050)

Install from VSIX
-----------------
1. Open VS Code and go to the Extensions view (Ctrl/Cmd+Shift+X).
2. Click the “…” menu, then “Install from VSIX…”.
3. Pick `pi-inspector-<version>.vsix` from `extensions/pi-inspector/`.
4. Reload if prompted.
