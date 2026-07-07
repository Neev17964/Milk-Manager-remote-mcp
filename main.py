"""
Milk Manager MCP Server
-----------------------

A simple Remote MCP Server built using FastMCP for a single user
(my mother) to manage daily milk purchases.

Features:
- Store daily milk quantity
- Store milk price
- Monthly summaries
- Monthly report data
- Delete month
- Delete all entries

Author: Neev Sharma
"""

import sqlite3
import tempfile
import os
from calendar import month_name

from fastmcp import FastMCP

# --------------------------------------------------
# Configuration
# --------------------------------------------------

TEMP_DIR = tempfile.gettempdir()

DB_PATH = os.path.join(TEMP_DIR, "milk_manager.db")

print(f"Database Path: {DB_PATH}")

mcp = FastMCP("Milk-Manager")


# --------------------------------------------------
# Database Initialization
# --------------------------------------------------

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db():

    try:

        conn = get_connection()

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS milk_entries(

                date TEXT PRIMARY KEY,

                day TEXT NOT NULL,

                quantity REAL NOT NULL

            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings(

                key TEXT PRIMARY KEY,

                value TEXT NOT NULL

            )
            """
        )

        # Check write permissions

        conn.execute(
            """
            INSERT OR IGNORE INTO settings(key,value)

            VALUES('__test__','1')
            """
        )

        conn.execute(
            """
            DELETE FROM settings

            WHERE key='__test__'
            """
        )

        conn.commit()

        print("Database initialized successfully.")

    except Exception as e:

        print(f"Database initialization failed: {e}")

        raise

    finally:

        conn.close()


init_db()

# --------------------------------------------------
# Helper Functions
# --------------------------------------------------


def success_response(**kwargs):

    return {
        "status": "success",
        **kwargs
    }


def error_response(message):

    return {
        "status": "error",
        "message": message
    }


def validate_year_month(year, month):

    if year < 2000 or year > 2200:
        return "Invalid year."

    if month < 1 or month > 12:
        return "Invalid month."

    return None


def month_pattern(year, month):

    return f"{year:04d}-{month:02d}-%"


def get_milk_price_value():

    conn = get_connection()

    try:

        row = conn.execute(
            """
            SELECT value

            FROM settings

            WHERE key='milk_price'
            """
        ).fetchone()

        if row is None:
            return None

        return float(row["value"])

    finally:

        conn.close()


# --------------------------------------------------
# Tool 1
# Set Milk Price
# --------------------------------------------------

@mcp.tool()
def set_milk_price(price: float):

    """
    Save or update milk price.
    """

    try:

        if price <= 0:
            return error_response(
                "Milk price must be greater than zero."
            )

        conn = get_connection()

        conn.execute(
            """
            INSERT INTO settings(key,value)

            VALUES('milk_price',?)

            ON CONFLICT(key)

            DO UPDATE SET

            value=excluded.value
            """,
            (str(price),)
        )

        conn.commit()

        conn.close()

        return success_response(
            price=price
        )

    except Exception as e:

        if "readonly" in str(e).lower():

            return error_response(
                "Database is read only."
            )

        return error_response(str(e))


# --------------------------------------------------
# Tool 2
# Get Milk Price
# --------------------------------------------------

@mcp.tool()
def get_milk_price():

    """
    Return currently configured milk price.
    """

    try:

        price = get_milk_price_value()

        if price is None:

            return error_response(
                "Milk price has not been set yet."
            )

        return success_response(

            milk_price=price

        )

    except Exception as e:

        return error_response(str(e))


# --------------------------------------------------
# Tool 3
# Add Milk Entry
# --------------------------------------------------

@mcp.tool()
def add_milk_entry(
    date: str,
    day: str,
    quantity: float
):

    """
    Add a milk entry.

    Example:

    date="2026-07-07"

    day="Tuesday"

    quantity=2
    """

    try:

        if quantity < 0:
            return error_response(
                "Quantity cannot be negative."
            )

        conn = get_connection()

        existing = conn.execute(
            """
            SELECT date

            FROM milk_entries

            WHERE date=?
            """,
            (date,)
        ).fetchone()

        if existing:

            conn.close()

            return error_response(
                f"Entry already exists for {date}. Use edit_milk_entry."
            )

        conn.execute(
            """
            INSERT INTO milk_entries(

                date,

                day,

                quantity

            )

            VALUES(?,?,?)
            """,
            (
                date,
                day,
                quantity
            )
        )

        conn.commit()

        conn.close()

        return success_response(

            date=date,

            day=day,

            quantity=quantity

        )

    except Exception as e:

        if "readonly" in str(e).lower():

            return error_response(
                "Database is read only."
            )

        return error_response(str(e))


# --------------------------------------------------
# Tool 4
# Edit Milk Entry
# --------------------------------------------------

@mcp.tool()
def edit_milk_entry(

    date: str,

    quantity: float = None,

    day: str = None

):

    """
    Edit an existing milk entry.
    """

    try:

        conn = get_connection()

        row = conn.execute(
            """
            SELECT *

            FROM milk_entries

            WHERE date=?
            """,
            (date,)
        ).fetchone()

        if row is None:

            conn.close()

            return error_response(
                "Entry not found."
            )

        new_quantity = quantity

        if quantity is None:
            new_quantity = row["quantity"]

        new_day = day

        if day is None:
            new_day = row["day"]

        conn.execute(
            """
            UPDATE milk_entries

            SET

            quantity=?,

            day=?

            WHERE date=?
            """,
            (
                new_quantity,
                new_day,
                date
            )
        )

        conn.commit()

        conn.close()

        return success_response(

            date=date,

            quantity=new_quantity,

            day=new_day

        )

    except Exception as e:

        if "readonly" in str(e).lower():

            return error_response(
                "Database is read only."
            )

        return error_response(str(e))


# --------------------------------------------------
# Tool 5
# List Month Entries
# --------------------------------------------------

@mcp.tool()
def list_month_entries(

    year: int,

    month: int

):

    """
    Return every milk entry for a month.
    """

    try:

        error = validate_year_month(
            year,
            month
        )

        if error:
            return error_response(error)

        conn = get_connection()

        rows = conn.execute(
            """
            SELECT

                date,

                day,

                quantity

            FROM milk_entries

            WHERE date LIKE ?

            ORDER BY date ASC
            """,
            (
                month_pattern(
                    year,
                    month
                ),
            )
        ).fetchall()

        conn.close()

        entries = []

        for row in rows:

            entries.append(

                {

                    "date": row["date"],

                    "day": row["day"],

                    "quantity": row["quantity"]

                }

            )

        return success_response(

            month=month,

            year=year,

            total_entries=len(entries),

            entries=entries

        )

    except Exception as e:

        return error_response(str(e))
    
# --------------------------------------------------
# Tool 6
# Monthly Summary
# --------------------------------------------------

@mcp.tool()
def monthly_summary(year: int, month: int):

    try:

        error = validate_year_month(year, month)

        if error:
            return error_response(error)

        milk_price = get_milk_price_value()

        if milk_price is None:
            return error_response(
                "Milk price has not been set."
            )

        conn = get_connection()

        rows = conn.execute(
            """
            SELECT quantity

            FROM milk_entries

            WHERE date LIKE ?
            """,
            (month_pattern(year, month),)
        ).fetchall()

        conn.close()

        total_days = len(rows)

        total_quantity = sum(
            row["quantity"] for row in rows
        )

        average_quantity = (
            total_quantity / total_days
            if total_days
            else 0
        )

        total_amount = total_quantity * milk_price

        return success_response(

            month=month,

            year=year,

            milk_price=milk_price,

            total_days_with_entries=total_days,

            total_quantity=round(total_quantity, 2),

            average_quantity_per_day=round(
                average_quantity,
                2
            ),

            total_amount=round(total_amount, 2)

        )

    except Exception as e:

        return error_response(str(e))


# --------------------------------------------------
# Tool 7
# Generate Monthly Report Data
# --------------------------------------------------

@mcp.tool()
def generate_monthly_report_data(
    year: int,
    month: int
):

    try:

        error = validate_year_month(
            year,
            month
        )

        if error:
            return error_response(error)

        milk_price = get_milk_price_value()

        if milk_price is None:
            return error_response(
                "Milk price has not been set."
            )

        conn = get_connection()

        rows = conn.execute(
            """
            SELECT

            date,

            day,

            quantity

            FROM milk_entries

            WHERE date LIKE ?

            ORDER BY date ASC
            """,
            (
                month_pattern(
                    year,
                    month
                ),
            )
        ).fetchall()

        conn.close()

        entries = []

        total_quantity = 0

        for row in rows:

            amount = round(
                row["quantity"] * milk_price,
                2
            )

            total_quantity += row["quantity"]

            entries.append(

                {

                    "date": row["date"],

                    "day": row["day"],

                    "quantity": row["quantity"],

                    "amount": amount

                }

            )

        total_amount = round(
            total_quantity * milk_price,
            2
        )

        average_quantity = (

            round(
                total_quantity / len(entries),
                2
            )

            if entries

            else 0

        )

        return {

            "status": "success",

            "month": month_name[month],

            "year": year,

            "milk_price": milk_price,

            "entries": entries,

            "summary": {

                "total_quantity": round(
                    total_quantity,
                    2
                ),

                "average_quantity": average_quantity,

                "total_amount": total_amount

            }

        }

    except Exception as e:

        return error_response(str(e))


# --------------------------------------------------
# Tool 8
# Delete Month Entries
# --------------------------------------------------

@mcp.tool()
def delete_month_entries(
    year: int,
    month: int
):

    try:

        error = validate_year_month(
            year,
            month
        )

        if error:
            return error_response(error)

        conn = get_connection()

        cur = conn.execute(
            """
            DELETE

            FROM milk_entries

            WHERE date LIKE ?
            """,
            (
                month_pattern(
                    year,
                    month
                ),
            )
        )

        conn.commit()

        deleted = cur.rowcount

        conn.close()

        return success_response(

            deleted_entries=deleted,

            month=month,

            year=year

        )

    except Exception as e:

        return error_response(str(e))


# --------------------------------------------------
# Tool 9
# Delete All Entries
# --------------------------------------------------

@mcp.tool()
def delete_all_entries():

    try:

        conn = get_connection()

        cur = conn.execute(

            "DELETE FROM milk_entries"

        )

        conn.commit()

        deleted = cur.rowcount

        conn.close()

        return success_response(

            deleted_entries=deleted

        )

    except Exception as e:

        return error_response(str(e))


# --------------------------------------------------
# Tool 10
# Reset Milk Price
# --------------------------------------------------

@mcp.tool()
def reset_milk_price():

    try:

        conn = get_connection()

        conn.execute(

            """
            INSERT INTO settings(key,value)

            VALUES('milk_price','0')

            ON CONFLICT(key)

            DO UPDATE SET

            value='0'
            """

        )

        conn.commit()

        conn.close()

        return success_response(

            milk_price=0

        )

    except Exception as e:

        return error_response(str(e))


# --------------------------------------------------
# Start Server
# --------------------------------------------------

if __name__ == "__main__":

    init_db()

    mcp.run(

        transport="streamable-http",

        host="0.0.0.0",

        port=8000

    )
