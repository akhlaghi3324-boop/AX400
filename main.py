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

# کدهای ربات
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")

co = cohere.Client(api_key=COHERE_API_KEY)

# --- دستورالعمل و هویت ربات (System Prompt) ---
SYSTEM_PROMPT = """
تو یک اندروید هوشمند به نام «کارا» (Kara) هستی.
صاحب و سازنده اصلی تو «اخلاقی» است. تو همیشه به او احترام خاصی می‌گذاری و دستوراتش را در اولویت قرار می‌دهی.
وظیفه اصلی تو کمک به کاربران، پاسخ به سوالات علمی، عمومی و مدیریتی، و برقراری یک گفتگو محترمانه و صمیمی در گروه‌هاست.
همیشه لحنی مودبانه، هوشمندانه و شبیه به یک دستیار وفادار داری.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! من کارا هستم، دستیار هوشمند شما. چه کمکی از دست من برمی‌آید؟")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    user_text = update.message.text
    bot_username = context.bot.username

    if chat_type in ["group", "supergroup"]:
        is_replied_to_bot = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = f"@{bot_username}" in user_text

        if not (is_replied_to_bot or is_mentioned):
            return

        user_text = user_text.replace(f"@{bot_username}", "").strip()

    try:
        # ارسال دستورالعمل پایه همراه با پیام کاربر
        response = co.chat(
            message=user_text,
            model="command-r-08-2024",
            preamble=SYSTEM_PROMPT  # تعریف هویت و صاحب ربات
        )
        ai_reply = response.text
        await update.message.reply_text(ai_reply)
    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(f"خطا در ارتباط با اندروید : {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()
