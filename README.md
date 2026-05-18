# SAP ERP Remote MCP Server

A **remote MCP server** that connects Claude AI to a MySQL SAP ERP database over HTTP + SSE transport.  
Claude generates and executes MySQL queries directly — no predefined tool limits.

Works with **Claude Desktop** (local) and **claude.ai browser** (via ngrok tunnel).

---

## How It Works

```
You (natural language)
        |
   Claude AI (Desktop / claude.ai)
        |  HTTP + SSE  (MCP protocol)
        v
   ngrok public URL --> localhost:8080
        |
   FastMCP SSE Server  (server.py)
        |
   MySQL 8.0  (sap_erp database)
```

Claude receives your request, generates the correct MySQL query, and executes it using the `execute_sql` tool — returning results in a clean formatted table.

---

## Features

- **Natural language to SQL** — Ask Claude anything; it generates and runs the query
- **Full SQL support** — SELECT, INSERT, UPDATE, DELETE, ALTER TABLE, CREATE, DROP
- **Auto audit log** — Every write is automatically recorded in `activity_log` with table name, SQL statement, duration, field changed, old value, and new value
- **Remote access** — Share the ngrok URL so teammates can connect from anywhere
- **API key auth** — Optional token-based auth for production use
- **SSE transport** — Works with Claude Desktop and claude.ai custom connectors

---

## Database Schema

| Table | Primary Key | Description |
|---|---|---|
| `materials` | `material_id` VARCHAR | Raw materials catalog with unit prices |
| `vendors` | `vendor_id` VARCHAR | Supplier directory |
| `purchase_orders` | `po_number` VARCHAR | POs linking vendors + materials; status: OPEN / CLOSED / PENDING |
| `inventory` | `(material_id, plant_code)` | Stock levels per plant |
| `activity_log` | `log_id` AUTO_INCREMENT | Full audit trail of all write operations |

---

## Prerequisites

| Tool | Version | Download |
|---|---|---|
| Python | 3.10+ | https://python.org/downloads |
| MySQL | 8.0+ | https://dev.mysql.com/downloads/installer |
| ngrok | any | https://ngrok.com/download |
| Claude Desktop | latest | https://claude.ai/download *(optional)* |

---

## Installation

### 1. Clone the repository

```powershell
git clone https://github.com/Onandthegr8/sap-remote-mcp.git
cd sap-remote-mcp
```

### 2. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment

```powershell
copy .env.example .env
notepad .env
```

Fill in your values:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=sap_erp
DB_POOL_SIZE=5
MCP_PORT=8080
API_KEY=
```

> Leave `API_KEY` empty for development. Set a secret string to enable token auth in production.

### 4. Create the database

Open MySQL Workbench or MySQL Shell and run:

```sql
CREATE DATABASE IF NOT EXISTS sap_erp;
```

### 5. Set up the audit log table

```powershell
python create_log_table.py
```

---

## Running the Server

### Option A — One click (Windows)

Double-click **`start.bat`**

Opens 3 PowerShell windows automatically:
- Window 1 → MCP server
- Window 2 → ngrok tunnel
- Window 3 → displays the public URL

### Option B — Manual (two terminals)

**Terminal 1 — Start the server:**
```powershell
python server.py
```

Expected output:
```
==============================================================
  SAP ERP MCP Server  -  RUNNING  (SSE transport)
==============================================================
  SSE Endpoint   :  http://localhost:8080/sse
  Environment    :  development
==============================================================
```

**Terminal 2 — Start ngrok:**
```powershell
ngrok http 8080
```

Copy the `https://xxxx.ngrok-free.app` URL shown in the ngrok output.

---

## Connecting Claude

### Claude Desktop (local access)

Edit the config file at:
```
C:\Users\<you>\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json
```

Add:
```json
{
  "mcpServers": {
    "sap-database": {
      "type": "sse",
      "url": "http://localhost:8080/sse"
    }
  }
}
```

Restart Claude Desktop after saving.

### claude.ai (remote access via ngrok)

1. Go to **claude.ai -> Customize -> Connectors -> Add custom connector**
2. Paste your ngrok URL: `https://xxxx.ngrok-free.app/sse`
3. Click **Connect**

---

## Usage Examples

Once connected, just talk to Claude naturally:

```
"Show me all materials in the database"
"Which purchase orders are still open?"
"What's the current stock level for MAT-001?"
"Add a new vendor V-010 called Tata Steel from India"
"Update the status of PO-2024-001 to CLOSED"
"Show me the last 20 entries in the activity log"
"Which items are below 50 units in stock?"
"What's the total spend per vendor this year?"
```

Claude generates the MySQL query and executes it immediately — no manual SQL needed.

---

## MCP Tool

This server exposes a single flexible tool:

### `execute_sql`

Executes any MySQL query against the SAP ERP database.

| Query type | Returns |
|---|---|
| `SELECT`, `SHOW`, `DESCRIBE` | Formatted ASCII table of results |
| `INSERT`, `UPDATE`, `DELETE` | Number of rows affected |
| `CREATE`, `ALTER`, `DROP` | Status message |

Claude decides what SQL to generate based on your request and runs it automatically.

---

## Audit Log

Every INSERT, UPDATE, and DELETE is automatically logged to `activity_log` with:

| Column | Description |
|---|---|
| `token_id` | Server session identifier |
| `login_time` | When the operation ran |
| `user_id` | Who ran it (`claude` for auto-logged ops) |
| `affected_table` | Which table was modified |
| `command_statement` | The SQL that was executed |
| `duration` | Execution time in milliseconds |
| `field_changed` | Which field was updated |
| `value_before` | Value before the change |
| `value_after` | Value after the change |

Ask Claude *"show me the activity log"* to view a full audit trail.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | MySQL server hostname |
| `DB_PORT` | `3306` | MySQL port |
| `DB_USER` | `root` | MySQL username |
| `DB_PASSWORD` | — | MySQL password |
| `DB_NAME` | `sap_erp` | Database name |
| `DB_POOL_SIZE` | `5` | Connection pool size |
| `MCP_PORT` | `8080` | Server port |
| `API_KEY` | *(empty)* | Leave empty to disable auth; set a secret string to enable |

---

## Project Structure

```
sap-remote-mcp/
├── server.py              # Entry point — FastMCP SSE server
├── database.py            # MySQL pool + auto-instrumentation
├── config.py              # Settings loader from .env
├── auth.py                # API key middleware
├── create_log_table.py    # Creates activity_log table
├── test_server.py         # Full test suite
├── start.bat              # One-click Windows launcher
├── requirements.txt       # Python dependencies
├── .env.example           # Environment variable template
└── tools/
    ├── sql_executor.py    # execute_sql tool (main tool)
    ├── audit_log.py       # Session + audit log tools
    ├── materials.py       # Materials tools
    ├── vendors.py         # Vendor tools
    ├── purchase_orders.py # Purchase order tools
    └── inventory.py       # Inventory tools
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'fastmcp'`
```powershell
pip install -r requirements.txt
```

### `Can't connect to MySQL server`
- Open `services.msc` -> find **MySQL80** -> click **Start**
- Check `.env` credentials match your MySQL setup

### `OSError: [WinError 10048] Address already in use`
Another process is using port 8080. Kill all Python processes and retry:
```powershell
Get-Process python | Stop-Process -Force
python server.py
```

### `ERR_NGROK_334 — Tunnel already online`
Old ngrok session still active. Go to **dashboard.ngrok.com/tunnels** and stop the old tunnel, then restart ngrok.

### claude.ai shows "Could not connect to MCP server"
1. Check server is running: open `http://localhost:8080/sse` in browser
2. Check ngrok is running: open `http://localhost:4040`
3. In claude.ai connector settings, click the 3-dot menu -> **Refresh tools list**

### Tools not showing after server restart
In claude.ai, click the 3-dot menu on the connector -> **Refresh tools list**

---

## Running Tests

```powershell
# Test DB connection + all tool functions (server does not need to be running)
python test_server.py
```

---

## Tech Stack

- **[FastMCP](https://github.com/jlowin/fastmcp)** — MCP server framework
- **[mysql-connector-python](https://pypi.org/project/mysql-connector-python/)** — MySQL driver
- **[ngrok](https://ngrok.com)** — HTTP tunneling for public access
- **[python-dotenv](https://pypi.org/project/python-dotenv/)** — Environment config
- **[Starlette](https://www.starlette.io/)** — ASGI middleware for auth

---

## License

MIT License — free to use, modify, and distribute.
