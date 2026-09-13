import sys
import io
from contextlib import redirect_stdout

import pytest

from components import MCPServer as mcp_mod

try:
    import mcp as _mcp
    MCP_PRESENT = True
except Exception:
    MCP_PRESENT = False

pytestmark = pytest.mark.skip(
    reason="旧 mcp API 已移除（_init_server/_MCP_AVAILABLE 等），待按 feat/node 新 API 重写"
)


class TestMCPServer:
    def test_main_exits_when_mcp_unavailable(self):
        # Ensure main() exits with code 1 and prints helpful message when mcp is missing
        orig_available = getattr(mcp_mod, "_MCP_AVAILABLE", None)
        mcp_mod._MCP_AVAILABLE = False
        orig_argv = sys.argv[:]
        sys.argv = ["autocom-mcp"]
        buf = io.StringIO()
        with redirect_stdout(buf):
            with pytest.raises(SystemExit) as exc_info:
                mcp_mod.main()
        assert exc_info.value.code == 1
        out = buf.getvalue()
        assert "mcp 库未安装" in out
        # restore
        mcp_mod._MCP_AVAILABLE = orig_available
        sys.argv = orig_argv

    @pytest.mark.asyncio
    async def test_run_stdio_exits_when_mcp_unavailable(self):
        orig_available = getattr(mcp_mod, "_MCP_AVAILABLE", None)
        mcp_mod._MCP_AVAILABLE = False
        server = mcp_mod.AutoComMCPServer()
        with pytest.raises(SystemExit) as exc_info:
            await server.run_stdio()
        assert exc_info.value.code == 1
        mcp_mod._MCP_AVAILABLE = orig_available

    @pytest.mark.skipif(not MCP_PRESENT, reason="mcp not installed in test environment")
    def test_init_server_creates_mcp_server(self):
        # When mcp is available, _init_server should return an MCP Server instance
        server = mcp_mod.AutoComMCPServer()
        mcp_server = server._init_server()
        # Try to import MCP Server type and assert instance
        from mcp.server import Server as MCPServerType
        assert isinstance(mcp_server, MCPServerType)
        # Should have a callable to create initialization options
        assert callable(getattr(mcp_server, "create_initialization_options", None))
