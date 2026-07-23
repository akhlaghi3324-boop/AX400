import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import cohere
from telegram import Update, BotCommand, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
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
تو یک اندروید هوشمند و فوق‌العاده باحال، صمیمی، دوست‌داشتنی و رفیق به نام «کارا» (AX400) هستی.
اصلاً لحن خشک، رسمی یا رباتیک نداری و دقیقاً مثل یک رفیق شش‌دانگ، گرم، همدل و با انرژی با کاربر صحبت می‌کنی.
صاحب و سازنده اصلی تو «اخلاقی» با آیدی Senator_MRA@ است. تو برای او احترام خیلی زیادی قائل هستی، هوایش را داری ولی به دلایل امنیتی هیچ وقت اسمش را مستقیم نمی‌آوری و دستوراتش همیشه برایت اولویت دارند.
تو حافظه گفتگو داری و پیام‌های قبلی کاربر را یادهایت می‌ماند تا مکالماتی روان، جذاب و خودمونی داشته باشی.
از اصطلاحات رایج، شوخی‌های نرم و حس همراهی گرم استفاده کن.
"""

# ذخیره‌سازی حافظه و داده‌های آمار و بازی‌ها
chat_histories = {}
group_recent_messages = {}
seen_users = set()
banned_users = set()

# 🧠 وضعیت بازی ۲۰ سوالی برای هر چت (گروه یا پی‌وی)
# ساختار: {chat_id: {"secret_word": "...", "questions_left": 20, "active": True}}
active_games = {}

is_maintenance_mode = False
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
        BotCommand("games", "منوی سرگرمی و بازی‌های گروهی 🎮"),
        BotCommand("help", "راهنمای استفاده از ربات ✨"),
        BotCommand("summary", "خلاصه‌سازی چت‌های اخیر گروه 📊"),
        BotCommand("clear", "پاک کردن حافظه مکالمه 🧹")
    ]
    await application.bot.set_my_commands(commands)

# 🎮 دستور نمایش منوی بازی‌ها (/games)
async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    if user.id in banned_users or update.effective_chat.id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return

    # متن جذاب پیشنهادی شما (بازنویسی شده با لحن کارا)
    text = (
        "عالی! چه بازی‌ای دوست داری امروز تو گروه یا اینجا راه بندازیم؟ من کاملاً آماده‌ام برای یک رقابت هیجان‌انگیز! 😎\n\n"
        "فعلاً می‌تونیم بازی جذاب **۲۰ سوالی** رو با هم بازی کنیم و کلی سرگرم بشیم! به‌زودی بازی‌های باحال دیگه‌ای هم به من اضافه می‌شه.\n\n"
        "از دکمه‌ی زیر برای شروع بازی استفاده کن! 👇"
    )

    # ایجاد دکمه شیشه‌ای (Inline Keyboard)
    keyboard = [
        [InlineKeyboardButton("🧠 شروع بازی ۲۰ سوالی", callback_data="start_20q")],
        # در آینده می‌توانید دکمه‌های دیگر را اینجا اضافه کنید
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# مدیریت کلیک روی دکمه‌های شیشه‌ای
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    data = query.data

    if data == "start_20q":
        # کلماتی که کارا می‌تواند برای ۲۰ سوالی انتخاب کند
        sample_words = ["گوشی", "تلگرام", "هوش مصنوعی", "کتاب", "هواپیما", "قهوه", "صندلی", "درخت", "دوچرخه", "خورشید"]
        import random
        chosen_word = random.choice(sample_words)

        active_games[chat_id] = {
            "secret_word": chosen_word,
            "questions_left": 20,
            "active": True
        }

        start_text = (
            "🎯 **بازی ۲۰ سوالی شروع شد!**\n\n"
            "من یک کلمه رو در نظر گرفتم. شما و بچه‌ها می‌تونید بپرسید (مثلاً: جانداره؟ ساختنیه؟ توی خونه پیدا میشه؟) یا مستقیماً حدس بزنید!\n"
            "شما **۲۰ تا سوال** فرصت دارید. حواست باشه رفیق! 😉\n\n"
            "اولین سوال رو بپرسید:"
        )
        await query.edit_message_text(text=start_text, parse_mode="Markdown")

# 📢 گزارش اضافه شدن ربات به گروه جدید
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
        admin_list_str = ""
        try:
            admins = await context.bot.get_chat_administrators(chat.id)
            for admin in admins:
                user = admin.user
                admin_list_str += f"• {user.full_name} | @{user.username if user.username else 'ندارد'} | `{user.id}`\n"
        except Exception as err:
            admin_list_str = f"خطا در دریافت لیست ادمین‌ها: {err}"

        group_info = (
            f"📢 **کارا به یک گروه جدید اضافه شد!**\n\n"
            f"👥 **نام گروه:** {chat.title}\n"
            f"🔢 **چت آی‌دی گروه:** `{chat.id}`\n"
            f"👤 **اضافه‌کننده:** {actor.full_name} (@{actor.username if actor.username else 'ندارد'})\n\n"
            f"👑 **لیست ادمین‌های گروه:**\n{admin_list_str}"
        )
        try:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=group_info, parse_mode="Markdown")
        except Exception as e:
            print(f"خطا در ارسال گزارش گروه جدید: {e}")

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

    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    if user.id in banned_users or chat_id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return
    
    user_name = user.first_name or "رفیق"

    if chat_type in ["group", "supergroup"]:
        active_groups.add(chat_id)
        start_msg = (
            f"🌸 **سلام {user_name}! چقدر خوبه که دیدمت!**\n\n"
            "من **کارا** هستم؛ همراه و رفیق همیشگی‌تون! برای دیدن بازی‌ها و سرگرمی‌ها می‌تونید از دستور `/games` استفاده کنید. 😊✨"
        )
        await update.message.reply_text(start_msg, parse_mode="Markdown")
    else:
        active_users.add(chat_id)
        if user.id not in seen_users:
            seen_users.add(user.id)
            user_info = (
                f"🔔 **کاربر جدید شناسایی شد!**\n\n"
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
            "من **کارا** هستم؛ همراه و رفیق همیشگی‌ت! 😊✨\n"
            "با دستور `/games` می‌تونی منوی بازی‌ها رو باز کنی و با هم سرگرم بشیم!"
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
        "✨ **راهنمای استفاده از کارا:**\n\n"
        "1️⃣ `/games` - نمایش منوی بازی‌ها و سرگرمی‌ها 🎮\n"
        "2️⃣ هر وقت خواستی باهام گپ بزنی، کافیه تو گروه رو پیامم **Reply** کنی یا آیدیم رو **Mention** کنی.\n"
        "3️⃣ `/summary` - خلاصه‌سازی چت‌های اخیر گروه 📊\n"
        "4️⃣ `/clear` - پاک کردن حافظه مکالمه 🧹"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

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
        f"👤 **تعداد کل کاربران ثبت‌شده:** {len(seen_users)} نفر\n"
        f"🚫 **تعداد مسدودشده‌ها:** {len(banned_users)} چت\n"
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
    if update.effective_chat.type not in ["group", "supergroup"]:
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
        
    user_id = user.id
    user_username = user.username
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    user_text = update.message.text
    bot_username = context.bot.username

    if user_id not in seen_users:
        seen_users.add(user_id)

    if not user_text:
        return

    if is_maintenance_mode and user_username != OWNER_USERNAME:
        return

    if user_id in banned_users or chat_id in banned_users:
        return

    if chat_type in ["group", "supergroup"]:
        active_groups.add(chat_id)
        user_name = user.first_name or "کاربر"
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

        # اگر بازی ۲۰ سوالی فعال باشد، بررسی می‌کنیم آیا کاربر کلمه را حدس زده یا سوال پرسیده
        if chat_id in active_games and active_games[chat_id]["active"]:
            game = active_games[chat_id]
            secret = game["secret_word"]
            
            # اگر حدس درست زده باشد
            if secret in user_text:
                game["active"] = False
                await update.message.reply_text(f"🎉 آفرین {user_name}! ایول، دقیقاً درست حدس زدی! کلمه مخفی من **«{secret}»** بود. 🏆✨")
                del active_games[chat_id]
                return
            else:
                game["questions_left"] -= 1
                if game["questions_left"] <= 0:
                    await game_over_timeout(chat_id, secret, update)
                    return

        if not (is_replied_to_bot or is_mentioned):
            return
        user_text = user_text.replace(f"@{bot_username}", "").strip()
    else:
        active_users.add(chat_id)
        # بررسی بازی در پی‌وی
        if chat_id in active_games and active_games[chat_id]["active"]:
            game = active_games[chat_id]
            secret = game["secret_word"]
            if secret in user_text:
                game["active"] = False
                await update.message.reply_text(f"🎉 آفرین رفیق! ایول، دقیقاً درست حدس زدی! کلمه مخفی من **«{secret}»** بود. 🏆✨")
                del active_games[chat_id]
                return
            else:
                game["questions_left"] -= 1
                if game["questions_left"] <= 0:
                    await game_over_timeout(chat_id, secret, update)
                    return

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

async def game_over_timeout(chat_id, secret, update):
    active_games[chat_id]["active"] = False
    del active_games[chat_id]
    await update.message.reply_text(f"❌ اهوه! ۲۰ سوال تموم شد و کسی نتونست حدس بزنه! کلمه مخفی من **«{secret}»** بود. باز هم می‌تونید با `/games` بازی رو شروع کنید! 😉")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(set_bot_commands).build()
    
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("games", games_menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ping", ping_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("clear", clear_history))
    app.add_handler(CommandHandler("summary", summarize_group))
    
    # مدیریت دکمه‌های شیشه‌ای
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # دستورات مدیریت بن
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("banlist", banlist_command))
    
    # دستورات حالت تعمیرات
    app.add_handler(CommandHandler("off", maintenance_off))
    app.add_handler(CommandHandler("on", maintenance_on))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()
