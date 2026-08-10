"""Builds the bot application: handlers, commands and routing.

Shared by the two entry points: run_local.py runs it with polling on a
local machine, api/index.py feeds it one update per request on Vercel.

There is no ConversationHandler on purpose. Vercel is serverless: every
update can land on a fresh instance, so any state kept in memory (like
the conversation state) would be lost between messages. The buttons of
each step have different texts, so each message is routed by its own
text. The steps that need to remember something (the goals
questionnaire and the daily report, which ask one question per
message) keep that in the pinned message of the chat instead of in
memory: see Models.streak_model.
"""

from telegram.ext import ApplicationBuilder , CommandHandler , MessageHandler , filters
from dotenv import load_dotenv
import os

from Controllers import tracker_controller


# Texts of the buttons shown in each step, used to route the messages.
WHO_ARE_YOU_BUTTONS = r"^(El Hi|El tornillo)$"
MENU_BUTTONS = r"^I want to (report my day|see my goals|see my friend's goals|add my goals)$"


def build_application():
    """Creates the Application with every handler already registered.

    Returns:
        telegram.ext.Application: The bot application, not started yet.

    Raises:
        RuntimeError: If TOKEN_BOT is not set in the environment.
    """
    load_dotenv()
    token = os.getenv("TOKEN_BOT")
    if not token:
        raise RuntimeError("TOKEN_BOT is not set (add it to .env or to the Vercel environment variables)")

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start" , tracker_controller.tracker_controller.who_are_you))
    application.add_handler(CommandHandler("id" , tracker_controller.tracker_controller.chat_id))
    application.add_handler(MessageHandler(filters.Regex(WHO_ARE_YOU_BUTTONS) , tracker_controller.tracker_controller.who_are_you_answer))
    application.add_handler(MessageHandler(filters.Regex(MENU_BUTTONS) , tracker_controller.tracker_controller.menu))
    # Registered last and in the same group: only the first handler that
    # matches inside a group runs, so this one catches anything else.
    # It is also where the answers of the questionnaires arrive (the
    # goals, and the Yes/No of the daily report), since those are not
    # menu buttons.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND , tracker_controller.tracker_controller.free_text))

    return application
