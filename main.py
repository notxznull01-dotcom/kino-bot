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

# ================= FLASK (RENDER UCHUN) =================
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

# ================= POSTGRESQL BAZA =================
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
    logger.info("✅ Baza tayyor!")

# ================= BAZA YORDAMCHI FUNKSIYALAR =================
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
            await conn.execute(
                "UPDATE users SET coins = coins + 50 WHERE user_id=$1", referrer_id
            )

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
        row = await conn.fetchrow(
            "SELECT id FROM purchases WHERE user_id=$1 AND movie_id=$2",
            user_id, movie_id
        )
        return row is not None

async def buy_movie(user_id: int, movie_id: int, price: int):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT coins FROM users WHERE user_id=$1", user_id)
        if not user or user['coins'] < price:
            return False
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id=$2", price, user_id)
        await conn.execute(
            "INSERT INTO purchases (user_id, movie_id) VALUES ($1, $2)", user_id, movie_id
        )
        return True

async def get_stats():
    async with db_pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        banned_users = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned=TRUE")
        total_movies = await conn.fetchval("SELECT COUNT(*) FROM movies")
        total_purchases = await conn.fetchval("SELECT COUNT(*) FROM purchases")
        today_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE joined_at=CURRENT_DATE"
        )
        return {
            "total_users": total_users,
            "banned_users": banned_users,
            "total_movies": total_movies,
            "total_purchases": total_purchases,
            "today_users": today_users
        }

# ================= MAJBURIY OBUNA FUNKSIYALAR =================
async def get_required_channels():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM required_channels ORDER BY id")

async def add_required_channel(link: str, title: str = "Kanal"):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO required_channels (link, title) VALUES ($1, $2)",
            link, title
        )

async def remove_required_channel(channel_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM required_channels WHERE id=$1", channel_id)

async def get_unsubscribed_channels(user_id: int) -> list:
    """
    Foydalanuvchi obuna bo'lmagan kanallar ro'yxatini qaytaradi.
    Faqat Telegram @username kanallarini bot API orqali tekshiradi.
    Boshqa platformalar (Instagram va h.k.) — har doim ko'rsatiladi.
    """
    channels = await get_required_channels()
    unsubscribed = []
    for channel in channels:
        link = channel['link']
        is_subscribed = False

        if 't.me/' in link or 'telegram.me/' in link:
            if 't.me/' in link:
                username = link.split('t.me/')[-1].strip().strip('/')
            else:
                username = link.split('telegram.me/')[-1].strip().strip('/')

            # Faqat oddiy @username formatini tekshiramiz
            if username and not username.startswith('+') and '/' not in username:
                try:
                    member = await bot.get_chat_member(f"@{username}", user_id)
                    if member.status not in ['left', 'kicked', 'banned']:
                        is_subscribed = True
                except Exception as e:
                    logger.warning(f"Kanal tekshirishda xato (@{username}): {e}")
                    is_subscribed = False
            else:
                # Invite link — tekshirib bo'lmaydi
                is_subscribed = False
        else:
            # Instagram, YouTube va boshqalar
            is_subscribed = False

        if not is_subscribed:
            unsubscribed.append(channel)

    return unsubscribed

def build_subscription_keyboard(channels: list):
    kb = InlineKeyboardBuilder()
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, ch in enumerate(channels):
        emoji = emojis[i % len(emojis)]
        kb.button(text=f"{emoji} {ch['title']} — A'zo bo'lish", url=ch['link'])
    kb.button(text="✅ Obunani Tekshirish", callback_data="check_subscription")
    kb.adjust(1)
    return kb.as_markup()

async def send_subscription_message(user_id: int):
    try:
        all_channels = await get_required_channels()
        if not all_channels:
            return
        unsubscribed = await get_unsubscribed_channels(user_id)
        channels_to_show = unsubscribed if unsubscribed else all_channels

        lines = ""
        for i, ch in enumerate(channels_to_show, 1):
            lines += f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n"

        text = (
            "⚠️ <b>Botdan foydalanish uchun\n"
            "quyidagi kanal/sahifalarga a'zo bo'ling:</b>\n\n"
            f"{lines}\n"
            "A'zo bo'lgach, <b>✅ Obunani Tekshirish</b> tugmasini bosing."
        )
        await bot.send_message(
            user_id,
            text,
            reply_markup=build_subscription_keyboard(channels_to_show),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning(f"send_subscription_message xato (user {user_id}): {e}")

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
    users_page = State()

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
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(2)
    return builder.as_markup()

def get_end_chat_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Aloqani Tugatish", callback_data="end_chat")
    return builder.as_markup()

# ================= OBUNA TEKSHIRISH MIDDLEWARE =================
async def subscription_check_middleware(m: Message) -> bool:
    user = await get_user(m.from_user.id)
    if not user:
        return True
    if user['is_banned']:
        return True
    unsubscribed = await get_unsubscribed_channels(m.from_user.id)
    if unsubscribed:
        await send_subscription_message(m.from_user.id)
        return False
    return True

# ================= START KOMANDASI =================
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
            referrer_id = None

    if user:
        if user['is_banned']:
            return await m.answer("🚫 Siz botdan bloklangansiz.")
        unsubscribed = await get_unsubscribed_channels(m.from_user.id)
        if unsubscribed:
            return await send_subscription_message(m.from_user.id)
        await m.answer(
            f"🌟 *Xush kelibsiz qaytib, {user['name']}!*\n\n"
            f"💰 Balansingiz: *{user['coins']} coin*",
            reply_markup=get_main_kb(m.from_user.id),
            parse_mode="Markdown"
        )
    else:
        await state.update_data(referrer_id=referrer_id)
        await m.answer(
            "👋 *Assalomu alaykum! Kino Botga xush kelibsiz!*\n\n"
            "Ro'yxatdan o'tish uchun *ismingizni* kiriting:",
            parse_mode="Markdown"
        )
        await state.set_state(BotState.waiting_name)

# =====================================================================
# ASOSIY TUZATISH: c.answer() BIRINCHI chaqiriladi (Telegram 10s timeout
# muammosini hal qiladi), keyin kanal tekshiruvi bajariladi.
# =====================================================================
@dp.callback_query(F.data == "check_subscription")
async def check_sub_callback(c: CallbackQuery):
    # 1-qadam: AVVAL callback'ni yopamiz — Telegram timeout bo'lmaydi
    await c.answer("⏳ Tekshirilmoqda...", show_alert=False)

    user = await get_user(c.from_user.id)
    if not user:
        await c.message.answer("❌ Avval ro'yxatdan o'ting! /start")
        return
    if user['is_banned']:
        await c.message.answer("🚫 Siz botdan bloklangansiz.")
        return

    # 2-qadam: Kanallarni tekshiramiz
    unsubscribed = await get_unsubscribed_channels(c.from_user.id)

    if not unsubscribed:
        # ✅ Barcha kanallarga obuna bo'lgan
        try:
            await c.message.edit_text(
                "✅ <b>Barcha kanal/sahifalarga a'zo bo'ldingiz!</b>\n\n"
                "Endi botdan to'liq foydalanishingiz mumkin!",
                parse_mode="HTML"
            )
        except Exception:
            pass
        await bot.send_message(
            c.from_user.id,
            f"🎉 <b>Xush kelibsiz, {user['name']}!</b>\n\n"
            f"💰 Balansingiz: <b>{user['coins']} coin</b>",
            reply_markup=get_main_kb(c.from_user.id),
            parse_mode="HTML"
        )
    else:
        # ❌ Hali obuna bo'lmagan kanallar bor
        lines = ""
        for i, ch in enumerate(unsubscribed, 1):
            lines += f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n"

        text = (
            f"❌ <b>Hali {len(unsubscribed)} ta kanal/sahifaga a'zo bo'lmadingiz:</b>\n\n"
            f"{lines}\n"
            f"A'zo bo'lib, <b>✅ Obunani Tekshirish</b> tugmasini qayta bosing."
        )
        try:
            await c.message.edit_text(
                text,
                reply_markup=build_subscription_keyboard(unsubscribed),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            await bot.send_message(
                c.from_user.id,
                text,
                reply_markup=build_subscription_keyboard(unsubscribed),
                parse_mode="HTML",
                disable_web_page_preview=True
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
    await m.answer(
        "📱 Telefon raqamingizni yuboring yoki o'tkazib yuboring:",
        reply_markup=kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(BotState.waiting_phone)

async def finish_registration(m: Message, state: FSMContext, name: str, phone: str = None):
    data = await state.get_data()
    await create_user(m.from_user.id, name, phone, data.get('referrer_id'))
    await state.clear()

    channels = await get_required_channels()
    if channels:
        await m.answer(
            f"✅ *Tabriklaymiz, {name}!*\n\n"
            "🎉 Ro'yxatdan o'tdingiz!\n"
            "💰 Sizga *100 coin* sovg'a qilindi!\n\n"
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        await send_subscription_message(m.from_user.id)
    else:
        await m.answer(
            f"✅ *Tabriklaymiz, {name}!*\n\n"
            "🎉 Ro'yxatdan o'tdingiz!\n"
            "💰 Sizga *100 coin* sovg'a qilindi!\n\n"
            "🎬 Endi kinolardan bahramand bo'ling!",
            reply_markup=get_main_kb(m.from_user.id),
            parse_mode="Markdown"
        )

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone_contact(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_registration(m, state, data['name'], m.contact.phone_number)

@dp.message(BotState.waiting_phone, F.text == "⏭ O'tkazib yuborish")
async def reg_skip_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_registration(m, state, data['name'], None)

# ================= KINOLAR RO'YXATI =================
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def show_movies(m: Message):
    if not await subscription_check_middleware(m):
        return
    movies = await get_all_movies()
    if not movies:
        return await m.answer("📽 Hozircha bazada kinolar mavjud emas.")
    text = "🔥 *KINOLAR RO'YXATI* 🔥\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    for movie in movies:
        text += f"🎬 *{movie['name']}*\n"
        text += f"📅 Yil: {movie['year']}\n"
        text += f"💎 Narx: *{movie['price']} coin*\n"
        text += f"🆔 Kod: `{movie['id']}`\n"
        text += "────────────────────\n"
    text += "\n🍿 *Sotib olish uchun: 🎟 Kino Sotib Olish tugmasini bosing!*"
    await m.answer(text, parse_mode="Markdown")

# ================= KINO SOTIB OLISH =================
@dp.message(F.text == "🎟 Kino Sotib Olish")
async def buy_movie_start(m: Message, state: FSMContext):
    if not await subscription_check_middleware(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    await m.answer(
        f"💰 Balansingiz: *{user['coins']} coin*\n\n"
        "🎬 Sotib olmoqchi bo'lgan *kino kodini* yuboring:",
        parse_mode="Markdown"
    )
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
        await m.answer(
            f"✅ Siz *{movie['name']}* kinoni allaqachon sotib olgansiz!\n\n"
            "🎬 Quyidagi tugmadan tomosha qiling:",
            parse_mode="Markdown"
        )
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
            f"❌ *Coinlar yetarli emas!*\n\n"
            f"💎 Kino narxi: {movie['price']} coin\n"
            f"💰 Sizda: {user['coins']} coin\n\n"
            f"🎁 Kunlik bonus va do'st taklif qilib coin yig'ing!",
            parse_mode="Markdown"
        )
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Ha, {movie['price']} coin to'layman", callback_data=f"confirm_buy_{movie['id']}")
    kb.button(text="❌ Bekor qilish", callback_data="cancel_buy")
    kb.adjust(1)
    await m.answer(
        f"🎬 *{movie['name']}* ({movie['year']})\n\n"
        f"📝 {movie['description'] or 'Tavsif mavjud emas'}\n\n"
        f"💎 Narx: *{movie['price']} coin*\n"
        f"💰 Sizda: *{user['coins']} coin*\n\n"
        "Sotib olishni tasdiqlaysizmi?",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await state.clear()

@dp.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_purchase(c: CallbackQuery):
    await c.answer()
    movie_id = int(c.data.split("_")[2])
    movie = await get_movie(movie_id)
    success = await buy_movie(c.from_user.id, movie_id, movie['price'])
    if success:
        await c.message.edit_text(
            f"✅ *Tabriklaymiz!*\n\n"
            f"🎬 *{movie['name']}* kinosi muvaffaqiyatli sotib olindi!\n\nKino yuborilmoqda...",
            parse_mode="Markdown"
        )
        if movie['file_id']:
            if movie['file_id'].startswith('http'):
                kb = InlineKeyboardBuilder()
                kb.button(text="🎬 Kinoni Tomosha Qilish", url=movie['file_id'])
                await bot.send_message(
                    c.from_user.id,
                    f"🎬 *{movie['name']}* ({movie['year']})\n\n✅ Kino tayyor! Quyidagi tugmani bosib tomosha qiling:",
                    reply_markup=kb.as_markup(),
                    parse_mode="Markdown"
                )
            else:
                await bot.send_video(
                    c.from_user.id,
                    movie['file_id'],
                    caption=f"🎬 *{movie['name']}* ({movie['year']})\n\nTomosha qiling!",
                    parse_mode="Markdown"
                )
        else:
            await c.message.answer("⚠️ Kino fayli hali qo'shilmagan. Admin tez orada qo'shadi!")
    else:
        await c.message.edit_text("❌ Xatolik yuz berdi. Qayta urinib ko'ring!")

@dp.callback_query(F.data == "cancel_buy")
async def cancel_purchase(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("❌ Sotib olish bekor qilindi.")

# ================= HISOBIM =================
@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    if not await subscription_check_middleware(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    async with db_pool.acquire() as conn:
        purchases_count = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE user_id=$1", m.from_user.id)
        referrals_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id)
    await m.answer(
        f"👤 *Shaxsiy Kabinet*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Ism: *{user['name']}*\n"
        f"📱 Tel: {user['phone'] or 'Kiritilmagan'}\n"
        f"💰 Balans: *{user['coins']} coin*\n"
        f"🎬 Sotib olingan kinolar: *{purchases_count}* ta\n"
        f"👥 Taklif qilingan do'stlar: *{referrals_count}* ta\n"
        f"📅 Ro'yxatdan o'tgan: *{user['joined_at']}*\n\n"
        f"🔑 ID: `{m.from_user.id}`",
        parse_mode="Markdown"
    )

# ================= KUNLIK BONUS =================
@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_bonus(m: Message):
    if not await subscription_check_middleware(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    today = date.today()
    last_bonus = user['last_bonus']
    if last_bonus and last_bonus >= today:
        await m.answer(
            "⏳ *Siz bugun allaqachon bonus oldingiz!*\n\n"
            "🔄 Ertaga qaytib keling — yangi bonus kutib turibdi!",
            parse_mode="Markdown"
        )
    else:
        bonus = 20
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET coins = coins + $1, last_bonus = CURRENT_DATE WHERE user_id=$2",
                bonus, m.from_user.id
            )
        updated_user = await get_user(m.from_user.id)
        await m.answer(
            f"🎉 *Kunlik Bonus!*\n\n"
            f"✅ Sizga *+{bonus} coin* qo'shildi!\n"
            f"💰 Yangi balans: *{updated_user['coins']} coin*\n\n"
            f"🔄 Ertaga yana keling!",
            parse_mode="Markdown"
        )

# ================= DO'ST TAKLIF QILISH =================
@dp.message(F.text == "👥 Do'st Taklif Qilish")
async def referral(m: Message):
    if not await subscription_check_middleware(m):
        return
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{m.from_user.id}"
    async with db_pool.acquire() as conn:
        referrals_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id)
    await m.answer(
        f"👥 *Do'stlarni Taklif Qilish*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Sizning referal havolangiz:\n"
        f"`{ref_link}`\n\n"
        f"💰 Har bir do'st uchun: *+50 coin*\n"
        f"👤 Jami taklif qilganlar: *{referrals_count}* ta\n\n"
        f"📤 Havolani do'stlaringizga yuboring!",
        parse_mode="Markdown"
    )

# ================= ADMINGA YOZISH =================
@dp.message(F.text == "✍️ Adminga Yozish")
async def write_to_admin(m: Message, state: FSMContext):
    if not await subscription_check_middleware(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")
    await m.answer(
        "✍️ *Adminga xabar yozing:*\n\n"
        "Xabaringizni yuboring, admin tez orada javob beradi!\n\n"
        "Suhbatni tugatish uchun /stop yozing.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(BotState.in_active_chat)
    await state.update_data(chat_with=ADMIN_ID, is_user_side=True)
    try:
        await bot.send_message(
            ADMIN_ID,
            f"📩 *Foydalanuvchi xabar yozmoqda!*\n\n"
            f"👤 Ism: *{user['name']}*\n"
            f"🔑 ID: `{m.from_user.id}`\n\n"
            f"Javob berish uchun Admin Paneldan 'Foydalanuvchi bilan Gaplash' tugmasini bosing.",
            parse_mode="Markdown"
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
                    await bot.send_message(partner, "📴 Admin suhbatni tugatdi. Aloqa uzildi.", reply_markup=get_main_kb(partner))
            except:
                pass
        return

    data = await state.get_data()
    partner = data.get("chat_with")
    is_user_side = data.get("is_user_side", True)
    user = await get_user(m.from_user.id)
    name = user['name'] if user else m.from_user.full_name

    if not partner:
        return

    prefix = f"📩 *Foydalanuvchi:* {name} (ID: `{m.from_user.id}`)\n\n" if is_user_side else "👑 *Admin javobi:*\n\n"

    try:
        if m.text:
            await bot.send_message(partner, f"{prefix}{m.text}", parse_mode="Markdown")
        elif m.photo:
            await bot.send_photo(partner, m.photo[-1].file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        elif m.video:
            await bot.send_video(partner, m.video.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        elif m.document:
            await bot.send_document(partner, m.document.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        await m.answer("✅ Xabar yuborildi! Tugatish: /stop")
    except Exception as e:
        await m.answer(f"❌ Xabar yuborilmadi: {e}")

# ================= STATISTIKA =================
@dp.message(F.text == "📊 Statistika")
async def show_stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    stats = await get_stats()
    await m.answer(
        f"📊 *BOT STATISTIKASI*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['total_users']}*\n"
        f"🆕 Bugun qo'shilganlar: *{stats['today_users']}*\n"
        f"🚫 Bloklangan: *{stats['banned_users']}*\n"
        f"🎬 Jami kinolar: *{stats['total_movies']}*\n"
        f"🛒 Jami sotuvlar: *{stats['total_purchases']}*",
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
        await m.answer("👑 *Xush kelibsiz, Admin!*\n\nBoshqaruv paneli:", reply_markup=get_admin_kb(), parse_mode="Markdown")
    else:
        await m.answer("❌ Parol noto'g'ri!")
        await state.clear()

@dp.callback_query(F.data == "adm_close")
async def close_admin(c: CallbackQuery):
    await c.answer()
    await c.message.delete()

@dp.callback_query(F.data == "adm_full_stats")
async def full_stats(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    stats = await get_stats()
    await c.message.edit_text(
        f"📊 *TO'LIQ STATISTIKA*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['total_users']}*\n"
        f"🆕 Bugun qo'shilganlar: *{stats['today_users']}*\n"
        f"🚫 Bloklangan: *{stats['banned_users']}*\n"
        f"🎬 Jami kinolar: *{stats['total_movies']}*\n"
        f"🛒 Jami sotuvlar: *{stats['total_purchases']}*",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )

# ================= FOYDALANUVCHILAR RO'YXATI (ADMIN) =================
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
        await c.message.answer("📭 Hali foydalanuvchilar yo'q!")
        return
    text = "👥 *FOYDALANUVCHILAR RO'YXATI*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(users, 1):
        status = "🚫" if u['is_banned'] else "✅"
        text += f"{i}. {status} *{u['name']}*\n"
        text += f"   🔑 ID: `{u['user_id']}`\n"
        text += f"   📱 Tel: {u['phone'] or 'Kiritilmagan'}\n"
        text += f"   💰 Coin: {u['coins']}\n"
        text += f"   📅 Sana: {u['joined_at']}\n"
        text += "   ──────────────\n"
    text += f"\n📊 Ko'rsatildi: *{len(users)}* ta (oxirgi 50)"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    kb.adjust(1)
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except Exception:
        await c.message.edit_text(
            f"👥 *FOYDALANUVCHILAR RO'YXATI*\n\nJami: *{len(users)}* ta\n_(Ro'yxat alohida xabarda)_",
            reply_markup=kb.as_markup(), parse_mode="Markdown"
        )
        chunk = ""
        for i, u in enumerate(users, 1):
            status = "🚫" if u['is_banned'] else "✅"
            line = f"{i}. {status} *{u['name']}* | ID: `{u['user_id']}` | {u['coins']} coin\n"
            if len(chunk) + len(line) > 3800:
                await bot.send_message(c.from_user.id, chunk, parse_mode="Markdown")
                chunk = line
            else:
                chunk += line
        if chunk:
            await bot.send_message(c.from_user.id, chunk, parse_mode="Markdown")

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
    text = "🔔 *Majburiy Obuna Sozlamalari*\n━━━━━━━━━━━━━━━━━━\n\n"
    if channels:
        text += "📋 *Hozirgi kanallar:*\n"
        for ch in channels:
            text += f"• [{ch['title']}]({ch['link']})\n"
    else:
        text += "📭 Hozircha kanallar qo'shilmagan.\n"
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
        "Misol:\n"
        "• `https://t.me/kanalnom`\n"
        "• `https://instagram.com/akkountnom`",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.adding_sub_link)

@dp.message(BotState.adding_sub_link)
async def sub_get_link(m: Message, state: FSMContext):
    link = m.text.strip()
    if not (link.startswith('http://') or link.startswith('https://')):
        return await m.answer("⚠️ Link http:// yoki https:// bilan boshlanishi kerak!\n\nQaytadan kiriting:")
    await state.update_data(sub_link=link)
    await m.answer(
        "📝 *Kanal/akkount nomini kiriting:*\n\n(Masalan: Kino Kanal, Instagram Sahifamiz)",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.adding_sub_title)

@dp.message(BotState.adding_sub_title)
async def sub_get_title(m: Message, state: FSMContext):
    try:
        data = await state.get_data()
        link = data.get('sub_link', '')
        title = m.text.strip()
        await add_required_channel(link, title)
        await state.clear()
        await m.answer(
            f"✅ <b>Kanal/akkount muvaffaqiyatli qo'shildi!</b>\n\n"
            f"📛 Nomi: <b>{title}</b>\n"
            f"🔗 Link: <code>{link}</code>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        asyncio.create_task(broadcast_subscription_to_all(m.from_user.id))
    except Exception as e:
        logger.error(f"sub_get_title xato: {e}")
        await state.clear()
        await m.answer(f"❌ Xatolik yuz berdi: {e}")

async def broadcast_subscription_to_all(admin_id: int):
    try:
        all_users = await get_all_users()
        sent = 0
        failed = 0
        for u in all_users:
            if u['user_id'] == admin_id:
                continue
            try:
                await send_subscription_message(u['user_id'])
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                failed += 1
                logger.warning(f"Broadcast xato (user {u['user_id']}): {e}")
        await bot.send_message(
            admin_id,
            f"📢 *Obuna xabari yuborildi!*\n\n"
            f"✅ Muvaffaqiyatli: *{sent}* ta\n"
            f"❌ Yuborilmadi: *{failed}* ta",
            parse_mode="Markdown",
            reply_markup=get_admin_kb()
        )
    except Exception as e:
        logger.error(f"broadcast_subscription_to_all xato: {e}")

@dp.callback_query(F.data == "sub_del_list")
async def sub_del_list(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    channels = await get_required_channels()
    if not channels:
        await c.message.answer("📭 Kanallar yo'q!")
        return
    kb = InlineKeyboardBuilder()
    for ch in channels:
        kb.button(text=f"🗑 {ch['title']}", callback_data=f"sub_del_{ch['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_subscription")
    kb.adjust(1)
    await c.message.edit_text("🗑 *O'chirmoqchi bo'lgan kanalni tanlang:*", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("sub_del_"))
async def sub_del_confirm(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        await c.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    channel_id = int(c.data.split("_")[2])
    async with db_pool.acquire() as conn:
        ch = await conn.fetchrow("SELECT title FROM required_channels WHERE id=$1", channel_id)
    await remove_required_channel(channel_id)
    ch_name = ch['title'] if ch else "Kanal"
    await c.answer(f"✅ '{ch_name}' o'chirildi!", show_alert=True)
    channels = await get_required_channels()
    kb = InlineKeyboardBuilder()
    if channels:
        for ch2 in channels:
            kb.button(text=f"🗑 {ch2['title']}", callback_data=f"sub_del_{ch2['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_subscription")
    kb.adjust(1)
    text = "🗑 *O'chirmoqchi bo'lgan kanalni tanlang:*" if channels else "📭 *Barcha kanallar o'chirildi.*"
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

# ================= COIN QO'SHISH =================
@dp.callback_query(F.data == "adm_add_coin")
async def add_coin_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💰 *Coin qo'shish*\n\nFoydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.add_coin_id)

@dp.message(BotState.add_coin_id)
async def add_coin_get_id(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    user_id = int(m.text)
    user = await get_user(user_id)
    if not user:
        await state.clear()
        return await m.answer("❌ Bunday foydalanuvchi topilmadi!")
    await state.update_data(target_user_id=user_id)
    await m.answer(
        f"👤 *Foydalanuvchi:* {user['name']}\n"
        f"💰 *Joriy balans:* {user['coins']} coin\n\nQancha coin qo'shmoqchisiz?",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.add_coin_amount)

@dp.message(BotState.add_coin_amount)
async def add_coin_process(m: Message, state: FSMContext):
    if not m.text.isdigit() or int(m.text) <= 0:
        return await m.answer("⚠️ Faqat musbat son kiriting!")
    data = await state.get_data()
    user_id = data['target_user_id']
    amount = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins + $1 WHERE user_id=$2", amount, user_id)
    updated_user = await get_user(user_id)
    await state.clear()
    await m.answer(
        f"✅ *Coin muvaffaqiyatli qo'shildi!*\n\n"
        f"👤 Foydalanuvchi ID: `{user_id}`\n"
        f"➕ Qo'shildi: *+{amount} coin*\n"
        f"💰 Yangi balans: *{updated_user['coins']} coin*",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )
    try:
        await bot.send_message(user_id, f"🎉 *Tabriklaymiz!*\n\nSizga *+{amount} coin* qo'shildi!\n💰 Yangi balans: *{updated_user['coins']} coin*", parse_mode="Markdown")
    except:
        pass

# ================= COIN OLISH =================
@dp.callback_query(F.data == "adm_remove_coin")
async def remove_coin_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💸 *Coin olish*\n\nFoydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.remove_coin_id)

@dp.message(BotState.remove_coin_id)
async def remove_coin_get_id(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    user_id = int(m.text)
    user = await get_user(user_id)
    if not user:
        await state.clear()
        return await m.answer("❌ Bunday foydalanuvchi topilmadi!")
    await state.update_data(target_user_id=user_id)
    await m.answer(
        f"👤 *Foydalanuvchi:* {user['name']}\n"
        f"💰 *Joriy balans:* {user['coins']} coin\n\nQancha coin olmoqchisiz?",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.remove_coin_amount)

@dp.message(BotState.remove_coin_amount)
async def remove_coin_process(m: Message, state: FSMContext):
    if not m.text.isdigit() or int(m.text) <= 0:
        return await m.answer("⚠️ Faqat musbat son kiriting!")
    data = await state.get_data()
    user_id = data['target_user_id']
    amount = int(m.text)
    user = await get_user(user_id)
    if user['coins'] < amount:
        await state.clear()
        return await m.answer(
            f"⚠️ *Foydalanuvchida coin yetarli emas!*\n\n"
            f"💰 Foydalanuvchi balansi: {user['coins']} coin\n"
            f"💸 Olmoqchi bo'lgan: {amount} coin",
            parse_mode="Markdown",
            reply_markup=get_admin_kb()
        )
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id=$2", amount, user_id)
    updated_user = await get_user(user_id)
    await state.clear()
    await m.answer(
        f"✅ *Coin muvaffaqiyatli olindi!*\n\n"
        f"👤 Foydalanuvchi ID: `{user_id}`\n"
        f"➖ Olindi: *-{amount} coin*\n"
        f"💰 Yangi balans: *{updated_user['coins']} coin*",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )
    try:
        await bot.send_message(user_id, f"⚠️ *E'tibor!*\n\nSizdan *-{amount} coin* yechildi!\n💰 Yangi balans: *{updated_user['coins']} coin*", parse_mode="Markdown")
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
    await m.answer("📅 *Kino yilini kiriting:* (masalan: 2024)", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_year)

@dp.message(BotState.adding_k_year)
async def set_k_year(m: Message, state: FSMContext):
    await state.update_data(k_year=m.text)
    await m.answer("📝 *Kino haqida qisqacha tavsif yozing:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_desc)

@dp.message(BotState.adding_k_desc)
async def set_k_desc(m: Message, state: FSMContext):
    await state.update_data(k_desc=m.text)
    await m.answer(
        "🔗 *Kino linkini yoki video faylini yuboring:*\n\n"
        "📎 Link yoki video fayl yuborishingiz mumkin\n"
        "⏭ Yo'q bo'lsa /skip yozing",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.adding_k_file)

@dp.message(BotState.adding_k_file, F.video)
async def set_k_file_video(m: Message, state: FSMContext):
    await state.update_data(k_file=m.video.file_id)
    await m.answer("💰 *Kino narxini coin da kiriting:* (masalan: 50)", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_file, F.text)
async def set_k_file_link(m: Message, state: FSMContext):
    if m.text == "/skip":
        await state.update_data(k_file=None)
    elif m.text.startswith('http://') or m.text.startswith('https://'):
        await state.update_data(k_file=m.text)
    else:
        return await m.answer("⚠️ To'g'ri link kiriting (http:// bilan) yoki video fayl yuboring!")
    await m.answer("💰 *Kino narxini coin da kiriting:* (masalan: 50)", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def save_kino(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    data = await state.get_data()
    new_id = await add_movie(data['k_name'], data['k_year'], data.get('k_desc', ''), data.get('k_file'), int(m.text))
    await state.clear()
    file_type = "Link" if data.get('k_file') and str(data.get('k_file')).startswith('http') else "Video fayl"
    await m.answer(
        f"✅ *Kino muvaffaqiyatli qo'shildi!*\n\n"
        f"🆔 Kodi: `{new_id}`\n"
        f"🎬 Nomi: {data['k_name']}\n"
        f"📅 Yil: {data['k_year']}\n"
        f"📎 Turi: {file_type}\n"
        f"💰 Narx: {m.text} coin",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )

# ================= KINO O'CHIRISH =================
@dp.callback_query(F.data == "adm_del_kino")
async def del_kino_start(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    movies = await get_all_movies()
    if not movies:
        await c.message.answer("📽 Kinolar yo'q!")
        return
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
    await c.message.edit_text(f"✅ *{movie['name']}* kinosi o'chirildi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ================= REKLAMA YUBORISH =================
@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("📢 *Barcha foydalanuvchilarga yuboriladigan xabarni yuboring:*\n(Matn, rasm, video bo'lishi mumkin)", parse_mode="Markdown")
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
    await status_msg.edit_text(
        f"✅ *Reklama yuborildi!*\n\n"
        f"📨 Muvaffaqiyatli: *{count}*\n"
        f"❌ Yuborilmagan: *{failed}*",
        parse_mode="Markdown"
    )

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
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
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
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    uid = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=FALSE WHERE user_id=$1", uid)
    try:
        await bot.send_message(uid, "✅ Blokingiz olib tashlandi! /start")
    except:
        pass
    await m.answer(f"✅ Foydalanuvchi (ID: `{uid}`) blokdan chiqarildi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ================= BLOKLANGAN FOYDALANUVCHI FILTRI =================
@dp.message()
async def global_message_handler(m: Message, state: FSMContext):
    user = await get_user(m.from_user.id)
    if user and user['is_banned']:
        return await m.answer("🚫 Siz botdan bloklangansiz.")

# ================= ADMIN CHAT =================
@dp.callback_query(F.data == "adm_start_chat")
async def admin_chat_init(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💬 Gaplashmoqchi bo'lgan foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.admin_chat_target)

@dp.message(BotState.admin_chat_target)
async def admin_ask_user(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    target_id = int(m.text)
    target_user = await get_user(target_id)
    if not target_user:
        await state.clear()
        return await m.answer("❌ Bu ID da foydalanuvchi topilmadi!")

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"chat_yes_{ADMIN_ID}")
    kb.button(text="❌ Yo'q", callback_data=f"chat_no_{ADMIN_ID}")
    kb.adjust(2)

    try:
        await bot.send_message(
            target_id,
            "🔔 *Admin siz bilan bog'lanmoqchi!*\n\nSuhbatga rozimisiz?",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        await state.update_data(chat_with=target_id, is_user_side=False)
        await state.set_state(BotState.in_active_chat)
        await m.answer(
            f"⏳ So'rov yuborildi (ID: {target_id}).\n"
            f"Foydalanuvchi rozilik bildirgach, xabar yubora olasiz.\n"
            f"Tugatish uchun /stop yoki quyidagi tugmani bosing:",
            reply_markup=get_end_chat_kb()
        )
    except Exception as e:
        await m.answer(f"❌ Foydalanuvchiga xabar yuborib bo'lmadi: {e}")
        await state.clear()

@dp.callback_query(F.data.startswith("chat_yes_"))
async def chat_accept(c: CallbackQuery, state: FSMContext):
    await c.answer()
    admin_id = int(c.data.split("_")[2])
    await state.set_state(BotState.in_active_chat)
    await state.update_data(chat_with=admin_id, is_user_side=True)
    await c.message.edit_text(
        "✅ *Aloqa o'rnatildi!*\n\nXabaringizni yozing. Tugatish uchun /stop",
        parse_mode="Markdown"
    )
    await bot.send_message(
        admin_id,
        f"✅ *Foydalanuvchi ({c.from_user.id}) suhbatga kirdi!*\n\n"
        f"Xabar yubora olasiz. Tugatish: /stop yoki tugma:",
        parse_mode="Markdown",
        reply_markup=get_end_chat_kb()
    )

@dp.callback_query(F.data.startswith("chat_no_"))
async def chat_reject(c: CallbackQuery):
    await c.answer()
    admin_id = int(c.data.split("_")[2])
    await c.message.edit_text("❌ Siz suhbatni rad etdingiz.")
    try:
        await bot.send_message(admin_id, f"😔 Foydalanuvchi ({c.from_user.id}) suhbatlashishni istamadi.", reply_markup=get_admin_kb())
    except:
        pass

@dp.callback_query(F.data == "end_chat")
async def end_chat_callback(c: CallbackQuery, state: FSMContext):
    await c.answer()
    data = await state.get_data()
    partner = data.get("chat_with")
    is_user_side = data.get("is_user_side", False)
    await state.clear()
    try:
        await c.message.edit_text("🔴 *Aloqa tugadi.*", parse_mode="Markdown")
    except:
        pass
    await bot.send_message(c.from_user.id, "📴 Suhbat yakunlandi.", reply_markup=get_main_kb(c.from_user.id))
    if partner:
        try:
            if is_user_side:
                await bot.send_message(partner, f"📴 Foydalanuvchi ({c.from_user.id}) suhbatni tugatdi.", reply_markup=get_admin_kb())
            else:
                await bot.send_message(partner, "📴 Admin suhbatni tugatdi. Aloqa uzildi.", reply_markup=get_main_kb(partner))
        except:
            pass

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
