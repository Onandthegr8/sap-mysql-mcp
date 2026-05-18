# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A **remote MCP server** that connects Claude AI (Desktop and claude.ai) to a MySQL SAP ERP database via HTTP + SSE transport. It exposes 31 tools that let Claude query and manage materials, vendors, purchase orders, inventory, and activity logs.

- **Local access**: Claude Desktop connects to `http://localhost:8000/sse`
- **Remote access**: Friends/colleagues connect via an ngrok tunnel (`https://xxxx.ngrok-free.app/sse`)
- **claude.ai access**: Add the ngrok URL as a custom connector at `claude.ai/customize/connectors`

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Create the activity_log table (first-time setup or after reset)
python create_log_table.py

# Start the MCP server (blocks; Ctrl+C to stop)
python server.py

# Run the full test suite (DB + all tool functions + /health endpoint)
# Run without server for tool tests only; run with server running for health check too
python test_server.py

# One-click launch: server + ngrok + URL fetcher in 3 separate PowerShell windows
start.bat
```

## Architecture

### Request Flow
```
Claude (Desktop / claude.ai)
  -> SSE connection to GET /sse
  -> Tool call via POST /messages/
  -> FastMCP dispatches to async tool function
  -> asyncio.to_thread() wraps sync MySQL pool call
  -> Result string returned to Claude
```

### Key Files
| File | Role |
|---|---|
| `server.py` | Entry point. Creates `FastMCP` instance, registers all tool modules, runs `mcp.run(transport="sse")`. DB pool is initialised with `asyncio.run(initialize_pool())` **before** `mcp.run()` creates its own event loop. |
| `database.py` | MySQL connection pool (`mysql-connector-python`). All DB ops are sync but wrapped in `asyncio.to_thread()`. Pool is lazily created with a double-checked `asyncio.Lock()`. Use `execute_query(sql, params)` for SELECTs and `execute_write(sql, params)` for INSERT/UPDATE/DELETE. |
| `config.py` | All settings loaded from `.env` via `python-dotenv`. Import named constants from here — never call `os.getenv` directly elsewhere. |
| `auth.py` | Starlette `BaseHTTPMiddleware` for API key auth. Auth is **disabled** (with a warning) when `API_KEY` is empty in `.env`. |
| `create_log_table.py` | Creates the `activity_log` table. Called at server startup via `ensure_log_table()`. Also runnable standalone. |

### Tool Module Pattern
Each `tools/*.py` file exports a single `register_tools(mcp: FastMCP)` function that defines all its tools as nested `async` functions decorated with `@mcp.tool()`. This avoids circular imports — `server.py` owns the `mcp` instance and passes it in.

Every tool module also defines a local `_fmt_table(headers, rows)` helper that renders bordered ASCII tables. This is intentionally duplicated across modules (not centralised) to keep each module self-contained.

### Database Tables
| Table | Primary Key | Notes |
|---|---|---|
| `materials` | `material_id` VARCHAR | Unit prices in USD |
| `vendors` | `vendor_id` VARCHAR | Contact is email or phone |
| `purchase_orders` | `po_number` VARCHAR | FKs to vendors + materials; `total_value` = qty × unit_price; status: OPEN / CLOSED / PENDING |
| `inventory` | `(material_id, plant_code)` composite | `available` = stock_quantity − reserved_quantity (calculated, not stored) |
| `activity_log` | `log_id` AUTO_INCREMENT | Session + command audit trail; `duration` in milliseconds |

## Adding a New Tool

1. Add the async function inside `register_tools()` in the appropriate `tools/*.py` file, decorated with `@mcp.tool()`.
2. Write a detailed docstring — FastMCP sends this to Claude as the tool description.
3. Call only `execute_query` or `execute_write` from `database.py` for all DB access.
4. If the tool goes in a new file, create `tools/newmodule.py` with a `register_tools(mcp)` function, then import and call it in `server.py`.
5. Update the tool count in `server.py`'s `logger.info("Registered N MCP tools...")` line.
6. Add a test case in `test_server.py`.

## Windows-Specific Notes

- All terminal-output strings must use **ASCII only** (`->` not `→`, `[!]` not `⚠️`). Windows `cp1252` encoding raises `UnicodeEncodeError` on non-ASCII characters in print/logging output.
- The server runs fine on Python 3.14 (Windows). The `asyncio.Lock()` at module level is safe in 3.10+.

## Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL host |
| `DB_PORT` | `3306` | MySQL port |
| `DB_USER` | `root` | MySQL user |
| `DB_PASSWORD` | `1234` | MySQL password |
| `DB_NAME` | `sap_erp` | Database name |
| `DB_POOL_SIZE` | `5` | Connection pool size |
| `MCP_PORT` | `8000` | SSE server port |
| `API_KEY` | _(empty)_ | Leave empty to disable auth in dev; set a secret string to enable |

## Claude Desktop Config

Location: `C:\Users\anand\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "sap-database": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

Restart Claude Desktop after editing this file.
