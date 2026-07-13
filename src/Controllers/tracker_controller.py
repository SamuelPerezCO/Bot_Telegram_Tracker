from telegram import Update , ReplyKeyboardRemove ,InlineKeyboardMarkup , InlineKeyboardButton , KeyboardButton , ReplyKeyboardMarkup
from telegram.ext import ContextTypes , ConversationHandler , CallbackContext

WHO_ARE_YOU = 0   
MENU = 1          

class tracker_controller:

    @staticmethod
    async def who_are_you(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("El Hi") , KeyboardButton("El tornillo")]
        ])
        await update.message.reply_text("Who are you?" , reply_markup=keyboard)
        return WHO_ARE_YOU

    @staticmethod
    async def who_are_you_answer(update:Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = ReplyKeyboardMarkup([
            [KeyboardButton("I want to report a new day") , KeyboardButton("I want to report that I lose")]
        ])
        if update.message.text == "El Hi":
            await update.message.reply_text("Your Current Streak Is EL HI" , reply_markup=ReplyKeyboardRemove())
            await update.message.reply_text("What do you want to do?" , reply_markup=keyboard)
        else:
            await update.message.reply_text("Your Current Streak Is TORNILLO" , reply_markup=ReplyKeyboardRemove())
            await update.message.reply_text("What do you want to do?" , reply_markup=keyboard)
        return MENU

    @staticmethod
    async def report_new_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text == "I want to report a new day":
            await update.message.reply_text("You won" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif update.message.text == "I want to report that I lose":
            await update.message.reply_text("You are gay" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        else:
            await update.message.reply_text("Please use one of the buttons")
            return MENU
