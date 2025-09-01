import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import gspread
from google.oauth2.service_account import Credentials

# --- تنظیمات اولیه --- #
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- توکن‌های تو (اینها را عوض کن) --- #
TELEGRAM_TOKEN = "TELEGRAM_BOT_TOKEN"  # توکن ربات تلگرام را اینجا بگذار
OPENAI_API_KEY = "OPENAI_API_KEY"      # کلید API OpenAI را اینجا بگذار (از platform.openai.com/api-keys)

# --- تنظیمات دسترسی به Google Sheets --- #
# اگر نمیخواهی از Sheets استفاده کنی، این بخش را پاک کن
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SHEETS_CREDENTIALS = Credentials.from_service_account_file('credentials.json')  # این فایل را بعداً میسازیم
SHEETS_CLIENT = gspread.authorize(SHEETS_CREDENTIALS)
SHEET_NAME = "UserData"  # اسم Sheet تو
SHEET = SHEETS_CLIENT.open(SHEET_NAME).sheet1  # به اولین sheet اشاره میکند

# --- کلاینت OpenAI --- #
client = OpenAI(api_key=OPENAI_API_KEY)

# --- دیکشنری برای ذخیره موقت داده کاربران --- #
user_data = {}

# --- حالتهای ربات --- #
class State:
    AWAITING_NAME = 1
    AWAITING_AGE = 2
    AWAITING_EMAIL = 3

# --- دستور /start --- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {}  # Reset user data
    await update.message.reply_text(
        "👋 سلام! به ربات هوشمند ثبت‌نام خوش آمدید.\nلطفاً نام و نام خانوادگی خود را وارد کنید:"
    )
    return State.AWAITING_NAME

# --- پردازش نام --- #
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]['name'] = update.message.text
    await update.message.reply_text("✅ نام ذخیره شد. لطفاً سن خود را وارد کنید:")
    return State.AWAITING_AGE

# --- پردازش سن --- #
async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        age = int(update.message.text)
        user_data[user_id]['age'] = age
        await update.message.reply_text("✅ سن ذخیره شد. لطفاً ایمیل خود را وارد کنید:")
        return State.AWAITING_EMAIL
    except ValueError:
        await update.message.reply_text("❌ سن باید یک عدد باشد. لطفاً دوباره وارد کنید:")
        return State.AWAITING_AGE

# --- پردازش ایمیل و ذخیره در Sheets --- #
async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    email = update.message.text
    user_data[user_id]['email'] = email

    # ذخیره در Google Sheets (اگر فعال باشد)
    try:
        row = [user_data[user_id].get('name', ''), user_data[user_id].get('age', ''), email]
        SHEET.append_row(row)
        await update.message.reply_text("🎉 اطلاعات شما با موفقیت در سیستم ثبت شد!")
    except Exception as e:
        logger.error(f"Error saving to sheet: {e}")
        await update.message.reply_text("✅ اطلاعات شما دریافت شد! (خطای ذخیره سازی)")

    # پاک کردن داده موقت
    user_data.pop(user_id, None)
    return ConversationHandler.END

# --- پردازش سوالات با هوش مصنوعی --- #
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.effective_user.id

    # اگر کاربر در حال ثبت‌نام است، پیامش را به عنوان پاسخ به ثبت‌نام در نظر بگیر
    if user_id in user_data:
        # این بخش را میتوانید برای مدیریت حالتهای مختلف گسترش دهید
        await update.message.reply_text("لطفاً فرآیند ثبت‌نام را تکمیل کنید.")
        return

    # اگر کاربر سوال میپرسد، به هوش مصنوعی بسپار
    try:
        # ساخت مکالمه برای هوش مصنوعی
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Answer the user's question. If the question is about politics, religion, or is inappropriate, politely refuse to answer. Keep your answers concise and in Persian."},
                {"role": "user", "content": user_message}
            ],
            max_tokens=150
        )
        ai_response = response.choices[0].message.content
        await update.message.reply_text(ai_response)

    except Exception as e:
        logger.error(f"OpenAI Error: {e}")
        await update.message.reply_text("⚡ متأسفانه در حال حاضر قادر به پاسخگویی نیستم.")

# --- دستور /cancel --- #
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    await update.message.reply_text("❌ عملیات ثبت‌نام لغو شد.")
    return ConversationHandler.END

# --- اصلی ترین تابع --- #
def main():
    # ساخت اپلیکیشن تلگرام
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # مدیریت مکالمه برای ثبت‌نام
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            State.AWAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            State.AWAITING_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            State.AWAITING_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # شروع ربات
    application.run_polling()

if __name__ == '__main__':
    main()
