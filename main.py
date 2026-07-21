import os
import cohere
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# دریافت کلیدها از متغیرهای محیطی سرور
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")

# راه اندازی کلاینت Cohere
co = cohere.ClientV2(api_key=COHERE_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! من ربات هوش مصنوعی شما هستم. هر سوالی داری بپرس!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        # ارسال پیام کاربر به هوش مصنوعی
        response = co.chat(
            model="command-r-plus",
            messages=[{"role": "user", "content": user_text}]
        )
        ai_reply = response.message.content[0].text
        await update.message.reply_text(ai_reply)
    except Exception as e:
        await update.message.reply_text("متأسفانه مشکلی در دریافت پاسخ پیش آمد. لطفاً دوباره تلاش کنید.")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot is running...")
    app.run_polling()

