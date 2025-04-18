# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project shape

A collection of standalone **FastMCP** server demos in Python (`mcp[cli]>=1.6.0` + `httpx`, Python 3.13, uv-managed). There is no single application — each top-level `*.py` is an independent MCP server. They share no internal modules, so changes in one file do not affect the others.

Dependency manager is **uv**; lockfile is `uv.lock`. There is no test suite, linter, or build step configured.

## Common commands

Run a server directly (each file's `__main__` calls `mcp.run()`, stdio transport):

```bash
uv run python server.py
uv run python comprehensive_server.py
uv run python node_mcp_server.py
uv run python node_mcp_server_minimal.py
```

Use the FastMCP CLI for development (inspector UI) or to install into Claude Desktop:

```bash
uv run mcp dev server.py       # launches the MCP Inspector against this server
uv run mcp install server.py   # registers the server with Claude Desktop
```

Dependency management:

```bash
uv sync                        # install from uv.lock
uv add <package>               # add a runtime dep (then re-sync)
```

Note: the `dependencies=[...]` argument to `FastMCP(...)` is only consumed by `mcp install` (Claude Desktop's isolated env). For plain `uv run python <file>.py`, runtime deps must be in `pyproject.toml`. Currently only `httpx` is needed beyond `mcp[cli]`.

## Architecture notes (FastMCP patterns to follow)

Each server file follows the same FastMCP recipe; when adding new servers or extending existing ones, match the pattern already in use:

- **Capability registration** is decorator-based on a single `mcp = FastMCP(...)` instance:
  - `@mcp.tool()` — callable tools (sync or `async`). Type hints drive the JSON schema; the docstring is the tool description.
  - `@mcp.resource("scheme://{param}")` — readable resources. URI template params become function params.
  - `@mcp.prompt()` — prompt templates; can return a string or `list[base.Message]` from `mcp.server.fastmcp.prompts.base`.
- **Lifespan + typed context** (see `comprehensive_server.py`, `node_mcp_server.py`): an `@asynccontextmanager` passed to `FastMCP(lifespan=...)` yields a `@dataclass` context. Inside handlers, reach it via the injected `ctx: Context` → `ctx.request_context.lifespan_context`. Resources, which do not take `ctx`, read it via `mcp.request_context.lifespan_context` instead.
- **Progress + logging** in long-running tools: `await ctx.report_progress(done, total)` and `ctx.info(...)` (see `process_data` in `comprehensive_server.py`).

`node_mcp_server.py` is by far the largest file (~2500 lines, ~14 tools for scaffolding TypeScript/Next.js/Docker/ESLint/Jest projects). When working on it, jump to the relevant `@mcp.tool()`/`@mcp.resource()` by name rather than reading top-to-bottom — the tools are independent of one another, and most of the bulk is string templates emitted as generated files. Notable convention: `generate_*` tools return strings of file content for the caller to materialize, while `create_*` tools (e.g. `create_react_component`) write directly to disk under the detected project root.

`node_mcp_server_minimal.py` is a stripped-down sanity-check variant — only one resource and one tool, useful for verifying the FastMCP install works.
