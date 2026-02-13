Import asyncio
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
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://kino_bot_db_duf5_user:MNiazQVid4iljB2dvN7LeJ8XfYFdnaJQ@dpg-d672bp8gjchc738fpdm0-a/kino_bot_db_duf5")  # Render PostgreSQL URL

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
        # Referal bonus
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
    builder.button(text="📢 Reklama Yuborish", callback_data="adm_broadcast")
    builder.button(text="🚫 Foydalanuvchi Bloklash", callback_data="adm_ban")
    builder.button(text="✅ Blokdan Chiqarish", callback_data="adm_unban")
    builder.button(text="💬 Foydalanuvchi bilan Gaplash", callback_data="adm_start_chat")
    builder.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(2)
    return builder.as_markup()

# ================= START KOMANDASI =================
@dp.message(CommandStart())
async def start_cmd(m: Message, state: FSMContext):
    await state.clear()
    user = await get_user(m.from_user.id)

    # Referal tekshirish
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

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone_contact(m: Message, state: FSMContext):
    data = await state.get_data()
    await create_user(
        m.from_user.id,
        data['name'],
        m.contact.phone_number,
        data.get('referrer_id')
    )
    await state.clear()
    await m.answer(
        f"✅ *Tabriklaymiz, {data['name']}!*\n\n"
        "🎉 Ro'yxatdan o'tdingiz!\n"
        "💰 Sizga *100 coin* sovg'a qilindi!\n\n"
        "🎬 Endi kinolardan bahramand bo'ling!",
        reply_markup=get_main_kb(m.from_user.id),
        parse_mode="Markdown"
    )

@dp.message(BotState.waiting_phone, F.text == "⏭ O'tkazib yuborish")
async def reg_skip_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    await create_user(m.from_user.id, data['name'], None, data.get('referrer_id'))
    await state.clear()
    await m.answer(
        f"✅ *Tabriklaymiz, {data['name']}!*\n\n"
        "🎉 Ro'yxatdan o'tdingiz!\n"
        "💰 Sizga *100 coin* sovg'a qilindi!",
        reply_markup=get_main_kb(m.from_user.id),
        parse_mode="Markdown"
    )

# ================= KINOLAR RO'YXATI =================
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def show_movies(m: Message):
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

    # Allaqachon sotib olinganmi?
    if await user_has_movie(m.from_user.id, movie['id']):
        await state.clear()
        await m.answer(
            f"✅ Siz *{movie['name']}* kinoni allaqachon sotib olgansiz!\n\n"
            "🎬 Quyidagi havoladan tomosha qiling:",
            parse_mode="Markdown"
        )
        if movie['file_id']:
            await bot.send_video(m.from_user.id, movie['file_id'], caption=f"🎬 {movie['name']}")
        return

    # Coin yetarlimi?
    if user['coins'] < movie['price']:
        await state.clear()
        return await m.answer(
            f"❌ *Coinlar yetarli emas!*\n\n"
            f"💎 Kino narxi: {movie['price']} coin\n"
            f"💰 Sizda: {user['coins']} coin\n\n"
            f"🎁 Kunlik bonus va do'st taklif qilib coin yig'ing!",
            parse_mode="Markdown"
        )

    # Tasdiqlash
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
    movie_id = int(c.data.split("_")[2])
    movie = await get_movie(movie_id)
    success = await buy_movie(c.from_user.id, movie_id, movie['price'])

    if success:
        await c.message.edit_text(
            f"✅ *Tabriklaymiz!*\n\n"
            f"🎬 *{movie['name']}* kinosi muvaffaqiyatli sotib olindi!\n\n"
            "Kino yuborilmoqda...",
            parse_mode="Markdown"
        )
        if movie['file_id']:
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
    await c.answer()

@dp.callback_query(F.data == "cancel_buy")
async def cancel_purchase(c: CallbackQuery):
    await c.message.edit_text("❌ Sotib olish bekor qilindi.")
    await c.answer()

# ================= HISOBIM =================
@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")

    async with db_pool.acquire() as conn:
        purchases_count = await conn.fetchval(
            "SELECT COUNT(*) FROM purchases WHERE user_id=$1", m.from_user.id
        )
        referrals_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id
        )

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
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{m.from_user.id}"

    async with db_pool.acquire() as conn:
        referrals_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id
        )

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
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")

    await m.answer(
        "✍️ *Adminga xabar yozing:*\n\n"
        "Xabaringizni yuboring, admin tez orada javob beradi!",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(BotState.in_active_chat)
    await state.update_data(chat_with=ADMIN_ID, is_user_side=True)

@dp.message(BotState.in_active_chat)
async def active_chat(m: Message, state: FSMContext):
    if m.text and m.text.lower() == "/stop":
        await state.clear()
        return await m.answer(
            "📴 Suhbat yakunlandi.",
            reply_markup=get_main_kb(m.from_user.id)
        )

    data = await state.get_data()
    partner = data.get("chat_with")
    is_user_side = data.get("is_user_side", True)
    user = await get_user(m.from_user.id)
    name = user['name'] if user else m.from_user.full_name

    if partner:
        prefix = f"📩 *Foydalanuvchi:* {name} (ID: `{m.from_user.id}`)\n\n" if is_user_side else f"👑 *Admin javobi:*\n\n"
        try:
            if m.text:
                await bot.send_message(partner, f"{prefix}{m.text}", parse_mode="Markdown")
            elif m.photo:
                await bot.send_photo(partner, m.photo[-1].file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
            elif m.video:
                await bot.send_video(partner, m.video.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
            elif m.document:
                await bot.send_document(partner, m.document.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
            await m.answer("✅ Xabar yuborildi!")
        except Exception as e:
            await m.answer(f"❌ Xabar yuborilmadi: {e}")

# ================= STATISTIKA =================
@dp.message(F.text == "📊 Statistika")
async def show_stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    stats = await get_stats()
    await m.answer(
        f"📊 *BOT STATISTIKASI*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
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
        await m.answer(
            "👑 *Xush kelibsiz, Admin!*\n\nBoshqaruv paneli:",
            reply_markup=get_admin_kb(),
            parse_mode="Markdown"
        )
    else:
        await m.answer("❌ Parol noto'g'ri!")
        await state.clear()

@dp.callback_query(F.data == "adm_close")
async def close_admin(c: CallbackQuery):
    await c.message.delete()
    await c.answer()

# --- TO'LIQ STATISTIKA ---
@dp.callback_query(F.data == "adm_full_stats")
async def full_stats(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    stats = await get_stats()
    await c.message.edit_text(
        f"📊 *TO'LIQ STATISTIKA*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami foydalanuvchilar: *{stats['total_users']}*\n"
        f"🆕 Bugun qo'shilganlar: *{stats['today_users']}*\n"
        f"🚫 Bloklangan: *{stats['banned_users']}*\n"
        f"🎬 Jami kinolar: *{stats['total_movies']}*\n"
        f"🛒 Jami sotuvlar: *{stats['total_purchases']}*",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )
    await c.answer()

# --- KINO QO'SHISH ---
@dp.callback_query(F.data == "adm_add_kino")
async def add_kino_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    await c.message.answer("🎬 *Kino nomini kiriting:*", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_name)
    await c.answer()

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
        "🎥 *Kino faylini (video) yuboring:*\n\n"
        "⏭ Fayl yo'q bo'lsa /skip yozing",
        parse_mode="Markdown"
    )
    await state.set_state(BotState.adding_k_file)

@dp.message(BotState.adding_k_file, F.video)
async def set_k_file(m: Message, state: FSMContext):
    await state.update_data(k_file=m.video.file_id)
    await m.answer("💰 *Kino narxini coin da kiriting:* (masalan: 50)", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_file, F.text == "/skip")
async def skip_k_file(m: Message, state: FSMContext):
    await state.update_data(k_file=None)
    await m.answer("💰 *Kino narxini coin da kiriting:* (masalan: 50)", parse_mode="Markdown")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def save_kino(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    data = await state.get_data()
    new_id = await add_movie(
        data['k_name'], data['k_year'],
        data.get('k_desc', ''), data.get('k_file'),
        int(m.text)
    )
    await state.clear()
    await m.answer(
        f"✅ *Kino muvaffaqiyatli qo'shildi!*\n\n"
        f"🆔 Kodi: `{new_id}`\n"
        f"🎬 Nomi: {data['k_name']}\n"
        f"📅 Yil: {data['k_year']}\n"
        f"💰 Narx: {m.text} coin",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )

# --- KINO O'CHIRISH ---
@dp.callback_query(F.data == "adm_del_kino")
async def del_kino_start(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    movies = await get_all_movies()
    if not movies:
        return await c.answer("📽 Kinolar yo'q!", show_alert=True)

    kb = InlineKeyboardBuilder()
    for movie in movies:
        kb.button(text=f"🗑 {movie['name']} ({movie['id']})", callback_data=f"del_movie_{movie['id']}")
    kb.button(text="❌ Bekor qilish", callback_data="adm_close")
    kb.adjust(1)

    await c.message.edit_text(
        "🗑 *O'chirmoqchi bo'lgan kinoni tanlang:*",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )
    await c.answer()

@dp.callback_query(F.data.startswith("del_movie_"))
async def delete_movie(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    movie_id = int(c.data.split("_")[2])
    async with db_pool.acquire() as conn:
        movie = await conn.fetchrow("SELECT name FROM movies WHERE id=$1", movie_id)
        await conn.execute("DELETE FROM movies WHERE id=$1", movie_id)
    await c.message.edit_text(
        f"✅ *{movie['name']}* kinosi o'chirildi!",
        parse_mode="Markdown",
        reply_markup=get_admin_kb()
    )
    await c.answer()

# --- REKLAMA YUBORISH ---
@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    await c.message.answer("📢 *Barcha foydalanuvchilarga yuboriladigan xabarni yuboring:*\n(Matn, rasm, video bo'lishi mumkin)", parse_mode="Markdown")
    await state.set_state(BotState.sending_broadcast)
    await c.answer()

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
                await status_msg.edit_text(f"⏳ Yuborilmoqda... {i}/{len(users)}")
        except:
            failed += 1

    await status_msg.edit_text(
        f"✅ *Reklama yuborildi!*\n\n"
        f"📨 Muvaffaqiyatli: *{count}*\n"
        f"❌ Yuborilmagan: *{failed}*",
        parse_mode="Markdown"
    )

# --- BLOKLASH ---
@dp.callback_query(F.data == "adm_ban")
async def ban_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    await c.message.answer("🚫 Bloklash uchun foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.blocking_id)
    await c.answer()

@dp.message(BotState.blocking_id)
async def process_ban(m: Message, state: FSMContext):
    await state.clear()
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    uid = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=TRUE WHERE user_id=$1", uid)
    try:
        await bot.send_message(uid, "🚫 Siz botdan bloklangansiz.")
    except:
        pass
    await m.answer(f"✅ Foydalanuvchi (ID: `{uid}`) bloklandi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# --- BLOKDAN CHIQARISH ---
@dp.callback_query(F.data == "adm_unban")
async def unban_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    await c.message.answer("✅ Blokdan chiqarish uchun foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.unblocking_id)
    await c.answer()

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

# --- ADMIN CHAT ---
@dp.callback_query(F.data == "adm_start_chat")
async def admin_chat_init(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    await c.message.answer("💬 Gaplashmoqchi bo'lgan foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(BotState.admin_chat_target)
    await c.answer()

@dp.message(BotState.admin_chat_target)
async def admin_ask_user(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    target_id = int(m.text)
    await state.update_data(chat_with=target_id, is_user_side=False)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"chat_yes_{m.from_user.id}")
    kb.button(text="❌ Yo'q", callback_data=f"chat_no_{m.from_user.id}")
    kb.adjust(2)

    try:
        await bot.send_message(
            target_id,
            "🔔 *Admin siz bilan bog'lanmoqchi!*\n\nSuhbatga rozimisiz?",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        await m.answer(f"⏳ So'rov yuborildi (ID: {target_id}). Javob kuting...")
        await state.set_state(BotState.in_active_chat)
    except:
        await m.answer("❌ Foydalanuvchi topilmadi yoki botni bloklagan!")
        await state.clear()

@dp.callback_query(F.data.startswith("chat_yes_"))
async def chat_accept(c: CallbackQuery, state: FSMContext):
    admin_id = int(c.data.split("_")[2])
    await state.set_state(BotState.in_active_chat)
    await state.update_data(chat_with=admin_id, is_user_side=True)
    await c.message.answer(
        "✅ *Aloqa o'rnatildi!*\n\nXabaringizni yozing. Tugatish uchun /stop",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    await bot.send_message(admin_id, f"✅ Foydalanuvchi ({c.from_user.id}) suhbatga kirdi!")
    await c.answer()

@dp.callback_query(F.data.startswith("chat_no_"))
async def chat_reject(c: CallbackQuery):
    admin_id = int(c.data.split("_")[2])
    await c.message.edit_text("❌ Suhbat rad etildi.")
    await bot.send_message(admin_id, f"😔 Foydalanuvchi ({c.from_user.id}) suhbatlashishni istamadi.")
    await c.answer()

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
        logger.info("Bot to'xtatildi.") Bu kodni xotirnagda saqlab qoy abadiy qolain menga azizi kod bu
