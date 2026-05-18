"""Vendor management tools for the SAP ERP MCP server."""

from __future__ import annotations

import logging
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
    async def get_all_vendors() -> str:
        """
        Retrieve the complete vendor master list from the SAP ERP system.

        Use this when the user asks to see all suppliers, wants to know which vendors
        are registered in the system, or needs to pick a vendor for a purchase order.

        Returns a formatted table:
            Vendor ID | Vendor Name | City | Country | Contact
        """
        try:
            rows = await execute_query(
                "SELECT vendor_id, vendor_name, city, country, contact "
                "FROM vendors ORDER BY vendor_id"
            )
            if not rows:
                return "No vendors found in the database."
            data = [
                [r["vendor_id"], r["vendor_name"], r["city"], r["country"], r["contact"]]
                for r in rows
            ]
            return (
                f"Vendor Master — {len(rows)} record(s)\n\n"
                + _fmt_table(["Vendor ID", "Vendor Name", "City", "Country", "Contact"], data)
            )
        except Exception as exc:
            logger.error(f"get_all_vendors: {exc}")
            return f"Error retrieving vendors: {exc}"

    @mcp.tool()
    async def get_vendor_by_id(vendor_id: str) -> str:
        """
        Look up the full details of a specific vendor by their Vendor ID.

        Use this when the user wants contact info for a supplier, needs to verify
        a vendor exists, or wants to see all fields for one vendor.

        Args:
            vendor_id: Unique vendor identifier, e.g. "V001" or "VEND-42".

        Returns all vendor fields or a not-found message.
        """
        try:
            rows = await execute_query(
                "SELECT * FROM vendors WHERE vendor_id = %s", (vendor_id.strip(),)
            )
            if not rows:
                return f"Vendor '{vendor_id}' not found."
            r = rows[0]
            return (
                f"Vendor: {r['vendor_id']}\n"
                f"  Name   : {r['vendor_name']}\n"
                f"  City   : {r['city']}\n"
                f"  Country: {r['country']}\n"
                f"  Contact: {r['contact']}\n"
            )
        except Exception as exc:
            logger.error(f"get_vendor_by_id: {exc}")
            return f"Error retrieving vendor '{vendor_id}': {exc}"

    @mcp.tool()
    async def search_vendors(keyword: str) -> str:
        """
        Search for vendors by keyword in their name or city.

        Use this when the user says things like "find vendors named Tata",
        "suppliers in Mumbai", or "search for vendors with 'steel' in their name".

        Args:
            keyword: Case-insensitive search term matched against vendor_name
                     and city columns. Examples: "Tata", "Chennai", "Auto".

        Returns a table of matching vendors.
        """
        try:
            rows = await execute_query(
                "SELECT vendor_id, vendor_name, city, country, contact "
                "FROM vendors WHERE vendor_name LIKE %s OR city LIKE %s "
                "ORDER BY vendor_name",
                (f"%{keyword}%", f"%{keyword}%"),
            )
            if not rows:
                return f"No vendors found matching '{keyword}'."
            data = [
                [r["vendor_id"], r["vendor_name"], r["city"], r["country"], r["contact"]]
                for r in rows
            ]
            return (
                f"Vendor search for '{keyword}' — {len(rows)} match(es)\n\n"
                + _fmt_table(["Vendor ID", "Vendor Name", "City", "Country", "Contact"], data)
            )
        except Exception as exc:
            logger.error(f"search_vendors: {exc}")
            return f"Error searching vendors: {exc}"

    @mcp.tool()
    async def get_vendors_by_country(country: str) -> str:
        """
        Retrieve all vendors located in a specific country.

        Use this when the user asks "show Indian suppliers",
        "vendors from Germany", or wants to filter suppliers geographically.

        Args:
            country: Country name (case-insensitive partial match).
                     Examples: "India", "Germany", "USA", "China".

        Returns a table of vendors in that country.
        """
        try:
            rows = await execute_query(
                "SELECT vendor_id, vendor_name, city, country, contact "
                "FROM vendors WHERE country LIKE %s ORDER BY vendor_name",
                (f"%{country}%",),
            )
            if not rows:
                return f"No vendors found in country '{country}'."
            data = [
                [r["vendor_id"], r["vendor_name"], r["city"], r["country"], r["contact"]]
                for r in rows
            ]
            return (
                f"Vendors in '{country}' — {len(rows)} record(s)\n\n"
                + _fmt_table(["Vendor ID", "Vendor Name", "City", "Country", "Contact"], data)
            )
        except Exception as exc:
            logger.error(f"get_vendors_by_country: {exc}")
            return f"Error retrieving vendors by country: {exc}"

    @mcp.tool()
    async def add_vendor(
        vendor_id: str,
        vendor_name: str,
        city: str,
        country: str,
        contact: str,
    ) -> str:
        """
        Register a new vendor in the SAP ERP vendor master.

        Use this when the user wants to add a new supplier or create a vendor record.
        Checks for duplicate Vendor IDs before inserting.

        Args:
            vendor_id  : Unique identifier for the vendor (e.g. "V050").
                         Must not already exist.
            vendor_name: Full company/supplier name (e.g. "Tata Steel Ltd.").
            city       : City where the vendor is located (e.g. "Mumbai").
            country    : Country name (e.g. "India", "Germany").
            contact    : Contact email or phone number for the vendor.

        Returns a confirmation message with the new vendor's details.
        """
        try:
            existing = await execute_query(
                "SELECT 1 FROM vendors WHERE vendor_id = %s", (vendor_id.strip(),)
            )
            if existing:
                return f"Error: Vendor ID '{vendor_id}' already exists. Choose a unique ID."

            affected = await execute_write(
                "INSERT INTO vendors (vendor_id, vendor_name, city, country, contact) "
                "VALUES (%s, %s, %s, %s, %s)",
                (vendor_id.strip(), vendor_name.strip(), city.strip(), country.strip(), contact.strip()),
            )
            if affected:
                return (
                    f"Vendor added successfully.\n"
                    f"  Vendor ID  : {vendor_id}\n"
                    f"  Name       : {vendor_name}\n"
                    f"  City       : {city}\n"
                    f"  Country    : {country}\n"
                    f"  Contact    : {contact}\n"
                )
            return "Insert failed — no rows affected."
        except Exception as exc:
            logger.error(f"add_vendor: {exc}")
            return f"Error adding vendor: {exc}"
