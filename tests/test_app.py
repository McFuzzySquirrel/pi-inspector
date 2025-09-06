import pytest

# This repository now provides a stdio-only MCP server.
# The legacy HTTP API and its Flask app have been removed.
pytest.skip("HTTP API deprecated; skipping legacy tests", allow_module_level=True)