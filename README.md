# SAP ERP Remote MCP Server

A production-ready **remote MCP server** that connects Claude AI to a MySQL SAP ERP database over HTTP + SSE transport. Works with **Claude Desktop** (local) and **claude.ai browser** (via ngrok).

---

## 1. Project Overview

This server exposes **25 MCP tools** across four SAP modules — Materials, Vendors, Purchase Orders, and Inventory — as a remotely accessible HTTP service. Claude can call these tools to query and update your ERP database using natural language.

```
Architecture:
  Claude (Desktop / claude.ai)
       │  HTTP + SSE (MCP protocol)
       ▼
  ngrok public URL  ──►  localhost:8000
       │
  FastMCP SSE Server (server.py)
       │
  MySQL 8.0 (sap_erp database)
```

---

## 2. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.14 | At `C:\Users\anand\AppData\Local\Programs\Python\Python314\` |
| MySQL | 8.0 | Running on `localhost:3306`, database `sap_erp` |
| ngrok | any | Installed via Microsoft Store, already authenticated |
| Claude Desktop | latest | Optional — for local SSE access |
| Claude.ai | Pro plan | For browser-based remote access |

---

## 3. Installation

```powershell
# 1. Open PowerShell in the project folder
cd "C:\Users\anand\OneDrive\Desktop\Codings\SAP MCP\sap-remote-mcp"

# 2. Install dependencies
C:\Users\anand\AppData\Local\Programs\Python\Python314\python.exe -m pip install -r requirements.txt

# 3. Verify .env has your credentials (already pre-filled)
type .env
```

---

## 4. Running with start.bat (Recommended — One Click)

Double-click **`start.bat`** in the project folder.

It automatically:
1. Opens Window 1 → starts the Python MCP server
2. Opens Window 2 → starts ngrok HTTP tunnel on port 8000
3. Opens Window 3 → fetches the ngrok public URL and displays it

**Look at Window 3** for your public URL.

---

## 5. Running Manually (Step by Step)

### Terminal 1 — Start the MCP Server
```powershell
cd "C:\Users\anand\OneDrive\Desktop\Codings\SAP MCP\sap-remote-mcp"
C:\Users\anand\AppData\Local\Programs\Python\Python314\python.exe server.py
```
You should see:
```
  SAP ERP MCP Server  —  RUNNING
  Local SSE URL  :  http://localhost:8000/sse
  Health check   :  http://localhost:8000/health
```

### Terminal 2 — Start ngrok
```powershell
ngrok http 8000
```

### Terminal 3 — Get the Public URL
```powershell
# Fetch the ngrok URL from the local API
curl http://localhost:4040/api/tunnels
```
Look for the `public_url` field in the JSON output. It will look like:
```
https://a1b2-99-88-77-66.ngrok-free.app
```

---

## 6. Getting the ngrok URL

After running `ngrok http 8000`:

**Option A — ngrok Web UI:**  
Open http://localhost:4040 in your browser → you'll see the public URL.

**Option B — PowerShell:**
```powershell
(Invoke-RestMethod http://localhost:4040/api/tunnels).tunnels[0].public_url
```

**Option C — Terminal output:**  
The ngrok terminal shows the URL directly under "Forwarding".

Your MCP SSE endpoint = `<ngrok-url>/sse`  
Example: `https://a1b2-99-88-77-66.ngrok-free.app/sse`

---

## 7. Claude Desktop Config (Local SSE)

Update `C:\Users\anand\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "excel-assistant": {
      "command": "C:\\Users\\anand\\AppData\\Local\\Programs\\Python\\Python314\\python.exe",
      "args": [
        "C:\\Users\\anand\\OneDrive\\Desktop\\Codings\\SAP MCP\\excel-mcp-server\\server.py"
      ]
    },
    "sap-database": {
      "type": "sse",
      "url": "http://localhost:8000/sse"
    }
  },
  "preferences": {
    "coworkWebSearchEnabled": true,
    "coworkScheduledTasksEnabled": false,
    "ccdScheduledTasksEnabled": false
  }
}
```

After saving, restart Claude Desktop. The `sap-database` tools will appear in the toolbar.

**When using ngrok** (to share with a friend or access from another machine), change the url to:
```json
"url": "https://a1b2-99-88-77-66.ngrok-free.app/sse"
```

---

## 8. Adding to claude.ai Browser (Settings → Integrations)

1. Make sure server.py and ngrok are both running
2. Get your ngrok URL (see Section 6)
3. Open **claude.ai** → click your profile → **Settings**
4. Go to **Integrations** (or "MCP Servers")
5. Click **Add MCP Server**
6. Paste: `https://a1b2-99-88-77-66.ngrok-free.app/sse`
7. Give it a name: `SAP ERP`
8. Click **Save / Connect**

Claude will now show the 25 SAP tools in a new panel. Test with: *"Show me all materials"*

> **Note:** If you test the `/sse` URL directly in a browser, add the header `ngrok-skip-browser-warning: true` to bypass the ngrok interstitial page. Claude does this automatically.

---

## 9. Sharing with a Friend

1. Start server.py and ngrok
2. Copy the ngrok `/sse` URL (e.g. `https://xxxx.ngrok-free.app/sse`)
3. Send that URL to your friend
4. They add it in their Claude Desktop config or claude.ai Integrations:
   ```json
   "sap-database": {
     "type": "sse",
     "url": "https://xxxx.ngrok-free.app/sse"
   }
   ```
5. Both of you connect to the same MySQL database through the same server

---

## 10. When the ngrok URL Changes (Free Plan)

ngrok free plan gives a **new random URL every time you restart ngrok**. When the URL changes:

1. Get the new URL from `http://localhost:4040`
2. Update `claude_desktop_config.json` with the new URL
3. Restart Claude Desktop
4. Send the new URL to anyone sharing your server

**Tip:** Start ngrok once in the morning and keep it running all day. The URL only changes on restart.

**Permanent fix (paid):** ngrok paid plans offer a fixed subdomain (e.g. `your-name.ngrok.io`).

---

## 11. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL server hostname |
| `DB_PORT` | `3306` | MySQL port |
| `DB_USER` | `root` | MySQL username |
| `DB_PASSWORD` | `1234` | MySQL password |
| `DB_NAME` | `sap_erp` | Database name |
| `DB_POOL_SIZE` | `5` | Connection pool size |
| `MCP_HOST` | `0.0.0.0` | Server bind address |
| `MCP_PORT` | `8000` | Server port |
| `API_KEY` | *(empty)* | Auth key — leave empty for dev mode |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## 12. MCP Tools Reference

### Materials (5 tools)

| Tool | Parameters | Description |
|---|---|---|
| `get_all_materials` | — | All materials as a table |
| `get_material_by_id` | `material_id` | Full detail of one material |
| `search_materials` | `keyword` | Search by description or group |
| `get_materials_by_group` | `group` | Filter by RAW-METAL, PACKAGING, etc. |
| `add_material` | `material_id, description, unit, material_group, price` | Create new material |

### Vendors (5 tools)

| Tool | Parameters | Description |
|---|---|---|
| `get_all_vendors` | — | All vendors as a table |
| `get_vendor_by_id` | `vendor_id` | Full vendor details |
| `search_vendors` | `keyword` | Search by name or city |
| `get_vendors_by_country` | `country` | Filter vendors by country |
| `add_vendor` | `vendor_id, vendor_name, city, country, contact` | Create new vendor |

### Purchase Orders (9 tools)

| Tool | Parameters | Description |
|---|---|---|
| `get_all_purchase_orders` | — | All POs with vendor + material names |
| `get_open_purchase_orders` | — | Only OPEN status POs |
| `get_po_by_number` | `po_number` | Full PO detail |
| `get_pos_by_vendor` | `vendor_id` | All POs for a vendor |
| `get_pos_by_status` | `status` | Filter by OPEN / CLOSED / PENDING |
| `get_total_spend_by_vendor` | — | Spend analysis grouped by vendor |
| `create_purchase_order` | `po_number, vendor_id, material_id, quantity, unit_price` | Create PO (auto-calculates total) |
| `update_po_status` | `po_number, new_status` | Change PO status |
| `get_po_summary` | — | Summary stats: count, total value, by status |

### Inventory (6 tools)

| Tool | Parameters | Description |
|---|---|---|
| `get_all_inventory` | — | All stock with descriptions |
| `check_stock` | `material_id` | Stock for one material (stock, reserved, available) |
| `get_low_stock_items` | `threshold` (default 100) | Items where available < threshold |
| `get_inventory_by_plant` | `plant_code` | All stock at a specific plant |
| `update_stock` | `material_id, new_quantity` | Update stock level |
| `get_stock_summary` | — | Dashboard: items, units, value, low-stock count |

---

## 13. Troubleshooting

### `ModuleNotFoundError: No module named 'fastmcp'`
```powershell
C:\Users\anand\AppData\Local\Programs\Python\Python314\python.exe -m pip install -r requirements.txt
```

### `mysql.connector.errors.DatabaseError: 2003 Can't connect`
- Ensure MySQL service is running: `services.msc` → MySQL80 → Start
- Check credentials in `.env` match your MySQL setup

### `OSError: [WinError 10048] Address already in use`
Port 8000 is taken. Either:
- Stop the old server (Task Manager → find python.exe → End Task)
- Change `MCP_PORT=8001` in `.env`

### ngrok shows "ERR_NGROK_3200 — Tunnel not found"
The ngrok URL has expired (server was restarted). Get the new URL from `http://localhost:4040` and update your config.

### claude.ai shows "Could not connect to MCP server"
1. Confirm server.py is running: `curl http://localhost:8000/health`
2. Confirm ngrok is running: open `http://localhost:4040`
3. Try opening `https://xxxx.ngrok-free.app/sse` in your browser — you should see an SSE stream start
4. Re-add the integration in claude.ai with the updated URL

### Tools appear but return "Error retrieving …"
- Check the server terminal for error details
- Run `python test_server.py` to diagnose which queries fail
- Confirm the `sap_erp` database tables exist and have data

### `RuntimeError: DB pool not initialised`
This shouldn't happen in normal use. If it does:
```powershell
python test_server.py  # will force-init the pool and report errors
```

---

## Running Tests

```powershell
cd "C:\Users\anand\OneDrive\Desktop\Codings\SAP MCP\sap-remote-mcp"

# Test DB + tools (server does NOT need to be running)
C:\Users\anand\AppData\Local\Programs\Python\Python314\python.exe test_server.py

# Test including /health endpoint (start server.py first)
C:\Users\anand\AppData\Local\Programs\Python\Python314\python.exe test_server.py
```
