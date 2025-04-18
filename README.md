# mcp-server-demo

A collection of standalone [Model Context Protocol](https://modelcontextprotocol.io) server examples built with the Python [FastMCP](https://github.com/modelcontextprotocol/python-sdk) SDK. Each file at the repo root is an independent server illustrating a different slice of the API.

## Requirements

- Python **3.13** (see `.python-version`)
- [uv](https://docs.astral.sh/uv/) for dependency management

## Setup

```bash
uv sync
```

## The servers

| File | What it shows |
| --- | --- |
| `server.py` | Minimal "Demo" server: one `add` tool, one dynamic `greeting://{name}` resource. The smallest end-to-end example. |
| `comprehensive_server.py` | Lifespan management with a typed dataclass context, static + dynamic resources, sync/async tools, progress reporting via `Context`, and prompt templates (string and message-list forms). |
| `node_mcp_server.py` | Large Node.js project-assistant server (~2500 lines). Tools for scaffolding TypeScript/Next.js projects, creating React components, generating Jest tests, ESLint/Prettier setup, Docker scaffolding, npm operations, performance tests, and TS conversion. |
| `node_mcp_server_minimal.py` | Stripped-down sanity-check variant of the Node.js server with just one tool and one resource. |

## Running

Each server speaks MCP over stdio when run directly:

```bash
uv run python server.py
uv run python comprehensive_server.py
uv run python node_mcp_server.py
```

For interactive development, use the FastMCP CLI to launch the MCP Inspector:

```bash
uv run mcp dev server.py
```

To register a server with Claude Desktop:

```bash
uv run mcp install server.py
```

> **Note:** the `dependencies=[...]` argument to `FastMCP(...)` (used by `node_mcp_server.py` for `httpx`) only applies to the isolated environment that `mcp install` creates. For `uv run`, runtime deps live in `pyproject.toml` — already set up here via `uv sync`.

## Project layout

```
.
├── server.py                       # minimal demo
├── comprehensive_server.py         # lifespan / context / progress / prompts
├── node_mcp_server.py              # full Node.js project assistant
├── node_mcp_server_minimal.py      # minimal Node.js sanity-check variant
├── pyproject.toml                  # uv project, depends on mcp[cli] + httpx
└── uv.lock
```

The four servers share no code — each is self-contained.
