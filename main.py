"""
Milk-Manager
------------
A simple Remote MCP server (built with FastMCP) to help manage daily milk
purchases: track quantity bought each day, the current milk price, and
generate monthly summaries / report data.

This is intentionally kept simple:
    - single user (no auth, no accounts)
    - synchronous sqlite3 (no async, no ORM)
    - one SQLite file, two tables
    - one file: main.py

Run it with:
    python main.py

The server will start on http://0.0.0.0:8000 using the streamable-http
transport.
"""

import sqlite3
import os
from calendar import month_name

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "milk_manager.db")

mcp = FastMCP("Milk-Manager")


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection():
    """
    Open a new connection to the SQLite database.

    A fresh connection is created per operation (simple and safe for a
    single-user, low-traffic server). `row_factory` is set so rows can be
    accessed like dictionaries.
    """
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys / basic sanity - not strictly needed here, but
    # a good habit.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Create the required tables if they do not already exist.
    Called once when the server starts.
    """
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS milk_entries (
                date     TEXT PRIMARY KEY,
                day      TEXT NOT NULL,
                quantity REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Small generic helpers
# ---------------------------------------------------------------------------

def error_response(message: str) -> dict:
    """Standard shape for an error JSON response."""
    return {"status": "error", "message": message}


def success_response(**fields) -> dict:
    """Standard shape for a success JSON response."""
    return {"status": "success", **fields}


def validate_year_month(year: int, month: int):
    """
    Basic sanity check for year/month values.
    Returns an error message string if invalid, otherwise None.
    """
    if not isinstance(year, int) or year < 1900 or year > 2200:
        return f"Invalid year: {year}"
    if not isinstance(month, int) or month < 1 or month > 12:
        return f"Invalid month: {month}. Must be between 1 and 12."
    return None


def month_range_pattern(year: int, month: int) -> str:
    """
    Build a SQL LIKE pattern (e.g. '2026-07-%') to match all dates
    belonging to the given year/month, since dates are stored as
    'YYYY-MM-DD' text.
    """
    return f"{year:04d}-{month:02d}-%"


def get_milk_price_value():
    """
    Internal helper: fetch the milk price as a float from the settings
    table. Returns None if it has not been set yet.
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", ("milk_price",)
        ).fetchone()
        return float(row["value"]) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool 1: set_milk_price
# ---------------------------------------------------------------------------

@mcp.tool()
def set_milk_price(price: float) -> dict:
    """
    Store (or update) the current price of one kilogram/litre of milk.

    Args:
        price: The new milk price. Must be a positive number.
    """
    try:
        if price is None or price <= 0:
            return error_response("Price must be a positive number.")

        conn = get_connection()
        try:
            # INSERT OR REPLACE keeps a single row for the 'milk_price' key.
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ('milk_price', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(price),),
            )
            conn.commit()
        finally:
            conn.close()

        return success_response(price=price)
    except Exception as exc:
        return error_response(f"Failed to set milk price: {exc}")


# ---------------------------------------------------------------------------
# Tool 2: get_milk_price
# ---------------------------------------------------------------------------

@mcp.tool()
def get_milk_price() -> dict:
    """Return the currently configured milk price."""
    try:
        price = get_milk_price_value()
        if price is None:
            return error_response("Milk price has not been set yet.")
        return success_response(price=price)
    except Exception as exc:
        return error_response(f"Failed to get milk price: {exc}")


# ---------------------------------------------------------------------------
# Tool 3: add_milk_entry
# ---------------------------------------------------------------------------

@mcp.tool()
def add_milk_entry(date: str, day: str, quantity: float) -> dict:
    """
    Add a new milk entry for a given date.

    Args:
        date: Date in 'YYYY-MM-DD' format, e.g. '2026-07-01'.
        day: Day of the week, e.g. 'Wednesday'.
        quantity: Quantity of milk purchased that day.
    """
    try:
        if not date or not day:
            return error_response("Both 'date' and 'day' are required.")
        if quantity is None or quantity < 0:
            return error_response("Quantity must be a non-negative number.")

        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT date FROM milk_entries WHERE date = ?", (date,)
            ).fetchone()
            if existing:
                return error_response(
                    f"An entry for {date} already exists. Use edit_milk_entry to modify it."
                )

            conn.execute(
                "INSERT INTO milk_entries (date, day, quantity) VALUES (?, ?, ?)",
                (date, day, quantity),
            )
            conn.commit()
        finally:
            conn.close()

        return success_response(date=date, day=day, quantity=quantity)
    except Exception as exc:
        return error_response(f"Failed to add milk entry: {exc}")


# ---------------------------------------------------------------------------
# Tool 4: edit_milk_entry
# ---------------------------------------------------------------------------

@mcp.tool()
def edit_milk_entry(date: str, quantity: float = None, day: str = None) -> dict:
    """
    Edit an existing milk entry. Only the fields provided are updated.

    Args:
        date: Date of the entry to edit ('YYYY-MM-DD').
        quantity: New quantity (optional).
        day: New day name (optional).
    """
    try:
        if not date:
            return error_response("'date' is required.")
        if quantity is None and day is None:
            return error_response("Provide at least one of 'quantity' or 'day' to update.")
        if quantity is not None and quantity < 0:
            return error_response("Quantity must be a non-negative number.")

        conn = get_connection()
        try:
            existing = conn.execute(
                "SELECT * FROM milk_entries WHERE date = ?", (date,)
            ).fetchone()
            if not existing:
                return error_response(f"No entry found for {date}.")

            new_quantity = quantity if quantity is not None else existing["quantity"]
            new_day = day if day is not None else existing["day"]

            conn.execute(
                "UPDATE milk_entries SET quantity = ?, day = ? WHERE date = ?",
                (new_quantity, new_day, date),
            )
            conn.commit()
        finally:
            conn.close()

        return success_response(date=date, day=new_day, quantity=new_quantity)
    except Exception as exc:
        return error_response(f"Failed to edit milk entry: {exc}")


# ---------------------------------------------------------------------------
# Tool 5: list_month_entries
# ---------------------------------------------------------------------------

@mcp.tool()
def list_month_entries(year: int, month: int) -> dict:
    """
    List every milk entry for the given month, ordered by date.

    Args:
        year: e.g. 2026
        month: 1-12
    """
    try:
        validation_error = validate_year_month(year, month)
        if validation_error:
            return error_response(validation_error)

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT date, day, quantity FROM milk_entries WHERE date LIKE ? ORDER BY date ASC",
                (month_range_pattern(year, month),),
            ).fetchall()
        finally:
            conn.close()

        entries = [dict(row) for row in rows]
        return success_response(year=year, month=month, entries=entries, count=len(entries))
    except Exception as exc:
        return error_response(f"Failed to list month entries: {exc}")


# ---------------------------------------------------------------------------
# Tool 6: monthly_summary
# ---------------------------------------------------------------------------

@mcp.tool()
def monthly_summary(year: int, month: int) -> dict:
    """
    Return a summary of milk purchases for the given month:
    total days with entries, total quantity, average quantity per day,
    and total amount (based on the currently configured milk price).

    Args:
        year: e.g. 2026
        month: 1-12
    """
    try:
        validation_error = validate_year_month(year, month)
        if validation_error:
            return error_response(validation_error)

        milk_price = get_milk_price_value()
        if milk_price is None:
            return error_response("Milk price has not been set yet. Use set_milk_price first.")

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT quantity FROM milk_entries WHERE date LIKE ?",
                (month_range_pattern(year, month),),
            ).fetchall()
        finally:
            conn.close()

        total_days_with_entries = len(rows)
        total_quantity = sum(row["quantity"] for row in rows)
        average_quantity_per_day = (
            total_quantity / total_days_with_entries if total_days_with_entries > 0 else 0
        )
        total_amount = total_quantity * milk_price

        return success_response(
            year=year,
            month=month,
            milk_price=milk_price,
            total_days_with_entries=total_days_with_entries,
            total_quantity=round(total_quantity, 3),
            average_quantity_per_day=round(average_quantity_per_day, 3),
            total_amount=round(total_amount, 2),
        )
    except Exception as exc:
        return error_response(f"Failed to compute monthly summary: {exc}")


# ---------------------------------------------------------------------------
# Tool 7: generate_monthly_report_data
# ---------------------------------------------------------------------------

@mcp.tool()
def generate_monthly_report_data(year: int, month: int) -> dict:
    """
    Return all the data needed to build a monthly milk report (e.g. a PDF
    to share with the milkman). This tool does NOT create a PDF itself -
    it just returns structured JSON data for that purpose.

    Args:
        year: e.g. 2026
        month: 1-12
    """
    try:
        validation_error = validate_year_month(year, month)
        if validation_error:
            return error_response(validation_error)

        milk_price = get_milk_price_value()
        if milk_price is None:
            return error_response("Milk price has not been set yet. Use set_milk_price first.")

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT date, day, quantity FROM milk_entries WHERE date LIKE ? ORDER BY date ASC",
                (month_range_pattern(year, month),),
            ).fetchall()
        finally:
            conn.close()

        entries = []
        total_quantity = 0.0
        for row in rows:
            amount = round(row["quantity"] * milk_price, 2)
            total_quantity += row["quantity"]
            entries.append(
                {
                    "date": row["date"],
                    "day": row["day"],
                    "quantity": row["quantity"],
                    "amount": amount,
                }
            )

        total_amount = round(total_quantity * milk_price, 2)
        average_quantity = round(total_quantity / len(entries), 3) if entries else 0

        return {
            "status": "success",
            "month": month_name[month],
            "year": year,
            "milk_price": milk_price,
            "entries": entries,
            "summary": {
                "total_quantity": round(total_quantity, 3),
                "average_quantity": average_quantity,
                "total_amount": total_amount,
            },
        }
    except Exception as exc:
        return error_response(f"Failed to generate monthly report data: {exc}")


# ---------------------------------------------------------------------------
# Tool 8: delete_month_entries (developer tool)
# ---------------------------------------------------------------------------

@mcp.tool()
def delete_month_entries(year: int, month: int) -> dict:
    """
    Developer tool: delete all milk entries belonging to the given month.

    Args:
        year: e.g. 2026
        month: 1-12
    """
    try:
        validation_error = validate_year_month(year, month)
        if validation_error:
            return error_response(validation_error)

        conn = get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM milk_entries WHERE date LIKE ?",
                (month_range_pattern(year, month),),
            )
            conn.commit()
            deleted_count = cursor.rowcount
        finally:
            conn.close()

        return success_response(year=year, month=month, deleted_count=deleted_count)
    except Exception as exc:
        return error_response(f"Failed to delete month entries: {exc}")


# ---------------------------------------------------------------------------
# Tool 9: delete_all_entries (developer tool)
# ---------------------------------------------------------------------------

@mcp.tool()
def delete_all_entries() -> dict:
    """
    Developer tool: delete every milk entry from the database.
    The milk price setting is left untouched.
    """
    try:
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM milk_entries")
            conn.commit()
            deleted_count = cursor.rowcount
        finally:
            conn.close()

        return success_response(deleted_count=deleted_count)
    except Exception as exc:
        return error_response(f"Failed to delete all entries: {exc}")


# ---------------------------------------------------------------------------
# Tool 10: reset_milk_price (developer tool)
# ---------------------------------------------------------------------------

@mcp.tool()
def reset_milk_price() -> dict:
    """
    Developer tool: reset the milk price back to 0, so a new price can be
    set from scratch using set_milk_price.
    """
    try:
        conn = get_connection()
        try:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES ('milk_price', '0')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
            conn.commit()
        finally:
            conn.close()

        return success_response(price=0)
    except Exception as exc:
        return error_response(f"Failed to reset milk price: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)