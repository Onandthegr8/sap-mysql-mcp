"""Inventory and stock management tools for the SAP ERP MCP server."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from database import execute_query, execute_write

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)


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


def register_tools(mcp: "FastMCP") -> None:

    @mcp.tool()
    async def get_all_inventory() -> str:
        """
        Retrieve the full inventory / warehouse stock listing.

        Use this when the user asks "show all inventory", "what stock do we have?",
        or wants a warehouse overview across all plants and materials.

        Returns a table with:
            Material ID | Description | Plant | Stock Qty | Reserved | Available | Last Updated
        Available = stock_quantity − reserved_quantity.
        """
        try:
            rows = await execute_query(
                "SELECT i.material_id, m.description, i.plant_code, "
                "i.stock_quantity, i.reserved_quantity, "
                "(i.stock_quantity - i.reserved_quantity) AS available, "
                "i.last_updated "
                "FROM inventory i "
                "JOIN materials m ON i.material_id = m.material_id "
                "ORDER BY i.plant_code, i.material_id"
            )
            if not rows:
                return "No inventory records found."
            data = [
                [
                    r["material_id"], r["description"], r["plant_code"],
                    r["stock_quantity"], r["reserved_quantity"],
                    r["available"], str(r["last_updated"]),
                ]
                for r in rows
            ]
            return (
                f"Inventory — {len(rows)} record(s)\n\n"
                + _fmt_table(
                    ["Material ID", "Description", "Plant", "Stock", "Reserved", "Available", "Updated"],
                    data,
                )
            )
        except Exception as exc:
            logger.error(f"get_all_inventory: {exc}")
            return f"Error retrieving inventory: {exc}"

    @mcp.tool()
    async def check_stock(material_id: str) -> str:
        """
        Check the current stock position for a specific material.

        Use this when the user asks "how much stock of MAT-001 do we have?",
        "is there enough X to fulfil an order?", or wants to see reserved vs available stock.

        Args:
            material_id: Material identifier to look up, e.g. "MAT-001".

        Returns stock_quantity, reserved_quantity, available (= stock − reserved),
        plant code, and last update date for the material.
        """
        try:
            rows = await execute_query(
                "SELECT i.material_id, m.description, i.plant_code, "
                "i.stock_quantity, i.reserved_quantity, "
                "(i.stock_quantity - i.reserved_quantity) AS available, "
                "i.last_updated "
                "FROM inventory i "
                "JOIN materials m ON i.material_id = m.material_id "
                "WHERE i.material_id = %s",
                (material_id.strip(),),
            )
            if not rows:
                return f"No inventory record found for material '{material_id}'."
            r = rows[0]
            available = r["available"]
            warning = "  [!] LOW STOCK\n" if available < 50 else ""
            return (
                f"Stock Check: {r['material_id']} — {r['description']}\n"
                f"  Plant        : {r['plant_code']}\n"
                f"  Stock Qty    : {r['stock_quantity']}\n"
                f"  Reserved     : {r['reserved_quantity']}\n"
                f"  Available    : {available}\n"
                f"{warning}"
                f"  Last Updated : {r['last_updated']}\n"
            )
        except Exception as exc:
            logger.error(f"check_stock: {exc}")
            return f"Error checking stock for '{material_id}': {exc}"

    @mcp.tool()
    async def get_low_stock_items(threshold: int = 100) -> str:
        """
        Find all materials where available stock is below a given threshold.

        Use this for replenishment planning questions like "what needs to be reordered?",
        "show low stock alerts", or "which materials are running out?".

        Args:
            threshold: Items with available stock BELOW this number are returned.
                       Default is 100 units. Example: threshold=50 shows critically low items.

        Returns materials sorted by available stock (lowest first) for prioritised reordering.
        """
        try:
            rows = await execute_query(
                "SELECT i.material_id, m.description, m.material_group, i.plant_code, "
                "i.stock_quantity, i.reserved_quantity, "
                "(i.stock_quantity - i.reserved_quantity) AS available "
                "FROM inventory i "
                "JOIN materials m ON i.material_id = m.material_id "
                "WHERE (i.stock_quantity - i.reserved_quantity) < %s "
                "ORDER BY available ASC",
                (threshold,),
            )
            if not rows:
                return f"No materials with available stock below {threshold} units. All stock levels are healthy."
            data = [
                [
                    r["material_id"], r["description"], r["material_group"],
                    r["plant_code"], r["stock_quantity"], r["reserved_quantity"], r["available"],
                ]
                for r in rows
            ]
            return (
                f"Low Stock Alert (threshold < {threshold}) — {len(rows)} item(s)\n\n"
                + _fmt_table(
                    ["Material ID", "Description", "Group", "Plant", "Stock", "Reserved", "Available"],
                    data,
                )
            )
        except Exception as exc:
            logger.error(f"get_low_stock_items: {exc}")
            return f"Error retrieving low stock items: {exc}"

    @mcp.tool()
    async def get_inventory_by_plant(plant_code: str) -> str:
        """
        Retrieve all inventory records for a specific plant / warehouse location.

        Use this when the user asks "what stock is at plant P001?",
        "show warehouse inventory for Chennai plant", or needs plant-level stock data.

        Args:
            plant_code: Plant / site identifier, e.g. "P001", "P002". Exact match.

        Returns all materials stocked at that plant with quantities.
        """
        try:
            rows = await execute_query(
                "SELECT i.material_id, m.description, m.unit, "
                "i.stock_quantity, i.reserved_quantity, "
                "(i.stock_quantity - i.reserved_quantity) AS available, "
                "i.last_updated "
                "FROM inventory i "
                "JOIN materials m ON i.material_id = m.material_id "
                "WHERE i.plant_code = %s ORDER BY i.material_id",
                (plant_code.strip().upper(),),
            )
            if not rows:
                return f"No inventory found for plant '{plant_code}'."
            data = [
                [
                    r["material_id"], r["description"], r["unit"],
                    r["stock_quantity"], r["reserved_quantity"],
                    r["available"], str(r["last_updated"]),
                ]
                for r in rows
            ]
            return (
                f"Inventory at Plant {plant_code.upper()} — {len(rows)} material(s)\n\n"
                + _fmt_table(
                    ["Material ID", "Description", "Unit", "Stock", "Reserved", "Available", "Updated"],
                    data,
                )
            )
        except Exception as exc:
            logger.error(f"get_inventory_by_plant: {exc}")
            return f"Error retrieving inventory for plant '{plant_code}': {exc}"

    @mcp.tool()
    async def update_stock(material_id: str, new_quantity: int) -> str:
        """
        Update the stock quantity for a material (goods receipt / adjustment).

        Use this when the user says "update stock for MAT-001 to 500 units",
        "we received a shipment of 200 units", or needs to correct inventory levels.
        The last_updated date is automatically set to today.

        Args:
            material_id  : The material whose stock to update (must exist in inventory).
            new_quantity : New total stock quantity. Must be >= 0.

        Returns confirmation with old and new stock levels.
        """
        try:
            if new_quantity < 0:
                return "Error: Stock quantity cannot be negative."

            existing = await execute_query(
                "SELECT stock_quantity, reserved_quantity FROM inventory WHERE material_id = %s",
                (material_id.strip(),),
            )
            if not existing:
                return f"Material '{material_id}' not found in inventory."

            old_qty = existing[0]["stock_quantity"]
            reserved = existing[0]["reserved_quantity"]

            if new_quantity < reserved:
                return (
                    f"Error: New quantity ({new_quantity}) is less than reserved quantity ({reserved}). "
                    f"Cannot set stock below reserved amount."
                )

            today = date.today().isoformat()
            await execute_write(
                "UPDATE inventory SET stock_quantity = %s, last_updated = %s WHERE material_id = %s",
                (new_quantity, today, material_id.strip()),
            )
            delta = new_quantity - old_qty
            delta_str = f"+{delta}" if delta >= 0 else str(delta)
            return (
                f"Stock updated for {material_id}.\n"
                f"  Old Quantity : {old_qty}\n"
                f"  New Quantity : {new_quantity}  ({delta_str})\n"
                f"  Reserved     : {reserved}\n"
                f"  Available    : {new_quantity - reserved}\n"
                f"  Updated      : {today}\n"
            )
        except Exception as exc:
            logger.error(f"update_stock: {exc}")
            return f"Error updating stock for '{material_id}': {exc}"

    @mcp.tool()
    async def get_stock_summary() -> str:
        """
        High-level inventory dashboard with KPIs across the entire warehouse.

        Use this for inventory overview questions like "give me a stock summary",
        "how many unique materials do we stock?", or "what is our total inventory value?".

        Returns:
            Total unique materials stocked, total units, total inventory value
            (stock_quantity × material price), and count of items below reorder point (100 units).
        """
        try:
            summary = await execute_query(
                "SELECT COUNT(*) AS total_items, "
                "SUM(i.stock_quantity) AS total_units, "
                "SUM((i.stock_quantity - i.reserved_quantity)) AS total_available, "
                "SUM(i.stock_quantity * m.price) AS total_value, "
                "SUM(CASE WHEN (i.stock_quantity - i.reserved_quantity) < 100 THEN 1 ELSE 0 END) AS low_stock_count "
                "FROM inventory i JOIN materials m ON i.material_id = m.material_id"
            )
            plants = await execute_query("SELECT COUNT(DISTINCT plant_code) AS plant_count FROM inventory")

            s = summary[0]
            p = plants[0]
            return (
                "Inventory Summary\n"
                "=" * 42 + "\n"
                f"  Unique Materials  : {s['total_items']}\n"
                f"  Plants / Sites    : {p['plant_count']}\n"
                f"  Total Stock Units : {s['total_units'] or 0:,}\n"
                f"  Total Available   : {s['total_available'] or 0:,}\n"
                f"  Total Stock Value : ${float(s['total_value'] or 0):,.2f}\n"
                f"  Low Stock Items   : {s['low_stock_count'] or 0}  (available < 100 units)\n"
            )
        except Exception as exc:
            logger.error(f"get_stock_summary: {exc}")
            return f"Error generating stock summary: {exc}"
