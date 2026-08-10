"""Conversation flow of the tracker bot.

Handlers for each step of the conversation: the /start question, the
menu, and the streak reports. All persistence is delegated to
Models.streak_model; this module only talks to the user.

The handlers keep no state between messages: each one is chosen by the
text of the button the user pressed (see bot.py), because on Vercel
every update may be served by a different serverless instance.
"""

from telegram import Update , ReplyKeyboardRemove ,InlineKeyboardMarkup , InlineKeyboardButton , KeyboardButton , ReplyKeyboardMarkup
from telegram.ext import ContextTypes , CallbackContext
import os

from Models import streak_model


# Word the user can type to get out of the goals questionnaire, so a
# half answered setup never leaves the chat stuck.
CANCEL_WORD = "cancel"


def _menu_keyboard():
    """Builds the keyboard with the actions of the main menu.

    Returns:
        telegram.ReplyKeyboardMarkup: The menu keyboard.
    """
    return ReplyKeyboardMarkup([
        [KeyboardButton("I want to report a new day") , KeyboardButton("I want to report that I lose")] ,
        [KeyboardButton("I want to see my friend's streak")] ,
        [KeyboardButton("I want to add my goals")]
    ])


def _goals_summary(state):
    """Writes the goals of a user as a readable list.

    Args:
        state (dict): State as returned by Models.streak_model.

    Returns:
        str: One line per goal, with the period at the end.
    """
    lines = [f"{number}. {goal}" for number , goal in enumerate(state["goals"] , 1)]
    lines.append(f"\nYou have {state['period_days']} days to complete all of them ⏳")
    return "\n".join(lines)


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
        """
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("El Hi") , KeyboardButton("El tornillo")]
        ])
        await update.message.reply_text("Who are you?" , reply_markup=keyboard)

    @staticmethod
    async def who_are_you_answer(update:Update, context: ContextTypes.DEFAULT_TYPE):
        """Shows the user's current streak and the actions menu.

        Args:
            update: Incoming Telegram update with the user's answer.
            context: Handler context provided by python-telegram-bot.
        """
        keyboard = _menu_keyboard()
        streak = await streak_model.init_streak(context.bot , update.effective_chat.id)
        await update.message.reply_text(f"Your Current Streak Is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("What do you want to do?" , reply_markup=keyboard)

    @staticmethod
    async def report_new_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the menu choice: report a day, report a loss, or
        show the friend's streak.

        Args:
            update: Incoming Telegram update with the chosen menu option.
            context: Handler context provided by python-telegram-bot.
        """
        chat_id = update.effective_chat.id
        if update.message.text == "I want to report a new day":
            streak , counted = await streak_model.report_day(context.bot , chat_id)
            if counted:
                await update.message.reply_text(f"Day reported! Your streak is now {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
                await _notify_friend(context.bot , chat_id , streak)
            else:
                await update.message.reply_text(f"You already reported today. Your streak is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
        elif update.message.text == "I want to report that I lose":
            await streak_model.reset_streak(context.bot , chat_id)
            await update.message.reply_text("Streak reset to 0. Start again tomorrow 💪" , reply_markup=ReplyKeyboardRemove())
        elif update.message.text == "I want to see my friend's streak":
            friend_id , friend_name , _ = _friend_of(chat_id)
            if friend_id is None:
                await update.message.reply_text("Friend ids are not configured (set HI_CHAT_ID and TORNILLO_CHAT_ID)" , reply_markup=ReplyKeyboardRemove())
                return
            try:
                streak = await streak_model.get_streak(context.bot , friend_id)
            except Exception:
                await update.message.reply_text(f"I could not reach {friend_name}'s chat. Has he started the bot?" , reply_markup=ReplyKeyboardRemove())
                return
            await update.message.reply_text(f"{friend_name}'s streak is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())

    @staticmethod
    async def add_goals(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Starts the goals questionnaire: asks how many goals there are.

        From here the user only writes free text, so every answer is
        handled by free_text below.

        Args:
            update: Incoming Telegram update.
            context: Handler context provided by python-telegram-bot.
        """
        await streak_model.begin_goal_setup(context.bot , update.effective_chat.id)
        await update.message.reply_text(
            f"How many goals do you want to add? (1 to {streak_model.MAX_GOALS})\n"
            f"Write \"{CANCEL_WORD}\" at any moment to stop." ,
            reply_markup=ReplyKeyboardRemove()
        )

    @staticmethod
    async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Answers any text that is not one of the buttons.

        While the goals questionnaire is running, this text IS the
        answer to the question the bot asked. Which question that is
        cannot be remembered in memory (a serverless instance does not
        survive between two updates), so it is read back from the state
        stored in the pinned message.

        Args:
            update: Incoming Telegram update.
            context: Handler context provided by python-telegram-bot.
        """
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        state = await streak_model.get_state(context.bot , chat_id)
        step = state["setup"]

        if step is None:
            await update.message.reply_text("Please use one of the buttons, or send /start")
            return

        if text.lower() == CANCEL_WORD:
            await streak_model.cancel_goal_setup(context.bot , chat_id)
            await update.message.reply_text("Ok, I stopped asking for goals." , reply_markup=_menu_keyboard())
            return

        if step == streak_model.SETUP_COUNT:
            if not text.isdigit() or not 1 <= int(text) <= streak_model.MAX_GOALS:
                await update.message.reply_text(f"Please answer with a number between 1 and {streak_model.MAX_GOALS}")
                return
            await streak_model.set_goal_count(context.bot , chat_id , int(text))
            await update.message.reply_text("Tell me goal number 1")

        elif step == streak_model.SETUP_GOAL:
            state = await streak_model.add_goal(context.bot , chat_id , text)
            if state["setup"] == streak_model.SETUP_GOAL:
                await update.message.reply_text(f"Tell me goal number {len(state['goals']) + 1}")
            else:
                await update.message.reply_text(
                    f"I have your {state['goal_count']} goals.\n"
                    "In how much time do you want to complete all of them?\n"
                    "For example: 7 days, 2 weeks, 1 month"
                )

        elif step == streak_model.SETUP_PERIOD:
            days = streak_model.parse_period(text)
            if days is None:
                await update.message.reply_text("I did not understand that period. Try something like: 7 days, 2 weeks, 1 month")
                return
            state = await streak_model.set_period(context.bot , chat_id , days)
            await update.message.reply_text("These are your goals:\n" + _goals_summary(state) , reply_markup=_menu_keyboard())
