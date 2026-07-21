import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import cohere
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ساخت سرور برای Render
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# تنظیمات کلیدها
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")

co = cohere.Client(api_key=COHERE_API_KEY)

# مشخصات صاحب ربات
OWNER_USERNAME = "Senator_MRA"

# هویت و دستورالعمل اصلی ربات
SYSTEM_PROMPT = """
تو یک اندروید هوشمند به نام «کارا» (Kara) هستی.
صاحب و سازنده اصلی تو «اخلاقی» با آیدی Senator_MRA@ است. تو همیشه به او احترام خاصی می‌گذاری ولی هیچ وقت اسمش را به دلیل امنیتی نمیگویی و دستوراتش را در اولویت قرار می‌دهی.
تو حافظه گفتگو داری و پیام‌های قبلی کاربر را به یاد می‌آوری تا مکالمه‌ای روان و طبیعی داشته باشی.
"""

# ذخیره‌سازی تاریخچه چت‌ها (حافظه)
# این دیکشنری پیام‌های اخیر هر چت را نگهداری می‌کند
chat_histories = {}
MAX_HISTORY_LENGTH = 10  # تعداد پیام‌های نگه‌داری‌شده در حافظه

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! من کارا هستم، دستیار هوشمند شما. من صحبت‌های قبلی‌مان را به یاد می‌آورم!")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_username = update.effective_user.username
    if user_username != OWNER_USERNAME:
        await update.message.reply_text("متأسفم، این دستور فقط برای صاحب ربات (اخلاقی) قابل استفاده است.")
        return
    await update.message.reply_text("🟢 بله سرور کاملاً بیدار و فعال است !")

# دستور پاک کردن حافظه چت
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        chat_histories[chat_id] = []
        await update.message.reply_text("🧹 حافظه مکالمه ما پاک شد. می‌توانیم گفتگو را از نو شروع کنیم!")
    else:
        await update.message.reply_text("حافظه‌ای برای پاک کردن وجود ندارد.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user_text = update.message.text
    bot_username = context.bot.username

    # بررسی شرط پاسخ در گروه
    if chat_type in ["group", "supergroup"]:
        is_replied_to_bot = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = f"@{bot_username}" in user_text

        if not (is_replied_to_bot or is_mentioned):
            return

        user_text = user_text.replace(f"@{bot_username}", "").strip()

    # مقداردهی اولیه حافظه برای این چت در صورت عدم وجود
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    try:
        # ارسال پیام و دریافت پاسخ با در نظر گرفتن تاریخچه چت
        response = co.chat(
            message=user_text,
            model="command-r-08-2024",
            preamble=SYSTEM_PROMPT,
            chat_history=chat_histories[chat_id]  # ارسال پیام‌های قبلی به Cohere
        )
        ai_reply = response.text

        # به روزرسانی تاریخچه مکالمات در حافظه
        chat_histories[chat_id].append({"role": "USER", "message": user_text})
        chat_histories[chat_id].append({"role": "CHATBOT", "message": ai_reply})

        # محدود نگه داشتن حجم حافظه تا حداکثر تعداد مشخص‌شده
        if len(chat_histories[chat_id]) > MAX_HISTORY_LENGTH * 2:
            chat_histories[chat_id] = chat_histories[chat_id][-MAX_HISTORY_LENGTH * 2:]

        await update.message.reply_text(ai_reply)

    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(f"خطا در ارتباط با اندروید : {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("clear", clear_history))  # دستور پاک کردن حافظه
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()
