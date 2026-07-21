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

# ذخیره‌سازی داده‌ها
chat_histories = {}
group_recent_messages = {}
MAX_HISTORY_LENGTH = 10
MAX_GROUP_MESSAGES = 30

# مجموعه‌های جدید برای ذخیره آمار (محیط‌های کاری)
active_groups = set()  # شناسه گروه‌ها
active_users = set()   # شناسه کاربران در پیوی

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    
    if chat_type in ["group", "supergroup"]:
        active_groups.add(chat_id)
    else:
        active_users.add(chat_id)
        
    await update.message.reply_text("سلام! من کارا هستم، دستیار هوشمند شما. من صحبت‌های قبلی‌مان را به یاد می‌آورم!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **راهنمای استفاده از اندروید کارا در گروه:**\n\n"
        "1️⃣ برای گفتگو در گروه، کافیست روی پیام من **Reply** کنید یا آیدی من را **Mention** کنید.\n"
        "2️⃣ **`/summary`**: دریافت خلاصه‌ای از آخرین گفتگوهای گروه.\n"
        "3️⃣ **`/clear`**: پاک کردن حافظه مکالمات اختصاصی.\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_username = update.effective_user.username
    if user_username != OWNER_USERNAME:
        await update.message.reply_text("متأسفم، این دستور فقط برای صاحب ربات (اخلاقی) قابل استفاده است.")
        return
    await update.message.reply_text("🟢 بله سرور کاملاً بیدار و فعال است !")

# دستور جدید: مشاهده آمار گروه‌ها و کاربران (مخصوص شما)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_username = update.effective_user.username
    if user_username != OWNER_USERNAME:
        await update.message.reply_text("متأسفم، این دستور فقط برای صاحب ربات قابل استفاده است.")
        return

    stats_msg = (
        "📊 **گزارش آمار اندروید کارا:**\n\n"
        f"👥 **تعداد گروه‌ها:** {len(active_groups)} گروه\n"
        f"👤 **تعداد کاربران خصوصی (PV):** {len(active_users)} کاربر\n"
        f"🌐 **مجموع کل چت‌های فعال:** {len(active_groups) + len(active_users)}"
    )
    await update.message.reply_text(stats_msg, parse_mode="Markdown")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        chat_histories[chat_id] = []
        await update.message.reply_text("🧹 حافظه مکالمه ما پاک شد. می‌توانیم گفتگو را از نو شروع کنیم!")
    else:
        await update.message.reply_text("حافظه‌ای برای پاک کردن وجود ندارد.")

async def summarize_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    if chat_type not in ["group", "supergroup"]:
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return

    messages = group_recent_messages.get(chat_id, [])
    if len(messages) < 3:
        await update.message.reply_text("پیام‌های کافی برای خلاصه کردن وجود ندارد.")
        return

    await update.message.reply_text("⏳ در حال پردازش و خلاصه‌سازی گفتگوهای اخیر گروه...")

    combined_text = "\n".join(messages)
    prompt = f"لطفاً متن زیر که مکالمات اخیر یک گروه تلگرامی است را به صورت بسیار مرتب، بولت‌پوینت و خلاصه به زبان فارسی توضیح بده:\n\n{combined_text}"

    try:
        response = co.chat(
            message=prompt,
            model="command-r-08-2024",
            preamble="تو یک دستیار هوشمند هستی که وظیفه داری گفتگوهای گروه را به صورت خلاصه و مفید جمع‌بندی کنی."
        )
        await update.message.reply_text(f"📊 **خلاصه مکالمات اخیر گروه:**\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"خطا در ایجاد خلاصه: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user_text = update.message.text
    bot_username = context.bot.username

    # نادیده گرفتن پیام‌های غیرمتنی
    if not user_text:
        return

    # ثبت آمار گروه‌ها و کاربران موقع ارسال پیام
    if chat_type in ["group", "supergroup"]:
        active_groups.add(chat_id)
    else:
        active_users.add(chat_id)

    # ذخیره پیام‌های گروه برای خلاصه‌سازی
    if chat_type in ["group", "supergroup"]:
        user_name = update.effective_user.first_name or "کاربر"
        if chat_id not in group_recent_messages:
            group_recent_messages[chat_id] = []
        
        group_recent_messages[chat_id].append(f"{user_name}: {user_text}")
        if len(group_recent_messages[chat_id]) > MAX_GROUP_MESSAGES:
            group_recent_messages[chat_id].pop(0)

        is_replied_to_bot = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = f"@{bot_username}" in user_text

        if not (is_replied_to_bot or is_mentioned):
            return

        user_text = user_text.replace(f"@{bot_username}", "").strip()

    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    try:
        response = co.chat(
            message=user_text,
            model="command-r-08-2024",
            preamble=SYSTEM_PROMPT,
            chat_history=chat_histories[chat_id]
        )
        ai_reply = response.text

        chat_histories[chat_id].append({"role": "USER", "message": user_text})
        chat_histories[chat_id].append({"role": "CHATBOT", "message": ai_reply})

        if len(chat_histories[chat_id]) > MAX_HISTORY_LENGTH * 2:
            chat_histories[chat_id] = chat_histories[chat_id][-MAX_HISTORY_LENGTH * 2:]

        await update.message.reply_text(ai_reply)

    except Exception as e:
        print(f"Error: {e}")
        await update.message.reply_text(f"خطا در ارتباط با اندروید : {e}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("stats", stats_command)) # ثبت دستور آمارگیری
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("summary", summarize_group))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()
