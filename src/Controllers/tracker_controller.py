from telegram import Update , ReplyKeyboardRemove ,InlineKeyboardMarkup , InlineKeyboardButton , KeyboardButton , ReplyKeyboardMarkup
from telegram.ext import ContextTypes , ConversationHandler , CallbackContext

from Models import streak_model

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
        streak = streak_model.get_streak(update.effective_user.id)
        await update.message.reply_text(f"Your Current Streak Is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("What do you want to do?" , reply_markup=keyboard)
        return MENU

    @staticmethod
    async def report_new_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if update.message.text == "I want to report a new day":
            streak , counted = streak_model.report_day(user.id , user.username)
            if counted:
                await update.message.reply_text(f"Day reported! Your streak is now {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
            else:
                await update.message.reply_text(f"You already reported today. Your streak is {streak} 🔥" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        elif update.message.text == "I want to report that I lose":
            streak_model.reset_streak(user.id , user.username)
            await update.message.reply_text("Streak reset to 0. Start again tomorrow 💪" , reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        else:
            await update.message.reply_text("Please use one of the buttons")
            return MENU
