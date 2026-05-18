"""Material master tools for the SAP ERP MCP server."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from database import execute_query, execute_write

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


# ── Shared table formatter ──────────────────────────────────────────────────

def _fmt_table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "(no rows)"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell) if cell is not None else ""))
    sep = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    hdr = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    lines = [sep, hdr, sep]
    for row in rows:
        lines.append(
            "| " + " | ".join(str(c if c is not None else "").ljust(widths[i]) for i, c in enumerate(row)) + " |"
        )
    lines.append(sep)
    return "\n".join(lines)


# ── Tool registration ───────────────────────────────────────────────────────

def register_tools(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def get_all_materials() -> str:
        """
        Retrieve the complete material master catalogue from the SAP ERP system.

        Use this when the user asks to see all materials, wants a product catalogue,
        or needs an overview of what raw materials / spare parts exist in the system.

        Returns a formatted table with columns:
            Material ID | Description | Unit | Group | Price (USD)
        """
        try:
            rows = await execute_query(
                "SELECT material_id, description, unit, material_group, price "
                "FROM materials ORDER BY material_id"
            )
            if not rows:
                return "No materials found in the database."
            data = [
                [r["material_id"], r["description"], r["unit"], r["material_group"], f"${float(r['price']):.2f}"]
                for r in rows
            ]
            return (
                f"Material Master — {len(rows)} record(s)\n\n"
                + _fmt_table(["Material ID", "Description", "Unit", "Group", "Price (USD)"], data)
            )
        except Exception as exc:
            logger.error(f"get_all_materials: {exc}")
            return f"Error retrieving materials: {exc}"

    @mcp.tool()
    async def get_material_by_id(material_id: str) -> str:
        """
        Look up the full details of a single material by its Material ID.

        Use this when the user asks about a specific material, wants to verify it
        exists before creating a Purchase Order, or needs its unit price.

        Args:
            material_id: Unique material identifier, e.g. "MAT-001" or "RAW-STEEL-01".

        Returns detailed fields or a not-found message.
        """
        try:
            rows = await execute_query(
                "SELECT * FROM materials WHERE material_id = %s", (material_id.strip(),)
            )
            if not rows:
                return f"Material '{material_id}' not found."
            r = rows[0]
            return (
                f"Material: {r['material_id']}\n"
                f"  Description   : {r['description']}\n"
                f"  Unit          : {r['unit']}\n"
                f"  Material Group: {r['material_group']}\n"
                f"  Unit Price    : ${float(r['price']):.2f}\n"
            )
        except Exception as exc:
            logger.error(f"get_material_by_id: {exc}")
            return f"Error retrieving material '{material_id}': {exc}"

    @mcp.tool()
    async def search_materials(keyword: str) -> str:
        """
        Search for materials by keyword in their description or material group.

        Use this when the user wants to find materials matching a term,
        e.g. "find all steel materials" or "search for anything packaging-related".

        Args:
            keyword: Case-insensitive search term matched against description and
                     material_group columns. Examples: "steel", "box", "bearing".

        Returns a table of matching materials or a not-found message.
        """
        try:
            rows = await execute_query(
                "SELECT material_id, description, unit, material_group, price "
                "FROM materials WHERE description LIKE %s OR material_group LIKE %s "
                "ORDER BY material_id",
                (f"%{keyword}%", f"%{keyword}%"),
            )
            if not rows:
                return f"No materials found matching '{keyword}'."
            data = [
                [r["material_id"], r["description"], r["unit"], r["material_group"], f"${float(r['price']):.2f}"]
                for r in rows
            ]
            return (
                f"Search results for '{keyword}' — {len(rows)} match(es)\n\n"
                + _fmt_table(["Material ID", "Description", "Unit", "Group", "Price (USD)"], data)
            )
        except Exception as exc:
            logger.error(f"search_materials: {exc}")
            return f"Error searching materials: {exc}"

    @mcp.tool()
    async def get_materials_by_group(group: str) -> str:
        """
        Retrieve all materials belonging to a specific material group.

        Use this when the user wants to filter by category, e.g.
        "show all raw metals" or "list spare parts".

        Args:
            group: Material group name (case-insensitive partial match).
                   Common values: "RAW-METAL", "PACKAGING", "SPARE-PARTS".

        Returns a table of materials in that group.
        """
        try:
            rows = await execute_query(
                "SELECT material_id, description, unit, material_group, price "
                "FROM materials WHERE material_group LIKE %s ORDER BY material_id",
                (f"%{group}%",),
            )
            if not rows:
                return f"No materials found in group '{group}'."
            data = [
                [r["material_id"], r["description"], r["unit"], r["material_group"], f"${float(r['price']):.2f}"]
                for r in rows
            ]
            return (
                f"Materials in group '{group}' — {len(rows)} record(s)\n\n"
                + _fmt_table(["Material ID", "Description", "Unit", "Group", "Price (USD)"], data)
            )
        except Exception as exc:
            logger.error(f"get_materials_by_group: {exc}")
            return f"Error retrieving materials by group: {exc}"

    @mcp.tool()
    async def add_material(
        material_id: str,
        description: str,
        unit: str,
        material_group: str,
        price: float,
    ) -> str:
        """
        Add a new material to the SAP ERP material master.

        Use this when the user wants to create / register a new material in the system.
        The tool checks for duplicate IDs before inserting.

        Args:
            material_id    : Unique identifier for the new material (e.g. "MAT-100").
                             Must not already exist in the database.
            description    : Human-readable name (e.g. "Steel Rod 10mm Dia.").
            unit           : Unit of measure code — KG, PCS, LTR, MTR, etc.
            material_group : Category name — e.g. "RAW-METAL", "PACKAGING", "SPARE-PARTS".
            price          : Unit price in USD (e.g. 25.50). Must be >= 0.

        Returns a success confirmation or an error message.
        """
        try:
            existing = await execute_query(
                "SELECT 1 FROM materials WHERE material_id = %s", (material_id.strip(),)
            )
            if existing:
                return f"Error: Material ID '{material_id}' already exists. Choose a unique ID."
            if price < 0:
                return "Error: Price must be >= 0."

            affected = await execute_write(
                "INSERT INTO materials (material_id, description, unit, material_group, price) "
                "VALUES (%s, %s, %s, %s, %s)",
                (material_id.strip(), description.strip(), unit.strip(), material_group.strip(), round(price, 2)),
            )
            if affected:
                return (
                    f"Material added successfully.\n"
                    f"  Material ID   : {material_id}\n"
                    f"  Description   : {description}\n"
                    f"  Unit          : {unit}\n"
                    f"  Material Group: {material_group}\n"
                    f"  Price         : ${price:.2f}\n"
                )
            return "Insert failed — no rows affected."
        except Exception as exc:
            logger.error(f"add_material: {exc}")
            return f"Error adding material: {exc}"
