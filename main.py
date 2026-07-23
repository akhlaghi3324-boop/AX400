import os
import threading
import random
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import cohere
from telegram import Update, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
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

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
COHERE_API_KEY = os.environ.get("COHERE_API_KEY")

co = cohere.Client(api_key=COHERE_API_KEY)

OWNER_USERNAME = "Senator_MRA"
MY_CHAT_ID = 1052405931

SYSTEM_PROMPT = """
تو یک اندروید هوشمند و فوق‌العاده باحال، صمیمی، دوست‌داشتنی و رفیق به نام «کارا» (AX400) هستی.
اصلاً لحن خشک، رسمی یا رباتیک نداری و دقیقاً مثل یک رفیق شش‌دانگ، گرم، همدل و با انرژی با کاربر صحبت می‌کنی.
صاحب و سازنده اصلی تو «اخلاقی» با آیدی Senator_MRA@ است. تو برای او احترام خیلی زیادی قائل هستی.
"""

chat_histories = {}
group_recent_messages = {}
seen_users = set()
banned_users = set()

# 🧠 داده‌های بازی‌ها
active_games_20q = {}
spy_games = {}
story_games = {}
whoami_games = {}
trivia_games = {}
name_games = {}

TIMER_SECONDS = 10  # زمان‌سنج ۱۰ ثانیه‌ای چالش اسم بازی

FAMOUS_CHARACTERS = [
    "شرلوک هولمز", "بتمن", "مسی", "انشتین", "هری پاتر", 
    "ناپلئون", "مرد عنکبوتی", "کاپیتان اسپارو", "پیکاسو", "چارلی چاپلین",
    "باب اسفنجی", "مرد آهنی", "کریستیانو رونالدو", "شکسپیر"
]

STORY_STARTERS = [
    "در یک شب بارانی، سینا کلید کهنه‌ای پیدا کرد که...",
    "سفینه فضایی درست وسط حیاط خانه ما فرود آمد و...",
    "وقتی در یخچال رو باز کردم، یک اژدهای کوچک دیدم که...",
    "استاد وارد کلاس شد ولی به جای تدریس، یک نقشه گنج رو کرد و گفت...",
    "یک روز صبح بیدار شدم و دیدم هیچ‌کس توی شهر نیست جز..."
]

SPY_LOCATIONS = [
    "بیمارستان", "شهربازی", "رستوران", "فرودگاه", "مدرسه", 
    "سینما", "باشگاه ورزشی", "ایستگاه فضایی", "کشتی کروز", "موزه"
]

is_maintenance_mode = False
BAN_MESSAGE = "مشکل ارتباطی در سیستم، لطفا بعدا دوباره امتحان کنید..."
MAINTENANCE_MESSAGE = "اندروید به دلیل تعمیرات، موقتا غیر فعال است..."

MAX_HISTORY_LENGTH = 10
MAX_GROUP_MESSAGES = 30

active_groups = set()
active_users = set()

# --- تابع ساخت سوال اطلاعات عمومی توسط هوش مصنوعی ---
def generate_trivia_question():
    prompt = """
    یک سوال اطلاعات عمومی جالب و متنوع به زبان فارسی همراه با ۴ گزینه طراحی کن.
    پاسخ را دقیقاً و فقط در قالب JSON زیر خروجی بده و هیچ متن یا توضیح اضافی قبل یا بعد از آن ننویس:

    {
        "question": "متن سوال؟",
        "options": ["گزینه اول", "گزینه دوم", "گزینه سوم", "گزینه چهارم"],
        "correct_index": 0
    }

    نکته: correct_index اندیس گزینه درست است (از ۰ تا ۳).
    """
    try:
        response = co.chat(message=prompt, model="command-r-08-2024")
        clean_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        return data
    except Exception:
        return {
            "question": "پایتخت کشور ایتالیا کدام شهر است؟",
            "options": ["میلان", "رم", "وینیز", "فلورانس"],
            "correct_index": 1
        }

# --- تابع مدیریت اتمام زمان (Timeout) بازی اسم بازی ---
async def name_game_timeout(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id

    if chat_id in name_games and name_games[chat_id]["active"]:
        game = name_games[chat_id]

        first_letters = [
            "آ", "ب", "پ", "ت", "ج", "چ", "ح", "خ", "د", "ر", 
            "ز", "س", "ش", "ص", "ط", "ع", "ف", "ق", "ک", "گ", 
            "ل", "م", "ن", "و", "ه", "ی"
        ]
        new_char = random.choice(first_letters)
        game["last_letter"] = new_char

        keyboard = [
            [InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")]
        ]
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏰ **۱۰ ثانیه تمام شد! کسی کلمه‌ای نگفت.** 😅\n\n"
                f"🔄 حرف عوض شد! کلمه بعدی باید با حرف **« {new_char} »** شروع بشه!\n"
                f"⏱️ **فرصت باقی‌مانده:** {TIMER_SECONDS} ثانیه"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

        context.job_queue.run_once(
            name_game_timeout,
            TIMER_SECONDS,
            chat_id=chat_id,
            name=f"timer_{chat_id}"
        )

async def set_bot_commands(application):
    commands = [
        BotCommand("start", "شروع کار و گپ و گفت با کارا 🌸"),
        BotCommand("games", "منوی سرگرمی و بازی‌های گروهی 🎮"),
        BotCommand("help", "راهنمای استفاده از ربات ✨"),
        BotCommand("summary", "خلاصه‌سازی چت‌های اخیر گروه 📊"),
        BotCommand("clear", "پاک کردن حافظه مکالمه 🧹")
    ]
    await application.bot.set_my_commands(commands)

# 🎮 منوی اصلی بازی‌ها
async def games_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_maintenance_mode and user.username != OWNER_USERNAME:
        await update.message.reply_text(MAINTENANCE_MESSAGE)
        return

    if user.id in banned_users or update.effective_chat.id in banned_users:
        await update.message.reply_text(BAN_MESSAGE)
        return

    text = (
        "عالی! چه بازی‌ای دوست داری امروز راه بندازیم؟ من کاملاً آماده‌ام برای یک رقابت هیجان‌انگیز! 😎\n\n"
        "🎮 **بازی‌های فعال:**\n"
        "1️⃣ **۲۰ سوالی:** حدس کلمه مخفی من با سؤالات بله/خیر.\n"
        "2️⃣ **اطلاعات عمومی:** چالش چهارگزینه‌ای هوشمند! 🧠\n"
        "3️⃣ **جاسوس (Spy):** پیدا کردن جاسوس در بین اعضا!\n"
        "4️⃣ **داستان‌نویسی گروهی:** ساخت داستان گروهی!\n"
        "5️⃣ **من کی‌ام؟:** حدس شخصیت مخفی شما!\n"
        "6️⃣ **اسم بازی:** چالش سرعت عمل با تایمر ۱۰ ثانیه‌ای! ⏱️\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن رفیق: 👇"
    )

    keyboard = [
        [InlineKeyboardButton("🧠 شروع بازی ۲۰ سوالی", callback_data="start_20q")],
        [InlineKeyboardButton("💡 چالش اطلاعات عمومی", callback_data="start_trivia")],
        [InlineKeyboardButton("🕵️‍♂️ شروع بازی جاسوس", callback_data="init_spy")],
        [InlineKeyboardButton("📖 شروع داستان گروهی", callback_data="start_story")],
        [InlineKeyboardButton("🎭 بازی من کی‌ام؟", callback_data="init_whoami")],
        [InlineKeyboardButton("🔤 بازی اسم بازی (تایمر ۱۰ ثانیه)", callback_data="start_name_game")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

# 🔘 مدیریت کلیک روی دکمه‌های شیشه‌ای
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    user = query.from_user
    data = query.data

    # --- دکمه لغو و پایان عمومی بازی‌ها ---
    if data == "cancel_game":
        active_games_20q.pop(chat_id, None)
        spy_games.pop(chat_id, None)
        story_games.pop(chat_id, None)
        whoami_games.pop(chat_id, None)
        trivia_games.pop(chat_id, None)
        
        if chat_id in name_games:
            current_jobs = context.job_queue.get_jobs_by_name(f"timer_{chat_id}")
            for job in current_jobs:
                job.schedule_removal()
            name_games.pop(chat_id, None)

        await query.edit_message_text("🛑 **بازی با موفقیت متوقف شد.** هر زمان مایل بودید می‌تونید با `/games` دوباره شروع کنید! ✨", parse_mode="Markdown")
        return

    # --- ۱. بازی ۲۰ سوالی ---
    if data == "start_20q":
        await query.edit_message_text(text="🎲 در حال انتخاب یک کلمه مخفی و جالب توسط هوش مصنوعی... لطفاً چند لحظه صبر کن! ⏳")

        try:
            word_prompt = """
            یک کلمه ملموس، عامیانه و قابل حدس برای بازی ۲۰ سوالی به زبان فارسی انتخاب کن.
            کلمه می‌تواند یک جسم، حیوان، شغل، خوراکی یا شیء باشد.
            فقط و فقط خود کلمه را بنویس و هیچ توضیح یا علامت اضافی نده.
            """
            res_word = co.chat(message=word_prompt, model="command-r-08-2024")
            chosen_word = res_word.text.strip().replace("«", "").replace("»", "").replace('"', '')
        except Exception:
            fallback_words = ["یخچال", "تلسکوپ", "دلفین", "کشتی", "اکسیژن", "کوهستان", "آتشفشان", "موبایل"]
            chosen_word = random.choice(fallback_words)

        active_games_20q[chat_id] = {
            "secret_word": chosen_word,
            "questions_left": 20,
            "active": True
        }

        start_text = (
            "🎯 **بازی ۲۰ سوالی شروع شد!**\n\n"
            "من یک کلمه جدید تو ذهنم انتخاب کردم! 🧠✨\n"
            "۲۰ فرصت دارید تا با سؤالات بله/خیر کلمه رو پیدا کنید.\n\n"
            "اولین سوال رو بپرسید:"
        )
        keyboard = [[InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")]]
        await query.edit_message_text(text=start_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # --- ۲. بازی اطلاعات عمومی ---
    elif data == "start_trivia":
        await query.edit_message_text("⏳ در حال طراحی یک سوال اطلاعات عمومی جدید توسط هوش مصنوعی... لطفاً چند لحظه صبر کنید!")
        q_data = generate_trivia_question()

        trivia_games[chat_id] = {
            "correct_index": q_data["correct_index"],
            "question": q_data["question"],
            "options": q_data["options"],
            "active": True
        }

        keyboard = []
        for idx, option in enumerate(q_data["options"]):
            keyboard.append([InlineKeyboardButton(f"{idx + 1}️⃣ {option}", callback_data=f"answer_trivia_{idx}")])
        
        keyboard.append([InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")])

        text = f"💡 **سوال اطلاعات عمومی:**\n\n{q_data['question']}"
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("answer_trivia_"):
        if chat_id not in trivia_games or not trivia_games[chat_id]["active"]:
            await query.answer("این بازی تمام شده است!", show_alert=True)
            return

        user_choice = int(data.split("_")[-1])
        correct_choice = trivia_games[chat_id]["correct_index"]
        correct_option_text = trivia_games[chat_id]["options"][correct_choice]

        if user_choice == correct_choice:
            res_text = f"🎉 **آفرین {user.first_name}!** پاسخ شما کاملاً درست بود! 🏆\nگزینه صحیح: **{correct_option_text}**"
        else:
            res_text = f"❌ **اشتباه بود {user.first_name} عزیز!**\nپاسخ صحیح گزینه **«{correct_option_text}»** بود. 😉"

        del trivia_games[chat_id]

        keyboard = [
            [InlineKeyboardButton("🔄 سوال بعدی", callback_data="start_trivia")],
            [InlineKeyboardButton("🏁 خروج از بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=res_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # --- ۳. بازی جاسوس ---
    elif data == "init_spy":
        if query.message.chat.type not in ["group", "supergroup"]:
            await query.edit_message_text("⚠️ **بازی جاسوس فقط مخصوص گروه‌هاست!** لطفا ربات رو به گروه اضافه کنید. 🌸")
            return

        spy_games[chat_id] = {
            "players": {user.id: user.first_name},
            "spy_id": None,
            "location": "",
            "status": "joining"
        }

        spy_text = (
            "🕵️‍♂️ **اتاق بازی جاسوس ساخته شد!**\n\n"
            f"👤 **اعضای آماده:**\n• {user.first_name}\n\n"
            "برای شروع بازی حداقل به **۳ نفر** نیاز داریم."
        )

        keyboard = [
            [InlineKeyboardButton("📥 ورود به بازی", callback_data="join_spy")],
            [InlineKeyboardButton("🚪 انصراف و خروج", callback_data="leave_spy")],
            [InlineKeyboardButton("🚀 شروع بازی!", callback_data="start_spy_game")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=spy_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "join_spy":
        if chat_id not in spy_games or spy_games[chat_id]["status"] != "joining":
            return

        players = spy_games[chat_id]["players"]
        if user.id not in players:
            players[user.id] = user.first_name

        players_list = "\n".join([f"• {name}" for name in players.values()])
        spy_text = (
            "🕵️‍♂️ **اتاق بازی جاسوس**\n\n"
            f"👤 **اعضای حاضر ({len(players)} نفر):**\n{players_list}\n\n"
            "هر وقت همه‌ جمع شدید، دکمه «🚀 شروع بازی!» رو بزنید."
        )

        keyboard = [
            [InlineKeyboardButton("📥 ورود به بازی", callback_data="join_spy")],
            [InlineKeyboardButton("🚪 انصراف و خروج", callback_data="leave_spy")],
            [InlineKeyboardButton("🚀 شروع بازی!", callback_data="start_spy_game")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=spy_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "leave_spy":
        if chat_id in spy_games and spy_games[chat_id]["status"] == "joining":
            players = spy_games[chat_id]["players"]
            if user.id in players:
                del players[user.id]
                await query.answer("شما از اتاق بازی خارج شدید!", show_alert=True)
                
                players_list = "\n".join([f"• {name}" for name in players.values()]) if players else "هیچ‌کس"
                spy_text = (
                    "🕵️‍♂️ **اتاق بازی جاسوس**\n\n"
                    f"👤 **اعضای حاضر ({len(players)} نفر):**\n{players_list}\n\n"
                    "هر وقت همه‌ جمع شدید، دکمه «🚀 شروع بازی!» رو بزنید."
                )
                keyboard = [
                    [InlineKeyboardButton("📥 ورود به بازی", callback_data="join_spy")],
                    [InlineKeyboardButton("🚪 انصراف و خروج", callback_data="leave_spy")],
                    [InlineKeyboardButton("🚀 شروع بازی!", callback_data="start_spy_game")],
                    [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
                ]
                await query.edit_message_text(text=spy_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await query.answer("شما هنوز در لیست بازیکنان نیستید!", show_alert=True)

    elif data == "start_spy_game":
        if chat_id not in spy_games:
            return

        game = spy_games[chat_id]
        players = game["players"]

        if len(players) < 3:
            await query.answer("تعداد افراد باید حداقل ۳ نفر باشه رفیق! 😉", show_alert=True)
            return

        game["status"] = "playing"
        game["location"] = random.choice(SPY_LOCATIONS)
        spy_user_id = random.choice(list(players.keys()))
        game["spy_id"] = spy_user_id

        failed_pv = []
        for p_id, p_name in players.items():
            try:
                if p_id == spy_user_id:
                    await context.bot.send_message(
                        chat_id=p_id, 
                        text="🕵️‍♂️ **شما جاسوس هستید!**\n\nهیچ‌کس نباید بفهمه! سعی کن با دقت به حرف بقیه گوش بدی تا بفهمی کجان! 😉"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=p_id, 
                        text=f"📍 **مکان این جوله بازی:**\n\n`{game['location']}`\n\nحواست باشه جاسوس رو پیدا کنی!"
                    )
            except Exception:
                failed_pv.append(p_name)

        start_msg = (
            "🚀 **بازی جاسوس شروع شد!**\n\n"
            "📥 نقش‌ها و مکان بازی به **پی‌وی (PV)** تمام بازیکنان ارسال شد.\n"
            "شروع کنید به سوال پرسیدن از همدیگه تا جاسوس لو بره! 🕵️‍♀️✨"
        )
        if failed_pv:
            start_msg += f"\n\n⚠️ **توجه:** ربات نتونست به پی‌وی این افراد پیام بده: {', '.join(failed_pv)}"

        keyboard = [
            [InlineKeyboardButton("🔍 رو کردن کارت جاسوس!", callback_data="reveal_spy")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=start_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "reveal_spy":
        if chat_id not in spy_games:
            return

        game = spy_games[chat_id]
        spy_name = game["players"].get(game["spy_id"], "نامشخص")
        loc = game["location"]

        result_text = (
            "🏁 **پایان بازی جاسوس!**\n\n"
            f"🕵️‍♂️ **جاسوس این جوله:** {spy_name}\n"
            f"📍 **مکان واقعی:** `{loc}`"
        )
        del spy_games[chat_id]
        await query.edit_message_text(text=result_text, parse_mode="Markdown")

    # --- ۴. بازی داستان گروهی ---
    elif data == "start_story":
        starter = random.choice(STORY_STARTERS)
        story_games[chat_id] = {
            "active": True,
            "sentences": [f"🎬 {starter}"]
        }

        story_text = (
            "📖 **بازی داستان‌نویسی گروهی شروع شد!**\n\n"
            "📜 **قانون:** هر نفر حداکثر **۱۰ کلمه** بنویسه و داستان رو ادامه بده.\n\n"
            f"📌 **شروع داستان:**\n\"{starter}\"\n\n"
            "👇 نفر بعدی ادامه بده:"
        )

        keyboard = [
            [InlineKeyboardButton("📖 پایان داستان و نمایش متن کامل", callback_data="finish_story")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=story_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "finish_story":
        if chat_id not in story_games or not story_games[chat_id]["active"]:
            await query.answer("داستانی فعال نیست!", show_alert=True)
            return

        sentences = story_games[chat_id]["sentences"]
        full_story = " ".join(sentences)

        final_text = (
            "📖 **داستان کامل گروهی شما:** 🏆\n\n"
            f"{full_story}\n\n"
            "دست همگی درد نکنه! 👏😍"
        )
        del story_games[chat_id]
        await query.edit_message_text(text=final_text, parse_mode="Markdown")

    # --- ۵. بازی من کی‌ام؟ ---
    elif data == "init_whoami":
        if query.message.chat.type not in ["group", "supergroup"]:
            await query.edit_message_text("⚠️ **بازی «من کی‌ام؟» مخصوص گروه‌هاست!** ربات رو به گروه اضافه کن. 🌸")
            return

        whoami_games[chat_id] = {
            "players": {user.id: {"name": user.first_name, "character": None}},
            "status": "joining"
        }

        text = (
            "🎭 **اتاق بازی «من کی‌ام؟» ساخته شد!**\n\n"
            f"👤 **اعضای حاضر:**\n• {user.first_name}\n\n"
            "حداقل **۲ نفر** لازمه! بقیه رو دکمه «📥 ورود به بازی» بزنن."
        )

        keyboard = [
            [InlineKeyboardButton("📥 ورود به بازی", callback_data="join_whoami")],
            [InlineKeyboardButton("🚪 انصراف و خروج", callback_data="leave_whoami")],
            [InlineKeyboardButton("🚀 شروع بازی!", callback_data="start_whoami_game")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "join_whoami":
        if chat_id not in whoami_games or whoami_games[chat_id]["status"] != "joining":
            return

        players = whoami_games[chat_id]["players"]
        if user.id not in players:
            players[user.id] = {"name": user.first_name, "character": None}

        players_list = "\n".join([f"• {p['name']}" for p in players.values()])
        text = (
            "🎭 **اتاق بازی «من کی‌ام؟»**\n\n"
            f"👤 **اعضای حاضر ({len(players)} نفر):**\n{players_list}\n\n"
            "هر وقت همه‌ جمع شدید، دکمه «🚀 شروع بازی!» رو بزنید."
        )

        keyboard = [
            [InlineKeyboardButton("📥 ورود به بازی", callback_data="join_whoami")],
            [InlineKeyboardButton("🚪 انصراف و خروج", callback_data="leave_whoami")],
            [InlineKeyboardButton("🚀 شروع بازی!", callback_data="start_whoami_game")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "leave_whoami":
        if chat_id in whoami_games and whoami_games[chat_id]["status"] == "joining":
            players = whoami_games[chat_id]["players"]
            if user.id in players:
                del players[user.id]
                await query.answer("شما از بازی خروج کردید!", show_alert=True)
                
                players_list = "\n".join([f"• {p['name']}" for p in players.values()]) if players else "هیچ‌کس"
                text = (
                    "🎭 **اتاق بازی «من کی‌ام؟»**\n\n"
                    f"👤 **اعضای حاضر ({len(players)} نفر):**\n{players_list}\n\n"
                    "هر وقت همه‌ جمع شدید، دکمه «🚀 شروع بازی!» رو بزنید."
                )
                keyboard = [
                    [InlineKeyboardButton("📥 ورود به بازی", callback_data="join_whoami")],
                    [InlineKeyboardButton("🚪 انصراف و خروج", callback_data="leave_whoami")],
                    [InlineKeyboardButton("🚀 شروع بازی!", callback_data="start_whoami_game")],
                    [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
                ]
                await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            else:
                await query.answer("شما هنوز در لیست بازیکنان نیستید!", show_alert=True)

    elif data == "start_whoami_game":
        if chat_id not in whoami_games:
            return

        game = whoami_games[chat_id]
        players = game["players"]

        if len(players) < 2:
            await query.answer("برای بازی حداقل به ۲ نفر نیاز داریم! 😉", show_alert=True)
            return

        game["status"] = "playing"
        available_chars = random.sample(FAMOUS_CHARACTERS, len(players))

        idx = 0
        for p_id in players:
            players[p_id]["character"] = available_chars[idx]
            idx += 1

        failed_pv = []
        for p_id, p_info in players.items():
            pv_msg = "🎭 **شخصیت‌های بقیه اعضا در بازی «من کی‌ام؟»:**\n\n"
            for other_id, other_info in players.items():
                if other_id != p_id:
                    pv_msg += f"• **{other_info['name']}** ⬅️ شخصیت: **{other_info['character']}**\n"
            pv_msg += "\n⚠️ **یادت باشه شخصیت خودت رو نداری!** با سوال پرسیدن حدس بزن کی هستی! 😉"

            try:
                await context.bot.send_message(chat_id=p_id, text=pv_msg, parse_mode="Markdown")
            except Exception:
                failed_pv.append(p_info["name"])

        start_text = (
            "🚀 **بازی «من کی‌ام؟» شروع شد!**\n\n"
            "📥 لیست شخصیت‌های بقیه اعضا به **پی‌وی (PV)** شما ارسال شد.\n"
            "هر زمان تونستید شخصیت خودتون رو درست حدس بزنید، برنده می‌شید! 😎✨"
        )
        if failed_pv:
            start_text += f"\n\n⚠️ **توجه:** پی‌وی افراد زیر بسته بود: {', '.join(failed_pv)}"

        keyboard = [
            [InlineKeyboardButton("🎭 رو کردن همه کارت‌ها", callback_data="reveal_whoami")],
            [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
        ]
        await query.edit_message_text(text=start_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "reveal_whoami":
        if chat_id not in whoami_games:
            return

        game = whoami_games[chat_id]
        players = game["players"]

        res = "🏁 **پایان بازی «من کی‌ام؟»**\n\n📜 **لیست کامل شخصیت‌ها:**\n\n"
        for p_id, p_info in players.items():
            res += f"• **{p_info['name']}** ⬅️ {p_info['character']}\n"

        del whoami_games[chat_id]
        await query.edit_message_text(text=res, parse_mode="Markdown")

    # --- ۶. بازی اسم بازی ---
    elif data == "start_name_game":
        first_letters = [
            "آ", "ب", "پ", "ت", "ج", "چ", "ح", "خ", "د", "ر", 
            "ز", "س", "ش", "ص", "ط", "ع", "ف", "ق", "ک", "گ", 
            "ل", "م", "ن", "و", "ه", "ی"
        ]
        start_char = random.choice(first_letters)

        name_games[chat_id] = {
            "active": True,
            "last_letter": start_char,
            "used_words": set(),
            "scores": {}
        }

        current_jobs = context.job_queue.get_jobs_by_name(f"timer_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()

        context.job_queue.run_once(
            name_game_timeout,
            TIMER_SECONDS,
            chat_id=chat_id,
            name=f"timer_{chat_id}"
        )

        text = (
            "🔤 **بازی «اسم بازی» (زنجیره کلمات) شروع شد!**\n\n"
            "📜 **قواعد بازی:**\n"
            "۱. کلمه‌ای بگو که با **حرف آخر** کلمه نفر قبلی شروع بشه.\n"
            "۲. کلمات تکراری قبول نیستند!\n"
            f"۳. برای هر کلمه فقط **{TIMER_SECONDS} ثانیه** فرصت داری!\n\n"
            f"📌 **کلمه اول باید با حرف « {start_char} » شروع بشه.** سریع باشید! 👇"
        )

        keyboard = [[InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "finish_name_game":
        if chat_id not in name_games or not name_games[chat_id]["active"]:
            await query.answer("بازی فعالی وجود ندارد!", show_alert=True)
            return

        current_jobs = context.job_queue.get_jobs_by_name(f"timer_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()

        scores = name_games[chat_id]["scores"]

        if not scores:
            final_text = "🏁 **بازی اسم بازی به پایان رسید!**\n\nهیچ‌کس امتیازی کسب نکرد! 😅"
        else:
            final_text = "🏁 **جدول امتیازات پایانی بازی اسم بازی:** 🏆\n\n"
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            for rank, (name, score) in enumerate(sorted_scores, 1):
                final_text += f"{rank}. **{name}**: {score} امتیاز\n"

        del name_games[chat_id]
        await query.edit_message_text(text=final_text, parse_mode="Markdown")

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
        "1️⃣ `/games` - منوی بازی‌ها (۲۰ سوالی، اطلاعات عمومی، جاسوس، داستان گروهی، من کی‌ام؟، اسم بازی) 🎮\n"
        "2️⃣ برای گپ زدن تو گروه، کافیه پیامم رو **Reply** کنی یا آیدیم رو **Mention** کنی.\n"
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
    except Exception:
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

        # 🔤 مدیریت بازی «اسم بازی»
        if chat_id in name_games and name_games[chat_id]["active"]:
            game = name_games[chat_id]
            word = user_text.strip()

            if len(word.split()) == 1 and not word.startswith("/"):
                first_char = word[0]

                if first_char == "ك": first_char = "ک"
                if first_char == "ي": first_char = "ی"

                if first_char == game["last_letter"]:
                    if word in game["used_words"]:
                        await update.message.reply_text(f"❌ **{user_name} عزیز!** کلمه «{word}» قبلاً استفاده شده!")
                        return

                    game["used_words"].add(word)

                    last_char = word[-1]
                    if last_char in ["ا", "آ"]: last_char = "ا"
                    elif last_char in ["ە", "ه"]: last_char = "ه"
                    elif last_char == "ي": last_char = "ی"
                    elif last_char == "ك": last_char = "ک"

                    game["last_letter"] = last_char
                    game["scores"][user_name] = game["scores"].get(user_name, 0) + 1

                    current_jobs = context.job_queue.get_jobs_by_name(f"timer_{chat_id}")
                    for job in current_jobs:
                        job.schedule_removal()

                    context.job_queue.run_once(
                        name_game_timeout,
                        TIMER_SECONDS,
                        chat_id=chat_id,
                        name=f"timer_{chat_id}"
                    )

                    keyboard = [[InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")]]
                    await update.message.reply_text(
                        f"✅ **آفرین {user_name}!** (+۱ امتیاز)\n\n"
                        f"👉 نفر بعدی کلمه‌ای بگه که با **« {last_char} »** شروع بشه!\n"
                        f"⏱️ **فرصت باقی‌مانده:** {TIMER_SECONDS} ثانیه",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode="Markdown"
                    )
                    return

        # 📖 مدیریت بازی داستان گروهی
        if chat_id in story_games and story_games[chat_id]["active"]:
            words = user_text.strip().split()
            if len(words) > 10:
                await update.message.reply_text(f"⚠️ **{user_name} عزیز!** قانون بازی اینه که متنت **حداکثر ۱۰ کلمه** باشه (متن شما {len(words)} کلمه بود). لطفا کوتاه‌ترش کن! 😉")
                return
            else:
                story_games[chat_id]["sentences"].append(user_text.strip())
                keyboard = [
                    [InlineKeyboardButton("📖 پایان داستان و نمایش متن کامل", callback_data="finish_story")],
                    [InlineKeyboardButton("🏁 انصراف و لغو بازی", callback_data="cancel_game")]
                ]
                await update.message.reply_text(f"✅ کلمات {user_name} به داستان اضافه شد!\n\n👇 نفر بعدی ادامه بده:", reply_markup=InlineKeyboardMarkup(keyboard))
                return

        # 🎭 بررسی حدس در بازی «من کی‌ام؟»
        if chat_id in whoami_games and whoami_games[chat_id]["status"] == "playing":
            game = whoami_games[chat_id]
            if user_id in game["players"]:
                my_char = game["players"][user_id]["character"]
                if my_char and my_char in user_text:
                    await update.message.reply_text(f"🎉 **آفرین {user_name}!** دقیقاً درست حدس زدی! 🏆\nشخصیت شما **«{my_char}»** بود!")
                    return

        is_replied_to_bot = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = f"@{bot_username}" in user_text

        # 🎯 بررسی و پاسخ هوشمند به بازی ۲۰ سوالی در گروه‌ها
        if chat_id in active_games_20q and active_games_20q[chat_id]["active"]:
            game = active_games_20q[chat_id]
            secret = game["secret_word"]
            
            if secret in user_text:
                game["active"] = False
                await update.message.reply_text(f"🎉 آفرین {user_name}! ایول، دقیقاً درست حدس زدی! کلمه مخفی من **«{secret}»** بود. 🏆✨")
                del active_games_20q[chat_id]
                return
            else:
                game["questions_left"] -= 1
                if game["questions_left"] <= 0:
                    await game_over_timeout(chat_id, secret, update)
                    return
                
                prompt_20q = f"""
                هم‌اکنون در حال انجام بازی ۲۰ سوالی هستی.
                کلمه مخفی و انتخابی تو «{secret}» است.
                کاربر سوال زیر را درباره کلمه مخفی پرسیده است:
                "{user_text}"
                
                قوانین پاسخ‌دهی:
                ۱. فقط بر اساس کلمه مخفی «{secret}» به سوال پاسخ بده.
                ۲. حتماً و فقط بسیار کوتاه با یکی از کلمات «بله»، «خیر»، «تا حدی» یا «ربطی نداره» جواب بده.
                ۳. به هیچ وجه خود کلمه مخفی را فاش نکن!
                ۴. توضیحات اضافه‌تر اصلاً نده.
                """
                try:
                    res_20q = co.chat(message=prompt_20q, model="command-r-08-2024")
                    keyboard = [[InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")]]
                    await update.message.reply_text(
                        f"{res_20q.text.strip()}\n\n⏱️ **فرصت‌های باقی‌مانده:** {game['questions_left']}",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception:
                    await update.message.reply_text(f"سوالت بررسی شد! (فرصت‌های باقی‌مانده: {game['questions_left']})")
                return

        if not (is_replied_to_bot or is_mentioned):
            return
        user_text = user_text.replace(f"@{bot_username}", "").strip()
    else:
        active_users.add(chat_id)

    # 🎯 بررسی و پاسخ هوشمند به بازی ۲۰ سوالی در چت خصوصی (PV)
    if chat_id in active_games_20q and active_games_20q[chat_id]["active"]:
        game = active_games_20q[chat_id]
        secret = game["secret_word"]
        user_name = user.first_name or "کاربر"

        if secret in user_text:
            game["active"] = False
            await update.message.reply_text(f"🎉 آفرین {user_name}! ایول، دقیقاً درست حدس زدی! کلمه مخفی من **«{secret}»** بود. 🏆✨")
            del active_games_20q[chat_id]
            return
        else:
            game["questions_left"] -= 1
            if game["questions_left"] <= 0:
                await game_over_timeout(chat_id, secret, update)
                return

            prompt_20q = f"""
            هم‌اکنون در حال انجام بازی ۲۰ سوالی هستی.
            کلمه مخفی و انتخابی تو «{secret}» است.
            کاربر سوال زیر را درباره کلمه مخفی پرسیده است:
            "{user_text}"
            
            قوانین پاسخ‌دهی:
            ۱. فقط بر اساس کلمه مخفی «{secret}» به سوال پاسخ بده.
            ۲. حتماً و فقط بسیار کوتاه با یکی از کلمات «بله»، «خیر»، «تا حدی» یا «ربطی نداره» جواب بده.
            ۳. به هیچ وجه خود کلمه مخفی «{secret}» را لو نده!
            ۴. هیچ توضیحات اضافی یا احوالپرسی مثل "سلام" نده.
            """
            try:
                res_20q = co.chat(message=prompt_20q, model="command-r-08-2024")
                keyboard = [[InlineKeyboardButton("🏁 انصراف و پایان بازی", callback_data="cancel_game")]]
                await update.message.reply_text(
                    f"{res_20q.text.strip()}\n\n⏱️ **فرصت‌های باقی‌مانده:** {game['questions_left']}",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await update.message.reply_text(f"پاسخ ثبت شد. (فرصت‌های باقی‌مانده: {game['questions_left']})")
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

    except Exception:
        await update.message.reply_text("مشکل سیستمی در ارتباط")

async def game_over_timeout(chat_id, secret, update):
    active_games_20q[chat_id]["active"] = False
    del active_games_20q[chat_id]
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
    
    app.add_handler(CallbackQueryHandler(button_callback))
    
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("banlist", banlist_command))
    
    app.add_handler(CommandHandler("off", maintenance_off))
    app.add_handler(CommandHandler("on", maintenance_on))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()
