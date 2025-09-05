"""
All-in-one MCP server that embeds the local API lifecycle.

Behavior:
- Finds an available localhost port (prefers --port if free, else picks ephemeral).
- Starts the inspector API in-process (quiet) bound to that port using a WSGI server.
- Waits for /health to succeed.
- Runs the MCP stdio server (no unsolicited stdout) proxying to the embedded API.
- On shutdown/exit, stops the embedded API server cleanly.

Notes:
- Absolutely avoid printing to stdout; use stderr for rare diagnostics.
- Designed for VS Code Copilot MCP which launches over stdio.
"""
from __future__ import annotations

import argparse
import os
import socket
import threading
import sys
import time
import urllib.error
import urllib.request
from typing import Optional

from .mcp_server import StdioJsonRpc, McpHandler
from .__main__ import create_app
from werkzeug.serving import make_server


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _pick_port(preferred: Optional[int] = None) -> int:
    if preferred and preferred > 0 and _port_is_free(preferred):
        return preferred
    # Ask OS for an ephemeral free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_health(base_url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{base_url}/health", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:  # nosec B310 (local-only)
                if resp.status == 200:
                    return True
        except Exception as e:  # noqa: BLE001 - keep minimal deps/logging
            last_err = e
            time.sleep(0.2)
    if last_err:
        try:
            sys.stderr.write(f"[inspector-raspi-mcp-all] Health check failed: {last_err}\n")
            sys.stderr.flush()
        except Exception:
            pass
    return False


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="All-in-one MCP for inspector-raspi (spawns API + serves MCP over stdio)")
    p.add_argument("--port", type=int, default=int(os.getenv("INSPECTOR_PORT", os.getenv("PORT", 5051))), help="Preferred API port to bind (if busy, a free port will be chosen)")
    p.add_argument("--no-wait", action="store_true", help="Do not wait for /health before starting MCP (not recommended)")
    args = p.parse_args(argv)

    api_port = _pick_port(args.port)
    base_url = f"http://127.0.0.1:{api_port}"

    # Start API in-process via a WSGI server; suppress noisy logs.
    app = create_app()
    try:
        # Reduce werkzeug logging
        import logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
    except Exception:
        pass
    try:
        server = make_server('127.0.0.1', api_port, app)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[inspector-raspi-mcp-all] Failed to bind API: {e}\n")
        sys.stderr.flush()
        return 1

    def _serve():
        try:
            server.serve_forever()
        except Exception:
            pass

    api_thread = threading.Thread(target=_serve, name="inspector-api", daemon=True)
    api_thread.start()

    # Optionally wait for health
    ok = True if args.no_wait else _wait_health(base_url, timeout=10.0)
    if not ok:
        # Continue anyway; MCP calls will surface errors. Don't emit to stdout.
        pass

    handler = McpHandler(base_url)
    rpc = StdioJsonRpc(sys.stdin.buffer, sys.stdout.buffer)
    exit_code = 0
    try:
        rpc.serve(handler)
    except KeyboardInterrupt:
        exit_code = 0
    except Exception as e:  # noqa: BLE001
        try:
            sys.stderr.write(f"[inspector-raspi-mcp-all] MCP server error: {e}\n")
            sys.stderr.flush()
        except Exception:
            pass
        exit_code = 1
    finally:
        # Stop embedded API server
        try:
            server.shutdown()
        except Exception:
            pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
