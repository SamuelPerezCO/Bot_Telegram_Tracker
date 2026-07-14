"""Streak storage inside Telegram itself (no database).

Telegram bots cannot read the chat history, but they CAN read the
chat's pinned message through get_chat. This module uses that: the
bot keeps each user's streak in a pinned status message, so the data
lives in Telegram, survives restarts/redeploys and needs no database.
"""

import re
from datetime import date , timedelta


def _format_status(streak , last_report):
    """Builds the text of the pinned status message.

    Args:
        streak (int): Current streak value.
        last_report (str): ISO date of the last report, or "none".

    Returns:
        str: The status message text.
    """
    return f"🔥 Streak: {streak} (last report: {last_report})"


def _parse_status(text):
    """Extracts the streak data from a pinned message text.

    Args:
        text (str): Text of the pinned message (may be anything).

    Returns:
        tuple[int, str] | None: (streak, last_report) if the text is a
        status message written by the bot, otherwise None.
    """
    match = re.search(r"Streak: (\d+) \(last report: (\S+)\)" , text or "")
    if match is None:
        return None
    return int(match.group(1)) , match.group(2)


async def _read_status(bot , chat_id):
    """Reads the streak data stored in the chat's pinned message.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id (same as the user id).

    Returns:
        tuple[int, str] | None: (streak, last_report), or None if there
        is no pinned status message.
    """
    chat = await bot.get_chat(chat_id)
    if chat.pinned_message is None:
        return None
    return _parse_status(chat.pinned_message.text)


async def _write_status(bot , chat_id , streak , last_report):
    """Saves the streak by sending and pinning a new status message.

    The previous status message is unpinned (and deleted when Telegram
    still allows it - bots can only delete messages younger than 48h).

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
        streak (int): New streak value.
        last_report (str): ISO date of the last report, or "none".
    """
    old_pinned = (await bot.get_chat(chat_id)).pinned_message
    message = await bot.send_message(chat_id , _format_status(streak , last_report))
    await bot.pin_chat_message(chat_id , message.message_id , disable_notification=True)
    if old_pinned is not None and _parse_status(old_pinned.text) is not None:
        try:
            await bot.unpin_chat_message(chat_id , old_pinned.message_id)
            await bot.delete_message(chat_id , old_pinned.message_id)
        except Exception:
            pass  # older than 48h: Telegram refuses the delete, not a problem


async def get_streak(bot , chat_id):
    """Reads the current streak of a user.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id (same as the user id).

    Returns:
        int: The current streak, or 0 if there is no status yet.
    """
    status = await _read_status(bot , chat_id)
    if status is None:
        return 0
    return status[0]


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
    status = await _read_status(bot , chat_id)
    if status is not None:
        return status[0]
    await _write_status(bot , chat_id , 0 , "none")
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
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    status = await _read_status(bot , chat_id)
    if status is None:
        new_streak = 1
    else:
        current_streak , last_report = status
        if last_report == today:
            return current_streak , False
        elif last_report == yesterday:
            new_streak = current_streak + 1
        else:
            new_streak = 1

    await _write_status(bot , chat_id , new_streak , today)
    return new_streak , True


async def reset_streak(bot , chat_id):
    """Sets the user's streak back to 0 (they lost).

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Private chat id.
    """
    await _write_status(bot , chat_id , 0 , "none")
