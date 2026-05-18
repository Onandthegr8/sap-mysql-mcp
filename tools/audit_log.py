"""Activity log / session audit tools for the SAP ERP MCP server."""

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
    async def start_session(token_id: str, user_id: str) -> str:
        """
        Record the start of a new user session in the activity log.

        Call this at the beginning of a work session to establish audit trail context.
        Creates a row with login_time = NOW() and logout_time = NULL (active session).

        Args:
            token_id : A unique identifier for this session, e.g. "tok-abc123" or "session-anand-001".
                       Used to link all subsequent log_command calls to this session.
            user_id  : Name or identifier of the person starting the session, e.g. "Anand" or "friend@email.com".

        Returns a confirmation with the session's log_id.
        """
        try:
            affected = await execute_write(
                "INSERT INTO activity_log (token_id, login_time, user_id) "
                "VALUES (%s, NOW(), %s)",
                (token_id.strip(), user_id.strip()),
            )
            if not affected:
                return "Failed to create session — no rows inserted."
            rows = await execute_query(
                "SELECT log_id, login_time FROM activity_log "
                "WHERE token_id = %s ORDER BY log_id DESC LIMIT 1",
                (token_id.strip(),),
            )
            r = rows[0] if rows else {}
            return (
                f"Session started.\n"
                f"  Log ID     : {r.get('log_id', 'N/A')}\n"
                f"  Token ID   : {token_id}\n"
                f"  User ID    : {user_id}\n"
                f"  Login Time : {r.get('login_time', 'N/A')}\n"
                f"  Status     : ACTIVE\n"
            )
        except Exception as exc:
            logger.error(f"start_session: {exc}")
            return f"Error starting session: {exc}"

    @mcp.tool()
    async def end_session(token_id: str) -> str:
        """
        Record the end of an active session by setting its logout_time to NOW().

        Call this when wrapping up a work session. Updates all open rows for
        the given token_id that have logout_time = NULL.

        Args:
            token_id: The session token used in start_session, e.g. "tok-abc123".

        Returns confirmation of how many rows were updated.
        """
        try:
            # Check if there are open sessions for this token
            open_rows = await execute_query(
                "SELECT COUNT(*) AS cnt FROM activity_log "
                "WHERE token_id = %s AND logout_time IS NULL",
                (token_id.strip(),),
            )
            count = open_rows[0]["cnt"] if open_rows else 0
            if count == 0:
                return f"No active session found for token '{token_id}'."

            affected = await execute_write(
                "UPDATE activity_log SET logout_time = NOW() "
                "WHERE token_id = %s AND logout_time IS NULL",
                (token_id.strip(),),
            )
            return (
                f"Session ended.\n"
                f"  Token ID     : {token_id}\n"
                f"  Rows Updated : {affected}\n"
                f"  Status       : CLOSED\n"
            )
        except Exception as exc:
            logger.error(f"end_session: {exc}")
            return f"Error ending session: {exc}"

    @mcp.tool()
    async def log_command(
        token_id: str,
        user_id: str,
        affected_table: str,
        command_statement: str,
        duration: float,
    ) -> str:
        """
        Log a single command/operation to the activity log.

        Use this to record what action was performed, which SAP table it touched,
        and how long it took. Each call creates one row with login_time = NOW().

        Args:
            token_id          : Session token linking this command to its session, e.g. "tok-abc123".
            user_id           : Who ran the command, e.g. "Anand".
            affected_table    : Which SAP table was accessed: "materials", "vendors",
                                "purchase_orders", "inventory", or "activity_log".
            command_statement : Description of what was run, e.g. "check_stock('MAT-001')"
                                or "create_purchase_order(vendor='V001', material='MAT-003', qty=100)".
            duration          : Execution time in milliseconds (e.g. 42.5).

        Returns a confirmation with the new log entry's ID.
        """
        try:
            affected = await execute_write(
                "INSERT INTO activity_log "
                "(token_id, login_time, user_id, affected_table, command_statement, duration) "
                "VALUES (%s, NOW(), %s, %s, %s, %s)",
                (
                    token_id.strip(),
                    user_id.strip(),
                    affected_table.strip() if affected_table else None,
                    command_statement.strip() if command_statement else None,
                    round(duration, 3),
                ),
            )
            if not affected:
                return "Failed to log command — no rows inserted."
            rows = await execute_query(
                "SELECT log_id, login_time FROM activity_log "
                "WHERE token_id = %s ORDER BY log_id DESC LIMIT 1",
                (token_id.strip(),),
            )
            log_id = rows[0]["log_id"] if rows else "N/A"
            return (
                f"Command logged.\n"
                f"  Log ID    : {log_id}\n"
                f"  Token     : {token_id}\n"
                f"  User      : {user_id}\n"
                f"  Table     : {affected_table}\n"
                f"  Command   : {command_statement[:80]}{'...' if len(command_statement) > 80 else ''}\n"
                f"  Duration  : {duration:.1f} ms\n"
            )
        except Exception as exc:
            logger.error(f"log_command: {exc}")
            return f"Error logging command: {exc}"

    @mcp.tool()
    async def get_activity_log(
        limit: int = 50,
        user_id: str = "",
        token_id: str = "",
    ) -> str:
        """
        Retrieve recent entries from the activity log.

        Use this to audit who did what, when, and how long it took.
        Optionally filter by user or session token.

        Args:
            limit    : Maximum number of rows to return (default 50, max 500).
            user_id  : Filter to a specific user. Leave blank for all users.
            token_id : Filter to a specific session token. Leave blank for all sessions.

        Returns a table sorted by login_time descending (most recent first).
        """
        try:
            limit = min(max(1, limit), 500)
            conditions = []
            params: list = []

            if user_id.strip():
                conditions.append("user_id = %s")
                params.append(user_id.strip())
            if token_id.strip():
                conditions.append("token_id = %s")
                params.append(token_id.strip())

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params.append(limit)

            rows = await execute_query(
                f"SELECT log_id, token_id, user_id, login_time, logout_time, "
                f"affected_table, command_statement, duration, "
                f"field_changed, value_before, value_after "
                f"FROM activity_log {where} "
                f"ORDER BY log_id DESC LIMIT %s",
                tuple(params),
            )
            if not rows:
                return "No activity log entries found."

            data = []
            for r in rows:
                cmd = str(r["command_statement"] or "")
                cmd_short = cmd[:30] + "..." if len(cmd) > 30 else cmd
                duration_str = f"{float(r['duration']):.1f}" if r["duration"] is not None else ""
                data.append([
                    str(r["log_id"]),
                    r["token_id"][:12] if r["token_id"] else "",
                    r["user_id"],
                    str(r["login_time"]),
                    str(r["logout_time"]) if r["logout_time"] else "ACTIVE",
                    r["affected_table"] or "",
                    cmd_short,
                    duration_str,
                    r["field_changed"] or "",
                    str(r["value_before"]) if r["value_before"] is not None else "",
                    str(r["value_after"]) if r["value_after"] is not None else "",
                ])

            filter_desc = ""
            if user_id.strip():
                filter_desc += f", user={user_id}"
            if token_id.strip():
                filter_desc += f", token={token_id}"

            return (
                f"Activity Log — {len(rows)} row(s){filter_desc}\n\n"
                + _fmt_table(
                    ["ID", "Token", "User", "Login Time", "Logout Time", "Table",
                     "Command", "ms", "Field Changed", "Value Before", "Value After"],
                    data,
                )
            )
        except Exception as exc:
            logger.error(f"get_activity_log: {exc}")
            return f"Error retrieving activity log: {exc}"

    @mcp.tool()
    async def get_active_sessions() -> str:
        """
        Show all currently active sessions (logout_time IS NULL).

        Use this to see who is currently logged in / working on the SAP ERP system.
        Active means start_session was called but end_session has not been called yet.

        Returns a table of open sessions sorted by login_time descending.
        """
        try:
            rows = await execute_query(
                "SELECT log_id, token_id, user_id, login_time, "
                "TIMESTAMPDIFF(MINUTE, login_time, NOW()) AS duration_min "
                "FROM activity_log "
                "WHERE logout_time IS NULL "
                "ORDER BY login_time DESC"
            )
            if not rows:
                return "No active sessions. All users have logged out."
            data = [
                [
                    str(r["log_id"]),
                    r["token_id"],
                    r["user_id"],
                    str(r["login_time"]),
                    f"{r['duration_min']} min",
                ]
                for r in rows
            ]
            return (
                f"Active Sessions — {len(rows)} session(s) currently open\n\n"
                + _fmt_table(["Log ID", "Token", "User", "Login Time", "Open For"], data)
            )
        except Exception as exc:
            logger.error(f"get_active_sessions: {exc}")
            return f"Error retrieving active sessions: {exc}"

    @mcp.tool()
    async def clear_old_logs(days: int = 30) -> str:
        """
        Delete activity log entries older than a specified number of days.

        Use this for log housekeeping, e.g. "clear logs older than 90 days".
        Only removes rows where login_time is before the cutoff — active sessions
        (logout_time IS NULL) are also removed if their login_time is old enough.

        Args:
            days: Delete rows with login_time older than this many days (default 30).
                  Must be >= 1.

        Returns count of deleted rows.
        """
        try:
            if days < 1:
                return "Error: days must be >= 1."

            # Count before deleting
            count_rows = await execute_query(
                "SELECT COUNT(*) AS cnt FROM activity_log "
                "WHERE login_time < NOW() - INTERVAL %s DAY",
                (days,),
            )
            count = count_rows[0]["cnt"] if count_rows else 0

            if count == 0:
                return f"No log entries older than {days} day(s) found. Nothing deleted."

            affected = await execute_write(
                "DELETE FROM activity_log WHERE login_time < NOW() - INTERVAL %s DAY",
                (days,),
            )
            return (
                f"Old logs cleared.\n"
                f"  Cutoff   : older than {days} day(s)\n"
                f"  Deleted  : {affected} row(s)\n"
            )
        except Exception as exc:
            logger.error(f"clear_old_logs: {exc}")
            return f"Error clearing old logs: {exc}"
