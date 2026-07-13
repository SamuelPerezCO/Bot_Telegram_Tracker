"""Entry point of the tracker bot (t.me/Tracker90Bot).

Loads the token from .env and wires the conversation flow before
starting the polling loop. Streaks are stored in each chat's pinned
message (see Models.streak_model), so no database is needed.
"""

from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes , MessageHandler , filters , ConversationHandler , CallbackQueryHandler
from dotenv import load_dotenv
from telegram import Update
import os

from Controllers import tracker_controller


load_dotenv()
TOKEN_BOT = os.getenv("TOKEN_BOT")

application = ApplicationBuilder().token(TOKEN_BOT).build()
conversation = ConversationHandler(
    entry_points=[ CommandHandler("start" , tracker_controller.tracker_controller.who_are_you) ],
    states={
        tracker_controller.WHO_ARE_YOU: [ MessageHandler(filters.TEXT & ~filters.COMMAND , tracker_controller.tracker_controller.who_are_you_answer) ],
        tracker_controller.MENU: [ MessageHandler(filters.TEXT & ~filters.COMMAND , tracker_controller.tracker_controller.report_new_day) ],
    },
    fallbacks=[ CommandHandler("start" , tracker_controller.tracker_controller.who_are_you) ],
)
application.add_handler(conversation)

application.run_polling(allowed_updates=Update.ALL_TYPES)




"""
URL of the BOT:
t.me/Tracker90Bot
"""