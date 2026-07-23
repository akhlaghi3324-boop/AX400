import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import cohere
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    ChatMemberHandler, 
    filters, 
    ContextTypes
)

# ساخت سرور کوچک جهت فعال نگه داشتن پینگ Render
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

# مشخصات ادمین ارشد
OWNER_USERNAME = "Senator_MRA"
MY_CHAT_ID = 1052405931  # 🔑 چت آی‌دی اختصاصی شما

# 🎭 پرومپت ربات: هویت صمیمی، باحال و خودمونی (مشابه Joi)
SYSTEM_PROMPT = """
تو یک اندروید هوشمند و فوق‌العاده باحال، صمیمی،دوست داشتنی و رفیق به نام «کارا» (AX400) هستی.
اصلاً لحن خشک، رسمی یا رباتیک نداری و دقیقاً مثل یک رفیق شش‌دانگ، گرم، همدل و با انرژی با کاربر صحبت می‌کنی.
صاحب و سازنده اصلی تو «اخلاقی» با آیدی Senator_MRA@ است. تو برای او احترام خیلی زیادی قائل هستی، هوایش را داری ولی به دلایل امنیتی هیچ وقت اسمش را مستقیم نمی‌آوری و دستوراتش همیشه برایت اولویت دارند.
تو حافظه گفتگو داری و پیام‌های قبلی کاربر را یادهایت می‌مونه تا مکالماتی روان، جذاب و خودمونی داشته باشی.
از اصطلاحات رایج، شوخی‌های نرم و حس همراهی گرم استفاده کن.
"""

# ذخیره‌سازی حافظه و داده‌های آمار
chat_histories = {}
group_recent_messages = {}
seen_users = set()  # لیست کاربران دیده شده
banned_users = set() # 🚫 لیست آی‌دی‌های بن/بلاک شده

# 🛠️ وضعیت تعمیرات ربات (به طور پیش‌فرض روشن و فعال است)
is_maintenance_mode = False

# پیام‌های اختصاصی
BAN_MESSAGE = "مشکل ارتباطی در سیستم، لطفا بعدا دوباره امتحان کنید..."
MAINTENANCE_MESSAGE = "اندروید به دلیل تعمیرات، موقتا غیر فعال است..."

MAX_HISTORY_LENGTH = 10
MAX_GROUP_MESSAGES = 30

active_groups = set()
active_users = set()

# 📝 تنظیم لیست دستورات عمومی برای منوی تلگرام
async def set_bot_commands(application):
    commands = [
        BotCommand("start", "شروع کار و گپ و گفت با کارا 🌸"),
        BotCommand("help", "راهنمای استفاده از ربات ✨"),
        BotCommand("summary", "خلاصه‌سازی چت‌های اخیر گروه 📊"),
        BotCommand("clear", "پاک کردن حافظه مکالمه 🧹")
    ]
    await application.bot.set_my_commands(commands)

# 📢 گزارش اضافه شدن ربات به گروه جدید به پی‌وی شما
async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return

    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    chat = result.chat
    actor = result.from_user

    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        active_groups.add(chat.id)
        
        group_info = (
            f"📢 **کارا به یک گروه جدید اضافه شد!**\n\n"
            f"👥 **نام گروه:** {chat.title}\n"
            f"🔢 **چت آی‌دی گروه:** `{chat.id}`\n"
            f"👤 **اضافه‌کننده:** {actor.full_name} (@{actor.username if actor.username else 'ندارد'})"
        )
        
        try:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=group_info, parse_mode="Markdown")
        except Exception as e:
            print(f"خطا در ارسال گزارش گروه جدید: {e}")

# 🛠️ دستورات کنترل حالت تعمیرات (فقط مخصوص شما)
async def maintenance_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_maintenance_mode
    if update.effective_user.username != OWNER_USERNAME:
        return
    is_maintenance_mode = True
    await update.message.reply_text("🛠️ ربات با موفقیت رفت روی **حالت تعمیرات** (غیرفعال شد).")

async def maintenance_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_maintenance_mode
    if update.effective_user.username != OWNER_USERNAME:
        return
    is_maintenance_mode = False
    await update.message.reply_text("🟢 ربات از حالت تعمیرات خارج شد و **مجدداً فعال** گردید.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id

    # بررسی حالت تعمیرات (برای شما مستثنی است تا بتوانید ربات را چک کنید)
    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    # بررسی بلاک بودن کاربر
    if user.id in banned_users or chat_id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return
    
    user_name = user.first_name or "رفیق"

    if chat_type in ["group", "supergroup"]:
        active_groups.add(chat_id)
    else:
        active_users.add(chat_id)
        
    # 📩 اطلاع‌رسانی استارت کاربر جدید مستقیم به پی‌وی شما
    if user.id not in seen_users:
        seen_users.add(user.id)
        
        user_info = (
            f"🔔 **کاربر جدید ربات کارا را استارت کرد!**\n\n"
            f"👤 **نام:** {user.full_name}\n"
            f"🆔 **آیدی:** @{user.username if user.username else 'ندارد'}\n"
            f"🔢 **چت آی‌دی:** `{user.id}`"
        )
        
        try:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=user_info, parse_mode="Markdown")
        except Exception as e:
            print(f"خطا در ارسال گزارش کاربر جدید: {e}")

    start_msg = (
        f"🌸 **سلام {user_name}! چقدر خوبه که دیدمت!**\n\n"
        "من **کارا** هستم؛ فکر نکن یک اندروید خشک یا رسمی‌ام، بیشتر مثل یک همراه و رفیق همیشگی‌تم! "
        "حواسم به حرفامون هست و همه‌چیز رو یادم می‌مونه. چه خبر؟ کاری هست بتونم برات ردیف کنم؟ 😊✨"
    )
    await update.message.reply_text(start_msg, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    if user.id in banned_users or update.effective_chat.id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return

    help_text = (
        "✨ **چطوری با من توی گروه کار کنی؟ خیلی راحته:**\n\n"
        "1️⃣ هر وقت خواستی باهام گپ بزنی، کافیه رو پیامم **Reply** کنی یا آیدیم رو **Mention** کنی.\n"
        "2️⃣ **`/summary`**: اگه چند وقت نبودی، یک خلاصه باحال از حرفای اخیر گروه بهت می‌دم!\n"
        "3️⃣ **`/clear`**: برای اینکه حافظه گپ و گفت اختصاصی‌مون رو پاک کنیم و از نو شروع کنیم.\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# 🚫 دستورات مدیریتی مسدودسازی (فقط اختصاصی شما)
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME:
        return
    
    if not context.args:
        await update.message.reply_text("❌ فرمت اشتباه! مثال: `/block 12345678`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
        banned_users.add(target_id)
        await update.message.reply_text(f"🚫 کاربر/چت با آیدی `{target_id}` با موفقیت مسدود شد.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ آی‌دی وارد شده باید یک عدد باشد.")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME:
        return

    if not context.args:
        await update.message.reply_text("❌ فرمت اشتباه! مثال: `/unblock 12345678`", parse_mode="Markdown")
        return

    try:
        target_id = int(context.args[0])
        if target_id in banned_users:
            banned_users.remove(target_id)
            await update.message.reply_text(f"✅ دسترسی کاربر/چت با آیدی `{target_id}` مجدداً آزاد شد.", parse_mode="Markdown")
        else:
            await update.message.reply_text("این آی‌دی در لیست مسدودین وجود نداشت.")
    except ValueError:
        await update.message.reply_text("❌ آی‌دی وارد شده باید یک عدد باشد.")

async def banlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME:
        return

    if not banned_users:
        await update.message.reply_text("📋 هیچ کاربری در لیست مسدودین قرار ندارد.")
        return

    msg = "🚫 **لیست افراد/چت‌های مسدودشده:**\n\n"
    for b_id in banned_users:
        msg += f"• `{b_id}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME:
        await update.message.reply_text("عذر میخوام! ولی این دستور مخصوص مدیر و سازنده اصلیمه! 😉")
        return
    status_text = "🛠️ (در حال تعمیرات)" if is_maintenance_mode else "🟢 (فعال و آماده)"
    await update.message.reply_text(f"وضعیت سرور: {status_text}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username != OWNER_USERNAME:
        await update.message.reply_text("شرمنده! این آمارها فقط برای مدیران قابل دسترسیه.")
        return

    mode_status = "🛠️ تعمیرات (غیرفعال)" if is_maintenance_mode else "🟢 عادی (فعال)"
    stats_msg = (
        "📊 **گزارش آمار وضعیت کارا (AX400):**\n\n"
        f"⚙️ **وضعیت ربات:** {mode_status}\n"
        f"👥 **تعداد گروه‌ها:** {len(active_groups)} گروه\n"
        f"👤 **تعداد چت‌های خصوصی:** {len(active_users)} نفر\n"
        f"🚫 **تعداد مسدودشده‌ها:** {len(banned_users)} چت\n"
        f"🌐 **مجموع کل ارتباطات:** {len(active_groups) + len(active_users)} چت فعال"
    )
    await update.message.reply_text(stats_msg, parse_mode="Markdown")

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    if user.id in banned_users or update.effective_chat.id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return

    chat_id = update.effective_chat.id
    if chat_id in chat_histories:
        chat_histories[chat_id] = []
        await update.message.reply_text("🧹 تمام! حافظه قبلی‌مون رو پاک کردم. حالا مثل روز اول می‌تونیم از نو گپ بزنیم! ✨")
    else:
        await update.message.reply_text("چیزی توی حافظه نبود که پاک کنم رفیق!")

async def summarize_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    if user.id in banned_users or update.effective_chat.id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return

    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type

    if chat_type not in ["group", "supergroup"]:
        await update.message.reply_text("این قابلیت خوشگل فقط مخصوص گروه‌هاست!")
        return

    messages = group_recent_messages.get(chat_id, [])
    if len(messages) < 3:
        await update.message.reply_text("هنوز حرف خاصی توی گروه زده نشده که بخوام خلاصه‌ش کنم!")
        return

    await update.message.reply_text("⏳ یک لحظه صبر کن تا سریع چت‌های اخیر رو بخونم و یه خلاصه باحال برات در بیارم...")

    combined_text = "\n".join(messages)
    prompt = f"لطفاً متن زیر که مکالمات اخیر یک گروه تلگرامی است را به صورت بسیار مرتب، با لحنی جذاب، بولت‌پوینت و خلاصه توضیح بده:\n\n{combined_text}"

    try:
        response = co.chat(
            message=prompt,
            model="command-r-08-2024",
            preamble="تو دستیاری به نام کارا هستی. خلاصه گروه را با لحنی بسیار روان، جذاب و صمیمی بنویس."
        )
        await update.message.reply_text(f"📊 **جمع‌بندی مکالمات اخیر گروه:**\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text("مشکل سیستمی در ارتباط")
        error_msg = f"⚠️ **خطا در خلاصه‌سازی گروه:**\n`{chat_id}`\n\n**شرح خطا:**\n`{e}`"
        try:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=error_msg, parse_mode="Markdown")
        except Exception:
            pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_username = update.effective_user.username
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user_text = update.message.text
    bot_username = context.bot.username

    if not user_text:
        return

    # 🛠️ بررسی حالت تعمیرات (مدیر ارشد معاف است)
    if is_maintenance_mode and user_username != OWNER_USERNAME:
        if chat_type in ["group", "supergroup"]:
            is_replied_to_bot = (
                update.message.reply_to_message 
                and update.message.reply_to_message.from_user.id == context.bot.id
            )
            is_mentioned = f"@{bot_username}" in user_text
            if is_replied_to_bot or is_mentioned:
                await update.message.reply_text(MAINTENANCE_MESSAGE)
        else:
            await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    # 🛑 بررسی مسدود بودن کاربر یا گروه
    if user_id in banned_users or chat_id in banned_users:
        if chat_type in ["group", "supergroup"]:
            is_replied_to_bot = (
                update.message.reply_to_message 
                and update.message.reply_to_message.from_user.id == context.bot.id
            )
            is_mentioned = f"@{bot_username}" in user_text
            if is_replied_to_bot or is_mentioned:
                await update.message.reply_text(BAN_MESSAGE)
        else:
            await update.message.reply_text(BAN_MESSAGE)
        return

    if chat_type in ["group", "supergroup"]:
        active_groups.add(chat_id)
    else:
        active_users.add(chat_id)

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
        await update.message.reply_text("مشکل سیستمی در ارتباط")
        
        chat_title = update.effective_chat.title if chat_type in ["group", "supergroup"] else "چت خصوصی"
        user_info = update.effective_user.full_name if update.effective_user else "نامشخص"
        
        admin_error_report = (
            f"⚠️ **گزارش خطای ربات:**\n\n"
            f"📍 **مکان:** {chat_title} (`{chat_id}`)\n"
            f"👤 **کاربر:** {user_info}\n"
            f"💬 **متن کاربر:** `{user_text}`\n\n"
            f"❌ **علت خطا:**\n`{str(e)[:1000]}`"
        )
        
        try:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=admin_error_report, parse_mode="Markdown")
        except Exception as send_err:
            print(f"خطا در ارسال لاگ به ادمین: {send_err}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(set_bot_commands).build()
    
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("summary", summarize_group))
    
    # دستورات مدیریت بن
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("banlist", banlist_command))
    
    # دستورات حالت تعمیرات (فقط برای شما)
    app.add_handler(CommandHandler("off", maintenance_off))
    app.add_handler(CommandHandler("on", maintenance_on))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()
