"""Purchase order tools for the SAP ERP MCP server."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from database import execute_query, execute_write

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = logging.getLogger(__name__)

VALID_STATUSES = {"OPEN", "CLOSED", "PENDING"}


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
    async def get_all_purchase_orders() -> str:
        """
        Retrieve all purchase orders with vendor names and material descriptions joined.

        Use this when the user wants a complete list of POs, asks "show me all purchase
        orders", or needs an overview of procurement activity.

        Returns a table:
            PO Number | Vendor Name | Material Desc | Qty | Unit Price | Total | Status | Date
        """
        try:
            rows = await execute_query(
                "SELECT p.po_number, v.vendor_name, m.description AS material, "
                "p.quantity, p.unit_price, p.total_value, p.status, p.order_date "
                "FROM purchase_orders p "
                "JOIN vendors v ON p.vendor_id = v.vendor_id "
                "JOIN materials m ON p.material_id = m.material_id "
                "ORDER BY p.order_date DESC, p.po_number"
            )
            if not rows:
                return "No purchase orders found."
            data = [
                [
                    r["po_number"], r["vendor_name"], r["material"],
                    r["quantity"], f"${float(r['unit_price']):.2f}",
                    f"${float(r['total_value']):.2f}", r["status"],
                    str(r["order_date"]),
                ]
                for r in rows
            ]
            return (
                f"Purchase Orders — {len(rows)} total\n\n"
                + _fmt_table(
                    ["PO Number", "Vendor", "Material", "Qty", "Unit Price", "Total Value", "Status", "Date"],
                    data,
                )
            )
        except Exception as exc:
            logger.error(f"get_all_purchase_orders: {exc}")
            return f"Error retrieving purchase orders: {exc}"

    @mcp.tool()
    async def get_open_purchase_orders() -> str:
        """
        Retrieve only OPEN (pending fulfilment) purchase orders.

        Use this when the user asks "what orders are still open?",
        "show outstanding POs", or "what are we waiting to receive?".

        Returns a table of POs with status = OPEN, sorted by date.
        """
        try:
            rows = await execute_query(
                "SELECT p.po_number, v.vendor_name, m.description AS material, "
                "p.quantity, p.unit_price, p.total_value, p.order_date "
                "FROM purchase_orders p "
                "JOIN vendors v ON p.vendor_id = v.vendor_id "
                "JOIN materials m ON p.material_id = m.material_id "
                "WHERE p.status = 'OPEN' ORDER BY p.order_date"
            )
            if not rows:
                return "No OPEN purchase orders found."
            data = [
                [
                    r["po_number"], r["vendor_name"], r["material"],
                    r["quantity"], f"${float(r['unit_price']):.2f}",
                    f"${float(r['total_value']):.2f}", str(r["order_date"]),
                ]
                for r in rows
            ]
            return (
                f"Open Purchase Orders — {len(rows)} pending\n\n"
                + _fmt_table(
                    ["PO Number", "Vendor", "Material", "Qty", "Unit Price", "Total Value", "Date"],
                    data,
                )
            )
        except Exception as exc:
            logger.error(f"get_open_purchase_orders: {exc}")
            return f"Error retrieving open POs: {exc}"

    @mcp.tool()
    async def get_po_by_number(po_number: str) -> str:
        """
        Look up the full details of a single purchase order by its PO number.

        Use this when the user references a specific PO, asks "what is PO-2024-001?",
        or wants to check the status / value of a particular order.

        Args:
            po_number: The purchase order number, e.g. "PO-2024-001".

        Returns all PO fields with joined vendor and material names.
        """
        try:
            rows = await execute_query(
                "SELECT p.*, v.vendor_name, m.description AS material_desc "
                "FROM purchase_orders p "
                "JOIN vendors v ON p.vendor_id = v.vendor_id "
                "JOIN materials m ON p.material_id = m.material_id "
                "WHERE p.po_number = %s",
                (po_number.strip(),),
            )
            if not rows:
                return f"Purchase Order '{po_number}' not found."
            r = rows[0]
            return (
                f"Purchase Order: {r['po_number']}\n"
                f"  Vendor        : {r['vendor_id']} — {r['vendor_name']}\n"
                f"  Material      : {r['material_id']} — {r['material_desc']}\n"
                f"  Quantity      : {r['quantity']}\n"
                f"  Unit Price    : ${float(r['unit_price']):.2f}\n"
                f"  Total Value   : ${float(r['total_value']):.2f}\n"
                f"  Status        : {r['status']}\n"
                f"  Order Date    : {r['order_date']}\n"
            )
        except Exception as exc:
            logger.error(f"get_po_by_number: {exc}")
            return f"Error retrieving PO '{po_number}': {exc}"

    @mcp.tool()
    async def get_pos_by_vendor(vendor_id: str) -> str:
        """
        Retrieve all purchase orders placed with a specific vendor.

        Use this when the user asks "show all orders for vendor V001",
        "what have we bought from Tata Steel?", or wants a vendor's PO history.

        Args:
            vendor_id: Vendor identifier, e.g. "V001". Exact match.

        Returns all POs for that vendor with status and totals.
        """
        try:
            rows = await execute_query(
                "SELECT p.po_number, m.description AS material, p.quantity, "
                "p.unit_price, p.total_value, p.status, p.order_date "
                "FROM purchase_orders p "
                "JOIN materials m ON p.material_id = m.material_id "
                "WHERE p.vendor_id = %s ORDER BY p.order_date DESC",
                (vendor_id.strip(),),
            )
            if not rows:
                return f"No purchase orders found for vendor '{vendor_id}'."
            # Fetch vendor name
            v_rows = await execute_query(
                "SELECT vendor_name FROM vendors WHERE vendor_id = %s", (vendor_id.strip(),)
            )
            vendor_label = v_rows[0]["vendor_name"] if v_rows else vendor_id
            data = [
                [
                    r["po_number"], r["material"], r["quantity"],
                    f"${float(r['unit_price']):.2f}", f"${float(r['total_value']):.2f}",
                    r["status"], str(r["order_date"]),
                ]
                for r in rows
            ]
            total = sum(float(r["total_value"]) for r in rows)
            return (
                f"POs for {vendor_id} ({vendor_label}) — {len(rows)} order(s)\n\n"
                + _fmt_table(
                    ["PO Number", "Material", "Qty", "Unit Price", "Total Value", "Status", "Date"],
                    data,
                )
                + f"\n\nCumulative spend: ${total:,.2f}"
            )
        except Exception as exc:
            logger.error(f"get_pos_by_vendor: {exc}")
            return f"Error retrieving POs for vendor '{vendor_id}': {exc}"

    @mcp.tool()
    async def get_pos_by_status(status: str) -> str:
        """
        Filter purchase orders by their status.

        Use this when the user asks "show all PENDING orders",
        "what's been closed?", or needs to filter by procurement lifecycle state.

        Args:
            status: Order status to filter by. Valid values: OPEN, CLOSED, PENDING.
                    Case-insensitive.

        Returns a table of matching POs.
        """
        try:
            status_upper = status.strip().upper()
            if status_upper not in VALID_STATUSES:
                return f"Invalid status '{status}'. Valid values: {', '.join(sorted(VALID_STATUSES))}."
            rows = await execute_query(
                "SELECT p.po_number, v.vendor_name, m.description AS material, "
                "p.quantity, p.total_value, p.order_date "
                "FROM purchase_orders p "
                "JOIN vendors v ON p.vendor_id = v.vendor_id "
                "JOIN materials m ON p.material_id = m.material_id "
                "WHERE p.status = %s ORDER BY p.order_date DESC",
                (status_upper,),
            )
            if not rows:
                return f"No purchase orders with status '{status_upper}'."
            data = [
                [r["po_number"], r["vendor_name"], r["material"],
                 r["quantity"], f"${float(r['total_value']):.2f}", str(r["order_date"])]
                for r in rows
            ]
            return (
                f"Purchase Orders — Status: {status_upper} ({len(rows)} found)\n\n"
                + _fmt_table(["PO Number", "Vendor", "Material", "Qty", "Total Value", "Date"], data)
            )
        except Exception as exc:
            logger.error(f"get_pos_by_status: {exc}")
            return f"Error filtering POs by status: {exc}"

    @mcp.tool()
    async def get_total_spend_by_vendor() -> str:
        """
        Spend analysis: total purchase value grouped by vendor, sorted highest first.

        Use this for procurement analytics questions like "who are our biggest suppliers?",
        "how much have we spent with each vendor?", or spend concentration analysis.

        Returns a ranked table of vendors with their total PO count and spend.
        """
        try:
            rows = await execute_query(
                "SELECT v.vendor_id, v.vendor_name, v.country, "
                "COUNT(p.po_number) AS po_count, SUM(p.total_value) AS total_spend "
                "FROM vendors v "
                "LEFT JOIN purchase_orders p ON v.vendor_id = p.vendor_id "
                "GROUP BY v.vendor_id, v.vendor_name, v.country "
                "ORDER BY total_spend DESC"
            )
            if not rows:
                return "No spend data available."
            data = [
                [
                    r["vendor_id"], r["vendor_name"], r["country"],
                    r["po_count"] or 0,
                    f"${float(r['total_spend']):.2f}" if r["total_spend"] else "$0.00",
                ]
                for r in rows
            ]
            grand_total = sum(float(r["total_spend"]) for r in rows if r["total_spend"])
            return (
                f"Spend Analysis by Vendor\n\n"
                + _fmt_table(["Vendor ID", "Vendor Name", "Country", "# POs", "Total Spend (USD)"], data)
                + f"\n\nGrand Total Spend: ${grand_total:,.2f}"
            )
        except Exception as exc:
            logger.error(f"get_total_spend_by_vendor: {exc}")
            return f"Error calculating spend by vendor: {exc}"

    @mcp.tool()
    async def create_purchase_order(
        po_number: str,
        vendor_id: str,
        material_id: str,
        quantity: int,
        unit_price: float,
    ) -> str:
        """
        Create a new purchase order in the SAP ERP system.

        Use this when the user wants to raise a new PO, place an order with a supplier,
        or procure materials. The total_value is calculated automatically (qty × unit_price).
        The initial status is set to OPEN and order_date is today.

        Args:
            po_number  : Unique PO reference (e.g. "PO-2024-050"). Must not exist already.
            vendor_id  : Vendor who will supply the material (must exist in vendors table).
            material_id: Material being ordered (must exist in materials table).
            quantity   : Number of units to order. Must be > 0.
            unit_price : Agreed price per unit in USD. Must be > 0.

        Returns the new PO details with calculated total value.
        """
        try:
            if quantity <= 0:
                return "Error: Quantity must be greater than 0."
            if unit_price <= 0:
                return "Error: Unit price must be greater than 0."

            # Duplicate check
            existing_po = await execute_query(
                "SELECT 1 FROM purchase_orders WHERE po_number = %s", (po_number.strip(),)
            )
            if existing_po:
                return f"Error: PO '{po_number}' already exists."

            # Validate vendor
            vendor = await execute_query(
                "SELECT vendor_name FROM vendors WHERE vendor_id = %s", (vendor_id.strip(),)
            )
            if not vendor:
                return f"Error: Vendor '{vendor_id}' not found. Use get_all_vendors() to see valid IDs."

            # Validate material
            material = await execute_query(
                "SELECT description FROM materials WHERE material_id = %s", (material_id.strip(),)
            )
            if not material:
                return f"Error: Material '{material_id}' not found. Use get_all_materials() to see valid IDs."

            total_value = round(quantity * unit_price, 2)
            today = date.today().isoformat()

            affected = await execute_write(
                "INSERT INTO purchase_orders "
                "(po_number, vendor_id, material_id, quantity, unit_price, total_value, status, order_date) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'OPEN', %s)",
                (po_number.strip(), vendor_id.strip(), material_id.strip(),
                 quantity, round(unit_price, 2), total_value, today),
            )
            if affected:
                return (
                    f"Purchase Order created successfully.\n"
                    f"  PO Number  : {po_number}\n"
                    f"  Vendor     : {vendor_id} — {vendor[0]['vendor_name']}\n"
                    f"  Material   : {material_id} — {material[0]['description']}\n"
                    f"  Quantity   : {quantity}\n"
                    f"  Unit Price : ${unit_price:.2f}\n"
                    f"  Total Value: ${total_value:.2f}\n"
                    f"  Status     : OPEN\n"
                    f"  Order Date : {today}\n"
                )
            return "PO creation failed — no rows affected."
        except Exception as exc:
            logger.error(f"create_purchase_order: {exc}")
            return f"Error creating purchase order: {exc}"

    @mcp.tool()
    async def update_po_status(po_number: str, new_status: str) -> str:
        """
        Change the status of an existing purchase order.

        Use this when the user wants to close a PO, mark it as pending,
        or update procurement status (e.g. "close PO-2024-001" or "set to PENDING").

        Args:
            po_number : The PO to update, e.g. "PO-2024-001".
            new_status: New status — must be one of OPEN, CLOSED, PENDING (case-insensitive).

        Returns a confirmation with the old and new status.
        """
        try:
            new_status_upper = new_status.strip().upper()
            if new_status_upper not in VALID_STATUSES:
                return f"Invalid status '{new_status}'. Valid: {', '.join(sorted(VALID_STATUSES))}."

            existing = await execute_query(
                "SELECT status FROM purchase_orders WHERE po_number = %s", (po_number.strip(),)
            )
            if not existing:
                return f"Purchase Order '{po_number}' not found."

            old_status = existing[0]["status"]
            if old_status == new_status_upper:
                return f"PO '{po_number}' is already {new_status_upper}. No change made."

            await execute_write(
                "UPDATE purchase_orders SET status = %s WHERE po_number = %s",
                (new_status_upper, po_number.strip()),
            )
            return (
                f"Status updated.\n"
                f"  PO Number : {po_number}\n"
                f"  Old Status: {old_status}\n"
                f"  New Status: {new_status_upper}\n"
            )
        except Exception as exc:
            logger.error(f"update_po_status: {exc}")
            return f"Error updating PO status: {exc}"

    @mcp.tool()
    async def get_po_summary() -> str:
        """
        High-level summary statistics for the purchase order module.

        Use this when the user asks for a procurement dashboard, KPI overview,
        "how many orders do we have?", or "what is the total procurement value?".

        Returns total PO count, total value, and breakdown by status.
        """
        try:
            totals = await execute_query(
                "SELECT COUNT(*) AS total_pos, "
                "COALESCE(SUM(total_value), 0) AS grand_total "
                "FROM purchase_orders"
            )
            by_status = await execute_query(
                "SELECT status, COUNT(*) AS cnt, "
                "COALESCE(SUM(total_value), 0) AS subtotal "
                "FROM purchase_orders GROUP BY status ORDER BY status"
            )
            t = totals[0]
            lines = [
                "Purchase Order Summary",
                "=" * 40,
                f"  Total POs    : {t['total_pos']}",
                f"  Grand Total  : ${float(t['grand_total']):,.2f}",
                "",
                "Breakdown by Status:",
            ]
            for r in by_status:
                lines.append(f"  {r['status']:<10}: {r['cnt']:>4} POs  —  ${float(r['subtotal']):>12,.2f}")
            return "\n".join(lines)
        except Exception as exc:
            logger.error(f"get_po_summary: {exc}")
            return f"Error generating PO summary: {exc}"
