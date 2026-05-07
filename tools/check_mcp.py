import sys, traceback
print('PYTHON', sys.executable)
try:
    import mcp
    print('MCP OK', getattr(mcp, '__file__', None), getattr(mcp, '__version__', None))
except Exception as e:
    print('IMPORT_MCP_ERROR', e)
    traceback.print_exc()
try:
    import mcp.server
    print('MCP.SERVER OK', mcp.server)
except Exception as e:
    print('IMPORT_MCP.SERVER_ERROR', e)
    traceback.print_exc()
print('\nSYS.PATH:')
for p in sys.path:
    print('  ', p)
