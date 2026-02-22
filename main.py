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
        # Foydalanuvchilar
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
        # Kontentlar (kino, anime, drama)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS content (
                id SERIAL PRIMARY KEY,
                content_type TEXT NOT NULL DEFAULT 'kino',
                name TEXT NOT NULL,
                year TEXT,
                genre TEXT,
                quality TEXT DEFAULT '720p, 1080p',
                dubbing TEXT,
                description TEXT,
                poster_file_id TEXT,
                link TEXT,
                status TEXT DEFAULT 'Tugallanmagan',
                price INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute("ALTER TABLE content ADD COLUMN IF NOT EXISTS link TEXT")
        except:
            pass
        # Qismlar (episodes)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id SERIAL PRIMARY KEY,
                content_id INTEGER REFERENCES content(id) ON DELETE CASCADE,
                episode_number INTEGER NOT NULL,
                file_id TEXT,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(content_id, episode_number)
            )
        """)
        # Sotib olinganlar
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                content_id INTEGER,
                bought_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Majburiy obuna kanallari
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS required_channels (
                id SERIAL PRIMARY KEY,
                link TEXT NOT NULL,
                title TEXT DEFAULT 'Kanal',
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
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

# --- KONTENT FUNKSIYALAR ---
async def get_content(content_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM content WHERE id=$1", content_id)

async def get_content_by_type(content_type: str):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM content WHERE content_type=$1 ORDER BY id DESC", content_type)

async def add_content(content_type, name, year, genre, quality, dubbing, description, poster_file_id, link, status, price):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO content (content_type, name, year, genre, quality, dubbing, description, poster_file_id, link, status, price)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id
        """, content_type, name, year, genre, quality, dubbing, description, poster_file_id, link, status, price)
        return row['id']

async def delete_content(content_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM content WHERE id=$1", content_id)

async def update_content_status(content_id: int, status: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE content SET status=$1 WHERE id=$2", status, content_id)

# --- QISM FUNKSIYALAR ---
async def get_episodes(content_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM episodes WHERE content_id=$1 ORDER BY episode_number", content_id)

async def get_episode(content_id: int, ep_num: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM episodes WHERE content_id=$1 AND episode_number=$2", content_id, ep_num)

async def add_episode(content_id: int, ep_num: int, file_id: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO episodes (content_id, episode_number, file_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (content_id, episode_number) DO UPDATE SET file_id=$3
        """, content_id, ep_num, file_id)

async def delete_episode(content_id: int, ep_num: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM episodes WHERE content_id=$1 AND episode_number=$2", content_id, ep_num)

# --- XARID FUNKSIYALAR ---
async def user_has_content(user_id: int, content_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM purchases WHERE user_id=$1 AND content_id=$2", user_id, content_id)
        return row is not None

async def buy_content(user_id: int, content_id: int, price: int):
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT coins FROM users WHERE user_id=$1", user_id)
        if not user or user['coins'] < price:
            return False
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id=$2", price, user_id)
        await conn.execute("INSERT INTO purchases (user_id, content_id) VALUES ($1, $2)", user_id, content_id)
        return True

async def get_stats():
    async with db_pool.acquire() as conn:
        return {
            "total_users": await conn.fetchval("SELECT COUNT(*) FROM users"),
            "banned_users": await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned=TRUE"),
            "total_kino": await conn.fetchval("SELECT COUNT(*) FROM content WHERE content_type='kino'"),
            "total_anime": await conn.fetchval("SELECT COUNT(*) FROM content WHERE content_type='anime'"),
            "total_drama": await conn.fetchval("SELECT COUNT(*) FROM content WHERE content_type='drama'"),
            "total_episodes": await conn.fetchval("SELECT COUNT(*) FROM episodes"),
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

async def check_tg_sub_api(user_id: int, link: str) -> bool:
    username = extract_tg_username(link)
    if not username:
        return False
    try:
        member = await bot.get_chat_member(username, user_id)
        result = member.status not in ('left', 'kicked', 'banned')
        return result
    except Exception as e:
        logger.warning(f"get_chat_member xato ({username}, {user_id}): {e}")
        return False

async def get_external_confirmed(user_id: int, channel_id: int) -> bool:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_subscribed FROM user_sub_status WHERE user_id=$1 AND channel_id=$2",
            user_id, channel_id
        )
        return bool(row and row['is_subscribed'])

async def set_external_confirmed(user_id: int, channel_id: int):
    now = datetime.now()
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_sub_status (user_id, channel_id, is_subscribed, last_checked, subscribed_at)
            VALUES ($1, $2, TRUE, $3, $3)
            ON CONFLICT (user_id, channel_id) DO UPDATE
            SET is_subscribed = TRUE, last_checked = $3,
                subscribed_at = COALESCE(user_sub_status.subscribed_at, $3)
        """, user_id, channel_id, now)

async def track_and_log(user_id: int, user_name: str, channel: dict, is_sub: bool):
    ch_id = channel['id']
    ch_title = channel['title']
    ch_link = channel['link']
    now = datetime.now()
    async with db_pool.acquire() as conn:
        prev = await conn.fetchrow(
            "SELECT is_subscribed FROM user_sub_status WHERE user_id=$1 AND channel_id=$2",
            user_id, ch_id
        )
        prev_status = prev['is_subscribed'] if prev else None
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
        event = None
        if prev_status is None and is_sub:
            event = 'first_subscribed'
        elif prev_status is None and not is_sub:
            event = 'checked_not_subscribed'
        elif prev_status is False and is_sub:
            event = 'subscribed'
        elif prev_status is True and not is_sub:
            event = 'unsubscribed'
        if event:
            await conn.execute("""
                INSERT INTO sub_logs (user_id, user_name, channel_id, channel_title, channel_link, event)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, user_id, user_name, ch_id, ch_title, ch_link, event)
            asyncio.create_task(notify_admin_sub(user_id, user_name, ch_title, ch_link, event))

async def notify_admin_sub(user_id: int, user_name: str, ch_title: str, ch_link: str, event: str):
    emoji = {
        'first_subscribed': '🆕✅', 'subscribed': '✅',
        'checked_not_subscribed': '❌', 'unsubscribed': '⚠️🔴',
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
            parse_mode="HTML", disable_web_page_preview=True
        )
    except:
        pass

async def check_all_subs(user_id: int, user_name: str) -> list:
    channels = await get_required_channels()
    if not channels:
        return []
    not_subscribed = []
    for ch in channels:
        if is_telegram_link(ch['link']):
            is_sub = await check_tg_sub_api(user_id, ch['link'])
        else:
            is_sub = await get_external_confirmed(user_id, ch['id'])
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
        await bot.send_message(user_id, text, reply_markup=build_sub_kb(channels),
                               parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"send_sub_msg xato: {e}")

async def sub_guard(m: Message) -> bool:
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
    # Ro'yxatdan o'tish
    waiting_name = State()
    waiting_phone = State()
    # Admin auth
    admin_auth = State()
    # Kontent qo'shish
    adding_c_type = State()
    adding_c_name = State()
    adding_c_year = State()
    adding_c_genre = State()
    adding_c_quality = State()
    adding_c_dubbing = State()
    adding_c_desc = State()
    adding_c_poster = State()
    adding_c_link = State()
    adding_c_status = State()
    adding_c_price = State()
    # Qism qo'shish
    adding_ep_content_id = State()
    adding_ep_number = State()
    adding_ep_file = State()
    # Qism o'chirish
    del_ep_content_id = State()
    del_ep_number = State()
    # Holat o'zgartirish
    change_status_id = State()
    # Sotib olish
    buying_content = State()
    # Boshqa
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
TYPE_EMOJI = {'kino': '🎬', 'anime': '🎌', 'drama': '🎭'}
TYPE_NAME = {'kino': 'Kino', 'anime': 'Anime', 'drama': 'Drama'}

def get_coin_rank(coins: int) -> str:
    """Coin miqdoriga qarab daraja va nom beradi."""
    if coins <= 0:
        return "💀 Tilanchivoy"
    elif coins <= 50:
        return "🪨 Kambag'al"
    elif coins <= 150:
        return "🌾 Oddiy"
    elif coins <= 300:
        return "🥉 O'rtahol"
    elif coins <= 500:
        return "🥈 Munosib"
    elif coins <= 1000:
        return "🥇 Badavlat"
    elif coins <= 2000:
        return "💰 Boy"
    elif coins <= 5000:
        return "💎 Millioner"
    elif coins <= 10000:
        return "👑 Magnit"
    elif coins <= 50000:
        return "🔱 Oligarx"
    elif coins <= 100000:
        return "🌟 VIP"
    else:
        return "🚀 SUPER VIP"

def get_main_kb(uid: int):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Kinolar")
    builder.button(text="🎌 Animelar")
    builder.button(text="🎭 Dramalar")
    builder.button(text="🎟 Kino Sotib Olish")
    builder.button(text="💰 Hisobim")
    builder.button(text="🎁 Kunlik Bonus")
    builder.button(text="👥 Do'st Taklif Qilish")
    builder.button(text="✍️ Adminga Yozish")
    if uid == ADMIN_ID:
        builder.button(text="👑 Admin Panel")
        builder.button(text="📊 Statistika")
    builder.adjust(3, 1, 2, 2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕🎬 Kino Qo'shish", callback_data="adm_add_kino")
    builder.button(text="➕🎌 Anime Qo'shish", callback_data="adm_add_anime")
    builder.button(text="➕🎭 Drama Qo'shish", callback_data="adm_add_drama")
    builder.button(text="🗑 Kontent O'chirish", callback_data="adm_del_content")
    builder.button(text="📺 Qism Qo'shish", callback_data="adm_add_episode")
    builder.button(text="🗑 Qism O'chirish", callback_data="adm_del_episode")
    builder.button(text="🔄 Holat O'zgartirish", callback_data="adm_change_status")
    builder.button(text="💰 Coin Qo'shish", callback_data="adm_add_coin")
    builder.button(text="💸 Coin Olish", callback_data="adm_remove_coin")
    builder.button(text="📢 Reklama Yuborish", callback_data="adm_broadcast")
    builder.button(text="🚫 Bloklash", callback_data="adm_ban")
    builder.button(text="✅ Blokdan Chiqarish", callback_data="adm_unban")
    builder.button(text="💬 Foydalanuvchi bilan Gaplash", callback_data="adm_start_chat")
    builder.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
    builder.button(text="🔔 Majburiy Obuna", callback_data="adm_subscription")
    builder.button(text="👥 Foydalanuvchilar Ro'yxati", callback_data="adm_users")
    builder.button(text="📋 Obuna Loglari", callback_data="adm_sub_logs")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(3, 1, 2, 1, 2, 2, 1, 1, 1, 1, 1)
    return builder.as_markup()

def get_admin_end_chat_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔴 Aloqani Tugatish", callback_data="end_chat")
    return builder.as_markup()

def build_episode_kb(content_id: int, episodes: list) -> InlineKeyboardMarkup:
    """Qismlar uchun raqamli tugmalar."""
    kb = InlineKeyboardBuilder()
    nums = sorted([ep['episode_number'] for ep in episodes])
    row = []
    for n in nums:
        row.append(InlineKeyboardButton(text=str(n), callback_data=f"ep_{content_id}_{n}"))
    # 6 ta qator bo'yicha
    for i in range(0, len(row), 6):
        kb.row(*row[i:i+6])
    return kb.as_markup()

def format_content_info(c: dict, episodes: list) -> str:
    """Kontent ma'lumotlarini chiroyli formatda."""
    emoji = TYPE_EMOJI.get(c['content_type'], '🎬')
    type_name = TYPE_NAME.get(c['content_type'], 'Kontent')
    status_emoji = "✅" if c['status'] == 'Tugallangan' else "🔄"
    ep_count = len(episodes)

    text = f"<b>{emoji} {type_name}: {c['name']}</b>\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"↳ <b>Holati:</b> {status_emoji} {c['status']}\n"
    if ep_count:
        text += f"↳ <b>Qismlar:</b> {ep_count} ta\n"
    if c['quality']:
        text += f"↳ <b>Sifat:</b> {c['quality']}\n"
    if c['genre']:
        text += f"↳ <b>Janrlari:</b> {c['genre']}\n"
    if c['year']:
        text += f"↳ <b>Yil:</b> {c['year']}\n"
    if c['dubbing']:
        text += f"↳ <b>Ovoz/Dublyaj:</b> {c['dubbing']}\n"
    if c['description']:
        text += f"\n📝 <b>Tavsif:</b>\n{c['description']}\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    if c['price'] > 0:
        text += f"💎 <b>Narx:</b> {c['price']} coin\n"
    else:
        text += f"💎 <b>Narx:</b> Bepul\n"
    text += f"🆔 <b>ID:</b> {c['id']}\n"
    if c.get('link'):
        text += f"🔗 <b>Link:</b> <a href='{c['link']}'>{c['link']}</a>"
    return text

# ================= START =================
@dp.message(CommandStart())
async def start_cmd(m: Message, state: FSMContext):
    await state.clear()
    user = await get_user(m.from_user.id)

    referrer_id = None
    args = m.text.split()
    content_id = None
    if len(args) > 1:
        if args[1].startswith("ref"):
            try:
                referrer_id = int(args[1][3:])
                if referrer_id == m.from_user.id:
                    referrer_id = None
            except:
                pass
        elif args[1].isdigit():
            content_id = int(args[1])

    if user:
        if user['is_banned']:
            return await m.answer("🚫 Siz botdan bloklangansiz.")
        not_sub = await check_all_subs(m.from_user.id, user['name'])
        if not_sub:
            return await send_sub_msg(m.from_user.id, not_sub)
        if content_id:
            return await show_content_detail(m.from_user.id, content_id)
        return await m.answer(
            f"🌟 <b>Xush kelibsiz qaytib, {user['name']}!</b>\n\n💰 Balansingiz: <b>{user['coins']} coin</b>",
            reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML"
        )
    else:
        await state.update_data(referrer_id=referrer_id)
        await m.answer(
            "👋 <b>Assalomu alaykum! Kino Botga xush kelibsiz!</b>\n\nRo'yxatdan o'tish uchun <b>ismingizni</b> kiriting:",
            parse_mode="HTML"
        )
        await state.set_state(BotState.waiting_name)

# ================= KONTENT DETAIL KO'RSATISH =================
async def show_content_detail(chat_id: int, content_id: int, user_id: int = None):
    """Kontent ma'lumotlarini ko'rsatadi (poster + info + qism tugmalari)."""
    c = await get_content(content_id)
    if not c:
        try:
            await bot.send_message(chat_id, "❌ Bunday ID li kontent topilmadi!")
        except:
            pass
        return

    uid = user_id or chat_id
    episodes = await get_episodes(content_id)
    text = format_content_info(c, episodes)

    kb = InlineKeyboardBuilder()

    is_free = c['price'] == 0
    already_bought = await user_has_content(uid, content_id)

    if episodes:
        if is_free or already_bought:
            # Tomosha qilish tugmasi + qism raqamlari
            nums = sorted([ep['episode_number'] for ep in episodes])
            row = []
            for n in nums:
                row.append(InlineKeyboardButton(text=str(n), callback_data=f"ep_{content_id}_{n}"))
            kb.row(InlineKeyboardButton(text="🎬 Tomosha qilish", callback_data=f"watch_{content_id}"))
            for i in range(0, len(row), 6):
                kb.row(*row[i:i+6])
        else:
            # Sotib olish tugmasi
            kb.button(text=f"🛒 {c['price']} coin to'lab sotib olish", callback_data=f"confirm_buy_{content_id}")
            kb.button(text="❌ Yo'q, shart emas", callback_data="cancel_buy")
            kb.adjust(1)
    elif c.get('link'):
        if is_free or already_bought:
            kb.button(text="🎬 Tomosha qilish", url=c['link'])
        else:
            kb.button(text=f"🛒 {c['price']} coin to'lab sotib olish", callback_data=f"confirm_buy_{content_id}")
            kb.button(text="❌ Yo'q, shart emas", callback_data="cancel_buy")
            kb.adjust(1)

    markup = kb.as_markup() if kb.buttons else None

    if c['poster_file_id']:
        try:
            await bot.send_photo(chat_id, c['poster_file_id'], caption=text,
                                 parse_mode="HTML", reply_markup=markup)
        except:
            await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

@dp.callback_query(F.data.startswith("watch_"))
async def watch_content(c: CallbackQuery):
    """Tomosha qilish bosilganda qism tanlash."""
    await c.answer()
    content_id = int(c.data.split("_")[1])
    episodes = await get_episodes(content_id)
    if not episodes:
        return await c.answer("❌ Qismlar hali qo'shilmagan!", show_alert=True)
    kb = InlineKeyboardBuilder()
    nums = sorted([ep['episode_number'] for ep in episodes])
    row = [InlineKeyboardButton(text=str(n), callback_data=f"ep_{content_id}_{n}") for n in nums]
    for i in range(0, len(row), 6):
        kb.row(*row[i:i+6])
    await c.message.answer("📺 <b>Qaysi qismni ko'rmoqchisiz?</b>", parse_mode="HTML", reply_markup=kb.as_markup())

# ================= QISM YUBORISH CALLBACK =================
@dp.callback_query(F.data.startswith("ep_"))
async def send_episode(c: CallbackQuery):
    await c.answer("⏳ Yuklanmoqda...")
    parts = c.data.split("_")
    content_id = int(parts[1])
    ep_num = int(parts[2])

    content = await get_content(content_id)
    if not content:
        return await c.answer("❌ Kontent topilmadi!", show_alert=True)

    user = await get_user(c.from_user.id)
    if not user:
        return await c.answer("❌ Avval ro'yxatdan o'ting!", show_alert=True)

    # Pullik va sotib olinmagan
    if content['price'] > 0 and not await user_has_content(c.from_user.id, content_id):
        kb = InlineKeyboardBuilder()
        kb.button(text=f"🛒 {content['price']} coin to'lab sotib olish", callback_data=f"confirm_buy_{content_id}")
        kb.button(text="❌ Yo'q, shart emas", callback_data="cancel_buy")
        kb.adjust(1)
        await bot.send_message(
            c.from_user.id,
            f"🔒 <b>Bu kontent pullik!</b>\n\n"
            f"🎬 <b>{content['name']}</b>\n"
            f"💎 Narx: <b>{content['price']} coin</b>\n"
            f"💰 Sizda: <b>{user['coins']} coin</b>",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
        return

    ep = await get_episode(content_id, ep_num)
    if not ep or not ep['file_id']:
        return await c.answer("❌ Bu qism hali qo'shilmagan!", show_alert=True)

    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
    caption = f"{emoji} <b>{content['name']}</b> — {ep_num}-qism"
    await bot.send_video(c.from_user.id, ep['file_id'], caption=caption, parse_mode="HTML")

# ================= OBUNA TEKSHIRISH =================
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
            is_sub = await check_tg_sub_api(c.from_user.id, ch['link'])
        else:
            is_sub = True
            await set_external_confirmed(c.from_user.id, ch['id'])
        await track_and_log(c.from_user.id, user['name'], ch, is_sub)
        if not is_sub:
            not_subscribed.append(ch)

    if not not_subscribed:
        try:
            await c.message.edit_text("✅ <b>Barcha kanallarga a'zo bo'ldingiz!</b>\n\nEndi botdan to'liq foydalaning!", parse_mode="HTML")
        except:
            pass
        await bot.send_message(
            c.from_user.id,
            f"🎉 <b>Xush kelibsiz, {user['name']}!</b>\n\n💰 Balansingiz: <b>{user['coins']} coin</b>",
            reply_markup=get_main_kb(c.from_user.id), parse_mode="HTML"
        )
    else:
        lines = "".join(f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n" for i, ch in enumerate(not_subscribed, 1))
        text = (f"❌ <b>Hali {len(not_subscribed)} ta kanalga a'zo bo'lmadingiz:</b>\n\n{lines}\n"
                "A'zo bo'lib, <b>✅ Obunani Tekshirish</b> tugmasini qayta bosing.")
        try:
            await c.message.edit_text(text, reply_markup=build_sub_kb(not_subscribed),
                                      parse_mode="HTML", disable_web_page_preview=True)
        except:
            await bot.send_message(c.from_user.id, text, reply_markup=build_sub_kb(not_subscribed),
                                   parse_mode="HTML", disable_web_page_preview=True)

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
            f"✅ <b>Tabriklaymiz, {name}!</b>\n\n🎉 Ro'yxatdan o'tdingiz!\n💰 Sizga <b>100 coin</b> sovg'a qilindi!\n\n"
            "⚠️ Botdan foydalanish uchun kanallarga obuna bo'ling:",
            parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
        )
        not_sub = await check_all_subs(m.from_user.id, name)
        if not_sub:
            await send_sub_msg(m.from_user.id, not_sub)
    else:
        await m.answer(
            f"✅ <b>Tabriklaymiz, {name}!</b>\n\n🎉 Ro'yxatdan o'tdingiz!\n💰 Sizga <b>100 coin</b> sovg'a qilindi!",
            reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML"
        )

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone_contact(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_registration(m, state, data['name'], m.contact.phone_number)

@dp.message(BotState.waiting_phone, F.text == "⏭ O'tkazib yuborish")
async def reg_skip_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_registration(m, state, data['name'], None)

# ================= KONTENT RO'YXATLARI =================
@dp.message(F.text == "🎬 Kinolar")
async def show_kino_list(m: Message):
    if not await sub_guard(m):
        return
    await show_content_list(m, 'kino')

@dp.message(F.text == "🎌 Animelar")
async def show_anime_list(m: Message):
    if not await sub_guard(m):
        return
    await show_content_list(m, 'anime')

@dp.message(F.text == "🎭 Dramalar")
async def show_drama_list(m: Message):
    if not await sub_guard(m):
        return
    await show_content_list(m, 'drama')

async def show_content_list(m: Message, content_type: str):
    items = await get_content_by_type(content_type)
    emoji = TYPE_EMOJI[content_type]
    name = TYPE_NAME[content_type]
    if not items:
        return await m.answer(f"{emoji} Hozircha {name.lower()}lar mavjud emas.")

    text = f"{emoji} <b>{name.upper()}LAR RO'YXATI</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for item in items:
        status_emoji = "✅" if item['status'] == 'Tugallangan' else "🔄"
        async with db_pool.acquire() as conn:
            ep_count = await conn.fetchval("SELECT COUNT(*) FROM episodes WHERE content_id=$1", item['id'])
        price_text = f"{item['price']} coin" if item['price'] > 0 else "Bepul"
        text += (f"{emoji} <b>{item['name']}</b>\n"
                 f"   {status_emoji} {item['status']} | 📺 {ep_count} qism\n"
                 f"   💎 {price_text} | 🆔 Kod: <code>{item['id']}</code>\n"
                 f"   ────────────────────\n")

    text += f"\n💡 Ko'rish uchun: <b>🎟 Kontent Olish</b> tugmasi yoki ID ni yuboring"
    await m.answer(text, parse_mode="HTML")

# ================= KONTENT OLISH (SOTIB OLISH) =================
@dp.message(F.text == "🎟 Kino Sotib Olish")
async def buy_content_start(m: Message, state: FSMContext):
    if not await sub_guard(m):
        return
    user = await get_user(m.from_user.id)
    if not user:
        return await m.answer("❌ Avval ro'yxatdan o'ting! /start")

    # Barcha kontentlar ro'yxatini chiqarish
    async with db_pool.acquire() as conn:
        all_items = await conn.fetch("SELECT * FROM content ORDER BY content_type, id DESC")

    if not all_items:
        return await m.answer("📭 Hozircha kontentlar mavjud emas!")

    text = "🎟 <b>BARCHA KONTENTLAR</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for item in all_items:
        emoji = TYPE_EMOJI.get(item['content_type'], '🎬')
        status_emoji = "✅" if item['status'] == 'Tugallangan' else "🔄"
        if item['price'] > 0:
            price_text = f"💎 {item['price']} coin"
        else:
            price_text = "🆓 Bepul"
        text += f"{emoji} <b>{item['name']}</b> | {status_emoji} {item['status']}\n"
        text += f"   {price_text} | 🆔 Kod: <code>{item['id']}</code>\n"
        text += f"   ─────────────────\n"

    text += "\n📌 Kontent <b>kodini</b> yuboring:"
    await m.answer(text, parse_mode="HTML")
    await state.set_state(BotState.buying_content)

@dp.message(BotState.buying_content)
async def process_buy(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit():
        return await m.answer("⚠️ Faqat kontent kodini raqamda yozing!")
    content = await get_content(int(m.text))
    if not content:
        return await m.answer("❌ Bunday kodli kontent topilmadi!\n\n💡 Ro'yxatdan to'g'ri ID ni tanlang.")
    user = await get_user(m.from_user.id)
    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')

    # Allaqachon sotib olingan yoki bepul
    if content['price'] == 0 or await user_has_content(m.from_user.id, content['id']):
        await state.clear()
        await show_content_detail(m.from_user.id, content['id'])
        return

    # Coin yetarli emas
    if user['coins'] < content['price']:
        await state.clear()
        return await m.answer(
            f"❌ <b>Coinlar yetarli emas!</b>\n\n"
            f"{emoji} <b>{content['name']}</b>\n"
            f"💎 Narx: <b>{content['price']} coin</b>\n"
            f"💰 Sizda: <b>{user['coins']} coin</b>\n\n"
            f"💡 Do'st taklif qiling yoki kunlik bonus oling!",
            parse_mode="HTML"
        )

    # Tasdiqlash tugmalari
    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"✅ {content['price']} coin to'lab sotib olish",
        callback_data=f"confirm_buy_{content['id']}"
    )
    kb.button(text="❌ Yo'q, shart emas", callback_data="cancel_buy")
    kb.adjust(1)

    status_emoji = "✅" if content['status'] == 'Tugallangan' else "🔄"
    await m.answer(
        f"{emoji} <b>{content['name']}</b>\n"
        f"📅 Yil: {content['year'] or '-'}\n"
        f"🎭 Janr: {content['genre'] or '-'}\n"
        f"📌 Holat: {status_emoji} {content['status']}\n\n"
        f"📝 {content['description'] or 'Tavsif mavjud emas'}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💎 Narx: <b>{content['price']} coin</b>\n"
        f"💰 Sizda: <b>{user['coins']} coin</b>\n\n"
        f"Sotib olasizmi?",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await state.clear()

@dp.callback_query(F.data.startswith("confirm_buy_"))
async def confirm_purchase(c: CallbackQuery):
    await c.answer()
    content_id = int(c.data.split("_")[2])
    content = await get_content(content_id)
    user = await get_user(c.from_user.id)

    if user['coins'] < content['price']:
        return await c.message.edit_text(
            f"❌ <b>Coinlar yetarli emas!</b>\n\n"
            f"💎 Narx: <b>{content['price']} coin</b>\n"
            f"💰 Sizda: <b>{user['coins']} coin</b>\n\n"
            f"💡 Do'st taklif qiling yoki kunlik bonus oling!",
            parse_mode="HTML"
        )

    success = await buy_content(c.from_user.id, content_id, content['price'])
    if success:
        emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
        await c.message.edit_text(
            f"✅ <b>Muvaffaqiyatli sotib olindi!</b>\n\n"
            f"{emoji} <b>{content['name']}</b>\n"
            f"💎 To'landi: <b>{content['price']} coin</b>",
            parse_mode="HTML"
        )
        await show_content_detail(c.from_user.id, content_id, c.from_user.id)
    else:
        await c.message.edit_text("❌ Xatolik yuz berdi. Qayta urinib ko'ring!")

@dp.callback_query(F.data == "cancel_buy")
async def cancel_purchase(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("❌ <b>Bekor qilindi.</b>\n\nBoshqa kino yoki anime ko'rish uchun ro'yxatga qarang.", parse_mode="HTML")

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
    rank = get_coin_rank(user['coins'])
    await m.answer(
        f"👤 <b>Shaxsiy Kabinet</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Ism: <b>{user['name']}</b>\n"
        f"🏆 Daraja: <b>{rank}</b>\n"
        f"📱 Tel: {user['phone'] or 'Kiritilmagan'}\n"
        f"💰 Balans: <b>{user['coins']} coin</b>\n"
        f"🎬 Sotib olingan: <b>{purchases_count}</b> ta\n"
        f"👥 Taklif qilingan: <b>{referrals_count}</b> ta\n"
        f"📅 Sana: <b>{user['joined_at']}</b>\n\n"
        f"🔑 ID: <code>{m.from_user.id}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Daraja tizimi:</b>\n"
        f"💀 0 — Tilanchivoy\n"
        f"🪨 1-50 — Kambag'al\n"
        f"🌾 51-150 — Oddiy\n"
        f"🥉 151-300 — O'rtahol\n"
        f"🥈 301-500 — Munosib\n"
        f"🥇 501-1000 — Badavlat\n"
        f"💰 1001-2000 — Boy\n"
        f"💎 2001-5000 — Millioner\n"
        f"👑 5001-10000 — Magnit\n"
        f"🔱 10001-50000 — Oligarx\n"
        f"🌟 50001-100000 — VIP\n"
        f"🚀 100000+ — SUPER VIP",
        parse_mode="HTML"
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
        return await m.answer("⏳ <b>Bugun allaqachon bonus oldingiz!</b>\n\n🔄 Ertaga qaytib keling!", parse_mode="HTML")
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins + 20, last_bonus = CURRENT_DATE WHERE user_id=$1", m.from_user.id)
    updated = await get_user(m.from_user.id)
    await m.answer(f"🎉 <b>Kunlik Bonus!</b>\n\n✅ <b>+20 coin</b> qo'shildi!\n💰 Balans: <b>{updated['coins']} coin</b>", parse_mode="HTML")

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
        f"👥 <b>Do'stlarni Taklif Qilish</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Havolangiz:\n<code>{ref_link}</code>\n\n"
        f"💰 Har bir do'st uchun: <b>+50 coin</b>\n👤 Taklif qilingan: <b>{cnt}</b> ta",
        parse_mode="HTML"
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
    # Foydalanuvchiga hech qanday tugma va /stop ko'rsatilmaydi
    await m.answer(
        "✍️ <b>Adminga xabar yozing:</b>\n\nAdmin javob berguncha kuting...",
        parse_mode="HTML", reply_markup=ReplyKeyboardRemove()
    )
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
    # Bloklangan bo'lsa chat holatida ham xabar ko'rsatamiz
    user = await get_user(m.from_user.id)
    if user and user['is_banned']:
        await state.clear()
        return await m.answer("🚫 Siz botdan bloklangansiz.")
    partner = data.get("chat_with")
    is_user_side = data.get("is_user_side", True)

    # /stop faqat admin uchun ishlaydi
    if m.text and m.text.lower() == "/stop":
        if m.from_user.id != ADMIN_ID:
            # Foydalanuvchi /stop yozsa — e'tibor bermaymiz, xabar sifatida yuboramiz
            pass
        else:
            # Faqat admin tugatishi mumkin
            await state.clear()
            await m.answer("📴 Suhbat yakunlandi.", reply_markup=get_admin_kb())
            if partner:
                try:
                    await bot.send_message(
                        partner,
                        "📴 Admin suhbatni yakunladi.",
                        reply_markup=get_main_kb(partner)
                    )
                except:
                    pass
            return

    if not partner:
        return

    user = await get_user(m.from_user.id)
    name = user['name'] if user else m.from_user.full_name
    prefix = f"📩 <b>{name}</b> (ID: <code>{m.from_user.id}</code>):\n\n" if is_user_side else "👑 <b>Admin:</b>\n\n"

    try:
        if m.text:
            await bot.send_message(partner, f"{prefix}{m.text}", parse_mode="HTML")
        elif m.photo:
            await bot.send_photo(partner, m.photo[-1].file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="HTML")
        elif m.video:
            await bot.send_video(partner, m.video.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="HTML")
        elif m.document:
            await bot.send_document(partner, m.document.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="HTML")

        # Faqat adminga tugatish tugmasi ko'rinadi
        if not is_user_side:
            await m.answer("✅ Yuborildi!", reply_markup=get_admin_end_chat_kb())
        else:
            await m.answer("✅ Yuborildi!")
    except Exception as e:
        await m.answer(f"❌ Yuborilmadi: {e}")

# ================= STATISTIKA =================
@dp.message(F.text == "📊 Statistika")
async def show_stats(m: Message):
    if m.from_user.id != ADMIN_ID:
        return
    s = await get_stats()
    await m.answer(
        f"📊 <b>BOT STATISTIKASI</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami foydalanuvchi: <b>{s['total_users']}</b>\n"
        f"🆕 Bugun qo'shildi: <b>{s['today_users']}</b>\n"
        f"🚫 Bloklangan: <b>{s['banned_users']}</b>\n\n"
        f"🎬 Kinolar: <b>{s['total_kino']}</b>\n"
        f"🎌 Animelar: <b>{s['total_anime']}</b>\n"
        f"🎭 Dramalar: <b>{s['total_drama']}</b>\n"
        f"📺 Jami qismlar: <b>{s['total_episodes']}</b>\n"
        f"🛒 Sotuvlar: <b>{s['total_purchases']}</b>",
        parse_mode="HTML"
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
        await m.answer("👑 <b>Xush kelibsiz, Admin!</b>", reply_markup=get_admin_kb(), parse_mode="HTML")
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
        f"📊 <b>TO'LIQ STATISTIKA</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami: <b>{s['total_users']}</b>\n🆕 Bugun: <b>{s['today_users']}</b>\n"
        f"🚫 Bloklangan: <b>{s['banned_users']}</b>\n\n"
        f"🎬 Kinolar: <b>{s['total_kino']}</b>\n"
        f"🎌 Animelar: <b>{s['total_anime']}</b>\n"
        f"🎭 Dramalar: <b>{s['total_drama']}</b>\n"
        f"📺 Qismlar: <b>{s['total_episodes']}</b>\n"
        f"🛒 Sotuvlar: <b>{s['total_purchases']}</b>",
        parse_mode="HTML", reply_markup=get_admin_kb()
    )

# ==========================================
# KONTENT QO'SHISH (kino / anime / drama)
# ==========================================

async def start_add_content(c: CallbackQuery, state: FSMContext, content_type: str):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await state.update_data(adding_content_type=content_type)
    emoji = TYPE_EMOJI[content_type]
    name = TYPE_NAME[content_type]
    await c.message.answer(f"{emoji} <b>Yangi {name} qo'shish</b>\n\n📛 <b>{name} nomini kiriting:</b>", parse_mode="HTML")
    await state.set_state(BotState.adding_c_name)

@dp.callback_query(F.data == "adm_add_kino")
async def add_kino_start(c: CallbackQuery, state: FSMContext):
    await start_add_content(c, state, 'kino')

@dp.callback_query(F.data == "adm_add_anime")
async def add_anime_start(c: CallbackQuery, state: FSMContext):
    await start_add_content(c, state, 'anime')

@dp.callback_query(F.data == "adm_add_drama")
async def add_drama_start(c: CallbackQuery, state: FSMContext):
    await start_add_content(c, state, 'drama')

@dp.message(BotState.adding_c_name)
async def set_c_name(m: Message, state: FSMContext):
    await state.update_data(c_name=m.text.strip())
    await m.answer("📅 <b>Yilini kiriting:</b> (masalan: 2024)", parse_mode="HTML")
    await state.set_state(BotState.adding_c_year)

@dp.message(BotState.adding_c_year)
async def set_c_year(m: Message, state: FSMContext):
    await state.update_data(c_year=m.text.strip())
    await m.answer("🎭 <b>Janrlarini kiriting:</b>\n(masalan: Sarguzasht, Sehr, Komediya)", parse_mode="HTML")
    await state.set_state(BotState.adding_c_genre)

@dp.message(BotState.adding_c_genre)
async def set_c_genre(m: Message, state: FSMContext):
    await state.update_data(c_genre=m.text.strip())
    await m.answer("📺 <b>Sifatini kiriting:</b>\n(masalan: 720p, 1080p)\n\nYo'q bo'lsa /skip", parse_mode="HTML")
    await state.set_state(BotState.adding_c_quality)

@dp.message(BotState.adding_c_quality)
async def set_c_quality(m: Message, state: FSMContext):
    await state.update_data(c_quality=None if m.text == '/skip' else m.text.strip())
    await m.answer("🎙 <b>Dublyaj/Ovoz ma'lumotini kiriting:</b>\n(masalan: AniDonUz, O'zbek tilida)\n\nYo'q bo'lsa /skip", parse_mode="HTML")
    await state.set_state(BotState.adding_c_dubbing)

@dp.message(BotState.adding_c_dubbing)
async def set_c_dubbing(m: Message, state: FSMContext):
    await state.update_data(c_dubbing=None if m.text == '/skip' else m.text.strip())
    await m.answer("📝 <b>Tavsifini yozing:</b>\n\nYo'q bo'lsa /skip", parse_mode="HTML")
    await state.set_state(BotState.adding_c_desc)

@dp.message(BotState.adding_c_desc)
async def set_c_desc(m: Message, state: FSMContext):
    await state.update_data(c_desc=None if m.text == '/skip' else m.text.strip())
    await m.answer("🖼 <b>Poster (rasm) yuboring:</b>\n\nYo'q bo'lsa /skip", parse_mode="HTML")
    await state.set_state(BotState.adding_c_poster)

@dp.message(BotState.adding_c_poster, F.photo)
async def set_c_poster_photo(m: Message, state: FSMContext):
    await state.update_data(c_poster=m.photo[-1].file_id)
    await ask_c_link(m, state)

@dp.message(BotState.adding_c_poster, F.text)
async def set_c_poster_skip(m: Message, state: FSMContext):
    await state.update_data(c_poster=None)
    await ask_c_link(m, state)

async def ask_c_link(m: Message, state: FSMContext):
    await m.answer("🔗 <b>Kino/Anime/Drama linkini kiriting:</b>\n(masalan: https://t.me/anireply?start=124)\n\nYo'q bo'lsa /skip", parse_mode="HTML")
    await state.set_state(BotState.adding_c_link)

@dp.message(BotState.adding_c_link)
async def set_c_link(m: Message, state: FSMContext):
    if m.text == '/skip':
        await state.update_data(c_link=None)
    else:
        await state.update_data(c_link=m.text.strip())
    await ask_c_status(m, state)

async def ask_c_status(m: Message, state: FSMContext):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tugallangan", callback_data="cstatus_Tugallangan")
    kb.button(text="🔄 Tugallanmagan", callback_data="cstatus_Tugallanmagan")
    kb.adjust(2)
    await m.answer("📌 <b>Holatini tanlang:</b>", parse_mode="HTML", reply_markup=kb.as_markup())
    await state.set_state(BotState.adding_c_status)

@dp.callback_query(F.data.startswith("cstatus_"))
async def set_c_status(c: CallbackQuery, state: FSMContext):
    await c.answer()
    status = c.data.replace("cstatus_", "")
    await state.update_data(c_status=status)
    await c.message.answer("💰 <b>Narxini coin da kiriting:</b>\n(Bepul bo'lsa 0 kiriting)", parse_mode="HTML")
    await state.set_state(BotState.adding_c_price)

@dp.message(BotState.adding_c_price)
async def save_content(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    data = await state.get_data()
    content_type = data.get('adding_content_type', 'kino')

    new_id = await add_content(
        content_type, data['c_name'], data.get('c_year'), data.get('c_genre'),
        data.get('c_quality', '720p, 1080p'), data.get('c_dubbing'),
        data.get('c_desc'), data.get('c_poster'), data.get('c_link'),
        data.get('c_status', 'Tugallanmagan'), int(m.text)
    )
    await state.clear()
    emoji = TYPE_EMOJI[content_type]
    name = TYPE_NAME[content_type]
    await m.answer(
        f"✅ <b>{name} qo'shildi!</b>\n\n"
        f"🆔 ID: <code>{new_id}</code>\n"
        f"{emoji} {data['c_name']}\n"
        f"📅 Yil: {data.get('c_year', '-')}\n"
        f"📌 Holat: {data.get('c_status', 'Tugallanmagan')}\n"
        f"💰 Narx: {m.text} coin\n\n"
        f"📢 Foydalanuvchilarga yangilik xabari yuborilmoqda...",
        parse_mode="HTML", reply_markup=get_admin_kb()
    )
    asyncio.create_task(broadcast_new_content(new_id))

# ==========================================
# KONTENT O'CHIRISH
# ==========================================
@dp.callback_query(F.data == "adm_del_content")
async def del_content_start(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardBuilder()
    for ctype, emoji, name in [('kino', '🎬', 'Kinolar'), ('anime', '🎌', 'Animelar'), ('drama', '🎭', 'Dramalar')]:
        kb.button(text=f"{emoji} {name}", callback_data=f"del_list_{ctype}")
    kb.button(text="❌ Bekor", callback_data="adm_close")
    kb.adjust(3, 1)
    await c.message.edit_text("🗑 <b>Qaysi turdan o'chirmoqchisiz?</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_list_"))
async def del_content_list(c: CallbackQuery):
    await c.answer()
    content_type = c.data.split("_")[2]
    items = await get_content_by_type(content_type)
    if not items:
        return await c.message.edit_text("📭 Hozircha kontentlar yo'q!", reply_markup=get_admin_kb())
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.button(text=f"🗑 [{item['id']}] {item['name']}", callback_data=f"del_content_{item['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_del_content")
    kb.adjust(1)
    await c.message.edit_text("🗑 <b>O'chirmoqchi bo'lgan kontentni tanlang:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("del_content_"))
async def delete_content_confirm(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    content_id = int(c.data.split("_")[2])
    content = await get_content(content_id)
    if content:
        await delete_content(content_id)
        await c.answer(f"✅ '{content['name']}' o'chirildi!", show_alert=True)
    await c.message.edit_text("👑 <b>Admin Panel</b>", reply_markup=get_admin_kb(), parse_mode="HTML")

# ==========================================
# HOLAT O'ZGARTIRISH
# ==========================================
@dp.callback_query(F.data == "adm_change_status")
async def change_status_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("🔄 <b>Holat o'zgartirish uchun kontent ID sini kiriting:</b>", parse_mode="HTML")
    await state.set_state(BotState.change_status_id)

@dp.message(BotState.change_status_id)
async def change_status_process(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID kiriting!")
    content = await get_content(int(m.text))
    if not content:
        await state.clear()
        return await m.answer("❌ Bunday ID li kontent topilmadi!")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Tugallangan", callback_data=f"setstatus_{content['id']}_Tugallangan")
    kb.button(text="🔄 Tugallanmagan", callback_data=f"setstatus_{content['id']}_Tugallanmagan")
    kb.adjust(2)
    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
    await m.answer(
        f"{emoji} <b>{content['name']}</b>\n\nHozirgi holat: {content['status']}\n\nYangi holatni tanlang:",
        parse_mode="HTML", reply_markup=kb.as_markup()
    )
    await state.clear()

@dp.callback_query(F.data.startswith("setstatus_"))
async def set_status_callback(c: CallbackQuery):
    await c.answer()
    parts = c.data.split("_")
    content_id = int(parts[1])
    status = parts[2]
    await update_content_status(content_id, status)
    content = await get_content(content_id)
    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
    await c.message.edit_text(
        f"✅ Holat yangilandi!\n\n{emoji} <b>{content['name']}</b>\n📌 Yangi holat: <b>{status}</b>",
        parse_mode="HTML", reply_markup=get_admin_kb()
    )

# ==========================================
# QISM QO'SHISH
# ==========================================
@dp.callback_query(F.data == "adm_add_episode")
async def add_ep_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("📺 <b>Qism qo'shish</b>\n\n🆔 Kontent <b>ID sini</b> kiriting:", parse_mode="HTML")
    await state.set_state(BotState.adding_ep_content_id)

@dp.message(BotState.adding_ep_content_id)
async def add_ep_get_content(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID raqamini kiriting!")
    content = await get_content(int(m.text))
    if not content:
        await state.clear()
        return await m.answer("❌ Bunday ID li kontent topilmadi!")
    await state.update_data(ep_content_id=content['id'])
    episodes = await get_episodes(content['id'])
    existing = ", ".join(str(ep['episode_number']) for ep in episodes) if episodes else "yo'q"
    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
    await m.answer(
        f"{emoji} <b>{content['name']}</b>\n\n"
        f"📺 Mavjud qismlar: {existing}\n\n"
        f"🔢 Qaysi <b>raqamli qism</b> qo'shmoqchisiz? (masalan: 1)",
        parse_mode="HTML"
    )
    await state.set_state(BotState.adding_ep_number)

@dp.message(BotState.adding_ep_number)
async def add_ep_get_number(m: Message, state: FSMContext):
    if not m.text.isdigit() or int(m.text) < 1:
        return await m.answer("⚠️ Musbat son kiriting!")
    await state.update_data(ep_number=int(m.text))
    await m.answer(f"🎬 <b>{m.text}-qism</b> uchun <b>video faylni yuboring:</b>", parse_mode="HTML")
    await state.set_state(BotState.adding_ep_file)

@dp.message(BotState.adding_ep_file, F.video)
async def add_ep_file(m: Message, state: FSMContext):
    data = await state.get_data()
    content_id = data['ep_content_id']
    ep_num = data['ep_number']
    await add_episode(content_id, ep_num, m.video.file_id)
    await state.clear()
    content = await get_content(content_id)
    episodes = await get_episodes(content_id)
    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
    await m.answer(
        f"✅ <b>{ep_num}-qism qo'shildi!</b>\n\n"
        f"{emoji} <b>{content['name']}</b>\n"
        f"📺 Jami qismlar: <b>{len(episodes)} ta</b>\n\n"
        f"➕ Yana qism qo'shish uchun: Admin Panel → 📺 Qism Qo'shish",
        parse_mode="HTML", reply_markup=get_admin_kb()
    )

@dp.message(BotState.adding_ep_file)
async def add_ep_file_wrong(m: Message, state: FSMContext):
    await m.answer("⚠️ Iltimos, video fayl yuboring!")

# ==========================================
# QISM O'CHIRISH
# ==========================================
@dp.callback_query(F.data == "adm_del_episode")
async def del_ep_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("🗑 <b>Qism o'chirish</b>\n\n🆔 Kontent <b>ID sini</b> kiriting:", parse_mode="HTML")
    await state.set_state(BotState.del_ep_content_id)

@dp.message(BotState.del_ep_content_id)
async def del_ep_get_content(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat ID kiriting!")
    content = await get_content(int(m.text))
    if not content:
        await state.clear()
        return await m.answer("❌ Bunday ID li kontent topilmadi!")
    episodes = await get_episodes(content['id'])
    if not episodes:
        await state.clear()
        return await m.answer("📭 Bu kontentda qismlar yo'q!")
    await state.update_data(ep_del_content_id=content['id'])
    nums = ", ".join(str(ep['episode_number']) for ep in episodes)
    emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
    await m.answer(
        f"{emoji} <b>{content['name']}</b>\n📺 Qismlar: {nums}\n\n🔢 O'chirmoqchi bo'lgan qism raqamini kiriting:",
        parse_mode="HTML"
    )
    await state.set_state(BotState.del_ep_number)

@dp.message(BotState.del_ep_number)
async def del_ep_process(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    data = await state.get_data()
    content_id = data['ep_del_content_id']
    ep_num = int(m.text)
    ep = await get_episode(content_id, ep_num)
    if not ep:
        await state.clear()
        return await m.answer(f"❌ {ep_num}-qism topilmadi!")
    await delete_episode(content_id, ep_num)
    await state.clear()
    await m.answer(f"✅ <b>{ep_num}-qism o'chirildi!</b>", parse_mode="HTML", reply_markup=get_admin_kb())

# ==========================================
# OBUNA LOGLARI
# ==========================================
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
    text = "📋 <b>Oxirgi Obuna Hodisalari</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for log in logs:
        emoji = emojis.get(log['event'], '❓')
        t = log['event_time'].strftime("%m-%d %H:%M") if log['event_time'] else ''
        text += f"{emoji} <b>{log['user_name']}</b> (<code>{log['user_id']}</code>)\n   📌 {log['channel_title']} | {t}\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except:
        await bot.send_message(c.from_user.id, text, parse_mode="HTML")

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
    text = "👥 <b>FOYDALANUVCHILAR</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(users, 1):
        s = "🚫" if u['is_banned'] else "✅"
        text += f"{i}. {s} <b>{u['name']}</b>\n   🔑 <code>{u['user_id']}</code> | 💰 {u['coins']} | 📅 {u['joined_at']}\n"
    text += f"\n📊 Ko'rsatildi: <b>{len(users)}</b> ta"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except:
        await bot.send_message(c.from_user.id, text, parse_mode="HTML")

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
    text = "🔔 <b>Majburiy Obuna</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    if channels:
        text += "📋 <b>Kanallar:</b>\n"
        for ch in channels:
            t = "📱 TG" if is_telegram_link(ch['link']) else "🌐 Tashqi"
            text += f"• <a href='{ch['link']}'>{ch['title']}</a> — {t}\n"
    else:
        text += "📭 Hozircha kanallar yo'q."
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data == "sub_back")
async def sub_back(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("👑 <b>Admin Panel</b>", reply_markup=get_admin_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "sub_add")
async def sub_add_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer(
        "🔗 <b>Kanal linkini yuboring:</b>\n\n"
        "📱 Telegram: <code>https://t.me/kanalnom</code>\n"
        "🌐 Tashqi: <code>https://instagram.com/nom</code>",
        parse_mode="HTML"
    )
    await state.set_state(BotState.adding_sub_link)

@dp.message(BotState.adding_sub_link)
async def sub_get_link(m: Message, state: FSMContext):
    link = m.text.strip()
    if not (link.startswith('http://') or link.startswith('https://')):
        return await m.answer("⚠️ Link http:// yoki https:// bilan boshlanishi kerak!")
    await state.update_data(sub_link=link)
    await m.answer("📝 <b>Kanal nomini kiriting:</b>", parse_mode="HTML")
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

async def broadcast_new_content(content_id: int):
    """Yangi kontent qo'shilganda barcha foydalanuvchilarga xabar yuboradi."""
    try:
        content = await get_content(content_id)
        if not content:
            return
        all_users = await get_all_users()
        emoji = TYPE_EMOJI.get(content['content_type'], '🎬')
        type_name = TYPE_NAME.get(content['content_type'], 'Kontent')
        status_emoji = "✅" if content['status'] == 'Tugallangan' else "🔄"

        if content['price'] > 0:
            price_text = f"💎 {content['price']} coin"
        else:
            price_text = "🆓 Bepul"

        text = (
            f"🆕✨ <b>YANGI {type_name.upper()} QO'SHILDI!</b> ✨🆕\n\n"
            f"{emoji} <b>{content['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Yil: {content['year'] or '-'}\n"
            f"🎭 Janr: {content['genre'] or '-'}\n"
            f"📺 Sifat: {content['quality'] or '-'}\n"
            f"🎙 Ovoz: {content['dubbing'] or '-'}\n"
            f"📌 Holat: {status_emoji} {content['status']}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{price_text}\n"
            f"🆔 Kod: <code>{content['id']}</code>\n\n"
            f"🎬 Ko'rish uchun — <b>🎟 Kino Sotib Olish</b> tugmasini bosing!"
        )

        count = 0
        for u in all_users:
            if u['user_id'] == ADMIN_ID:
                continue
            try:
                if content['poster_file_id']:
                    await bot.send_photo(u['user_id'], content['poster_file_id'],
                                         caption=text, parse_mode="HTML")
                else:
                    await bot.send_message(u['user_id'], text, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)
            except:
                pass

        logger.info(f"Yangi kontent xabari {count} ta foydalanuvchiga yuborildi")
        try:
            await bot.send_message(ADMIN_ID, f"✅ Yangilik xabari <b>{count}</b> ta foydalanuvchiga yuborildi!", parse_mode="HTML")
        except:
            pass
    except Exception as e:
        logger.error(f"broadcast_new_content xato: {e}")
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
    await c.message.edit_text("🗑 <b>O'chirmoqchi bo'lgan kanalni tanlang:</b>", reply_markup=kb.as_markup(), parse_mode="HTML")

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
    text = "🗑 <b>Kanal tanlang:</b>" if channels else "📭 <b>Barcha kanallar o'chirildi.</b>"
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ================= COIN QO'SHISH =================
@dp.callback_query(F.data == "adm_add_coin")
async def add_coin_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💰 Foydalanuvchi <b>ID</b> sini kiriting:", parse_mode="HTML")
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
    await m.answer(f"👤 <b>{user['name']}</b> | 💰 {user['coins']} coin\n\nQancha coin qo'shmoqchisiz?", parse_mode="HTML")
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
    await m.answer(f"✅ <b>+{amount} coin</b> qo'shildi!\n💰 Yangi balans: <b>{updated['coins']} coin</b>", parse_mode="HTML", reply_markup=get_admin_kb())
    try:
        await bot.send_message(uid, f"🎉 Sizga <b>+{amount} coin</b> qo'shildi!\n💰 Balans: <b>{updated['coins']} coin</b>", parse_mode="HTML")
    except:
        pass

# ================= COIN OLISH =================
@dp.callback_query(F.data == "adm_remove_coin")
async def remove_coin_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("💸 Foydalanuvchi <b>ID</b> sini kiriting:", parse_mode="HTML")
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
    await m.answer(f"👤 <b>{user['name']}</b> | 💰 {user['coins']} coin\n\nQancha coin olmoqchisiz?", parse_mode="HTML")
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
        return await m.answer(f"⚠️ Foydalanuvchida faqat {user['coins']} coin bor!", parse_mode="HTML", reply_markup=get_admin_kb())
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins = coins - $1 WHERE user_id=$2", amount, uid)
    updated = await get_user(uid)
    await state.clear()
    await m.answer(f"✅ <b>-{amount} coin</b> yechildi!\n💰 Yangi balans: <b>{updated['coins']} coin</b>", parse_mode="HTML", reply_markup=get_admin_kb())
    try:
        await bot.send_message(uid, f"⚠️ Sizdan <b>-{amount} coin</b> yechildi!\n💰 Balans: <b>{updated['coins']} coin</b>", parse_mode="HTML")
    except:
        pass

# ================= REKLAMA =================
@dp.callback_query(F.data == "adm_broadcast")
async def broadcast_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("📢 <b>Yubormoqchi bo'lgan xabarni yuboring:</b>", parse_mode="HTML")
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
    await status_msg.edit_text(f"✅ <b>Reklama yuborildi!</b>\n\n📨 Muvaffaqiyatli: <b>{count}</b>\n❌ Yuborilmagan: <b>{failed}</b>", parse_mode="HTML")

# ================= BLOKLASH =================
@dp.callback_query(F.data == "adm_ban")
async def ban_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("🚫 Bloklash uchun foydalanuvchi <b>ID</b> sini kiriting:", parse_mode="HTML")
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
    await m.answer(f"✅ Foydalanuvchi (ID: <code>{uid}</code>) bloklandi!", parse_mode="HTML", reply_markup=get_admin_kb())

# ================= BLOKDAN CHIQARISH =================
@dp.callback_query(F.data == "adm_unban")
async def unban_start(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await c.message.answer("✅ Blokdan chiqarish uchun foydalanuvchi <b>ID</b> sini kiriting:", parse_mode="HTML")
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
    await m.answer(f"✅ Foydalanuvchi (ID: <code>{uid}</code>) blokdan chiqarildi!", parse_mode="HTML", reply_markup=get_admin_kb())

# ================= ADMIN CHAT =================
@dp.callback_query(F.data == "adm_start_chat")
async def admin_chat_init(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await state.set_state(BotState.admin_chat_target)
    await c.message.answer(
        "💬 <b>Gaplashmoqchi bo'lgan foydalanuvchi ID sini kiriting:</b>\n\n"
        "<i>(Foydalanuvchi 'Hisobim' bo'limida ID sini ko'rishi mumkin)</i>",
        parse_mode="HTML"
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
        return await m.answer(f"❌ ID: <code>{target_id}</code> foydalanuvchi topilmadi!", parse_mode="HTML")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"chat_yes_{ADMIN_ID}")
    kb.button(text="❌ Yo'q, rad etaman", callback_data=f"chat_no_{ADMIN_ID}")
    kb.adjust(1)
    try:
        await bot.send_message(
            target_id, "🔔 <b>Admin siz bilan bog'lanmoqchi!</b>\n\nSuhbatga rozimisiz?",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
        await state.set_state(BotState.in_active_chat)
        await state.update_data(chat_with=target_id, is_user_side=False)
        await m.answer(
            f"✅ So'rov yuborildi!\n\n👤 <b>{target_user['name']}</b> | ID: <code>{target_id}</code>\n\n⏳ Javob kutilmoqda...\nBekor qilish: /stop",
            parse_mode="HTML", reply_markup=get_admin_end_chat_kb()
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
    await c.message.edit_text("✅ <b>Aloqa o'rnatildi!</b>\n\n💬 Xabaringizni yozing.\nTugatish: /stop", parse_mode="HTML")
    try:
        await bot.send_message(
            admin_id,
            f"✅ <b>Foydalanuvchi ({c.from_user.id}) suhbatga kirdi!</b>\nXabar yubora olasiz.\nTugatish: /stop",
            parse_mode="HTML", reply_markup=get_admin_end_chat_kb()
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
    # Faqat admin tugatishi mumkin
    if c.from_user.id != ADMIN_ID:
        return await c.answer("❌ Bu tugma faqat admin uchun!", show_alert=True)
    await c.answer()
    data = await state.get_data()
    partner = data.get("chat_with")
    await state.clear()
    try:
        await c.message.edit_text("🔴 <b>Aloqa tugadi.</b>", parse_mode="HTML")
    except:
        pass
    await bot.send_message(c.from_user.id, "📴 Suhbat yakunlandi.", reply_markup=get_admin_kb())
    if partner:
        try:
            await bot.send_message(
                partner,
                "📴 Admin suhbatni yakunladi.",
                reply_markup=get_main_kb(partner)
            )
        except:
            pass

# ================= ID orqali kontent ko'rish =================
@dp.message(F.text.regexp(r'^\d+$'))
async def content_by_id(m: Message):
    """Foydalanuvchi raqam yuborganda kontent qidiradi."""
    user = await get_user(m.from_user.id)
    if not user:
        return
    if user['is_banned']:
        return
    content_id = int(m.text)
    content = await get_content(content_id)
    if content:
        not_sub = await check_all_subs(m.from_user.id, user['name'])
        if not_sub:
            return await send_sub_msg(m.from_user.id, not_sub)
        await show_content_detail(m.from_user.id, content_id)
    else:
        await m.answer(f"❌ ID: <b>{content_id}</b> — bunday kontent topilmadi!\n\n💡 To'g'ri ID ni ro'yxatdan tekshiring.", parse_mode="HTML")

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
