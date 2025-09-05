MCP-first Pi Inspector – Proposal
=================================

Goal
----
Make MCP the default, lightweight way for Copilot Agent Mode and custom chats to consider live Raspberry Pi capabilities during development on-device.

Why MCP-first
-------------
- Portable across editors/agents, not tied to VS Code APIs.
- Auto-launches on demand (stdio), zero resident footprint when idle.
- Simple, stable contract: small set of tools (pi.health, pi.cpuTemp, pi.systemInfo, pi.capabilities).

Planned improvements
--------------------
1) Tool coverage and schemas
   - Add minimal JSON Schemas to tools for better argument validation.
   - Add `pi.gpuInfo` and `pi.cameraInfo` (summaries extracted from /system-info) as read-only tools.
2) Performance & resilience
   - Tighten timeouts and degrade gracefully (return partials with reason fields).
   - Cache expensive probes per-process for a few seconds (e.g., pip list).
3) Security & privacy
   - Double-check masking of serials and network identifiers.
   - Keep binding strictly to 127.0.0.1; document security posture.
4) Developer UX
   - Add a one-liner installer snippet to create user MCP config.
   - Provide a VS Code Task/Command to restart the API quickly.
5) Documentation
   - Consolidate a “Developing on your Pi with MCP” quick guide.
   - Troubleshooting: common errors (connection refused, missing API), and fixes.

Acceptance criteria
-------------------
- With only inspector-raspi (API) running and VS Code Toolsets MCP configured, a new Copilot Chat:
  - Can call pi.capabilities automatically without prompts (with auto-config enabled).
  - Produces answers that respect the live capability booleans (no libcamera if absent, etc.).
- Roundtrip script covers all tools and prints concise results.

Open questions
--------------
- Should we expose installation helpers as tools (e.g., pi.install.ffmpeg)? Likely no; keep read-only.
- Do we need a “thin cache” layer in the MCP server or rely on API to cache?

Next steps
----------
- [ ] Add schemas and two new tools (gpuInfo, cameraInfo).
- [ ] Add short-lived cache in API for pip list and lsusb.
- [ ] Add docs: MCP quick guide + VS Code settings to auto-config.
- [ ] Optional: VS Code command to open mcp.json for editing and validate path.
