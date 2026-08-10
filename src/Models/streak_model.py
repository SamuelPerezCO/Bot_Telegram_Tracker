"""Goals storage inside Telegram itself (no database).

Telegram bots cannot read the chat history, but they CAN read the
chat's pinned message through get_chat. This module uses that: the
bot keeps each user's state in a pinned status message, so the data
lives in Telegram, survives restarts/redeploys and needs no database.

Every goal is its own streak: it counts the days in a row it has been
achieved, out of the period the user asked for. Answering "no" for a
goal sends only that goal back to 0, the others keep their count.

The pinned message looks like this:

    🎯 Goals (5, period: 90 days)
    1. Wake Up at 5:00 am 12/90 (last: 2026-08-09)
    2. Journal 12/90 (last: 2026-08-09)
    3. No FAP 0/90 (last: 2026-08-09)

While the bot is waiting for an answer it also writes what it asked
for, because nothing can be kept in memory between two updates on a
serverless host:

    🎯 Goals (5, period: pending) [waiting: goal]
"""

import os
import re
from datetime import datetime , timedelta
from zoneinfo import ZoneInfo


# Limits for what the user is allowed to type, so a single message can
# never grow past what Telegram accepts as a message text.
MAX_GOALS = 10
MAX_GOAL_LENGTH = 200

# What the bot is waiting for, stored in the pinned message:
#   "count"  -> how many goals the user wants
#   "goal"   -> the text of the next goal
#   "period" -> the time to complete all of them
#   "report" -> whether the next goal was achieved today
#   None     -> nothing pending, the user is in the normal menu
WAITING_COUNT = "count"
WAITING_GOAL = "goal"
WAITING_PERIOD = "period"
WAITING_REPORT = "report"

# How many days each unit is worth when the user writes "2 weeks".
_PERIOD_UNITS = {"day": 1 , "days": 1 , "week": 7 , "weeks": 7 , "month": 30 , "months": 30}

_HEADER_PATTERN = re.compile(r"Goals \((\d+), period: ([^)]+)\)(?: \[waiting: (\w+)\])?")
_GOAL_PATTERN = re.compile(r"^\d+\. (.+?) (\d+)/(?:\d+|\?) \(last: (\S+)\)$" , re.MULTILINE)
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
        dict: A state with no goals.
    """
    return {"goal_count": 0 , "period_days": None , "waiting": None , "goals": []}


def _new_goal(text):
    """Builds a goal that has never been reported.

    Args:
        text (str): The goal as the user wrote it.

    Returns:
        dict: The goal, with its counter at 0.
    """
    # Everything is stored in one message, so a goal has to stay on a
    # single line and cannot be longer than the status message allows.
    return {"text": " ".join(text.split())[:MAX_GOAL_LENGTH] , "count": 0 , "last": "none"}


def count_of(goal):
    """Current streak of one goal, in days.

    The stored number is only worth something while the streak is
    alive: if the last answer is older than yesterday the user stopped
    reporting and the streak is already broken, so it counts as 0.

    Args:
        goal (dict): One goal of the state.

    Returns:
        int: The days in a row this goal has been achieved.
    """
    today = _today()
    if goal["last"] in (today.isoformat() , (today - timedelta(days=1)).isoformat()):
        return goal["count"]
    return 0


def is_complete(goal , period_days):
    """Says whether a goal already reached the period asked for.

    Args:
        goal (dict): One goal of the state.
        period_days (int | None): The period of the state.

    Returns:
        bool: True when the goal is finished.
    """
    return bool(period_days) and count_of(goal) >= period_days


def next_pending(state):
    """Finds the goal the bot still has to ask about today.

    Goals already answered today are skipped, so an interrupted report
    continues where it stopped instead of asking everything again.

    Args:
        state (dict): The state of the user.

    Returns:
        int | None: Index of the next goal to ask about, or None when
        every goal has an answer for today.
    """
    today = _today().isoformat()
    for index , goal in enumerate(state["goals"]):
        if goal["last"] != today:
            return index
    return None


def parse_period(text):
    """Reads a period of time written by the user.

    Accepts a plain number of days ("90") or a number with a unit
    ("90 days", "2 weeks", "3 months").

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
    period = f"{state['period_days']} days" if state["period_days"] else "pending"
    header = f"🎯 Goals ({state['goal_count']}, period: {period})"
    if state["waiting"]:
        header += f" [waiting: {state['waiting']}]"

    lines = [header]
    denominator = state["period_days"] or "?"
    for number , goal in enumerate(state["goals"] , 1):
        lines.append(f"{number}. {goal['text']} {goal['count']}/{denominator} (last: {goal['last']})")
    return "\n".join(lines)


def _parse_status(text):
    """Extracts the state from a pinned message text.

    Args:
        text (str): Text of the pinned message (may be anything).

    Returns:
        dict | None: The stored state if the text is a status message
        written by the bot, otherwise None.
    """
    header = _HEADER_PATTERN.search(text or "")
    if header is None:
        return None

    state = _empty_state()
    state["goal_count"] = int(header.group(1))
    period = header.group(2)
    state["period_days"] = int(period.split()[0]) if period != "pending" else None
    state["waiting"] = header.group(3)
    state["goals"] = [
        {"text": goal_text , "count": int(count) , "last": last}
        for goal_text , count , last in _GOAL_PATTERN.findall(text)
    ]
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


async def init_state(bot , chat_id):
    """Makes sure the user has a pinned status, creating it if not.

    Called when the user starts the bot, so the friend can already
    look at this chat before anything has been reported.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.

    Returns:
        dict: The state of the user.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is not None:
        return state
    state = _empty_state()
    await _write_state(bot , chat_id , state , pinned)
    return state


async def begin_goal_setup(bot , chat_id):
    """Starts the goals questionnaire: the bot now waits for a number.

    Any goal added before is dropped, because the user is about to say
    again how many goals there will be.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
    """
    _ , pinned = await _read_state(bot , chat_id)
    state = _empty_state()
    state["waiting"] = WAITING_COUNT
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
    _ , pinned = await _read_state(bot , chat_id)
    state = _empty_state()
    state["goal_count"] = count
    state["waiting"] = WAITING_GOAL
    await _write_state(bot , chat_id , state , pinned)
    return state


async def add_goal(bot , chat_id , text):
    """Stores one goal and moves to the next question.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        text (str): The goal as the user wrote it.

    Returns:
        dict: The state after the change. Its "waiting" says what the
        bot needs now: another goal, or the period.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()

    state["goals"].append(_new_goal(text))
    state["waiting"] = WAITING_GOAL if len(state["goals"]) < state["goal_count"] else WAITING_PERIOD
    await _write_state(bot , chat_id , state , pinned)
    return state


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
    state["waiting"] = None
    await _write_state(bot , chat_id , state , pinned)
    return state


async def cancel_setup(bot , chat_id):
    """Stops whatever the bot was asking, keeping the answers given.

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
    state["waiting"] = None
    await _write_state(bot , chat_id , state , pinned)


async def begin_report(bot , chat_id):
    """Starts the daily report: the bot now waits for a yes or a no.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.

    Returns:
        dict: The state after the change.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()
    state["waiting"] = WAITING_REPORT
    await _write_state(bot , chat_id , state , pinned)
    return state


async def answer_goal(bot , chat_id , achieved):
    """Answers the goal the bot is currently asking about.

    A goal achieved today continues its streak (+1 when it was also
    achieved yesterday, 1 otherwise). A goal missed today goes back to
    0: every goal is its own streak.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        achieved (bool): The user's answer for that goal.

    Returns:
        tuple[dict, dict | None]: The state after the change, and the
        goal that was just answered (None when there was nothing left
        to answer).
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        return _empty_state() , None

    index = next_pending(state)
    if index is None:
        return state , None

    goal = state["goals"][index]
    if achieved:
        # count_of() is 0 unless the streak is still alive, so this is
        # "+1" after a good day and "restart at 1" after a broken one.
        goal["count"] = count_of(goal) + 1
        if state["period_days"]:
            goal["count"] = min(goal["count"] , state["period_days"])
    else:
        goal["count"] = 0
    goal["last"] = _today().isoformat()

    if next_pending(state) is None:
        state["waiting"] = None
    await _write_state(bot , chat_id , state , pinned)
    return state , goal
