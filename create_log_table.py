"""
Create (or verify) the activity_log table in the sap_erp database.

Run standalone:
    python create_log_table.py

Also imported by server.py at startup via ensure_log_table().
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

logger = logging.getLogger(__name__)

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS activity_log (
    log_id            INT AUTO_INCREMENT PRIMARY KEY,
    token_id          VARCHAR(100)   NOT NULL,
    login_time        DATETIME       NOT NULL,
    logout_time       DATETIME       DEFAULT NULL,
    user_id           VARCHAR(100)   NOT NULL,
    affected_table    VARCHAR(100)   DEFAULT NULL,
    command_statement TEXT           DEFAULT NULL,
    duration          DECIMAL(10,3)  DEFAULT NULL
)
"""


async def ensure_log_table() -> None:
    """Create the activity_log table if it doesn't already exist."""
    from database import initialize_pool, execute_write
    await initialize_pool()
    await execute_write(_CREATE_SQL)
    logger.info("activity_log table ensured.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    print("Creating activity_log table...")
    try:
        asyncio.run(ensure_log_table())
        print("  [OK] activity_log table is ready.")
    except Exception as exc:
        print(f"  [ERROR] {exc}")
        print("  Make sure MySQL is running and .env credentials are correct.")
        sys.exit(1)
