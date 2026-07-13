from telegram import Update , ReplyKeyboardRemove ,InlineKeyboardMarkup , InlineKeyboardButton , KeyboardButton , ReplyKeyboardMarkup
from telegram.ext import ContextTypes , ConversationHandler , CallbackContext

class tracker_controller:
    @staticmethod
    async def who_are_you(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("El Hi") , KeyboardButton("El tornillo")]
        ])
        await update.message.reply_text("Who are you?" , reply_markup=ReplyKeyboardRemove())