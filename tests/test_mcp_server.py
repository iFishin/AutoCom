import unittest
import sys
import io
import asyncio
import importlib
from contextlib import redirect_stdout

from components import MCPServer as mcp_mod

try:
    import mcp as _mcp
    MCP_PRESENT = True
except Exception:
    MCP_PRESENT = False


class TestMCPServer(unittest.TestCase):
    def test_main_exits_when_mcp_unavailable(self):
        # Ensure main() exits with code 1 and prints helpful message when mcp is missing
        orig_available = getattr(mcp_mod, "_MCP_AVAILABLE", None)
        mcp_mod._MCP_AVAILABLE = False
        orig_argv = sys.argv[:]
        sys.argv = ["autocom-mcp"]
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(SystemExit) as cm:
                mcp_mod.main()
        self.assertEqual(cm.exception.code, 1)
        out = buf.getvalue()
        self.assertIn("mcp 库未安装", out)
        # restore
        mcp_mod._MCP_AVAILABLE = orig_available
        sys.argv = orig_argv

    def test_run_stdio_exits_when_mcp_unavailable(self):
        orig_available = getattr(mcp_mod, "_MCP_AVAILABLE", None)
        mcp_mod._MCP_AVAILABLE = False
        server = mcp_mod.AutoComMCPServer()
        with self.assertRaises(SystemExit) as cm:
            asyncio.run(server.run_stdio())
        self.assertEqual(cm.exception.code, 1)
        mcp_mod._MCP_AVAILABLE = orig_available

    @unittest.skipIf(not MCP_PRESENT, "mcp not installed in test environment")
    def test_init_server_creates_mcp_server(self):
        # When mcp is available, _init_server should return an MCP Server instance
        server = mcp_mod.AutoComMCPServer()
        mcp_server = server._init_server()
        # Try to import MCP Server type and assert instance
        from mcp.server import Server as MCPServerType
        self.assertIsInstance(mcp_server, MCPServerType)
        # Should have a callable to create initialization options
        self.assertTrue(callable(getattr(mcp_server, "create_initialization_options", None)))


if __name__ == "__main__":
    unittest.main()
