"""
Minimal Node.js MCP Server

A simplified version of the Node.js MCP server with the smallest possible
surface — one resource and one tool — for sanity-checking the FastMCP setup.
"""

from mcp.server.fastmcp import FastMCP, Context

mcp = FastMCP("Node.js Helper")

# =========== RESOURCES ===========

@mcp.resource("node://info")
def get_node_info() -> str:
    """Get information about the Node.js environment"""
    return "Node.js helper is active and ready to use."

# =========== TOOLS ===========

@mcp.tool()
def hello_node(ctx: Context) -> str:
    """Simple test function to verify MCP server is working"""
    return "Hello from Node.js MCP server! The server is working correctly."

# Run the server if executed directly
if __name__ == "__main__":
    mcp.run()