"""Goals storage inside Telegram itself (no database).

Telegram bots cannot read the chat history, but they CAN read the
chat's pinned message through get_chat. This module uses that: the
bot keeps each user's state in a pinned status message, so the data
lives in Telegram, survives restarts/redeploys and needs no database.

Every goal is its own streak: it counts the days in a row it has been
achieved, out of the period the user asked for. Answering "no" for a
goal sends only that goal back to 0, the others keep their count.

Each goal can also have a time at which the bot reminds the user about
it, and the day that reminder was last sent (so it is sent once a day
and never twice).

The pinned message looks like this:

    🎯 Goals (5, period: 90 days)
    1. Wake Up at 5:00 am 12/90 (last: 2026-08-09, at: 05:00, sent: 2026-08-09)
    2. Journal 12/90 (last: 2026-08-09, at: 22:00, sent: none)
    3. No FAP 0/90 (last: 2026-08-09, at: none, sent: none)

While the bot is waiting for an answer it also writes what it asked
for, because nothing can be kept in memory between two updates on a
serverless host:

    🎯 Goals (5, period: pending) [waiting: goal]

While reporting, the goals answered "not yet" are listed as well, so
the bot stops asking about them until the next report:

    🎯 Goals (5, period: 90 days) [waiting: report] [later: 2,3]
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
#   "time"   -> at what time that goal should be reminded
#   "period" -> the time to complete all of them
#   "report" -> whether the next goal was achieved today
#   None     -> nothing pending, the user is in the normal menu
WAITING_COUNT = "count"
WAITING_GOAL = "goal"
WAITING_TIME = "time"
WAITING_PERIOD = "period"
WAITING_REPORT = "report"

# How late a reminder may still be sent, in minutes. A scheduler run
# can be missed (a cold start, a network hiccup), so the reminder is
# not tied to one exact minute; but a goal whose time passed hours ago
# is left alone instead of arriving in the middle of the night.
CATCH_UP_MINUTES = 60

# The three answers a goal can get while reporting.
ANSWER_YES = "yes"
ANSWER_NO = "no"
ANSWER_LATER = "later"

# How many days each unit is worth when the user writes "2 weeks".
_PERIOD_UNITS = {"day": 1 , "days": 1 , "week": 7 , "weeks": 7 , "month": 30 , "months": 30}

_HEADER_PATTERN = re.compile(r"Goals \((\d+), period: ([^)]+)\)(?: \[waiting: (\w+)\])?(?: \[later: ([\d,]+)\])?")
# The reminder part is optional so the goals written before this
# feature existed are still read correctly.
_GOAL_PATTERN = re.compile(
    r"^\d+\. (.+?) (\d+)/(?:\d+|\?) \(last: (\S+?)(?:, at: (\S+?), sent: (\S+?))?\)$" ,
    re.MULTILINE
)
_PERIOD_PATTERN = re.compile(r"^(\d+)\s*([a-z]+)?$" , re.IGNORECASE)
_TIME_PATTERN = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$" , re.IGNORECASE)


def _now():
    """Current time in the users' timezone, not the server's.

    The server may run in another timezone (Vercel uses UTC), so there
    the date already flips to the next day during the evening here and
    a reminder set for 05:00 would arrive at midnight. The timezone
    comes from the TIMEZONE environment variable and defaults to
    America/Bogota.

    Returns:
        datetime.datetime: Now, for the users.
    """
    return datetime.now(ZoneInfo(os.getenv("TIMEZONE" , "America/Bogota")))


def _today():
    """Today's date in the users' timezone.

    Returns:
        datetime.date: Today's date for the users.
    """
    return _now().date()


def now_hhmm():
    """Current time of day for the users, as written in the status.

    Returns:
        str: Now as "HH:MM".
    """
    return _now().strftime("%H:%M")


def today_iso():
    """Today's date for the users, as it is written in the status.

    Returns:
        str: Today in ISO format, comparable with a goal's "last".
    """
    return _today().isoformat()


def _empty_state():
    """Builds the state of a user who has never used the bot.

    Returns:
        dict: A state with no goals.
    """
    return {"goal_count": 0 , "period_days": None , "waiting": None , "later": [] , "goals": []}


def _new_goal(text):
    """Builds a goal that has never been reported.

    Args:
        text (str): The goal as the user wrote it.

    Returns:
        dict: The goal, with its counter at 0 and no reminder yet.
    """
    # Everything is stored in one message, so a goal has to stay on a
    # single line and cannot be longer than the status message allows.
    return {
        "text": " ".join(text.split())[:MAX_GOAL_LENGTH] ,
        "count": 0 ,
        "last": "none" ,
        "time": "none" ,   # hour of the reminder, "none" when there is none
        "sent": "none" ,   # day that reminder was last sent
    }


def parse_time(text):
    """Reads an hour written by the user.

    Accepts "5", "5:00", "05:00", "5 am", "5:30pm", "17:30".

    Args:
        text (str): What the user typed.

    Returns:
        str | None: The hour as "HH:MM", or None if it is not a valid
        hour.
    """
    match = _TIME_PATTERN.match((text or "").strip())
    if match is None:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    half = (match.group(3) or "").lower()
    if minute > 59:
        return None

    if half:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if half == "pm" else 0)
    elif hour > 23:
        return None

    return f"{hour:02d}:{minute:02d}"


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


def next_unanswered(state):
    """Finds a goal with no answer for today, "not yet" included.

    Goals already answered today are skipped, so an interrupted report
    continues where it stopped instead of asking everything again.

    Args:
        state (dict): The state of the user.

    Returns:
        int | None: Index of the goal, or None when every goal was
        answered today.
    """
    today = _today().isoformat()
    for index , goal in enumerate(state["goals"]):
        if goal["last"] != today:
            return index
    return None


def next_to_ask(state):
    """Finds the goal to ask about right now, during a report.

    Same as next_unanswered, except that the goals answered "not yet"
    are left out: the user asked to be questioned about them later, so
    they are only brought back the next time a report is started.

    Args:
        state (dict): The state of the user.

    Returns:
        int | None: Index of the goal, or None when there is nothing
        left to ask in this report.
    """
    today = _today().isoformat()
    for index , goal in enumerate(state["goals"]):
        if goal["last"] != today and (index + 1) not in state["later"]:
            return index
    return None


def due_reminders(state):
    """Finds the goals whose reminder should be sent right now.

    A reminder is due when its hour has arrived (or passed by less than
    CATCH_UP_MINUTES), it was not sent today already, and the goal has
    no answer for today yet - reminding somebody about something they
    already reported is only noise.

    Args:
        state (dict): The state of the user.

    Returns:
        list[tuple[int, dict]]: (number of the goal, goal) for each
        reminder to send now.
    """
    now = _now()
    today = now.date().isoformat()

    due = []
    for number , goal in enumerate(state["goals"] , 1):
        if goal["time"] == "none" or goal["sent"] == today or goal["last"] == today:
            continue
        hour , minute = goal["time"].split(":")
        moment = now.replace(hour=int(hour) , minute=int(minute) , second=0 , microsecond=0)
        late_minutes = (now - moment).total_seconds() / 60
        if 0 <= late_minutes <= CATCH_UP_MINUTES:
            due.append((number , goal))
    return due


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
    if state["later"]:
        header += f" [later: {','.join(str(number) for number in state['later'])}]"

    lines = [header]
    denominator = state["period_days"] or "?"
    for number , goal in enumerate(state["goals"] , 1):
        lines.append(
            f"{number}. {goal['text']} {goal['count']}/{denominator}"
            f" (last: {goal['last']}, at: {goal['time']}, sent: {goal['sent']})"
        )
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
    state["later"] = [int(number) for number in (header.group(4) or "").split(",") if number]
    state["goals"] = [
        {"text": goal_text , "count": int(count) , "last": last , "time": time or "none" , "sent": sent or "none"}
        for goal_text , count , last , time , sent in _GOAL_PATTERN.findall(text)
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

    Returns:
        dict: The state after the change.
    """
    _ , pinned = await _read_state(bot , chat_id)
    state = _empty_state()
    state["waiting"] = WAITING_COUNT
    await _write_state(bot , chat_id , state , pinned)
    return state


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
        dict: The state after the change. The bot now needs the hour of
        that goal's reminder.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        state = _empty_state()

    state["goals"].append(_new_goal(text))
    state["waiting"] = WAITING_TIME
    await _write_state(bot , chat_id , state , pinned)
    return state


async def set_goal_time(bot , chat_id , time):
    """Stores the reminder hour of the goal just written.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        time (str): Hour as "HH:MM", or "none" for no reminder.

    Returns:
        dict: The state after the change. Its "waiting" says what the
        bot needs now: another goal, or the period.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None or not state["goals"]:
        return await begin_goal_setup(bot , chat_id)

    state["goals"][-1]["time"] = time
    state["waiting"] = WAITING_GOAL if len(state["goals"]) < state["goal_count"] else WAITING_PERIOD
    await _write_state(bot , chat_id , state , pinned)
    return state


async def mark_reminders_sent(bot , chat_id , numbers):
    """Writes down that today's reminders were already sent.

    Args:
        bot: The bot instance.
        chat_id (int): Private chat id.
        numbers (list[int]): Numbers of the goals that were reminded,
            as given by due_reminders.
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        return
    today = today_iso()
    for number in numbers:
        if 1 <= number <= len(state["goals"]):
            state["goals"][number - 1]["sent"] = today
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
    state["later"] = []  # a new report asks again about everything pending
    await _write_state(bot , chat_id , state , pinned)
    return state


async def answer_goal(bot , chat_id , answer):
    """Answers the goal the bot is currently asking about.

    A goal achieved today continues its streak (+1 when it was also
    achieved yesterday, 1 otherwise). A goal missed today goes back to
    0: every goal is its own streak. A goal answered "not yet" is not
    touched at all - the day is not over, so the bot only stops asking
    about it until the next report.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        answer (str): ANSWER_YES, ANSWER_NO or ANSWER_LATER.

    Returns:
        tuple[dict, dict | None]: The state after the change, and the
        goal that was just answered (None when there was nothing left
        to answer).
    """
    state , pinned = await _read_state(bot , chat_id)
    if state is None:
        return _empty_state() , None

    index = next_to_ask(state)
    if index is None:
        return state , None

    goal = state["goals"][index]
    if answer == ANSWER_LATER:
        state["later"].append(index + 1)
    else:
        if answer == ANSWER_YES:
            # count_of() is 0 unless the streak is still alive, so this
            # is "+1" after a good day and "restart at 1" after a
            # broken one.
            goal["count"] = count_of(goal) + 1
            if state["period_days"]:
                goal["count"] = min(goal["count"] , state["period_days"])
        else:
            goal["count"] = 0
        goal["last"] = _today().isoformat()

    if next_to_ask(state) is None:
        state["waiting"] = None
    # "later" is deliberately NOT cleared here: the caller still has to
    # see which goals were left aside to close the report properly.
    # begin_report clears it, so the next report asks about them again.
    await _write_state(bot , chat_id , state , pinned)
    return state , goal
