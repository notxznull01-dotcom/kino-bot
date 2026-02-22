import asyncio
import os
import logging
import sys
from datetime import datetime, date
from threading import Thread
from flask import Flask
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove,
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

# ================= KONFIGURATSIYA =================
TOKEN = os.environ.get("BOT_TOKEN", "8366692220:AAHKoIz6A__Ll1V5yvcjcjWVaFr5Xcf9HQQ")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7492227388"))
ADMIN_PASS = os.environ.get("ADMIN_PASS", "456")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://kino_bot_db_duf5_user:MNiazQVid4iljB2dvN7LeJ8XfYFdnaJQ@dpg-d672bp8gjchc738fpdm0-a/kino_bot_db_duf5")

# ================= FLASK =================
app = Flask('')

@app.route('/')
def home():
    return "✅ Kino Bot ishlayapti!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= POSTGRESQL =================
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT,
                coins INTEGER DEFAULT 100,
                referrer_id BIGINT DEFAULT NULL,
                joined_at DATE DEFAULT CURRENT_DATE,
                last_bonus DATE DEFAULT NULL,
                is_banned BOOLEAN DEFAULT FALSE
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                year TEXT,
                description TEXT,
                file_id TEXT,
                price INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                movie_id INTEGER,
                bought_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS required_channels (
                id SERIAL PRIMARY KEY,
                link TEXT NOT NULL,
                title TEXT DEFAULT 'Kanal',
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Har bir foydalanuvchi + kanal juftligi uchun holat
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sub_status (
                user_id BIGINT,
                channel_id INTEGER,
                is_subscribed BOOLEAN DEFAULT FALSE,
                last_checked TIMESTAMP DEFAULT NOW(),
                subscribed_at TIMESTAMP,
                unsubscribed_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
        """)
        # Barcha obuna hodisalari logi
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sub_logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                user_name TEXT,
                channel_id INTEGER,
                channel_title TEXT,
                channel_link TEXT,
                event TEXT,
                event_time TIMESTAMP DEFAULT NOW()
            )
        """)
    logger.info("✅ Baza tayyor!")

# ================= BAZA FUNKSIYALAR =================
async def get_user(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)

async def create_user(user_id: int, name: str, phone: str = None, referrer_id: int = None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, name, phone, coins, referrer_id)
            VALUES ($1, $2, $3, 100, $4)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, name, phone, referrer_id)
        if referrer_id:
            await conn.execute("UPDATE users SET coins = coins + 50 WHERE user_id=$1", referrer_id)

async def get_all_users():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users WHERE is_banned=FALSE")

async def get_movie(movie_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM movies WHERE id=$1", movie_id)

async def get_all_movies():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM movies ORDER BY id DESC")

async def add_movie(name, year, description, file_id, price):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO movies (name, year, description, file_id, price)
            VALUES ($1, $2, $3, $4, $5) RETURNING id
        """, name, year, description, file_id, price)
        return row['id']

async def user_has_movie(user_id: int, movie_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM purchases WHERE user_id=$1 AND movie_id=$2", user_id, movie_id)
        return row is not None

async def buy_movie(user_id: int, movie_id: int, price: int):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT coins FROM users WHERE user_id=$1", user_id)
        if not user or user['coins'] < price:
            return False
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id=$2", price, user_id)
        await conn.execute("INSERT INTO purchases (user_id, movie_id) VALUES ($1, $2)", user_id, movie_id)
        return True

async def get_stats():
    async with db_pool.acquire() as conn:
        return {
            "total_users": await conn.fetchval("SELECT COUNT(*) FROM users"),
            "banned_users": await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned=TRUE"),
            "total_movies": await conn.fetchval("SELECT COUNT(*) FROM movies"),
            "total_purchases": await conn.fetchval("SELECT COUNT(*) FROM purchases"),
            "today_users": await conn.fetchval("SELECT COUNT(*) FROM users WHERE joined_at=CURRENT_DATE"),
        }

# ================= MAJBURIY OBUNA =================
async def get_required_channels():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM required_channels ORDER BY id")

async def add_required_channel(link: str, title: str = "Kanal"):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO required_channels (link, title) VALUES ($1, $2)", link, title)

async def remove_required_channel(channel_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM required_channels WHERE id=$1", channel_id)
        await conn.execute("DELETE FROM user_sub_status WHERE channel_id=$1", channel_id)

def is_telegram_link(link: str) -> bool:
    return 't.me/' in link or 'telegram.me/' in link

def extract_tg_username(link: str):
    """Link dan @username chiqaradi. Invite link bo'lsa None qaytaradi."""
    try:
        if 't.me/' in link:
            uname = link.split('t.me/')[-1].strip().strip('/')
        elif 'telegram.me/' in link:
            uname = link.split('telegram.me/')[-1].strip().strip('/')
        else:
            return None
        if uname.startswith('+') or '/' in uname or not uname:
            return None
        return f"@{uname}"
    except:
        return None

# ===================================================================
# ASOSIY TEKSHIRISH: Telegram API orqali REAL VAQTDA foydalanuvchi ID
# Hech qanday kesh yo'q — har safar to'g'ridan-to'g'ri API ga so'rov
# ===================================================================
async def check_tg_sub_api(user_id: int, link: str) -> bool:
    """
    Telegram get_chat_member API orqali foydalanuvchi ID sini tekshiradi.
    True  = obuna bo'lgan (member, administrator, creator)
    False = obuna bo'lmagan (left, kicked, banned) yoki xato
    """
    username = extract_tg_username(link)
    if not username:
        logger.warning(f"Invite link yoki noto'g'ri format: {link}")
        return False
    try:
        member = await bot.get_chat_member(username, user_id)
        result = member.status not in ('left', 'kicked', 'banned')
        logger.info(f"check_tg_sub_api: user={user_id} channel={username} status={member.status} result={result}")
        return result
    except Exception as e:
        logger.warning(f"get_chat_member xato ({username}, {user_id}): {e}")
        return False

async def get_external_confirmed(user_id: int, channel_id: int) -> bool:
    """Tashqi kanal (Instagram va h.k.) uchun DB dagi tasdiqlash holatini qaytaradi."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_subscribed FROM user_sub_status WHERE user_id=$1 AND channel_id=$2",
            user_id, channel_id
        )
        return bool(row and row['is_subscribed'])

async def set_external_confirmed(user_id: int, channel_id: int):
    """Tashqi kanal uchun tasdiqlashni DB ga yozadi."""
    now = datetime.now()
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_sub_status (user_id, channel_id, is_subscribed, last_checked, subscribed_at)
            VALUES ($1, $2, TRUE, $3, $3)
            ON CONFLICT (user_id, channel_id) DO UPDATE
            SET is_subscribed = TRUE, last_checked = $3,
                subscribed_at = COALESCE(user_sub_status.subscribed_at, $3)
        """, user_id, channel_id, now)

# ===================================================================
# HOLAT KUZATISH VA LOGLASH
# Oldingi holat bilan solishtiradi, o'zgarsa — log yozadi va admin xabardor qiladi
# ===================================================================
async def track_and_log(user_id: int, user_name: str, channel: dict, is_sub: bool):
    """Obuna holatini DB ga yozadi, o'zgarish bo'lsa log qiladi."""
    ch_id = channel['id']
    ch_title = channel['title']
    ch_link = channel['link']
    now = datetime.now()

    async with db_pool.acquire() as conn:
        # Oldingi holatni olamiz
        prev = await conn.fetchrow(
            "SELECT is_subscribed FROM user_sub_status WHERE user_id=$1 AND channel_id=$2",
            user_id, ch_id
        )
        prev_status = prev['is_subscribed'] if prev else None

        # Yangi holatni yozamiz
        if is_sub:
            await conn.execute("""
                INSERT INTO user_sub_status (user_id, channel_id, is_subscribed, last_checked, subscribed_at)
                VALUES ($1, $2, TRUE, $3, $3)
                ON CONFLICT (user_id, channel_id) DO UPDATE
                SET is_subscribed = TRUE, last_checked = $3,
                    subscribed_at = CASE WHEN user_sub_status.is_subscribed = FALSE OR user_sub_status.subscribed_at IS NULL
                                         THEN $3 ELSE user_sub_status.subscribed_at END
            """, user_id, ch_id, now)
        else:
            await conn.execute("""
                INSERT INTO user_sub_status (user_id, channel_id, is_subscribed, last_checked, unsubscribed_at)
                VALUES ($1, $2, FALSE, $3, $3)
                ON CONFLICT (user_id, channel_id) DO UPDATE
                SET is_subscribed = FALSE, last_checked = $3,
                    unsubscribed_at = CASE WHEN user_sub_status.is_subscribed = TRUE
                                           THEN $3 ELSE user_sub_status.unsubscribed_at END
            """, user_id, ch_id, now)

        # Hodisani aniqlash (faqat o'zgarishda yoki birinchi marta)
        event = None
        if prev_status is None and is_sub:
            event = 'first_subscribed'
        elif prev_status is None and not is_sub:
            event = 'checked_not_subscribed'
        elif prev_status is False and is_sub:
            event = 'subscribed'
        elif prev_status is True and not is_sub:
            event = 'unsubscribed'  # Obunani olib tashladi!

        if event:
            await conn.execute("""
                INSERT INTO sub_logs (user_id, user_name, channel_id, channel_title, channel_link, event)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, user_id, user_name, ch_id, ch_title, ch_link, event)
            # Adminga xabar
            asyncio.create_task(notify_admin_sub(user_id, user_name, ch_title, ch_link, event))

async def notify_admin_sub(user_id: int, user_name: str, ch_title: str, ch_link: str, event: str):
    """Admin ga obuna o'zgarishi haqida xabar yuboradi."""
    emoji = {
        'first_subscribed': '🆕✅',
        'subscribed': '✅',
        'checked_not_subscribed': '❌',
        'unsubscribed': '⚠️🔴',
    }.get(event, '❓')
    label = {
        'first_subscribed': "birinchi marta obuna bo'ldi",
        'subscribed': "qayta obuna bo'ldi",
        'checked_not_subscribed': "tekshirdi, obuna emas",
        'unsubscribed': "OBUNANI OLIB TASHLADI!",
    }.get(event, event)
    t = datetime.now().strftime("%d.%m.%Y %H:%M")
    try:
        await bot.send_message(
            ADMIN_ID,
            f"{emoji} <b>Obuna hodisasi</b> | {t}\n"
            f"👤 <b>{user_name}</b> (<code>{user_id}</code>)\n"
            f"📌 <a href='{ch_link}'>{ch_title}</a>\n"
            f"📋 <b>{label}</b>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except:
        pass

# ===================================================================
# BARCHA KANALLARGA TEKSHIRISH — har bir funksiyada chaqiriladi
# ===================================================================
async def check_all_subs(user_id: int, user_name: str) -> list:
    """
    Barcha majburiy kanallarga obunani REAL VAQTDA tekshiradi.
    Telegram: API orqali, Tashqi: DB dan.
    Qaytaradi: obuna bo'lmagan kanallar ro'yxati.
    """
    channels = await get_required_channels()
    if not channels:
        return []

    not_subscribed = []
    for ch in channels:
        if is_telegram_link(ch['link']):
            is_sub = await check_tg_sub_api(user_id, ch['link'])
        else:
            is_sub = await get_external_confirmed(user_id, ch['id'])

        # DB ga yozamiz va loglaymiz
        await track_and_log(user_id, user_name, ch, is_sub)

        if not is_sub:
            not_subscribed.append(ch)

    return not_subscribed

def build_sub_kb(channels: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, ch in enumerate(channels):
        kb.button(text=f"{emojis[i % 5]} {ch['title']} — A'zo bo'lish", url=ch['link'])
    kb.button(text="✅ Obunani Tekshirish", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

async def send_sub_msg(user_id: int, channels: list):
    lines = "".join(f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n" for i, ch in enumerate(channels, 1))
    text = (
        "⚠️ <b>Botdan foydalanish uchun\n"
        "quyidagi kanallarga a'zo bo'ling:</b>\n\n"
        f"{lines}\n"
        "A'zo bo'lgach ✅ <b>Obunani Tekshirish</b> tugmasini bosing."
    )
    try:
        await bot.send_message(
            user_id, text,
            reply_markup=build_sub_kb(channels),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning(f"send_sub_msg xato: {e}")

async def sub_guard(m: Message) -> bool:
    """
    Har bir bot funksiyasining boshida chaqiriladi.
    True = davom etish | False = obuna talab qilindi.
    """
    user = await get_user(m.from_user.id)
    if not user:
        return True
    if user['is_banned']:
        return True
    not_sub = await check_all_subs(m.from_user.id, user['name'])
    if not_sub:
        await send_sub_msg(m.from_user.id, not_sub)
        return False
    return True

# ================= FSM HOLATLAR =================
class BotState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    admin_auth = State()
    adding_k_name = State()
    adding_k_year = State()
    adding_k_desc = State()
    adding_k_file = State()
    adding_k_price = State()
    buying_movie = State()
    sending_broadcast = State()
    blocking_id = State()
    unblocking_id = State()
    admin_chat_target = State()
    in_active_chat = State()
    add_coin_id = State()
    add_coin_amount = State()
    remove_coin_id = State()
    remove_coin_amount = State()
    adding_sub_link = State()
    adding_sub_title = State()

# ================= KLAVIATURALAR =================
def get_main_kb(uid: int):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Kinolar Ro'yxati")
    builder.button(text="🎟 Kino Sotib Olish")
    builder.button(text="💰 Hisobim")
    builder.button(text="🎁 Kunlik Bonus")
    builder.button(text="👥 Do'st Taklif Qilish")
    builder.button(text="✍️ Adminga Yozish")
    if uid == ADMIN_ID:
        builder.button(text="👑 Admin Panel")
        builder.button(text="📊 Statistika")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kino Qo'shish", callback_data="adm_add_kino")
    builder.button(text="🗑 Kino O'chirish", callback_data="adm_del_kino")
    builder.button(text="💰 Coin Qo'shish", callback_data="adm_add_coin")
    builder.button(text="💸 Coin Olish", callback_data="adm_remove_coin")
    builder.button(text="📢 Reklama Yuborish", callback_data="adm_broadcast")
    builder.button(text="🚫 Foydalanuvchi Bloklash", callback_data="adm_ban")
    builder.button(text="✅ Blokdan Chiqarish", callback_data="adm_unban")
    builder.button(text="💬 Foydalanuvchi bilan Gaplash", callback_data="adm_start_chat")
    builder.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
    builder.button(text="🔔 Majburiy Obuna", callback_data="adm_subscription")
    builder.button(text="👥 Foydalanuvchilar Ro'yxati", callback_data="adm_users")
    builder.button(text="📋 Obuna Loglari", callback_data="adm_sub_logs")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_end_chat_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Aloqani Tugatish", callback_data="end_chat")
    return builder.as_markup()

# ================= START =================
@dp.message(CommandStart())
async def start_cmd(m: Message, state: FSMContext):
    await state.clear()
    user = await get_user(m.from_user.id)

    referrer_id = None
    args = m.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
            if referrer_id == m.from_user.id:
                referrer_id = None
        except:
            pass

    if user:
        if user['is_banned']:
            return await m.answer("🚫 Siz botdan bloklangansiz.")
        not_sub = await check_all_subs(m.from_user.id, user['name'])
        if not_sub:
            return await send_sub_msg(m.from_user.id, not_sub)
        return await m.answer(
            f"🌟 *Xush kelibsiz qaytib, {user['name']}!*\n\n💰 Balansingiz: *{user['coins']} coin*",
            reply_markup=get_main_kb(m.from_user.id), parse_mode="Markdown"
        )
    else:
        await state.update_data(referrer_id=referrer_id)
        await m.answer(
            "👋 *Assalomu alaykum! Kino Botga xush kelibsiz!*\n\nRo'yxatdan o'tish uchun *ismingizni* kiriting:",
            parse_mode="Markdown"
        )
        await state.set_state(BotState.waiting_name)

# ===================================================================
# "TEKSHIRISH" TUGMASI
# Telegram: API orqali, Tashqi: "Tekshirish" bosilganda tasdiqlanadi
# ===================================================================
@dp.callback_query(F.data == "check_subscription")
async def check_sub_callback(c: CallbackQuery):
    await c.answer("⏳ Tekshirilmoqda...", show_alert=False)

    user = await get_user(c.from_user.id)
    if not user:
        return await c.message.answer("❌ Avval ro'yxatdan o'ting! /start")
    if user['is_banned']:
        return await c.message.answer("🚫 Siz botdan bloklangansiz.")

    channels = await get_required_channels()
    not_subscribed = []

    for ch in channels:
        if is_telegram_link(ch['link']):
            # Telegram: API orqali haqiqiy tekshirish
            is_sub = await check_tg_sub_api(c.from_user.id, ch['link'])
        else:
            # Tashqi kanal: foydalanuvchi "Tekshirish" tugmasini bosdi = tasdiqlandi
            is_sub = True
            await set_external_confirmed(c.from_user.id, ch['id'])

        await track_and_log(c.from_user.id, user['name'], ch, is_sub)

        if not is_sub:
            not_subscribed.append(ch)

    if not not_subscribed:
        try:
            await c.message.edit_text(
                "✅ <b>Barcha kanallarga a'zo bo'ldingiz!</b>\n\nEndi botdan to'liq foydalaning!",
                parse_mode="HTML"
            )
        except:
            pass
        await bot.send_message(
            c.from_user.id,
            f"🎉 <b>Xush kelibsiz, {user['name']}!</b>\n\n💰 Balansingiz: <b>{user['coins']} coin</b>",
            reply_markup=get_main_kb(c.from_user.id),
            parse_mode="HTML"
        )
    else:
        lines = "".join(f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n" for i, ch in enumerate(not_subscribed, 1))
        text = (
            f"❌ <b>Hali {len(not_subscribed)} ta kanalga a'zo bo'lmadingiz:</b>\n\n"
            f"{lines}\n"
            "A'zo bo'lib, <b>✅ Obunani Tekshirish</b> tugmasini qayta bosing."
        )
        try:
            await c.message.edit_text(
                text, reply_markup=build_sub_kb(not_subscribed),
                parse_mode="HTML", disable_web_page_preview=True
            )
        except:
            await bot.send_message(
                c.from_user.id, text,
                reply_markup=build_sub_kb(not_subscribed),
                parse_mode="HTML", disable_web_page_preview=True
            )

# ================= RO'YXATDAN O'TISH =================
@dp.message(BotState.waiting_name)
async def reg_name(m: Message, state: FSMContext):
    if len(m.text) < 2:
        return await m.answer("⚠️ Ism kamida 2 ta harf bo'lishi kerak!")
    await state.update_data(name=m.text.strip())
    kb = ReplyKeyboardBuilder()
    kb.button(text="📱 Raqamni Yuborish", request_contact=True)
    kb.button(text="⏭ O'tkazib yuborish")
    kb.adjust(1)
    await m.answer("📱 Telefon raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.waiting_phone)

async def finish_registration(m: Message, state: FSMContext, name: str, phone: str = None):
    data = await state.get_data()
    await create_user(m.from_user.id, name, phone, data.get('referrer_id'))
    await state.clear()
    channels = await get_required_channels()
    if channels:
        await m.answer(
            f"✅ *Tabriklaymiz, {name}!*\n\n🎉 Ro'yxatdan o'tdingiz!\n💰 Sizga *100 coin* sovg'a qilindi!\n\n"
            "⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:",
            parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
        )
        not_sub = await check_all_subs(m.from_user.id, name)
        if not_sub:
            await send_sub_msg(m.from_user.id, not_sub)
    else:
        await m.answer(
            f"✅ *Tabriklaymiz, {name}!*\n\n🎉 Ro'yxatdan o'tdingiz!\n💰 Sizga *100 coin* sovg'a qilindi!",
            reply_markup=get_main_kb(m.from_user.id), parse_mode="Markdown"
        )

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone_contact(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_registration(m, state, data['name'], m.contact.phone_number)

@dp.message(BotState.waiting_phone, F.text == "⏭ O'tkazib yuborish")
async def reg_skip_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_registration(m, state, data['name'], None)

# ================= KINOLAR =================
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def show_movies(m: Message):
    if not await sub_guard(m):
        return
    movies = await get_all_movies()
    if not movies:
        return await m.answer("📽 Hozircha bazada kinolar mavjud emas.")
    text = "🔥 *KINOLAR RO'YXATI* 🔥\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for movie in movies:
        text += f"🎬 *{movie['name']}*\n📅 Yil: {movie['year']}\n💎 Narx: *{movie['price']} coin*\n🆔 Kod: `{movie['id']}`\n────────────────────\n"
    text += "\n🍿 *Sotib olish: 🎟 Kino Sotib Olish tugmasi*"
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎟 Kino Sotib Olish")
async def buy_movie_start(m: Message, state: FSMContext):
    if not await sub_guard(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    await m.answer(f"💰 Balansingiz: *{user['coins']} coin*\n\n🎬 Kino *kodini* yuboring:", parse_mode="Markdown")
    await state.set_state(BotState.buying_movie)

@dp.message(BotState.buying_movie)
async def process_buy(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat kino kodini raqamda yozing!")
    movie = await get_movie(int(m.text))
    if not movie:
        return await m.answer("❌ Bunday kodli kino topilmadi!")
    user = await get_user(m.from_user.id)
    if await user_has_movie(m.from_user.id, movie['id']):
        await state.clear()
        await m.answer(f"✅ Siz *{movie['name']}* kinoni allaqachon sotib olgansiz!", parse_mode="Markdown")
        if movie['file_id']:
            if movie['file_id'].startswith('http'):
                kb = InlineKeyboardBuilder()
                kb.button(text="🎬 Kinoni Tomosha Qilish", url=movie['file_id'])
                await m.answer(f"🎬 *{movie['name']}*", reply_markup=kb.as_markup(), parse_mode="Markdown")
            else:
                await bot.send_video(m.from_user.id, movie['file_id'], caption=f"🎬 {movie['name']}")
        return
    if user['coins'] < movie['price']:
        await state.clear()
        return await m.answer(
            f"❌ *Coinlar yetarli emas!*\n\n💎 Narx: {movie['price']} coin\n💰 Sizda: {user['coins']} coin",
            parse_mode="Markdown"
        )
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Ha, {movie['price']} coin to'layman", callback_data=f"confirm_buy_{movie['id']}")
    kb.button(text="❌ Bekor qilish", callback_data="cancel_buy")
    kb.adjust(1)
    await m.answer(
        f"🎬 *{movie['name']}* ({movie['year']})\n\n📝 {movie['description'] or 'Tavsif mavjud emas'}\n\n"
        f"💎 Narx: *{movie['price']} coin*\n💰 Sizda: *{user['coins']} coin*\n\nTasdiqlaysizmi?",
        reply_markup=kb.as_markup(), parse_mode="Markdown"
    )
    await state.clear()

@dp.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_purchase(c: CallbackQuery):
    await c.answer()
    movie_id = int(c.data.split("_")[2])
    movie = await get_movie(movie_id)
    success = await buy_movie(c.from_user.id, movie_id, movie['price'])
    if success:
        await c.message.edit_text(f"✅ *{movie['name']}* sotib olindi!\nKino yuborilmoqda...", parse_mode="Markdown")
        if movie['file_id']:
            if movie['file_id'].startswith('http'):
                kb = InlineKeyboardBuilder()
                kb.button(text="🎬 Kinoni Tomosha Qilish", url=movie['file_id'])
                await bot.send_message(c.from_user.id, f"🎬 *{movie['name']}* tayyor!", reply_markup=kb.as_markup(), parse_mode="Markdown")
            else:
                await bot.send_video(c.from_user.id, movie['file_id'], caption=f"🎬 {movie['name']}")
        else:
            await c.message.answer("⚠️ Kino fayli hali qo'shilmagan.")
    else:
        await c.message.edit_text("❌ Xatolik. Qayta urinib ko'ring!")

@dp.callback_query(F.data == "cancel_buy")
async def cancel_purchase(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("❌ Bekor qilindi.")

# ================= HISOBIM =================
@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    if not await sub_guard(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    async with db_pool.acquire() as conn:
        purchases_count = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE user_id=$1", m.from_user.id)
        referrals_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id)
    await m.answer(
        f"👤 *Shaxsiy Kabinet*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Ism: *{user['name']}*\n📱 Tel: {user['phone'] or 'Kiritilmagan'}\n"
        f"💰 Balans: *{user['coins']} coin*\n🎬 Sotib olingan: *{purchases_count}* ta\n"
        f"👥 Taklif qilingan: *{referrals_count}* ta\n📅 Sana: *{user['joined_at']}*\n\n"
        f"🔑 ID: `{m.from_user.id}`",
        parse_mode="Markdown"
    )

# ================= KUNLIK BONUS =================
@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_bonus(m: Message):
    if not await sub_guard(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    today = date.today()
    if user['last_bonus'] and user['last_bonus'] >= today:
        return await m.answer("⏳ *Bugun allaqachon bonus oldingiz!*\n\n🔄 Ertaga qaytib keling!", parse_mode="Markdown")
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins + 20, last_bonus = CURRENT_DATE WHERE user_id=$1", m.from_user.id)
    updated = await get_user(m.from_user.id)
    await m.answer(f"🎉 *Kunlik Bonus!*\n\n✅ *+20 coin* qo'shildi!\n💰 Balans: *{updated['coins']} coin*", parse_mode="Markdown")

# ================= DO'ST TAKLIF =================
@dp.message(F.text == "👥 Do'st Taklif Qilish")
async def referral(m: Message):
    if not await sub_guard(m):
        return
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{m.from_user.id}"
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id)
    await m.answer(
        f"👥 *Do'stlarni Taklif Qilish*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Havolangiz:\n`{ref_link}`\n\n"
        f"💰 Har bir do'st uchun: *+50 coin*\n👤 Taklif qilingan: *{cnt}* ta",
        parse_mode="Markdown"
    )

# ================= ADMINGA YOZISH =================
@dp.message(F.text == "✍️ Adminga Yozish")
async def write_to_admin(m: Message, state: FSMContext):
    if not await sub_guard(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    await state.set_state(BotState.in_active_chat)
    await state.update_data(chat_with=ADMIN_ID, is_user_side=True)
    await m.answer("✍️ *Adminga xabar yozing:*\n\nTugatish: /stop", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 <b>Foydalanuvchi xabar yozmoqda!</b>\n\n"
            f"👤 <b>{user['name']}</b> | ID: <code>{m.from_user.id}</code>\n\n"
            "Javob: Admin Panel → 💬 Foydalanuvchi bilan Gaplash",
            parse_mode="HTML"
        )
    except:
        pass

# ================= AKTIV CHAT =================
@dp.message(BotState.in_active_chat)
async def active_chat(m: Message, state: FSMContext):
    if m.text and m.text.lower() == "/stop":
        data = await state.get_data()
        partner = data.get("chat_with")
        is_user_side = data.get("is_user_side", True)
        await state.clear()
        await m.answer("📴 Suhbat yakunlandi.", reply_markup=get_main_kb(m.from_user.id))
        if partner:
            try:
                if is_user_side:
                    await bot.send_message(partner, f"📴 Foydalanuvchi ({m.from_user.id}) suhbatni tugatdi.", reply_markup=get_admin_kb())
                else:
                    await bot.send_message(partner, "📴 Admin suhbatni tugatdi.", reply_markup=get_main_kb(partner))
            except:
                pass
        return

    data = await state.get_data()
    partner = data.get("chat_with")
    is_user_side = data.get("is_user_side", True)
    if not partner:
        return

    user = await get_user(m.from_user.id)
    name = user['name'] if user else m.from_user.full_name
    prefix = f"📩 *{name}* (ID: `{m.from_user.id}`):\n\n" if is_user_side else "👑 *Admin:*\n\n"

    try:
        if m.text:
            await bot.send_message(partner, f"{prefix}{m.text}", parse_mode="Markdown")
        elif m.photo:
            await bot.send_photo(partner, m.photo[-1].file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        elif m.video:
            await bot.send_video(partner, m.video.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        elif m.document:
            await bot.send_document(partner, m.document.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        # Faqat admin uchun tugma
        if not is_user_side:
            await m.answer("✅ Yuborildi! Tugatish: /stop", reply_markup=get_admin_end_chat_kb())
        else:
            await m.answer("✅ Yuborildi! Tugatish: /stop")
    except Exception as e:
        await m.answer(f"❌ Yuborilmadi: {e}")

# ================= STATISTIKA =================
@dp.message(F.text == "📊 Statistika")
async def show_stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    s = await get_stats()
    await m.answer(
        f"📊 *BOT STATISTIKASI*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami: *{s['total_users']}*\n🆕 Bugun: *{s['today_users']}*\n"
        f"🚫 Bloklangan: *{s['banned_users']}*\n🎬 Kinolar: *{s['total_movies']}*\n"
        f"🛒 Sotuvlar: *{s['total_purchases']}*",
        parse_mode="Markdown"
    )

# ================= ADMIN PANEL =================
@dp.message(F.text == "👑 Admin Panel")
async def admin_panel(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer("🔐 Admin parolini kiriting:")
    await state.set_state(BotState.admin_auth)

@dp.message(BotState.admin_auth)
async def verify_admin(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        await state.clear()
        await m.answer("👑 *Xush kelibsiz, Admin!*", reply_markup=get_admin_kb(), parse_mode="Markdown")
    else:
        await state.clear()
        await m.answer("❌ Parol noto'g'ri!")

@dp.callback_query(F.data == "adm_close")
async def close_admin(c: CallbackQuery):
    await c.answer()
    await c.message.delete()

@dp.callback_query(F.data == "adm_full_stats")
async def full_stats(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    s = await get_stats()
    await c.message.edit_text(
        f"📊 *TO'LIQ STATISTIKA*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami: *{s['total_users']}*\n🆕 Bugun: *{s['today_users']}*\n"
        f"🚫 Bloklangan: *{s['banned_users']}*\n🎬 Kinolar: *{s['total_movies']}*\n"
        f"🛒 Sotuvlar: *{s['total_purchases']}*",
        parse_mode="Markdown", reply_markup=get_admin_kb()
    )

# ================= OBUNA LOGLARI =================
@dp.callback_query(F.data == "adm_sub_logs")
async def admin_sub_logs(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    async with db_pool.acquire() as conn:
        logs = await conn.fetch(
            "SELECT user_id, user_name, channel_title, channel_link, event, event_time FROM sub_logs ORDER BY event_time DESC LIMIT 40"
        )
    if not logs:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Orqaga", callback_data="sub_back")
        return await c.message.edit_text("📋 Hozircha hodisalar yo'q.", reply_markup=kb.as_markup())
    emojis = {'first_subscribed': '🆕✅', 'subscribed': '✅', 'checked_not_subscribed': '❌', 'unsubscribed': '⚠️🔴'}
    text = "📋 *Oxirgi Obuna Hodisalari*\n━━━━━━━━━━━━━━━━━━\n\n"
    for log in logs:
        emoji = emojis.get(log['event'], '❓')
        t = log['event_time'].strftime("%m-%d %H:%M") if log['event_time'] else ''
        text += f"{emoji} *{log['user_name']}* (`{log['user_id']}`)\n   📌 {log['channel_title']} | {t}\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except:
        await bot.send_message(c.from_user.id, text, parse_mode="Markdown")

# ================= FOYDALANUVCHILAR RO'YXATI =================
@dp.callback_query(F.data == "adm_users")
async def admin_users_list(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    async with db_pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT user_id, name, phone, coins, joined_at, is_banned FROM users ORDER BY joined_at DESC LIMIT 50"
        )
    if not users:
        return await c.message.answer("📭 Hali foydalanuvchilar yo'q!")
    text = "👥 *FOYDALANUVCHILAR*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(users, 1):
        s = "🚫" if u['is_banned'] else "✅"
        text += f"{i}. {s} *{u['name']}*\n   🔑 `{u['user_id']}` | 💰 {u['coins']} | 📅 {u['joined_at']}\n"
    text += f"\n📊 Ko'rsatildi: *{len(users)}* ta"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except:
        await bot.send_message(c.from_user.id, text, parse_mode="Markdown")

# ================= MAJBURIY OBUNA BOSHQARUVI =================
@dp.callback_query(F.data == "adm_subscription")
async def admin_subscription_menu(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    channels = await get_required_channels()
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Kanal Qo'shish", callback_data="sub_add")
    if channels:
        kb.button(text="🗑 Kanal O'chirish", callback_data="sub_del_list")
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    kb.adjust(1)
    text = "🔔 *Majburiy Obuna*\n━━━━━━━━━━━━━━━━━━\n\n"
    if channels:
        text += "📋 *Kanallar:*\n"
        for ch in channels:
            t = "📱 TG" if is_telegram_link(ch['link']) else "🌐 Tashqi"
            text += f"• [{ch['title']}]({ch['link']}) — {t}\n"
        text += "\n💡 TG: API tekshiruv | Tashqi: foydalanuvchi tasdiqlaydi"
    else:
        text += "📭 Hozircha kanallar yo'q."
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown", disable_web_page_preview=True)

@dp.callback_query(F.data == "sub_back")
async def sub_back(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("👑 *Admin Panel*", reply_markup=get_admin_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "sub_add")
async def sub_add_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer(
        "🔗 *Kanal linkini yuboring:*\n\n"
        "📱 Telegram: `https://t.me/kanalnom`\n"
        "🌐 Tashqi: `https://instagram.com/nom`",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.adding_sub_link)

@dp.message(BotState.adding_sub_link)
async def sub_get_link(m: Message, state: FSMContext):
    link = m.text.strip()
    if not (link.startswith('http://') or link.startswith('https://')):
        return await m.answer("⚠️ Link http:// yoki https:// bilan boshlanishi kerak!")
    await state.update_data(sub_link=link)
    await m.answer("📝 *Kanal nomini kiriting:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_sub_title)

@dp.message(BotState.adding_sub_title)
async def sub_get_title(m: Message, state: FSMContext):
    try:
        data = await state.get_data()
        link = data.get('sub_link', '')
        title = m.text.strip()
        await add_required_channel(link, title)
        await state.clear()
        note = "⚠️ Botni kanalga admin qilib qo'shing!" if is_telegram_link(link) else "✅ Tashqi kanal — foydalanuvchi tasdiqlaydi."
        await m.answer(
            f"✅ <b>Kanal qo'shildi!</b>\n\n📛 {title}\n🔗 <code>{link}</code>\n\n{note}",
            parse_mode="HTML", disable_web_page_preview=True, reply_markup=get_admin_kb()
        )
        asyncio.create_task(broadcast_new_sub())
    except Exception as e:
        await state.clear()
        await m.answer(f"❌ Xatolik: {e}")

async def broadcast_new_sub():
    """Yangi kanal qo'shilganda barcha foydalanuvchilarga obuna xabari."""
    try:
        all_users = await get_all_users()
        for u in all_users:
            if u['user_id'] == ADMIN_ID:
                continue
            try:
                user = await get_user(u['user_id'])
                if not user:
                    continue
                not_sub = await check_all_subs(u['user_id'], user['name'])
                if not_sub:
                    await send_sub_msg(u['user_id'], not_sub)
                await asyncio.sleep(0.05)
            except:
                pass
    except Exception as e:
        logger.error(f"broadcast_new_sub xato: {e}")

@dp.callback_query(F.data == "sub_del_list")
async def sub_del_list(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    channels = await get_required_channels()
    if not channels:
        return await c.message.answer("📭 Kanallar yo'q!")
    kb = InlineKeyboardBuilder()
    for ch in channels:
        kb.button(text=f"🗑 {ch['title']}", callback_data=f"sub_del_{ch['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_subscription")
    kb.adjust(1)
    await c.message.edit_text("🗑 *O'chirmoqchi bo'lgan kanalni tanlang:*", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("sub_del_"))
async def sub_del_confirm(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    channel_id = int(c.data.split("_")[2])
    async with db_pool.acquire() as conn:
        ch = await conn.fetchrow("SELECT title FROM required_channels WHERE id=$1", channel_id)
    await remove_required_channel(channel_id)
    await c.answer(f"✅ '{ch['title'] if ch else 'Kanal'}' o'chirildi!", show_alert=True)
    channels = await get_required_channels()
    kb = InlineKeyboardBuilder()
    for ch2 in channels:
        kb.button(text=f"🗑 {ch2['title']}", callback_data=f"sub_del_{ch2['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_subscription")
    kb.adjust(1)
    text = "🗑 *Kanal tanlang:*" if channels else "📭 *Barcha kanallar o'chirildi.*"
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

# ================= COIN QO'SHISH =================
@dp.callback_query(F.data == "adm_add_coin")
async def add_coin_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💰 Foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.add_coin_id)

@dp.message(BotState.add_coin_id)
async def add_coin_get_id(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    user = await get_user(int(m.text))
    if not user:
        await state.clear()
        return await m.answer("❌ Foydalanuvchi topilmadi!")
    await state.update_data(target_user_id=int(m.text))
    await m.answer(f"👤 *{user['name']}* | 💰 {user['coins']} coin\n\nQancha coin qo'shmoqchisiz?", parse_mode="Markdown")
    await state.set_state(BotState.add_coin_amount)

@dp.message(BotState.add_coin_amount)
async def add_coin_process(m: Message, state: FSMContext):
    if not m.text.isdigit() or int(m.text) <= 0:
        return await m.answer("⚠️ Musbat son kiriting!")
    data = await state.get_data()
    uid = data['target_user_id']
    amount = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins + $1 WHERE user_id=$2", amount, uid)
    updated = await get_user(uid)
    await state.clear()
    await m.answer(f"✅ *+{amount} coin* qo'shildi!\n💰 Yangi balans: *{updated['coins']} coin*", parse_mode="Markdown", reply_markup=get_admin_kb())
    try:
        await bot.send_message(uid, f"🎉 Sizga *+{amount} coin* qo'shildi!\n💰 Balans: *{updated['coins']} coin*", parse_mode="Markdown")
    except:
        pass

# ================= COIN OLISH =================
@dp.callback_query(F.data == "adm_remove_coin")
async def remove_coin_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💸 Foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.remove_coin_id)

@dp.message(BotState.remove_coin_id)
async def remove_coin_get_id(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    user = await get_user(int(m.text))
    if not user:
        await state.clear()
        return await m.answer("❌ Foydalanuvchi topilmadi!")
    await state.update_data(target_user_id=int(m.text))
    await m.answer(f"👤 *{user['name']}* | 💰 {user['coins']} coin\n\nQancha coin olmoqchisiz?", parse_mode="Markdown")
    await state.set_state(BotState.remove_coin_amount)

@dp.message(BotState.remove_coin_amount)
async def remove_coin_process(m: Message, state: FSMContext):
    if not m.text.isdigit() or int(m.text) <= 0:
        return await m.answer("⚠️ Musbat son kiriting!")
    data = await state.get_data()
    uid = data['target_user_id']
    amount = int(m.text)
    user = await get_user(uid)
    if user['coins'] < amount:
        await state.clear()
        return await m.answer(f"⚠️ Foydalanuvchida faqat {user['coins']} coin bor!", parse_mode="Markdown", reply_markup=get_admin_kb())
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id=$2", amount, uid)
    updated = await get_user(uid)
    await state.clear()
    await m.answer(f"✅ *-{amount} coin* yechildi!\n💰 Yangi balans: *{updated['coins']} coin*", parse_mode="Markdown", reply_markup=get_admin_kb())
    try:
        await bot.send_message(uid, f"⚠️ Sizdan *-{amount} coin* yechildi!\n💰 Balans: *{updated['coins']} coin*", parse_mode="Markdown")
    except:
        pass

# ================= KINO QO'SHISH =================
@dp.callback_query(F.data == "adm_add_kino")
async def add_kino_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("🎬 *Kino nomini kiriting:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_name)

@dp.message(BotState.adding_k_name)
async def set_k_name(m: Message, state: FSMContext):
    await state.update_data(k_name=m.text)
    await m.answer("📅 *Kino yilini kiriting:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_year)

@dp.message(BotState.adding_k_year)
async def set_k_year(m: Message, state: FSMContext):
    await state.update_data(k_year=m.text)
    await m.answer("📝 *Tavsif yozing:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_desc)

@dp.message(BotState.adding_k_desc)
async def set_k_desc(m: Message, state: FSMContext):
    await state.update_data(k_desc=m.text)
    await m.answer("🔗 *Kino linkini yoki video faylini yuboring.*\n\nYo'q bo'lsa /skip yozing.", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_file)

@dp.message(BotState.adding_k_file, F.video)
async def set_k_file_video(m: Message, state: FSMContext):
    await state.update_data(k_file=m.video.file_id)
    await m.answer("💰 *Kino narxini coin da kiriting:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_file, F.text)
async def set_k_file_link(m: Message, state: FSMContext):
    if m.text == "/skip":
        await state.update_data(k_file=None)
    elif m.text.startswith('http://') or m.text.startswith('https://'):
        await state.update_data(k_file=m.text)
    else:
        return await m.answer("⚠️ To'g'ri link kiriting yoki video fayl yuboring!")
    await m.answer("💰 *Kino narxini coin da kiriting:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def save_kino(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    data = await state.get_data()
    new_id = await add_movie(data['k_name'], data['k_year'], data.get('k_desc', ''), data.get('k_file'), int(m.text))
    await state.clear()
    await m.answer(
        f"✅ *Kino qo'shildi!*\n\n🆔 Kod: `{new_id}`\n🎬 {data['k_name']}\n📅 {data['k_year']}\n💰 {m.text} coin",
        parse_mode="Markdown", reply_markup=get_admin_kb()
    )

# ================= KINO O'CHIRISH =================
@dp.callback_query(F.data == "adm_del_kino")
async def del_kino_start(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    movies = await get_all_movies()
    if not movies:
        return await c.message.answer("📽 Kinolar yo'q!")
    kb = InlineKeyboardBuilder()
    for movie in movies:
        kb.button(text=f"🗑 {movie['name']} ({movie['id']})", callback_data=f"del_movie_{movie['id']}")
    kb.button(text="❌ Bekor qilish", callback_data="adm_close")
    kb.adjust(1)
    await c.message.edit_text("🗑 *O'chirmoqchi bo'lgan kinoni tanlang:*", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("del_movie_"))
async def delete_movie(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    movie_id = int(c.data.split("_")[2])
    async with db_pool.acquire() as conn:
        movie = await conn.fetchrow("SELECT name FROM movies WHERE id=$1", movie_id)
        await conn.execute("DELETE FROM movies WHERE id=$1", movie_id)
    await c.message.edit_text(f"✅ *{movie['name']}* o'chirildi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ================= REKLAMA =================
@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("📢 *Yubormoqchi bo'lgan xabarni yuboring:*", parse_mode="Markdown")
    await state.set_state(BotState.sending_broadcast)

@dp.message(BotState.sending_broadcast)
async def process_broadcast(m: Message, state: FSMContext):
    await state.clear()
    users = await get_all_users()
    count, failed = 0, 0
    status_msg = await m.answer(f"⏳ Yuborilmoqda... 0/{len(users)}")
    for i, user in enumerate(users):
        try:
            await m.copy_to(chat_id=user['user_id'])
            count += 1
            await asyncio.sleep(0.05)
            if i % 20 == 0:
                try:
                    await status_msg.edit_text(f"⏳ Yuborilmoqda... {i}/{len(users)}")
                except:
                    pass
        except:
            failed += 1
    await status_msg.edit_text(f"✅ *Reklama yuborildi!*\n\n📨 Muvaffaqiyatli: *{count}*\n❌ Yuborilmagan: *{failed}*", parse_mode="Markdown")

# ================= BLOKLASH =================
@dp.callback_query(F.data == "adm_ban")
async def ban_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("🚫 Bloklash uchun foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.blocking_id)

@dp.message(BotState.blocking_id)
async def process_ban(m: Message, state: FSMContext):
    await state.clear()
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID kiriting!")
    uid = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=TRUE WHERE user_id=$1", uid)
    try:
        await bot.send_message(uid, "🚫 Siz botdan bloklangansiz.", reply_markup=ReplyKeyboardRemove())
    except:
        pass
    await m.answer(f"✅ Foydalanuvchi (ID: `{uid}`) bloklandi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ================= BLOKDAN CHIQARISH =================
@dp.callback_query(F.data == "adm_unban")
async def unban_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("✅ Blokdan chiqarish uchun foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.unblocking_id)

@dp.message(BotState.unblocking_id)
async def process_unban(m: Message, state: FSMContext):
    await state.clear()
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID kiriting!")
    uid = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=FALSE WHERE user_id=$1", uid)
    try:
        await bot.send_message(uid, "✅ Blokingiz olib tashlandi! /start")
    except:
        pass
    await m.answer(f"✅ Foydalanuvchi (ID: `{uid}`) blokdan chiqarildi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ================= ADMIN CHAT =================
@dp.callback_query(F.data == "adm_start_chat")
async def admin_chat_init(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await state.set_state(BotState.admin_chat_target)
    await c.message.answer(
        "💬 *Gaplashmoqchi bo'lgan foydalanuvchi ID sini kiriting:*\n\n"
        "_(Foydalanuvchi 'Hisobim' bo'limida ID sini ko'rishi mumkin)_",
        parse_mode="Markdown"
    )

@dp.message(BotState.admin_chat_target)
async def admin_ask_user(m: Message, state: FSMContext):
    if not m.text or not m.text.strip().isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    target_id = int(m.text.strip())
    if target_id == ADMIN_ID:
        return await m.answer("⚠️ O'zingizga xabar yubora olmaysiz!")
    target_user = await get_user(target_id)
    if not target_user:
        await state.clear()
        return await m.answer(f"❌ ID: `{target_id}` foydalanuvchi topilmadi!", parse_mode="Markdown")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"chat_yes_{ADMIN_ID}")
    kb.button(text="❌ Yo'q, rad etaman", callback_data=f"chat_no_{ADMIN_ID}")
    kb.adjust(1)
    try:
        await bot.send_message(
            target_id,
            "🔔 <b>Admin siz bilan bog'lanmoqchi!</b>\n\nSuhbatga rozimisiz?",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
        await state.set_state(BotState.in_active_chat)
        await state.update_data(chat_with=target_id, is_user_side=False)
        await m.answer(
            f"✅ So'rov yuborildi!\n\n👤 *{target_user['name']}* | ID: `{target_id}`\n\n⏳ Javob kutilmoqda...\nBekor qilish: /stop",
            parse_mode="Markdown", reply_markup=get_admin_end_chat_kb()
        )
    except Exception as e:
        await state.clear()
        await m.answer(f"❌ Xabar yuborib bo'lmadi: {e}")

@dp.callback_query(F.data.startswith("chat_yes_"))
async def chat_accept(c: CallbackQuery, state: FSMContext):
    await c.answer("✅ Suhbat boshlandi!")
    admin_id = int(c.data.split("_")[2])
    await state.set_state(BotState.in_active_chat)
    await state.update_data(chat_with=admin_id, is_user_side=True)
    # Foydalanuvchiga FAQAT /stop, tugma yo'q
    await c.message.edit_text("✅ <b>Aloqa o'rnatildi!</b>\n\n💬 Xabaringizni yozing.\nTugatish: /stop", parse_mode="HTML")
    try:
        await bot.send_message(
            admin_id,
            f"✅ *Foydalanuvchi ({c.from_user.id}) suhbatga kirdi!*\nXabar yubora olasiz.\nTugatish: /stop",
            parse_mode="Markdown", reply_markup=get_admin_end_chat_kb()
        )
    except:
        pass

@dp.callback_query(F.data.startswith("chat_no_"))
async def chat_reject(c: CallbackQuery):
    await c.answer("❌ Rad etildi")
    admin_id = int(c.data.split("_")[2])
    await c.message.edit_text("❌ Siz suhbatni rad etdingiz.")
    try:
        await bot.send_message(admin_id, f"😔 Foydalanuvchi ({c.from_user.id}) suhbatlashishni istamadi.", reply_markup=get_admin_kb())
    except:
        pass

@dp.callback_query(F.data == "end_chat")
async def end_chat_callback(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Bu tugma faqat admin uchun!", show_alert=True)
    await c.answer()
    data = await state.get_data()
    partner = data.get("chat_with")
    await state.clear()
    try:
        await c.message.edit_text("🔴 *Aloqa tugadi.*", parse_mode="Markdown")
    except:
        pass
    await bot.send_message(c.from_user.id, "📴 Suhbat yakunlandi.", reply_markup=get_admin_kb())
    if partner:
        try:
            await bot.send_message(partner, "📴 Admin suhbatni tugatdi.", reply_markup=get_main_kb(partner))
        except:
            pass

# ================= GLOBAL HANDLER =================
@dp.message()
async def global_message_handler(m: Message, state: FSMContext):
    user = await get_user(m.from_user.id)
    if user and user['is_banned']:
        await m.answer("🚫 Siz botdan bloklangansiz.")

# ================= BOTNI ISHGA TUSHIRISH =================
async def main():
    keep_alive()
    await init_db()
    logger.info("🚀 Bot ishga tushmoqda...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
