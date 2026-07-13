from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes , MessageHandler , filters , ConversationHandler , CallbackQueryHandler
from dotenv import load_dotenv
from telegram import Update
import os

from Controllers import tracker_controller
from Models import streak_model


load_dotenv()
TOKEN_BOT = os.getenv("TOKEN_BOT")

streak_model.create_table()

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