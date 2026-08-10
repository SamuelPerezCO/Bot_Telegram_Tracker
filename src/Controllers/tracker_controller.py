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

# Answers that mean "this goal does not need a reminder".
SKIP_ANSWERS = {"no" , "none" , "skip" , "nada" , "-"}


def configured_users():
    """Lists the people using the bot, from the environment.

    They are configured in USERS as "name:chat_id" pairs:

        USERS=El Hi:12345,El tornillo:67890,Samuel:24680

    Adding somebody is only adding a pair there, no code changes. The
    older HI_CHAT_ID / TORNILLO_CHAT_ID variables still work when USERS
    is not set, so an existing deployment keeps running until it is.

    Returns:
        list[tuple[int, str]]: (chat_id, name) of every configured user.
    """
    users = []
    for entry in os.getenv("USERS" , "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name , _ , chat_id = entry.rpartition(":")
        if chat_id.strip().lstrip("-").isdigit():
            users.append((int(chat_id.strip()) , name.strip()))

    if not users:
        for variable , name in (("HI_CHAT_ID" , "El Hi") , ("TORNILLO_CHAT_ID" , "El tornillo")):
            chat_id = os.getenv(variable)
            if chat_id:
                users.append((int(chat_id) , name))
    return users


def _friends_of(chat_id):
    """Lists everybody except the user asking.

    Args:
        chat_id (int): Chat id of the user asking.

    Returns:
        list[tuple[int, str]]: (chat_id, name) of the other users.
    """
    return [user for user in configured_users() if user[0] != chat_id]


def _name_of(chat_id):
    """Name of one user, for the messages sent to the others.

    Args:
        chat_id (int): Chat id to look up.

    Returns:
        str: The configured name, or "Somebody" when it is unknown.
    """
    for user_id , name in configured_users():
        if user_id == chat_id:
            return name
    return "Somebody"


def menu_keyboard():
    """Builds the keyboard with the actions of the main menu.

    Public because the daily reminder (api/remind.py) sends it too, so
    the user can start the report with one tap.

    Returns:
        telegram.ReplyKeyboardMarkup: The menu keyboard.
    """
    return ReplyKeyboardMarkup([
        [KeyboardButton("I want to report my day")] ,
        [KeyboardButton("I want to see my goals") , KeyboardButton("I want to see my friends' goals")] ,
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
        alarm = f" ⏰{goal['time']}" if goal["time"] != "none" else ""
        lines.append(f"{number}. {goal['text']} {streak_model.count_of(goal)}/{denominator}{alarm}{done}")
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


async def _notify_friends(bot , chat_id , state):
    """Tells everybody else that this user just reported the day.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Chat id of the user who reported.
        state (dict): State of the user after the report.
    """
    own_name = _name_of(chat_id)
    for friend_id , _ in _friends_of(chat_id):
        try:
            await bot.send_message(friend_id , f"{own_name} just reported the day!\n\n{_goals_list(state)}")
        except Exception:
            pass  # that friend has not started the bot yet, nothing to do


async def send_due_reminders(bot):
    """Sends the reminder of every goal whose hour has arrived.

    Called by the scheduled endpoint (api/remind.py) once a minute.
    The hour of each goal is stored with the goal itself, so this is
    the only place that decides whether it is time.

    Args:
        bot: The bot instance.

    Returns:
        list[str]: One line per user for the scheduler log.
    """
    report = []
    for chat_id , name in configured_users():
        try:
            state = await streak_model.get_state(bot , chat_id)
        except Exception as error:
            report.append(f"{name}: could not read the chat ({error!r})")
            continue

        due = streak_model.due_reminders(state)
        if not due:
            continue

        sent = []
        for number , goal in due:
            text = (
                f"⏰ {goal['time']} - {goal['text']}\n"
                f"{streak_model.count_of(goal)}/{state['period_days'] or '?'} so far. Is it done?"
            )
            try:
                await bot.send_message(chat_id , text , reply_markup=menu_keyboard())
            except Exception as error:
                report.append(f"{name}: could not send the reminder of goal {number} ({error!r})")
                continue
            sent.append(number)

        if sent:
            # Written down only after the message left, so a failure is
            # retried on the next run instead of being lost.
            await streak_model.mark_reminders_sent(bot , chat_id , sent)
            report.append(f"{name}: reminded about goal(s) {' , '.join(str(number) for number in sent)}")

    return report


async def send_daily_reminders(bot):
    """Asks every user to report the day, unless they already did.

    Called by the scheduled endpoint (api/remind.py), never by an
    update: this is the only message the bot sends on its own.

    Args:
        bot: The bot instance.

    Returns:
        list[str]: One line per user saying what was done, so the cron
        log shows why somebody was not written to.
    """
    report = []
    for chat_id , name in configured_users():
        try:
            state = await streak_model.get_state(bot , chat_id)
        except Exception as error:
            report.append(f"{name}: could not read the chat ({error!r})")
            continue

        if not state["goals"]:
            report.append(f"{name}: skipped, no goals yet")
            continue

        pending = [
            (number , goal) for number , goal in enumerate(state["goals"] , 1)
            if goal["last"] != streak_model.today_iso()
        ]
        if not pending:
            report.append(f"{name}: skipped, already reported today")
            continue

        denominator = state["period_days"] or "?"
        lines = [f"{number}. {goal['text']} {streak_model.count_of(goal)}/{denominator}" for number , goal in pending]
        try:
            await bot.send_message(
                chat_id ,
                "Ready to report your day? ⏰\n\nStill pending:\n" + "\n".join(lines) ,
                reply_markup=menu_keyboard()
            )
        except Exception as error:
            report.append(f"{name}: could not send the reminder ({error!r})")
            continue
        report.append(f"{name}: reminded, {len(pending)} goal(s) pending")

    return report


class tracker_controller:
    """Handlers for each step of the bot conversation."""

    @staticmethod
    async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Replies with the chat id (/id command).

        Used once per person to build the USERS variable of the
        environment.

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
        names = [name for _ , name in configured_users()]
        if not names:
            # Nobody configured yet: skip the question instead of
            # showing an empty keyboard.
            await tracker_controller.who_are_you_answer(update , context)
            return

        keyboard = ReplyKeyboardMarkup([[KeyboardButton(name) for name in names]])
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
        await update.message.reply_text("What do you want to do?" , reply_markup=menu_keyboard())

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
                await update.message.reply_text("You have no goals yet, add them first." , reply_markup=menu_keyboard())
                return
            if streak_model.next_pending(state) is None:
                await update.message.reply_text("You already reported every goal today.\n\n" + _goals_list(state) , reply_markup=menu_keyboard())
                return
            state = await streak_model.begin_report(context.bot , chat_id)
            await _ask_next_goal(update , state)

        elif choice == "I want to see my goals":
            state = await streak_model.get_state(context.bot , chat_id)
            if not state["goals"]:
                await update.message.reply_text("You have no goals yet, add them first." , reply_markup=menu_keyboard())
                return
            await update.message.reply_text("Your goals:\n" + _goals_list(state) , reply_markup=menu_keyboard())

        elif choice == "I want to see my friends' goals":
            friends = _friends_of(chat_id)
            if not friends:
                await update.message.reply_text("Nobody else is configured yet (set USERS)" , reply_markup=menu_keyboard())
                return

            # One message with everybody, so it stays readable however
            # many people end up using the bot.
            blocks = []
            for friend_id , friend_name in friends:
                try:
                    state = await streak_model.get_state(context.bot , friend_id)
                except Exception:
                    blocks.append(f"{friend_name}: I could not reach the chat. Has he started the bot?")
                    continue
                blocks.append(f"{friend_name}:\n" + (_goals_list(state) if state["goals"] else "no goals yet"))
            await update.message.reply_text("\n\n".join(blocks) , reply_markup=menu_keyboard())

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
            await update.message.reply_text("Ok, I stopped asking." , reply_markup=menu_keyboard())
            return

        if waiting == streak_model.WAITING_COUNT:
            if not text.isdigit() or not 1 <= int(text) <= streak_model.MAX_GOALS:
                await update.message.reply_text(f"Please answer with a number between 1 and {streak_model.MAX_GOALS}")
                return
            await streak_model.set_goal_count(context.bot , chat_id , int(text))
            await update.message.reply_text("Tell me goal number 1")

        elif waiting == streak_model.WAITING_GOAL:
            state = await streak_model.add_goal(context.bot , chat_id , text)
            await update.message.reply_text(
                f"At what time do you want a reminder for \"{state['goals'][-1]['text']}\"?\n"
                "For example: 5:00, 17:30, 9 pm\n"
                "Answer \"no\" if you do not want one."
            )

        elif waiting == streak_model.WAITING_TIME:
            if text.lower() in SKIP_ANSWERS:
                time = "none"
            else:
                time = streak_model.parse_time(text)
                if time is None:
                    await update.message.reply_text("I did not understand that hour. Try something like: 5:00, 17:30, 9 pm - or \"no\"")
                    return

            state = await streak_model.set_goal_time(context.bot , chat_id , time)
            confirmation = f"Reminder set at {time} ⏰" if time != "none" else "No reminder for that one"
            if state["waiting"] == streak_model.WAITING_GOAL:
                await update.message.reply_text(f"{confirmation}\n\nTell me goal number {len(state['goals']) + 1}")
            else:
                await update.message.reply_text(
                    f"{confirmation}\n\nI have your {state['goal_count']} goals.\n"
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
                reply_markup=menu_keyboard()
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
            await update.message.reply_text("Day reported!\n\n" + _goals_list(state) , reply_markup=menu_keyboard())
            await _notify_friends(context.bot , chat_id , state)
