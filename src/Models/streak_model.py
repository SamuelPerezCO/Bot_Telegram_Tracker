"""Streak and goals storage inside Telegram itself (no database).

Telegram bots cannot read the chat history, but they CAN read the
chat's pinned message through get_chat. This module uses that: the
bot keeps each user's state in a pinned status message, so the data
lives in Telegram, survives restarts/redeploys and needs no database.

The pinned message looks like this once everything is filled in:

    🔥 Streak: 3 (last report: 2026-08-09)
    🎯 Goals (2, period: 7 days)
    1. Read one chapter
    2. Go to the gym

While the user is still answering the goals questions, the header also
carries the step the bot is waiting for, because nothing can be kept in
memory between two updates on a serverless host:

    🎯 Goals (4, period: pending) [setup: goal]
"""

import os
import re
from datetime import datetime , timedelta
from zoneinfo import ZoneInfo


# Limits for what the user is allowed to type, so a single message can
# never grow past what Telegram accepts as a message text.
MAX_GOALS = 10
MAX_GOAL_LENGTH = 200

# Steps of the goals questionnaire, stored in the pinned message:
#   "count"  -> waiting for how many goals the user wants
#   "goal"   -> waiting for the text of the next goal
#   "period" -> waiting for the time to complete all of them
#   None     -> nothing pending, the user is in the normal menu
SETUP_COUNT = "count"
SETUP_GOAL = "goal"
SETUP_PERIOD = "period"

# How many days each unit is worth when the user writes "2 weeks".
_PERIOD_UNITS = {"day": 1 , "days": 1 , "week": 7 , "weeks": 7 , "month": 30 , "months": 30}

_STREAK_PATTERN = re.compile(r"Streak: (\d+) \(last report: (\S+)\)")
_GOALS_PATTERN = re.compile(r"Goals \((\d+), period: ([^)]+)\)(?: \[setup: (\w+)\])?")
_GOAL_LINE_PATTERN = re.compile(r"^\d+\. (.+)$" , re.MULTILINE)
_PERIOD_PATTERN = re.compile(r"^(\d+)\s*([a-z]+)?$" , re.IGNORECASE)


def _today():
    """Current date in the users' timezone, not the server's.

    The server may run in another timezone (Vercel uses UTC), so there
    date.today() already flips to the next day during the evening here.
    The timezone comes from the TIMEZONE environment variable and
    defaults to America/Bogota.

    Returns:
        datetime.date: Today's date for the users.
    """
    timezone = ZoneInfo(os.getenv("TIMEZONE" , "America/Bogota"))
    return datetime.now(timezone).date()


def _empty_state():
    """Builds the state of a user who has never used the bot.

    Returns:
        dict: A state with an empty streak and no goals.
    """
    return {
        "streak": 0 ,
        "last_report": "none" ,
        "goal_count": 0 ,
        "goals": [] ,
        "period_days": None ,
        "setup": None ,
    }


def parse_period(text):
    """Reads a period of time written by the user.

    Accepts a plain number of days ("7") or a number with a unit
    ("7 days", "2 weeks", "1 month").

    Args:
        text (str): What the user typed.

    Returns:
        int | None: The period in days, or None if it is not a valid
        period.
    """
    match = _PERIOD_PATTERN.match((text or "").strip())
    if match is None:
        return None

    amount = int(match.group(1))
    unit = (match.group(2) or "days").lower()
    if amount < 1 or unit not in _PERIOD_UNITS:
        return None

    days = amount * _PERIOD_UNITS[unit]
    return days if days <= 365 else None


def _format_status(state):
    """Builds the text of the pinned status message.

    Args:
        state (dict): The state to store.

    Returns:
        str: The status message text.
    """
    lines = [f"🔥 Streak: {state['streak']} (last report: {state['last_report']})"]

    # The goals block is only written once the user has started adding
    # goals, so an untouched status stays as short as it used to be.
    if state["goal_count"] or state["goals"] or state["setup"]:
        period = f"{state['period_days']} days" if state["period_days"] else "pending"
        header = f"🎯 Goals ({state['goal_count']}, period: {period})"
        if state["setup"]:
            header += f" [setup: {state['setup']}]"
        lines.append(header)
        lines.extend(f"{number}. {goal}" for number , goal in enumerate(state["goals"] , 1))

    return "\n".join(lines)


def _parse_status(text):
    """Extracts the state from a pinned message text.

    Args:
        text (str): Text of the pinned message (may be anything).

    Returns:
        dict | None: The stored state if the text is a status message
        written by the bot, otherwise None.
    """
    text = text or ""
    streak = _STREAK_PATTERN.search(text)
    if streak is None:
        return None

    state = _empty_state()
    state["streak"] = int(streak.group(1))
    state["last_report"] = streak.group(2)

    goals = _GOALS_PATTERN.search(text)
    if goals is not None:
        state["goal_count"] = int(goals.group(1))
        period = goals.group(2)
        state["period_days"] = int(period.split()[0]) if period != "pending" else None
        state["setup"] = goals.group(3)
        state["goals"] = _GOAL_LINE_PATTERN.findall(text)

    return state


async def _read_state(bot , chat_id):
    """Reads the state stored in the chat's pinned message.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id (same as the user id).

    Returns:
        tuple[dict | None, telegram.Message | None]: The stored state
        (None when there is no status message yet) and the pinned
        message it was read from, which is reused when writing back.
    """
    pinned = (await bot.get_chat(chat_id)).pinned_message
    if pinned is None:
        return None , None
    return _parse_status(pinned.text) , pinned


async def _write_state(bot , chat_id , state , old_pinned):
    """Saves the state by sending and pinning a new status message.

    The previous status message is unpinned (and deleted when Telegram
    still allows it - bots can only delete messages younger than 48h).

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        state (dict): The state to store.
        old_pinned (telegram.Message | None): The message currently
            pinned, as returned by _read_state.
    """
    message = await bot.send_message(chat_id , _format_status(state))
    await bot.pin_chat_message(chat_id , message.message_id , disable_notification=True)
    if old_pinned is not None and _parse_status(old_pinned.text) is not None:
        try:
            await bot.unpin_chat_message(chat_id , old_pinned.message_id)
            await bot.delete_message(chat_id , old_pinned.message_id)
        except Exception:
            pass  # older than 48h: Telegram refuses the delete, not a problem


async def get_state(bot , chat_id):
    """Reads everything the bot knows about a user.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.

    Returns:
        dict: The stored state, or an empty state when the user has no
        status message yet.
    """
    state , _ = await _read_state(bot , chat_id)
    return state if state is not None else _empty_state()


async def get_streak(bot , chat_id):
    """Reads the current streak of a user.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id (same as the user id).

    Returns:
        int: The current streak, or 0 if there is no status yet.
    """
    state , _ = await _read_state(bot , chat_id)
    if state is None:
        return 0
    return state["streak"]


async def init_streak(bot , chat_id):
    """Makes sure the user has a pinned status, creating it at 0 if not.

    Called when the user starts the bot, so the friend can already
    check this streak (day 0) before any day has been reported.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.

    Returns:
        int: The current streak (0 when the status was just created).
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is not None:
        return state["streak"]
    await _write_state(bot , chat_id , _empty_state() , pinned)
    return 0


async def report_day(bot , chat_id):
    """Registers today as a completed day and updates the streak.

    The streak rules are:
        - Last report was today: nothing changes, the report does not count.
        - Last report was yesterday: the streak continues (+1).
        - Last report is older, or there is no status yet: restarts at 1.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.

    Returns:
        tuple[int, bool]: The streak after the report, and whether the
        report counted (False means the user had already reported today).
    """
    today = _today().isoformat()
    yesterday = (_today() - timedelta(days=1)).isoformat()

    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
        state["streak"] = 1
    elif state["last_report"] == today:
        return state["streak"] , False
    elif state["last_report"] == yesterday:
        state["streak"] += 1
    else:
        state["streak"] = 1

    state["last_report"] = today
    await _write_state(bot , chat_id , state , pinned)
    return state["streak"] , True


async def reset_streak(bot , chat_id):
    """Sets the user's streak back to 0 (they lost).

    The goals are kept: losing the streak does not mean the user wants
    to write all of them again.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
    state["streak"] = 0
    state["last_report"] = "none"
    await _write_state(bot , chat_id , state , pinned)


async def begin_goal_setup(bot , chat_id):
    """Starts the goals questionnaire: the bot now waits for a number.

    Any goals added before are dropped, because the user is about to
    say again how many goals there will be.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
    state["goal_count"] = 0
    state["goals"] = []
    state["period_days"] = None
    state["setup"] = SETUP_COUNT
    await _write_state(bot , chat_id , state , pinned)


async def set_goal_count(bot , chat_id , count):
    """Stores how many goals the user wants and waits for the first one.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        count (int): Number of goals the user announced.

    Returns:
        dict: The state after the change.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
    state["goal_count"] = count
    state["goals"] = []
    state["period_days"] = None
    state["setup"] = SETUP_GOAL
    await _write_state(bot , chat_id , state , pinned)
    return state


async def add_goal(bot , chat_id , text):
    """Stores one goal and moves to the next question.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        text (str): The goal as the user wrote it.

    Returns:
        dict: The state after the change. Its "setup" says what the bot
        is waiting for now: another goal, or the period.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()

    # Everything is stored in one message, so a goal has to stay on a
    # single line and cannot be longer than the status message allows.
    goal = " ".join(text.split())[:MAX_GOAL_LENGTH]
    state["goals"].append(goal)
    state["setup"] = SETUP_GOAL if len(state["goals"]) < state["goal_count"] else SETUP_PERIOD

    await _write_state(bot , chat_id , state , pinned)
    return state


async def cancel_goal_setup(bot , chat_id):
    """Stops the goals questionnaire, keeping what was already answered.

    The announced number of goals is lowered to the goals actually
    written, so the stored state stays coherent.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
    state["goal_count"] = len(state["goals"])
    state["setup"] = None
    await _write_state(bot , chat_id , state , pinned)


async def set_period(bot , chat_id , days):
    """Stores the period to complete the goals and ends the setup.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        days (int): Period in days.

    Returns:
        dict: The state after the change.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
    state["period_days"] = days
    state["setup"] = None
    await _write_state(bot , chat_id , state , pinned)
    return state
