"""Conversation flow of the tracker bot.

Handlers for each step of the conversation: the /start question, the
menu, the goals questionnaire and the daily report. All persistence is
delegated to Models.streak_model; this module only talks to the user.

The handlers keep no state in memory: each one is chosen by the text of
the button the user pressed (see bot.py), and the questions that need
free text answers read what the bot is waiting for from the stored
state, because on Vercel every update may be served by a different
serverless instance.
"""

from telegram import Update , ReplyKeyboardRemove ,InlineKeyboardMarkup , InlineKeyboardButton , KeyboardButton , ReplyKeyboardMarkup
from telegram.ext import ContextTypes , CallbackContext
import os

from Models import streak_model


# Word the user can type to get out of a questionnaire, so a half
# answered setup never leaves the chat stuck.
CANCEL_WORD = "cancel"

# Accepted answers when the bot asks whether a goal was achieved.
YES_ANSWERS = {"yes" , "y" , "si" , "sí" , "yeah" , "yep" , "✅"}
NO_ANSWERS = {"no" , "n" , "nope" , "nah" , "❌"}


def _menu_keyboard():
    """Builds the keyboard with the actions of the main menu.

    Returns:
        telegram.ReplyKeyboardMarkup: The menu keyboard.
    """
    return ReplyKeyboardMarkup([
        [KeyboardButton("I want to report my day")] ,
        [KeyboardButton("I want to see my goals") , KeyboardButton("I want to see my friend's goals")] ,
        [KeyboardButton("I want to add my goals")]
    ])


def _yes_no_keyboard():
    """Builds the keyboard used while reporting the day.

    Returns:
        telegram.ReplyKeyboardMarkup: A keyboard with Yes and No.
    """
    return ReplyKeyboardMarkup([[KeyboardButton("Yes") , KeyboardButton("No")]] , resize_keyboard=True)


def _goals_list(state):
    """Writes the goals of a user with their counters.

    Args:
        state (dict): State as returned by Models.streak_model.

    Returns:
        str: One line per goal, like "1. Journal 12/90".
    """
    denominator = state["period_days"] or "?"
    lines = []
    for number , goal in enumerate(state["goals"] , 1):
        done = " 🏆" if streak_model.is_complete(goal , state["period_days"]) else ""
        lines.append(f"{number}. {goal['text']} {streak_model.count_of(goal)}/{denominator}{done}")
    return "\n".join(lines)


async def _ask_next_goal(update , state):
    """Asks whether the next pending goal was achieved today.

    Args:
        update: Incoming Telegram update, used to answer.
        state (dict): State of the user.

    Returns:
        bool: True if a question was asked, False when every goal was
        already answered today.
    """
    index = streak_model.next_pending(state)
    if index is None:
        return False

    goal = state["goals"][index]
    await update.message.reply_text(
        f"Did you achieve it today?\n\n{index + 1}. {goal['text']} ({streak_model.count_of(goal)}/{state['period_days'] or '?'})" ,
        reply_markup=_yes_no_keyboard()
    )
    return True


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


async def _notify_friend(bot , chat_id , state):
    """Tells the friend that this user just reported his day.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Chat id of the user who reported.
        state (dict): State of the user after the report.
    """
    friend_id , _ , own_name = _friend_of(chat_id)
    if friend_id is None:
        return
    try:
        await bot.send_message(friend_id , f"{own_name} just reported his day!\n\n{_goals_list(state)}")
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
        """Shows the user's goals and the actions menu.

        Args:
            update: Incoming Telegram update with the user's answer.
            context: Handler context provided by python-telegram-bot.
        """
        state = await streak_model.init_state(context.bot , update.effective_chat.id)
        if state["goals"]:
            await update.message.reply_text("Your goals:\n" + _goals_list(state) , reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text("You have no goals yet." , reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("What do you want to do?" , reply_markup=_menu_keyboard())

    @staticmethod
    async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the menu choice.

        Args:
            update: Incoming Telegram update with the chosen menu option.
            context: Handler context provided by python-telegram-bot.
        """
        chat_id = update.effective_chat.id
        choice = update.message.text

        if choice == "I want to report my day":
            state = await streak_model.get_state(context.bot , chat_id)
            if not state["goals"]:
                await update.message.reply_text("You have no goals yet, add them first." , reply_markup=_menu_keyboard())
                return
            if streak_model.next_pending(state) is None:
                await update.message.reply_text("You already reported every goal today.\n\n" + _goals_list(state) , reply_markup=_menu_keyboard())
                return
            state = await streak_model.begin_report(context.bot , chat_id)
            await _ask_next_goal(update , state)

        elif choice == "I want to see my goals":
            state = await streak_model.get_state(context.bot , chat_id)
            if not state["goals"]:
                await update.message.reply_text("You have no goals yet, add them first." , reply_markup=_menu_keyboard())
                return
            await update.message.reply_text("Your goals:\n" + _goals_list(state) , reply_markup=_menu_keyboard())

        elif choice == "I want to see my friend's goals":
            friend_id , friend_name , _ = _friend_of(chat_id)
            if friend_id is None:
                await update.message.reply_text("Friend ids are not configured (set HI_CHAT_ID and TORNILLO_CHAT_ID)" , reply_markup=_menu_keyboard())
                return
            try:
                state = await streak_model.get_state(context.bot , friend_id)
            except Exception:
                await update.message.reply_text(f"I could not reach {friend_name}'s chat. Has he started the bot?" , reply_markup=_menu_keyboard())
                return
            if not state["goals"]:
                await update.message.reply_text(f"{friend_name} has no goals yet." , reply_markup=_menu_keyboard())
                return
            await update.message.reply_text(f"{friend_name}'s goals:\n" + _goals_list(state) , reply_markup=_menu_keyboard())

        elif choice == "I want to add my goals":
            await streak_model.begin_goal_setup(context.bot , chat_id)
            await update.message.reply_text(
                f"How many goals do you want to add? (1 to {streak_model.MAX_GOALS})\n"
                f"Write \"{CANCEL_WORD}\" at any moment to stop." ,
                reply_markup=ReplyKeyboardRemove()
            )

    @staticmethod
    async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Answers any text that is not one of the buttons.

        While a questionnaire is running, this text IS the answer to the
        question the bot asked. Which question that is cannot be
        remembered in memory (a serverless instance does not survive
        between two updates), so it is read back from the state stored
        in the pinned message.

        Args:
            update: Incoming Telegram update.
            context: Handler context provided by python-telegram-bot.
        """
        chat_id = update.effective_chat.id
        text = update.message.text.strip()
        state = await streak_model.get_state(context.bot , chat_id)
        waiting = state["waiting"]

        if waiting is None:
            await update.message.reply_text("Please use one of the buttons, or send /start")
            return

        if text.lower() == CANCEL_WORD:
            await streak_model.cancel_setup(context.bot , chat_id)
            await update.message.reply_text("Ok, I stopped asking." , reply_markup=_menu_keyboard())
            return

        if waiting == streak_model.WAITING_COUNT:
            if not text.isdigit() or not 1 <= int(text) <= streak_model.MAX_GOALS:
                await update.message.reply_text(f"Please answer with a number between 1 and {streak_model.MAX_GOALS}")
                return
            await streak_model.set_goal_count(context.bot , chat_id , int(text))
            await update.message.reply_text("Tell me goal number 1")

        elif waiting == streak_model.WAITING_GOAL:
            state = await streak_model.add_goal(context.bot , chat_id , text)
            if state["waiting"] == streak_model.WAITING_GOAL:
                await update.message.reply_text(f"Tell me goal number {len(state['goals']) + 1}")
            else:
                await update.message.reply_text(
                    f"I have your {state['goal_count']} goals.\n"
                    "In how much time do you want to complete all of them?\n"
                    "For example: 90 days, 2 weeks, 3 months"
                )

        elif waiting == streak_model.WAITING_PERIOD:
            days = streak_model.parse_period(text)
            if days is None:
                await update.message.reply_text("I did not understand that period. Try something like: 90 days, 2 weeks, 3 months")
                return
            state = await streak_model.set_period(context.bot , chat_id , days)
            await update.message.reply_text(
                f"These are your goals, {days} days each:\n" + _goals_list(state) ,
                reply_markup=_menu_keyboard()
            )

        elif waiting == streak_model.WAITING_REPORT:
            answer = text.lower()
            if answer not in YES_ANSWERS and answer not in NO_ANSWERS:
                await update.message.reply_text("Please answer Yes or No" , reply_markup=_yes_no_keyboard())
                return

            state , goal = await streak_model.answer_goal(context.bot , chat_id , answer in YES_ANSWERS)
            if goal is not None:
                if answer in YES_ANSWERS:
                    await update.message.reply_text(f"{goal['text']}: {streak_model.count_of(goal)}/{state['period_days'] or '?'} 🔥")
                else:
                    await update.message.reply_text(f"{goal['text']}: back to 0. Tomorrow is a new day 💪")

            # Every goal gets its own question, one message each.
            if await _ask_next_goal(update , state):
                return
            await update.message.reply_text("Day reported!\n\n" + _goals_list(state) , reply_markup=_menu_keyboard())
            await _notify_friend(context.bot , chat_id , state)
