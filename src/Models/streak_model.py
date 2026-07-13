"""SQLite persistence for user streaks.

This module owns everything related to storing streaks: the database
connection, the table schema and the streak rules (continue, restart,
already-reported). Controllers should never touch SQL directly.
"""

import sqlite3
import os
from datetime import date , timedelta

DB_PATH = os.path.join(os.path.dirname(__file__) , ".." , "streaks.db")


def get_connection():
    """Opens a connection to the streaks database.

    Returns:
        sqlite3.Connection: An open connection. The caller is responsible
        for closing it.
    """
    return sqlite3.connect(DB_PATH)


def create_table():
    """Creates the users table if it does not exist yet.

    Must be called once at startup, before the bot starts handling
    updates. Safe to call on every run thanks to IF NOT EXISTS.
    """
    connection = get_connection()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            current_streak INTEGER DEFAULT 0,
            last_report TEXT
        )
    """)
    connection.commit()
    connection.close()


def get_streak(user_id):
    """Reads the current streak of a user.

    Args:
        user_id (int): Telegram user id.

    Returns:
        int: The current streak, or 0 if the user has never reported.
    """
    connection = get_connection()
    row = connection.execute("SELECT current_streak FROM users WHERE user_id = ?" , (user_id,)).fetchone()
    connection.close()
    if row is None:
        return 0
    return row[0]


def report_day(user_id , username):
    """Registers today as a completed day and updates the streak.

    The streak rules are:
        - Last report was today: nothing changes, the report does not count.
        - Last report was yesterday: the streak continues (+1).
        - Last report is older, or the user is new: the streak restarts at 1.

    Args:
        user_id (int): Telegram user id.
        username (str): Telegram username, stored only for readability.

    Returns:
        tuple[int, bool]: The streak after the report, and whether the
        report counted (False means the user had already reported today).
    """
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    connection = get_connection()
    row = connection.execute("SELECT current_streak , last_report FROM users WHERE user_id = ?" , (user_id,)).fetchone()

    if row is None:
        new_streak = 1
        connection.execute(
            "INSERT INTO users (user_id , username , current_streak , last_report) VALUES (? , ? , ? , ?)" ,
            (user_id , username , new_streak , today)
        )
    else:
        current_streak , last_report = row
        if last_report == today:
            connection.close()
            return current_streak , False
        elif last_report == yesterday:
            new_streak = current_streak + 1
        else:
            new_streak = 1
        connection.execute(
            "UPDATE users SET current_streak = ? , last_report = ? , username = ? WHERE user_id = ?" ,
            (new_streak , today , username , user_id)
        )

    connection.commit()
    connection.close()
    return new_streak , True


def reset_streak(user_id , username):
    """Sets the user's streak back to 0 (they lost).

    Creates the user row if it does not exist yet.

    Args:
        user_id (int): Telegram user id.
        username (str): Telegram username, stored only for readability.
    """
    connection = get_connection()
    connection.execute(
        """INSERT INTO users (user_id , username , current_streak , last_report) VALUES (? , ? , 0 , NULL)
           ON CONFLICT(user_id) DO UPDATE SET current_streak = 0 , last_report = NULL""" ,
        (user_id , username)
    )
    connection.commit()
    connection.close()
