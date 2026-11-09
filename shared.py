import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import calendar
import copy
import json
import re
import threading
import ctypes
import os
import queue
import sys

import mysql.connector
from mysql.connector import Error

import pyautogui
import pyperclip


# ============================================================
# CONFIGURATION
# ============================================================

BASE = Path(__file__).resolve().parent
INK_FILE = BASE / "ink.txt"

# Existing JSON file is no longer used for database storage.
# Keep food_bills.json as a backup of your old bills.

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "billing_app",
    "database": "meqeta_billing",
    "connection_timeout": 5
}

# Internal automation timings
INTERNAL_FIELD_DELAY_MS = 2000
INTERNAL_DROPDOWN_HOLD_MS = 350

# External automation timings
TARGET_DELAY_MS = 3000
EXTERNAL_FIELD_DELAY = 2
EXTERNAL_DROPDOWN_DELAY = 0.4

EXTERNAL_NEXT_KEY = "enter"

PMS_FIELDS = (
    "bill",
    "date",
    "waiter",
    "service",
    "kot"
)

DROPDOWN_FIELDS = (
    "date",
    "waiter",
    "service"
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_db_connection():
    """
    Connect to the existing MariaDB database.

    Password comes from the environment variable:
        MEQETA_DB_PASSWORD
    """

    password = os.environ.get("MEQETA_DB_PASSWORD")

    if not password:
        raise RuntimeError(
            "Database password is not configured.\n\n"
            "In PowerShell, run:\n"
            '$env:MEQETA_DB_PASSWORD = "YOUR_PASSWORD"\n\n'
            "Then start this application from that terminal."
        )

    config = dict(DB_CONFIG)
    config["password"] = password

    return mysql.connector.connect(**config)


def test_database_connection():
    """
    Test connectivity and verify required tables.
    """

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("SHOW TABLES")
        tables = {
            row[0]
            for row in cursor.fetchall()
        }

        required = {"bills", "bill_items"}

        missing = required - tables

        if missing:
            raise RuntimeError(
                "Missing database tables: "
                + ", ".join(sorted(missing))
            )

        print("MariaDB connected successfully!")
        print("Database: meqeta_billing")
        print("Tables: bills, bill_items")

        return True

    except (Error, RuntimeError) as error:
        print("Database connection failed:", error)
        return False

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None:
            connection.close()


# ============================================================
# WINDOWS ACTIVE WINDOW DETECTION
# ============================================================

def active_window_handle():
    try:
        return ctypes.windll.user32.GetForegroundWindow()

    except (AttributeError, OSError):
        return None


def root_window_handle(hwnd):
    if not hwnd or sys.platform != "win32":
        return None

    try:
        return ctypes.windll.user32.GetAncestor(hwnd, 2)

    except (AttributeError, OSError):
        return None


# ============================================================
# GENERAL HELPERS
# ============================================================

def num(value):
    try:
        result = Decimal(str(value).strip() or "0")

        if not result.is_finite() or result < 0:
            return Decimal("0")

        return result

    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def money(value):
    return str(
        Decimal(value).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    )


def normalize_date(value):
    value = str(value).strip()

    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d"
    ):
        try:
            return datetime.strptime(
                value, fmt
            ).strftime("%d/%m/%Y")

        except ValueError:
            continue

    raise ValueError(
        f"Invalid date: {value}. Use DD/MM/YYYY."
    )


def optional_sql_date(value):
    """
    Convert a date string to a Python date,
    or return None for an empty date.
    """

    value = str(value).strip()

    if not value:
        return None

    normalized = normalize_date(value)

    return datetime.strptime(
        normalized, "%d/%m/%Y"
    ).date()


def sql_date_to_text(value):
    if value is None:
        return ""

    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")

    return normalize_date(value)


def generate_date_options():
    today = datetime.now()
    dates = []

    for offset in (-1, 0, 1):
        month_index = (
            today.year * 12
            + today.month - 1
            + offset
        )

        year, zero_month = divmod(month_index, 12)
        month = zero_month + 1

        days = calendar.monthrange(year, month)[1]

        for day_number in range(1, days + 1):
            dates.append(
                f"{day_number:02d}/{month:02d}/{year}"
            )

    return dates


# ============================================================
# READ ink.txt
# ============================================================

def read_ink():
    """
    Supported ink.txt:

    bill=1001
    date=05/11/2026
    waiter=AKASH
    service=ROOM SERVICE
    kot=501
    """

    if not INK_FILE.exists():
        raise FileNotFoundError(
            f"ink.txt not found:\n{INK_FILE}"
        )

    content = INK_FILE.read_text(
        encoding="utf-8-sig"
    ).strip()

    if not content:
        raise ValueError("ink.txt is empty.")

    aliases = {
        "bill": "bill",
        "billno": "bill",
        "billnumber": "bill",
        "billid": "bill",

        "date": "date",
        "billdate": "date",

        "waiter": "waiter",
        "waitername": "waiter",

        "service": "service",
        "servicetype": "service",
        "sertype": "service",

        "kot": "kot",
        "kotno": "kot",
        "kotnumber": "kot"
    }

    data = {}

    def add_value(raw_key, value):
        key = re.sub(
            r"[^a-z0-9]",
            "",
            str(raw_key).lower()
        )

        mapped = aliases.get(key)

        if mapped and value is not None:
            value = str(value).strip()

            if value:
                data[mapped] = value

    if content.startswith("{"):
        try:
            parsed = json.loads(content)

            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    add_value(key, value)

        except json.JSONDecodeError:
            pass

    if not data:
        for line in content.splitlines():
            line = line.strip()

            if not line or line.startswith(
                ("#", ";", "//")
            ):
                continue

            match = re.match(
                r"^([^=:]+?)\s*[:=]\s*(.*)$",
                line
            )

            if match:
                add_value(
                    match.group(1),
                    match.group(2)
                )

    missing = [
        key for key in PMS_FIELDS
        if not data.get(key)
    ]

    if missing:
        raise ValueError(
            "Missing ink.txt fields: "
            + ", ".join(missing)
        )

    data["date"] = normalize_date(data["date"])

    return data


# ============================================================
# MAIN APPLICATION
# ============================================================

