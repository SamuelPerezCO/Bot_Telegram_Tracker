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
# "Not yet" is for the goals that are simply not done at this hour of
# the day: it changes nothing, so somebody can confirm one goal in the
# morning without having to lie about the rest.
YES_ANSWERS = {"yes" , "y" , "si" , "sí" , "yeah" , "yep" , "✅"}
NO_ANSWERS = {"no" , "n" , "nope" , "nah" , "❌"}
LATER_ANSWERS = {"not yet" , "notyet" , "later" , "aun no" , "aún no" , "todavia no" , "todavía no" , "⏳"}

# Answers that mean "this goal does not need a reminder".
SKIP_ANSWERS = {"no" , "none" , "skip" , "nada" , "-"}


def _parse_pairs(value):
    """Reads a "name:chat_id" list as written in the environment.

    Args:
        value (str): Something like "El Hi:12345,Samuel:67890".

    Returns:
        list[tuple[int, str]]: (chat_id, name) of each valid pair.
    """
    pairs = []
    for entry in (value or "").split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name , _ , chat_id = entry.rpartition(":")
        if chat_id.strip().lstrip("-").isdigit():
            pairs.append((int(chat_id.strip()) , name.strip()))
    return pairs


def configured_users():
    """Lists the people using the bot, from the environment.

    They are configured in USERS as "name:chat_id" pairs:

        USERS=El Hi:12345,El tornillo:67890,Samuel:24680

    Adding somebody is only adding a pair there, no code changes. The
    chat listed here is the one holding that person's goals: their
    other chats point back to it (see extra_chats).

    The older HI_CHAT_ID / TORNILLO_CHAT_ID variables still work when
    USERS is not set, so an existing deployment keeps running until it
    is migrated.

    Returns:
        list[tuple[int, str]]: (chat_id, name) of every configured user.
    """
    users = _parse_pairs(os.getenv("USERS"))
    if not users:
        for variable , name in (("HI_CHAT_ID" , "El Hi") , ("TORNILLO_CHAT_ID" , "El tornillo")):
            chat_id = os.getenv(variable)
            if chat_id:
                users.append((int(chat_id) , name))
    return users


def extra_chats():
    """Lists the other chats of somebody already in USERS.

    The same person can use the bot from two phones, which for Telegram
    are two different chats. They are configured in SEND_REMINDER with
    the same shape as USERS, repeating the name:

        SEND_REMINDER=El Hi:24680

    Those chats are the same person: they share the goals of the chat
    in USERS, can report from either side, and all of them receive the
    reminders and what the others report.

    Returns:
        list[tuple[int, str]]: (chat_id, name) of every extra chat.
    """
    extras = _parse_pairs(os.getenv("SEND_REMINDER"))
    if not extras and not os.getenv("USERS") and os.getenv("HI_CHAT_ID_2"):
        extras = [(int(os.getenv("HI_CHAT_ID_2")) , "El Hi")]
    return extras


def _name_of(chat_id):
    """Name of the person writing from a chat, main one or extra.

    Args:
        chat_id (int): Chat id to look up.

    Returns:
        str | None: The configured name, or None when the chat belongs
        to nobody known.
    """
    for known_id , name in configured_users() + extra_chats():
        if known_id == chat_id:
            return name
    return None


def home_chat(chat_id):
    """Finds the chat holding the goals of whoever writes from here.

    Everything is stored in the pinned message of one chat per person,
    so a message coming from a second phone has to read and write that
    same chat instead of starting a second, separate set of goals.

    Args:
        chat_id (int): Chat the message came from.

    Returns:
        int: Chat id where that person's goals live. The chat itself
        when it belongs to nobody configured.
    """
    name = _name_of(chat_id)
    if name is not None:
        for user_id , user_name in configured_users():
            if user_name == name:
                return user_id
    return chat_id


def chats_of(name):
    """Every chat of one person: the main one and the extras.

    Args:
        name (str): Configured name of the person.

    Returns:
        list[int]: Chat ids to write to when telling them something.
    """
    return [chat_id for chat_id , other in configured_users() + extra_chats() if other == name]


def _friends_of(chat_id):
    """Lists everybody except the person asking.

    Args:
        chat_id (int): Chat id of the person asking.

    Returns:
        list[tuple[int, str]]: (home chat id, name) of the others.
    """
    me = _name_of(chat_id)
    return [(user_id , name) for user_id , name in configured_users() if name != me]


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


def _answer_keyboard():
    """Builds the keyboard used while reporting the day.

    Returns:
        telegram.ReplyKeyboardMarkup: A keyboard with Yes, No and
        Not yet.
    """
    return ReplyKeyboardMarkup(
        [[KeyboardButton("Yes") , KeyboardButton("No") , KeyboardButton("Not yet")]] ,
        resize_keyboard=True
    )


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
    index = streak_model.next_to_ask(state)
    if index is None:
        return False

    goal = state["goals"][index]
    await update.message.reply_text(
        f"Did you achieve it today?\n\n{index + 1}. {goal['text']} ({streak_model.count_of(goal)}/{state['period_days'] or '?'})" ,
        reply_markup=_answer_keyboard()
    )
    return True


async def _send_to_person(bot , name , text , reply_markup=None):
    """Writes to every chat of one person.

    Args:
        bot: The bot instance.
        name (str): Configured name of the person.
        text (str): Message to send.
        reply_markup: Keyboard to attach, if any.

    Returns:
        int: How many chats received the message.
    """
    delivered = 0
    for chat_id in chats_of(name):
        try:
            await bot.send_message(chat_id , text , reply_markup=reply_markup)
            delivered += 1
        except Exception:
            pass  # that chat has not started the bot yet, nothing to do
    return delivered


async def _notify_friends(bot , chat_id , state):
    """Tells everybody else that this person just reported the day.

    Args:
        bot: The bot instance (context.bot).
        chat_id (int): Chat id of the person who reported.
        state (dict): State of the person after the report.
    """
    own_name = _name_of(chat_id) or "Somebody"
    for _ , friend_name in _friends_of(chat_id):
        await _send_to_person(bot , friend_name , f"{own_name} just reported the day!\n\n{_goals_list(state)}")


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
            # Every chat of that person, so the reminder arrives on
            # both phones.
            if await _send_to_person(bot , name , text , menu_keyboard()):
                sent.append(number)
            else:
                report.append(f"{name}: could not send the reminder of goal {number}")

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
        delivered = await _send_to_person(
            bot , name ,
            "Ready to report your day? ⏰\n\nStill pending:\n" + "\n".join(lines) ,
            menu_keyboard()
        )
        if not delivered:
            report.append(f"{name}: could not send the summary")
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
        state = await streak_model.init_state(context.bot , home_chat(update.effective_chat.id))
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
        # The goals live in one chat per person, so a message coming
        # from that person's second phone works on the same ones.
        chat_id = home_chat(update.effective_chat.id)
        choice = update.message.text

        if choice == "I want to report my day":
            state = await streak_model.get_state(context.bot , chat_id)
            if not state["goals"]:
                await update.message.reply_text("You have no goals yet, add them first." , reply_markup=menu_keyboard())
                return
            # next_unanswered and not next_to_ask: a goal left for
            # later is still pending, so asking again has to work.
            if streak_model.next_unanswered(state) is None:
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
        chat_id = home_chat(update.effective_chat.id)
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
                reply_markup=ReplyKeyboardRemove()
            )

        elif waiting == streak_model.WAITING_REPORT:
            written = text.lower()
            if written in YES_ANSWERS:
                answer = streak_model.ANSWER_YES
            elif written in NO_ANSWERS:
                answer = streak_model.ANSWER_NO
            elif written in LATER_ANSWERS:
                answer = streak_model.ANSWER_LATER
            else:
                await update.message.reply_text("Please answer Yes, No or Not yet" , reply_markup=_answer_keyboard())
                return

            state , goal = await streak_model.answer_goal(context.bot , chat_id , answer)
            if goal is not None:
                if answer == streak_model.ANSWER_YES:
                    await update.message.reply_text(f"{goal['text']}: {streak_model.count_of(goal)}/{state['period_days'] or '?'} 🔥")
                elif answer == streak_model.ANSWER_NO:
                    await update.message.reply_text(f"{goal['text']}: back to 0. Tomorrow is a new day 💪")
                else:
                    await update.message.reply_text(f"{goal['text']}: left for later ⏳")

            # Every goal gets its own question, one message each.
            if await _ask_next_goal(update , state):
                return

            # Whatever was left for later is still waiting for an
            # answer, so the report is only "done" for the rest.
            left = [
                f"{number}. {goal['text']}" for number , goal in enumerate(state["goals"] , 1)
                if goal["last"] != streak_model.today_iso()
            ]
            answered = len(state["goals"]) - len(left)
            summary = "Day reported!\n\n" if answered else "Nothing confirmed yet.\n\n"
            summary += _goals_list(state)
            if left:
                summary += "\n\nStill to confirm today:\n" + "\n".join(left)
            await update.message.reply_text(summary , reply_markup=ReplyKeyboardRemove())

            # Nothing to tell the others when everything was left for
            # later: there is no news yet.
            if answered:
                await _notify_friends(context.bot , chat_id , state)
