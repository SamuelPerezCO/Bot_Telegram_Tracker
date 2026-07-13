from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes , MessageHandler , filters , ConversationHandler , CallbackQueryHandler
from dotenv import load_dotenv
from telegram import Update
import os

from Controllers import tracker_controller


load_dotenv()
TOKEN_BOT = os.getenv("TOKEN_BOT")

application = ApplicationBuilder().token(TOKEN_BOT).build()
application.add_handler( CommandHandler("start" , tracker_controller.tracker_controller.who_are_you ) )
application.run_polling(allowed_updates=Update.ALL_TYPES)


"""
URL of the BOT:
t.me/Tracker90Bot
"""