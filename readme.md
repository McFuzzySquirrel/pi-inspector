Raspberry Pi Inspector
======================

Local-only Flask API exposing Raspberry Pi environment details for Copilot Agent Mode.

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
- Register http://127.0.0.1:5050/openapi.json as a tool spec.
- Tools:
  - GET /health
  - GET /cpu-temp
  - GET /system-info
