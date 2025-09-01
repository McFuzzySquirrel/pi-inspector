Pi Inspector VS Code Extension
==============================

This extension helps wire GitHub Copilot Agent Mode to the local Pi Inspector API.

Setup
-----
1. Ensure the API is running: `inspector-raspi` (defaults to 127.0.0.1:5050).
2. In this folder, run:
   - npm install
   - npm run build
3. Use the Command Palette and run:
   - "Pi Inspector: Health" (command id: `piInspector.health`)
   - "Pi Inspector: Capabilities" (command id: `piInspector.capabilities`)

Copilot Agent Mode
------------------
- Register the OpenAPI tool URL `http://127.0.0.1:5050/openapi.json` with your Copilot Agent profile.
- The agent can then call `/system-info`, `/cpu-temp`, etc.

Configuration
-------------
- Setting: `piInspector.port` (default 5050)