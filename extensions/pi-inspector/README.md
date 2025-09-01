Pi Inspector VS Code Extension
==============================

If you’re building apps that run on a Raspberry Pi, this extension can help. It connects VS Code (and GitHub Copilot Chat/Agent Modes) to a local Raspberry Pi inspector service so Copilot can understand your Pi’s live environment and suggest code that fits your hardware and OS.

How it works
------------
- A local-only API (the “Pi Inspector” service) runs on your Pi and exposes endpoints like `/health`, `/system-info`, and `/cpu-temp` at `http://127.0.0.1:<port>`.
- This extension calls that API and optionally registers lightweight tools for Copilot Agent Mode so the model can query your Pi’s capabilities and environment on demand.

Quick start
-----------
1. Start the API on your Pi:
   - Run `inspector-raspi` (defaults to 127.0.0.1:5050). Use `-p PORT` to override.
2. Install the extension:
   - Build and package here, then install the generated `.vsix`, or install from a marketplace if available.
3. Use the commands (Command Palette):
   - Pi Inspector: Health (`piInspector.health`)
   - Pi Inspector: Capabilities (`piInspector.capabilities`)

Install from VSIX
-----------------
1. Open VS Code and go to the Extensions view (Ctrl/Cmd+Shift+X).
2. Click the “…” menu in the Extensions view and choose “Install from VSIX…”.
3. Select the packaged file: `pi-inspector-<version>.vsix`.
4. Reload the window if prompted.

Use with GitHub Copilot
-----------------------
- Copilot Chat: Ask it to “call Pi Inspector health” or “fetch Pi capabilities” after activating the extension; results are printed to the Output channel and surfaced as tool responses where supported.
- Copilot Agent Mode: The extension attempts to register tools (e.g., `pi.health`, `pi.systemInfo`) via the VS Code Language Model API when available. As an alternative, you can register the OpenAPI tool at `http://127.0.0.1:5050/openapi.json` so the agent can call `/system-info`, `/cpu-temp`, etc.

Configuration
-------------
- `piInspector.port` (number): Local port of the Pi Inspector API (default 5050).

Notes
-----
- The API binds to loopback (127.0.0.1) by default for privacy. To allow remote access, override host/port explicitly and consider your network security.
- If your VS Code build doesn’t expose the LM Tools API, the extension still works via its commands; you can also wire the OpenAPI spec directly into your Copilot Agent configuration.