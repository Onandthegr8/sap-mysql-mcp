"""
Central configuration — all values loaded from .env via python-dotenv.
Import individual names wherever needed; never import os.getenv directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ───────────────────────────────────────────────────────────────
DB_HOST: str       = os.getenv("DB_HOST", "localhost")
DB_PORT: int       = int(os.getenv("DB_PORT", "3306"))
DB_USER: str       = os.getenv("DB_USER", "root")
DB_PASSWORD: str   = os.getenv("DB_PASSWORD", "1234")
DB_NAME: str       = os.getenv("DB_NAME", "sap_erp")
DB_POOL_SIZE: int  = int(os.getenv("DB_POOL_SIZE", "5"))

# ── Server ─────────────────────────────────────────────────────────────────
MCP_HOST: str = os.getenv("MCP_HOST", "0.0.0.0")
MCP_PORT: int = int(os.getenv("MCP_PORT", "8000"))

# ── Auth ───────────────────────────────────────────────────────────────────
_raw_key      = os.getenv("API_KEY", "").strip()
API_KEY: str | None = _raw_key if _raw_key else None   # None  →  auth disabled

# ── General ────────────────────────────────────────────────────────────────
ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL: str   = os.getenv("LOG_LEVEL", "INFO").upper()
