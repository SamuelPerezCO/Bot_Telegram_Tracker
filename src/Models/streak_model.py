import sqlite3
import os
from datetime import date , timedelta

DB_PATH = os.path.join(os.path.dirname(__file__) , ".." , "streaks.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def create_table():
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
    connection = get_connection()
    row = connection.execute("SELECT current_streak FROM users WHERE user_id = ?" , (user_id,)).fetchone()
    connection.close()
    if row is None:
        return 0
    return row[0]


def report_day(user_id , username):
    """Returns (streak, counted). counted is False if the user already reported today."""
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
    connection = get_connection()
    connection.execute(
        """INSERT INTO users (user_id , username , current_streak , last_report) VALUES (? , ? , 0 , NULL)
           ON CONFLICT(user_id) DO UPDATE SET current_streak = 0 , last_report = NULL""" ,
        (user_id , username)
    )
    connection.commit()
    connection.close()
