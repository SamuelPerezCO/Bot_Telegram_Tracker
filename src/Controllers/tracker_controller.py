"""Conversation flow of the tracker bot.

Handlers for each step of the conversation: the /start question, the
menu, and the streak reports. All persistence is delegated to
Models.streak_model; this module only talks to the user.
"""

from telegram import Update , ReplyKeyboardRemove ,InlineKeyboardMarkup , InlineKeyboardButton , KeyboardButton , ReplyKeyboardMarkup
from telegram.ext import ContextTypes , ConversationHandler , CallbackContext
import os

from Models import streak_model

# Conversation states used by the ConversationHandler in main.py.
WHO_ARE_YOU = 0
MENU = 1


def _friend_of(chat_id):
    """Finds the chat id and name of the OTHER user (the friend).

    The two private chat ids are configured in the environment as
    HI_CHAT_ID (El Hi) and TORNILLO_CHAT_ID (El tornillo). A private
    chat id is the same as the user's Telegram id.

    Args:
        chat_id (int): Chat id of the user asking.

    Returns:
        tuple[int, str, str] | tuple[None, None, None]: (friend_chat_id,
        friend_name, own_name), or (None, None, None) if the ids are
        not configured.
    """
    hi_id = os.getenv("HI_CHAT_ID")
    tornillo_id = os.getenv("TORNILLO_CHAT_ID")
    if not hi_id or not tornillo_id:
        return None , None , None
    if str(chat_id) == hi_id:
        return int(tornillo_id) , "El tornillo" , "El Hi"
    return int(hi_id) , "El Hi" , "El tornillo"


async def _notify_friend(bot , chat_id , streak):
    """Tells the friend that this user just reported his day.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Chat id of the user who reported.
        streak (int): The streak after the report.
    """
    friend_id , _ , own_name = _friend_of(chat_id)
    if friend_id is None:
        return
    try:
        await bot.send_message(friend_id , f"{own_name} just reported his day! His streak is now {streak} 🔥")
    except Exception:
        pass  # the friend has not started the bot yet, nothing to do

class tracker_controller:
    """Handlers for each step of the bot conversation."""

    @staticmethod
    async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Replies with the chat id (/id command).

        Used once per user to get the values for HI_CHAT_ID and
        TORNILLO_CHAT_ID in the environment.

        Args:
            update: Incoming Telegram update.
            context: Handler context provided by python-telegram-bot.
        """
        await update.message.reply_text(f"Your chat id is: {update.effective_chat.id}")

    @staticmethod
    async def who_are_you(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point of the conversation (/start): asks who the user is.

        Args:
            update: Incoming Telegram update.
            context: Handler context provided by python-telegram-bot.

        Returns:
            int: The WHO_ARE_YOU state, so the next message goes to
            who_are_you_answer.
        """
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("El Hi") , KeyboardButton("El tornillo")]
        ])
        await update.message.reply_text("Who are you?" , reply_markup=keyboard)
        return WHO_ARE_YOU

    @staticmethod
    async def who_are_you_answer(update:Update, context: ContextTypes.DEFAULT_TYPE):
        """Shows the user's current streak and the actions menu.

        Args:
            update: Incoming Telegram update with the user's answer.
            context: Handler context provided by python-telegram-bot.

        Returns:
            int: The MENU state, so the next message goes to report_new_day.
        """
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("I want to report a new day") , KeyboardButton("I want to report that I lose")] ,
            [KeyboardButton("I want to see my friend's streak")]
        ])
        streak = await streak_model.init_streak(context.bot , update.effective_chat.id)
        await update.message.reply_text(f"Your Current Streak Is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("What do you want to do?" , reply_markup=keyboard)
        return MENU

    @staticmethod
    async def report_new_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the menu choice: report a day, report a loss, or
        show the friend's streak.

        Args:
            update: Incoming Telegram update with the chosen menu option.
            context: Handler context provided by python-telegram-bot.

        Returns:
            int: ConversationHandler.END when the report is processed,
            or MENU again if the message matched no button.
        """
        chat_id = update.effective_chat.id
        if update.message.text == "I want to report a new day":
            streak , counted = await streak_model.report_day(context.bot , chat_id)
            if counted:
                await update.message.reply_text(f"Day reported! Your streak is now {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
                await _notify_friend(context.bot , chat_id , streak)
            else:
                await update.message.reply_text(f"You already reported today. Your streak is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif update.message.text == "I want to report that I lose":
            await streak_model.reset_streak(context.bot , chat_id)
            await update.message.reply_text("Streak reset to 0. Start again tomorrow 💪" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif update.message.text == "I want to see my friend's streak":
            friend_id , friend_name , _ = _friend_of(chat_id)
            if friend_id is None:
                await update.message.reply_text("Friend ids are not configured (set HI_CHAT_ID and TORNILLO_CHAT_ID)" , reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END
            try:
                streak = await streak_model.get_streak(context.bot , friend_id)
            except Exception:
                await update.message.reply_text(f"I could not reach {friend_name}'s chat. Has he started the bot?" , reply_markup=ReplyKeyboardRemove())
                return ConversationHandler.END
            await update.message.reply_text(f"{friend_name}'s streak is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        else:
            await update.message.reply_text("Please use one of the buttons")
            return MENU
