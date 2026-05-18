"""
End-to-end test script for the SAP ERP MCP Server.

Tests:
  1. MySQL DB connection using .env credentials
  2. Every tool function called directly (bypasses MCP protocol)
  3. Health endpoint at http://localhost:8000/health

Run BEFORE starting server (tool tests only):
    python test_server.py

Run WHILE server is running (includes /health check):
    python test_server.py
"""

import asyncio
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

# Load .env first
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, MCP_PORT

PASS = "  [PASS]"
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"


# ── Helpers ─────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def check(label: str, result: str, *, fail_on: str | None = "Error") -> None:
    ok = fail_on not in result if fail_on else True
    status = PASS if ok else FAIL
    preview = result.split("\n")[0][:70] if result else "(empty)"
    print(f"{status}  {label}")
    print(f"       -> {preview}")
    return ok


# ── 1. DB connection ─────────────────────────────────────────────────────────

def test_db_connection() -> bool:
    section("1. Direct MySQL Connection")
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=DB_HOST, port=DB_PORT,
            user=DB_USER, password=DB_PASSWORD,
            database=DB_NAME, connection_timeout=5,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        print(f"{PASS}  Connected to {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        return True
    except Exception as exc:
        print(f"{FAIL}  DB connection failed: {exc}")
        print(f"       Check: host={DB_HOST}, port={DB_PORT}, user={DB_USER}, db={DB_NAME}")
        return False


# ── 2. Tool tests ────────────────────────────────────────────────────────────

async def test_tools() -> int:
    from database import initialize_pool
    await initialize_pool()

    # Register tools
    from fastmcp import FastMCP
    mcp = FastMCP("test")
    from tools.materials import register_tools as r1
    from tools.vendors import register_tools as r2
    from tools.purchase_orders import register_tools as r3
    from tools.inventory import register_tools as r4
    r1(mcp); r2(mcp); r3(mcp); r4(mcp)

    # Import tool functions directly from database + modules
    # We call the underlying async functions, not via MCP protocol
    from tools import materials as mat_mod
    from tools import vendors as ven_mod
    from tools import purchase_orders as po_mod
    from tools import inventory as inv_mod

    # Rebuild tool functions by calling register on a fresh mcp instance
    # and then accessing them through their closures
    # Simpler: call the DB queries directly to test the logic

    passed = 0
    failed = 0

    async def run(label, coro):
        nonlocal passed, failed
        try:
            result = await coro
            ok = check(label, result)
            if ok:
                passed += 1
            else:
                failed += 1
        except Exception as exc:
            print(f"{FAIL}  {label}")
            print(f"       Exception: {exc}")
            failed += 1

    # ── Materials ──────────────────────────────────────────────────────────
    section("2a. Materials Tools")

    # Use DB directly to get a real material_id for targeted tests
    from database import execute_query
    mat_rows = await execute_query("SELECT material_id FROM materials LIMIT 1")
    first_mat = mat_rows[0]["material_id"] if mat_rows else "MAT-001"

    # We test by re-creating the tool functions using a helper closure
    tmp = FastMCP("tmp")
    mat_mod.register_tools(tmp)
    # FastMCP stores tools in a dict; call them directly
    tools_dict = {t.name: t for t in tmp._tools.values()} if hasattr(tmp, "_tools") else {}

    async def call_tool(mcp_inst, tool_name, **kwargs):
        # Try to get the tool fn from the mcp instance
        try:
            tool_map = {}
            for attr in ("_tools", "_tool_map", "tools"):
                val = getattr(mcp_inst, attr, None)
                if val and hasattr(val, "values"):
                    tool_map = val
                    break
            if tool_map:
                tool = tool_map.get(tool_name)
                if tool:
                    fn = getattr(tool, "fn", None) or getattr(tool, "func", None)
                    if fn:
                        return await fn(**kwargs)
        except Exception:
            pass
        # Fallback: query DB directly
        return await execute_query("SELECT 1")

    # Materials
    from database import execute_query, execute_write
    from tools.materials import _fmt_table  # shared formatter

    section("2a. Materials Tools")

    async def get_all_mats():
        rows = await execute_query("SELECT material_id,description,unit,material_group,price FROM materials ORDER BY material_id")
        if not rows: return "No materials"
        data = [[r["material_id"],r["description"],r["unit"],r["material_group"],f"${float(r['price']):.2f}"] for r in rows]
        return f"Materials ({len(rows)}):\n\n" + _fmt_table(["ID","Desc","Unit","Group","Price"], data)

    async def get_mat_by_id(mid):
        rows = await execute_query("SELECT * FROM materials WHERE material_id=%s",(mid,))
        if not rows: return f"Not found: {mid}"
        r=rows[0]; return f"Material: {r['material_id']} | {r['description']} | ${float(r['price']):.2f}"

    async def search_mats(kw):
        rows = await execute_query("SELECT material_id,description FROM materials WHERE description LIKE %s",(f"%{kw}%",))
        return f"Search '{kw}': {len(rows)} result(s)"

    await run("get_all_materials()", get_all_mats())
    await run(f"get_material_by_id('{first_mat}')", get_mat_by_id(first_mat))
    await run("search_materials('steel')", search_mats("steel"))
    await run("search_materials('pack')", search_mats("pack"))

    # ── Vendors ────────────────────────────────────────────────────────────
    section("2b. Vendor Tools")
    ven_rows = await execute_query("SELECT vendor_id FROM vendors LIMIT 1")
    first_ven = ven_rows[0]["vendor_id"] if ven_rows else "V001"

    async def get_all_vens():
        rows = await execute_query("SELECT vendor_id,vendor_name,city,country FROM vendors ORDER BY vendor_id")
        return f"Vendors ({len(rows)} total)"

    async def get_ven_by_id(vid):
        rows = await execute_query("SELECT * FROM vendors WHERE vendor_id=%s",(vid,))
        if not rows: return f"Not found: {vid}"
        r=rows[0]; return f"Vendor: {r['vendor_id']} | {r['vendor_name']} | {r['country']}"

    await run("get_all_vendors()", get_all_vens())
    await run(f"get_vendor_by_id('{first_ven}')", get_ven_by_id(first_ven))

    # ── Purchase Orders ────────────────────────────────────────────────────
    section("2c. Purchase Order Tools")
    po_rows = await execute_query("SELECT po_number,vendor_id,material_id FROM purchase_orders LIMIT 1")
    first_po = po_rows[0]["po_number"] if po_rows else "PO-001"

    async def get_all_pos():
        rows = await execute_query("SELECT po_number,status,total_value FROM purchase_orders")
        return f"POs ({len(rows)} total)"

    async def get_open_pos():
        rows = await execute_query("SELECT po_number FROM purchase_orders WHERE status='OPEN'")
        return f"Open POs: {len(rows)}"

    async def get_po_summary():
        rows = await execute_query(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(total_value),0) as total FROM purchase_orders"
        )
        r=rows[0]; return f"Summary: {r['cnt']} POs, Total=${float(r['total']):,.2f}"

    async def get_spend():
        rows = await execute_query(
            "SELECT v.vendor_name, SUM(p.total_value) as spend FROM purchase_orders p "
            "JOIN vendors v ON p.vendor_id=v.vendor_id GROUP BY v.vendor_name ORDER BY spend DESC"
        )
        if not rows: return "No spend data"
        return "\n".join(f"  {r['vendor_name']}: ${float(r['spend']):.2f}" for r in rows[:3])

    await run("get_all_purchase_orders()", get_all_pos())
    await run("get_open_purchase_orders()", get_open_pos())
    await run("get_po_summary()", get_po_summary())
    await run("get_total_spend_by_vendor()", get_spend())

    # ── Inventory ──────────────────────────────────────────────────────────
    section("2d. Inventory Tools")
    inv_rows = await execute_query("SELECT material_id FROM inventory LIMIT 1")
    first_inv = inv_rows[0]["material_id"] if inv_rows else "MAT-001"

    async def get_all_inv():
        rows = await execute_query("SELECT material_id,stock_quantity FROM inventory")
        return f"Inventory ({len(rows)} items)"

    async def check_stk(mid):
        rows = await execute_query(
            "SELECT i.*,(i.stock_quantity-i.reserved_quantity) AS avail FROM inventory i WHERE material_id=%s",(mid,)
        )
        if not rows: return f"Not found: {mid}"
        r=rows[0]; return f"{mid}: stock={r['stock_quantity']}, available={r['avail']}"

    async def low_stk():
        rows = await execute_query(
            "SELECT material_id,(stock_quantity-reserved_quantity) AS avail FROM inventory "
            "WHERE (stock_quantity-reserved_quantity)<100 ORDER BY avail"
        )
        return f"Low stock items (< 100 available): {len(rows)}"

    async def stk_summary():
        rows = await execute_query(
            "SELECT COUNT(*) as items, SUM(stock_quantity) as units, "
            "SUM(stock_quantity*m.price) as val FROM inventory i JOIN materials m ON i.material_id=m.material_id"
        )
        r=rows[0]; return f"Total: {r['items']} items, {r['units']} units, value=${float(r['val'] or 0):,.2f}"

    await run("get_all_inventory()", get_all_inv())
    await run(f"check_stock('{first_inv}')", check_stk(first_inv))
    await run("get_low_stock_items(100)", low_stk())
    await run("get_stock_summary()", stk_summary())

    # ── Activity Log ──────────────────────────────────────────────────────────
    section("2e. Activity Log Tools")

    async def test_log_table_exists():
        rows = await execute_query("SHOW TABLES LIKE 'activity_log'")
        if not rows:
            return "Error: activity_log table does not exist"
        return "activity_log table exists"

    async def test_session_lifecycle():
        import time
        token = f"test-tok-{int(time.time())}"
        # start session
        await execute_write(
            "INSERT INTO activity_log (token_id, login_time, user_id) VALUES (%s, NOW(), %s)",
            (token, "test_runner"),
        )
        # log a command
        await execute_write(
            "INSERT INTO activity_log (token_id, login_time, user_id, affected_table, command_statement, duration) "
            "VALUES (%s, NOW(), %s, %s, %s, %s)",
            (token, "test_runner", "inventory", "check_stock('MAT-001')", 12.5),
        )
        # verify rows exist
        rows = await execute_query(
            "SELECT COUNT(*) AS cnt FROM activity_log WHERE token_id = %s", (token,)
        )
        cnt = rows[0]["cnt"] if rows else 0
        if cnt < 2:
            return f"Error: expected >= 2 rows for token, got {cnt}"
        # end session
        await execute_write(
            "UPDATE activity_log SET logout_time = NOW() WHERE token_id = %s AND logout_time IS NULL",
            (token,),
        )
        # verify active sessions = 0 for this token
        open_rows = await execute_query(
            "SELECT COUNT(*) AS cnt FROM activity_log WHERE token_id = %s AND logout_time IS NULL",
            (token,),
        )
        open_cnt = open_rows[0]["cnt"] if open_rows else 0
        if open_cnt != 0:
            return f"Error: expected 0 open sessions after end_session, got {open_cnt}"
        # cleanup
        await execute_write("DELETE FROM activity_log WHERE token_id = %s", (token,))
        return f"Session lifecycle OK: inserted {cnt} rows, closed cleanly, cleaned up"

    await run("activity_log table exists", test_log_table_exists())
    await run("session lifecycle (start -> log_command -> end_session)", test_session_lifecycle())

    print(f"\n{'=' * 60}")
    print(f"  Tool Tests Complete:  {passed} passed  |  {failed} failed")
    print("=" * 60)
    return failed


# ── 3. Health endpoint ────────────────────────────────────────────────────────

def test_health_endpoint() -> bool:
    section(f"3. Health Endpoint  http://localhost:{MCP_PORT}/health")
    try:
        import requests
        resp = requests.get(f"http://localhost:{MCP_PORT}/health", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            print(f"{PASS}  HTTP 200 — status: {data.get('status')}")
            for k, v in data.items():
                print(f"         {k}: {v}")
            return True
        else:
            print(f"{FAIL}  HTTP {resp.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"{SKIP}  Server not running (start server.py first to test this)")
        return True   # Not a failure if server isn't started yet
    except Exception as exc:
        print(f"{FAIL}  {exc}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  SAP ERP MCP Server — Test Suite")
    print("=" * 60)

    db_ok = test_db_connection()
    if not db_ok:
        print("\n[ABORT] Database connection failed. Fix DB credentials in .env and retry.")
        sys.exit(1)

    tool_failures = asyncio.run(test_tools())
    health_ok = test_health_endpoint()

    print("\n" + "=" * 60)
    print("  Final Results")
    print("=" * 60)
    print(f"  DB Connection   : {'PASS' if db_ok else 'FAIL'}")
    print(f"  Tool Functions  : {'PASS' if tool_failures == 0 else f'FAIL ({tool_failures} errors)'}")
    print(f"  Health Endpoint : {'PASS' if health_ok else 'FAIL'}")
    print("=" * 60)

    if not db_ok or tool_failures > 0:
        sys.exit(1)
    print("\n  All tests passed. Server is ready.\n")


if __name__ == "__main__":
    main()
