"""
Generic SQL executor tool.

Gives Claude one flexible tool to run any MySQL query it generates,
instead of being limited to the 31 hardcoded tools.

  - SELECT / SHOW / DESCRIBE  -> returns rows as a formatted table
  - INSERT / UPDATE / DELETE   -> returns affected row count
  - Any other DDL (CREATE etc) -> returns status message
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Table formatter ───────────────────────────────────────────────────────────

def _fmt_table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "(no rows returned)"
    cols = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    sep  = "+" + "+".join("-" * (c + 2) for c in cols) + "+"
    head = "|" + "|".join(f" {str(h):<{cols[i]}} " for i, h in enumerate(headers)) + "|"
    lines = [sep, head, sep]
    for row in rows:
        lines.append("|" + "|".join(f" {str(v):<{cols[i]}} " for i, v in enumerate(row)) + "|")
    lines.append(sep)
    return "\n".join(lines)


# ── Query type detector ───────────────────────────────────────────────────────

_READ_RE  = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.IGNORECASE)
_WRITE_RE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE)\b",      re.IGNORECASE)


# ── Tool registration ─────────────────────────────────────────────────────────

def register_tools(mcp):

    @mcp.tool()
    async def execute_sql(query: str) -> str:
        """
        Execute any MySQL query against the SAP ERP database and return the result.

        Use this tool when the user asks for anything that doesn't map to an
        existing specific tool — Claude generates the appropriate SQL and runs it here.

        - SELECT / SHOW / DESCRIBE  -> returns a formatted table of results
        - INSERT / UPDATE / DELETE  -> returns the number of affected rows
        - Other DDL (CREATE, ALTER) -> returns a status message

        Args:
            query: A valid MySQL query string. Do NOT include a trailing semicolon.

        Examples:
            SELECT * FROM purchase_orders WHERE status = 'OPEN'
            UPDATE vendors SET city = 'Mumbai' WHERE vendor_id = 'V-002'
            INSERT INTO materials (material_id, material_name, unit, material_group, price)
              VALUES ('MAT-010', 'Copper Wire', 'KG', 'Electrical', 320.00)
            DELETE FROM inventory WHERE stock_quantity = 0
            SHOW TABLES
            DESCRIBE purchase_orders
        """
        from database import execute_query, execute_write

        query = query.strip().rstrip(";")

        if not query:
            return "Error: empty query."

        try:
            if _READ_RE.match(query):
                rows_raw = await execute_query(query)
                if not rows_raw:
                    return "Query returned 0 rows."
                headers = list(rows_raw[0].keys())
                rows    = [[row[h] for h in headers] for row in rows_raw]
                result  = _fmt_table(headers, rows)
                return f"{len(rows_raw)} row(s) returned:\n\n{result}"

            elif _WRITE_RE.match(query):
                affected = await execute_write(query)
                return f"Success. {affected} row(s) affected."

            else:
                # DDL or other statement — run as write (no result set)
                affected = await execute_write(query)
                return f"Statement executed successfully. {affected} row(s) affected."

        except Exception as exc:
            logger.error(f"execute_sql error | query: {query} | {exc}")
            return f"Error executing query: {exc}"
