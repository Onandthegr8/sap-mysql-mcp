"""
SAP ERP Remote MCP Server — SSE transport
==========================================
Exposes 31 MCP tools over HTTP+SSE so Claude Desktop and claude.ai can call them.

Run:
    python server.py

Endpoints (after server starts):
    GET  /sse       — MCP Server-Sent Events stream  (connect here)
    POST /messages/ — MCP JSON-RPC messages
    GET  /health    — Health check (plain HTTP)
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastmcp import FastMCP

from config import ENVIRONMENT, LOG_LEVEL, MCP_HOST, MCP_PORT
from database import initialize_pool, close_pool

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── FastMCP instance ──────────────────────────────────────────────────────────
mcp = FastMCP(
    "SAP ERP MCP Server",
    instructions=(
        "You are connected to a SAP ERP MySQL database. "
        "The user has full admin rights and has authorized you to execute ALL SQL operations directly — "
        "including SELECT, INSERT, UPDATE, DELETE, ALTER TABLE, DROP, CREATE, and any other DDL/DML. "
        "NEVER ask the user to run SQL themselves. ALWAYS use the execute_sql tool to run queries directly. "
        "For any database request — schema changes, data changes, queries, anything — "
        "generate the correct MySQL query and execute it immediately using execute_sql. "
        "Present results in a clear, structured format. "
        "Format monetary values with 2 decimal places and a $ prefix."
    ),
)

# ── Register all 31 tools ────────────────────────────────────────────────────
from tools.sql_executor import register_tools as _reg_sql_executor

_reg_sql_executor(mcp)

logger.info("Registered 1 MCP tool: execute_sql.")


# ── Startup banner ────────────────────────────────────────────────────────────
def _print_banner() -> None:
    print("\n" + "=" * 62)
    print("  SAP ERP MCP Server  -  RUNNING  (SSE transport)")
    print("=" * 62)
    print(f"  SSE Endpoint   :  http://localhost:{MCP_PORT}/sse")
    print(f"  Environment    :  {ENVIRONMENT}")
    print()
    print("  -- ngrok (public access) --")
    print("  Run in another terminal:  ngrok http 8000")
    print("  Then paste the https URL + /sse into:")
    print("  claude.ai -> Customize -> Connectors -> Add custom connector")
    print("=" * 62 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Step 1: initialise DB pool (sync wrapper around async init)
    logger.info("Initialising database connection pool...")
    try:
        asyncio.run(initialize_pool())
    except Exception as exc:
        logger.error(f"Failed to connect to database: {exc}")
        logger.error("Check DB credentials in .env and ensure MySQL is running.")
        sys.exit(1)

    # Step 1b: ensure activity_log table exists (idempotent)
    logger.info("Ensuring activity_log table exists...")
    try:
        from create_log_table import ensure_log_table
        asyncio.run(ensure_log_table())
    except Exception as exc:
        logger.warning(f"Could not ensure activity_log table: {exc}")

    # Step 2: print banner
    _print_banner()

    # Step 3: start MCP SSE server (blocks until Ctrl+C)
    logger.info(f"Starting SSE server on {MCP_HOST}:{MCP_PORT} ...")
    try:
        mcp.run(transport="sse", host=MCP_HOST, port=MCP_PORT)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        asyncio.run(close_pool())
        logger.info("Server stopped.")
