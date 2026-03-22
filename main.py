import asyncio, os, logging, sys, json, re, httpx
from datetime import datetime, date, timedelta
from threading import Thread
from flask import Flask
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove, CallbackQuery, Message, InlineKeyboardMarkup
)

# ═══════════════════════════════════════════════════
#  KONFIGURATSIYA
# ═══════════════════════════════════════════════════
TOKEN        = os.environ.get("BOT_TOKEN",    "8366692220:AAHKoIz6A__Ll1V5yvcjcjWVaFr5Xcf9HQQ")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "7492227388"))
ADMIN_PASS   = os.environ.get("ADMIN_PASS",   "456")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://kino_bot_db_duf5_user:MNiazQVid4iljB2dvN7LeJ8XfYFdnaJQ@dpg-d672bp8gjchc738fpdm0-a/kino_bot_db_duf5")
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "AIzaSyBAUbeVvAboH4jOtE6jBPzIgiJg9zssjhg")

AI_FREE_LIMIT    = 10
AI_PREMIUM_LIMIT = 50
AI_VIP_LIMIT     = 999

VIP_PLANS = {
    "premium_day":   {"name": "⭐ Premium 1 kun",   "days": 1,   "coins": 50,   "label": "premium"},
    "premium_week":  {"name": "⭐ Premium 1 hafta",  "days": 7,   "coins": 200,  "label": "premium"},
    "premium_month": {"name": "⭐ Premium 1 oy",     "days": 30,  "coins": 500,  "label": "premium"},
    "premium_year":  {"name": "⭐ Premium 1 yil",    "days": 365, "coins": 3000, "label": "premium"},
    "vip_day":       {"name": "👑 VIP 1 kun",        "days": 1,   "coins": 100,  "label": "vip"},
    "vip_week":      {"name": "👑 VIP 1 hafta",      "days": 7,   "coins": 400,  "label": "vip"},
    "vip_month":     {"name": "👑 VIP 1 oy",         "days": 30,  "coins": 1000, "label": "vip"},
    "vip_year":      {"name": "👑 VIP 1 yil",        "days": 365, "coins": 6000, "label": "vip"},
}

# ═══════════════════════════════════════════════════
#  FLASK
# ═══════════════════════════════════════════════════
app = Flask('')

@app.route('/')
def home():
    return "✅ CineBot 2026 ishlayapti!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ═══════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp  = Dispatcher()

# ═══════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      BIGINT PRIMARY KEY,
                name         TEXT NOT NULL,
                phone        TEXT,
                coins        INTEGER   DEFAULT 100,
                referrer_id  BIGINT    DEFAULT NULL,
                joined_at    DATE      DEFAULT CURRENT_DATE,
                last_bonus   DATE      DEFAULT NULL,
                is_banned    BOOLEAN   DEFAULT FALSE,
                vip_type     TEXT      DEFAULT NULL,
                vip_expires  TIMESTAMP DEFAULT NULL,
                ai_used_today INTEGER  DEFAULT 0,
                ai_last_date DATE      DEFAULT NULL
            )
        """)
        for col, defn in [
            ("vip_type",      "TEXT DEFAULT NULL"),
            ("vip_expires",   "TIMESTAMP DEFAULT NULL"),
            ("ai_used_today", "INTEGER DEFAULT 0"),
            ("ai_last_date",  "DATE DEFAULT NULL"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {defn}")
            except:
                pass
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                year        TEXT,
                description TEXT,
                file_id     TEXT,
                price       INTEGER   DEFAULT 0,
                genre       TEXT      DEFAULT NULL,
                added_at    TIMESTAMP DEFAULT NOW()
            )
        """)
        try:
            await conn.execute("ALTER TABLE movies ADD COLUMN IF NOT EXISTS genre TEXT DEFAULT NULL")
        except:
            pass
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id        SERIAL PRIMARY KEY,
                user_id   BIGINT,
                movie_id  INTEGER,
                bought_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS required_channels (
                id       SERIAL PRIMARY KEY,
                link     TEXT NOT NULL,
                title    TEXT DEFAULT 'Kanal',
                added_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_sub_status (
                user_id         BIGINT,
                channel_id      INTEGER,
                is_subscribed   BOOLEAN   DEFAULT FALSE,
                last_checked    TIMESTAMP DEFAULT NOW(),
                subscribed_at   TIMESTAMP,
                unsubscribed_at TIMESTAMP,
                PRIMARY KEY (user_id, channel_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sub_logs (
                id            SERIAL PRIMARY KEY,
                user_id       BIGINT,
                user_name     TEXT,
                channel_id    INTEGER,
                channel_title TEXT,
                channel_link  TEXT,
                event         TEXT,
                event_time    TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_sessions (
                user_id    BIGINT PRIMARY KEY,
                context    TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vip_history (
                id         SERIAL PRIMARY KEY,
                user_id    BIGINT,
                vip_type   TEXT,
                given_by   TEXT,
                started_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP,
                coins_paid INTEGER DEFAULT 0
            )
        """)
    logger.info("✅ CineBot 2026 DB tayyor!")

# ═══════════════════════════════════════════════════
#  DB FUNKSIYALAR
# ═══════════════════════════════════════════════════
async def get_user(uid):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)

async def create_user(uid, name, phone=None, referrer_id=None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id,name,phone,coins,referrer_id)
            VALUES ($1,$2,$3,100,$4) ON CONFLICT (user_id) DO NOTHING
        """, uid, name, phone, referrer_id)
        if referrer_id:
            await conn.execute("UPDATE users SET coins=coins+50 WHERE user_id=$1", referrer_id)

async def get_all_users():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users WHERE is_banned=FALSE")

async def get_movie(mid):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM movies WHERE id=$1", mid)

async def get_all_movies():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM movies ORDER BY id DESC")

async def add_movie(name, year, desc, file_id, price, genre=None):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO movies (name,year,description,file_id,price,genre)
            VALUES ($1,$2,$3,$4,$5,$6) RETURNING id
        """, name, year, desc, file_id, price, genre)
        return row['id']

async def user_has_movie(uid, mid):
    async with db_pool.acquire() as conn:
        r = await conn.fetchrow("SELECT id FROM purchases WHERE user_id=$1 AND movie_id=$2", uid, mid)
        return r is not None

async def buy_movie_db(uid, mid, price):
    async with db_pool.acquire() as conn:
        u = await conn.fetchrow("SELECT coins FROM users WHERE user_id=$1", uid)
        if not u or u['coins'] < price:
            return False
        await conn.execute("UPDATE users SET coins=coins-$1 WHERE user_id=$2", price, uid)
        await conn.execute("INSERT INTO purchases (user_id,movie_id) VALUES ($1,$2)", uid, mid)
        return True

async def get_stats():
    async with db_pool.acquire() as conn:
        return {
            "total_users":     await conn.fetchval("SELECT COUNT(*) FROM users"),
            "banned_users":    await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned=TRUE"),
            "total_movies":    await conn.fetchval("SELECT COUNT(*) FROM movies"),
            "total_purchases": await conn.fetchval("SELECT COUNT(*) FROM purchases"),
            "today_users":     await conn.fetchval("SELECT COUNT(*) FROM users WHERE joined_at=CURRENT_DATE"),
            "vip_users":       await conn.fetchval("SELECT COUNT(*) FROM users WHERE vip_type IS NOT NULL AND (vip_expires IS NULL OR vip_expires>NOW())"),
            "total_ai_msgs":   await conn.fetchval("SELECT COUNT(*) FROM ai_sessions"),
        }

# ═══════════════════════════════════════════════════
#  VIP TIZIM
# ═══════════════════════════════════════════════════
async def get_vip_status(uid):
    u = await get_user(uid)
    if not u or not u['vip_type']:
        return None
    if u['vip_expires'] and u['vip_expires'] < datetime.now():
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET vip_type=NULL,vip_expires=NULL WHERE user_id=$1", uid)
        return None
    return u['vip_type']

async def set_vip(uid, vip_label, days, given_by="admin", coins_paid=0):
    expires = datetime.now() + timedelta(days=days)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET vip_type=$1,vip_expires=$2 WHERE user_id=$3", vip_label, expires, uid)
        await conn.execute("""
            INSERT INTO vip_history (user_id,vip_type,given_by,expires_at,coins_paid)
            VALUES ($1,$2,$3,$4,$5)
        """, uid, vip_label, given_by, expires, coins_paid)
    return expires

async def buy_vip_coins(uid, plan_key):
    plan = VIP_PLANS.get(plan_key)
    if not plan:
        return False, "Noma'lum plan"
    u = await get_user(uid)
    if not u:
        return False, "Foydalanuvchi topilmadi"
    if u['coins'] < plan['coins']:
        return False, f"Yetarli coin yo'q. Kerak: {plan['coins']}, sizda: {u['coins']}"
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins=coins-$1 WHERE user_id=$2", plan['coins'], uid)
    expires = await set_vip(uid, plan['label'], plan['days'], "coins", plan['coins'])
    return True, expires

def get_ai_limit(vip):
    if vip == 'vip':     return AI_VIP_LIMIT
    if vip == 'premium': return AI_PREMIUM_LIMIT
    return AI_FREE_LIMIT

async def check_ai_limit(uid):
    u = await get_user(uid)
    vip = await get_vip_status(uid)
    limit = get_ai_limit(vip)
    today = date.today()
    used = u['ai_used_today'] if u and u['ai_last_date'] == today else 0
    return used < limit, used, limit

async def increment_ai(uid):
    today = date.today()
    async with db_pool.acquire() as conn:
        u = await conn.fetchrow("SELECT ai_used_today,ai_last_date FROM users WHERE user_id=$1", uid)
        if u and u['ai_last_date'] == today:
            await conn.execute("UPDATE users SET ai_used_today=ai_used_today+1 WHERE user_id=$1", uid)
        else:
            await conn.execute("UPDATE users SET ai_used_today=1,ai_last_date=$1 WHERE user_id=$2", today, uid)

# ═══════════════════════════════════════════════════
#  GEMINI AI
# ═══════════════════════════════════════════════════
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
SYSTEM_PROMPT = (
    "Sen CineBot — Uzbek tilidagi kino yordamchisisiz. "
    "Foydalanuvchilarga kinolar haqida ma'lumot berasan, tavsiya qilasan, kino tavsiflarini yozasan. "
    "Doim uzbek tilida javob ber. Qisqa, aniq va do'stona bo'l. "
    "Agar kino so'rashsa — janr, yil, aktyorlar haqida ma'lumot ber."
)

async def get_ai_context(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT context FROM ai_sessions WHERE user_id=$1", uid)
        if row:
            try:
                return json.loads(row['context'])
            except:
                return []
        return []

async def save_ai_context(uid, ctx):
    ctx = ctx[-20:]
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ai_sessions (user_id,context,updated_at)
            VALUES ($1,$2,NOW())
            ON CONFLICT (user_id) DO UPDATE SET context=$2,updated_at=NOW()
        """, uid, json.dumps(ctx, ensure_ascii=False))

async def clear_ai_context(uid):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM ai_sessions WHERE user_id=$1", uid)

async def ask_gemini(uid, text):
    if not GEMINI_KEY:
        return "❌ Gemini API kaliti sozlanmagan. GEMINI_API_KEY ni muhit o'zgaruvchisiga qo'shing."
    ctx = await get_ai_context(uid)
    ctx.append({"role": "user", "parts": [{"text": text}]})
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": ctx,
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 1024}
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=payload,
                                     headers={"Content-Type": "application/json"})
            data = resp.json()
        if "candidates" in data:
            answer = data["candidates"][0]["content"]["parts"][0]["text"]
            ctx.append({"role": "model", "parts": [{"text": answer}]})
            await save_ai_context(uid, ctx)
            return answer
        elif "error" in data:
            return f"❌ AI xatosi: {data['error'].get('message','Noma\'lum')}"
        return "❌ AI javob bermadi."
    except httpx.TimeoutException:
        return "⏳ AI vaqt limiti. Qayta urinib ko'ring."
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        return "❌ AI bilan ulanishda xato."

async def gemini_auto_desc(name, year):
    if not GEMINI_KEY:
        return "Tavsif mavjud emas"
    payload = {
        "contents": [{"role":"user","parts":[{"text":
            f"'{name}' ({year}) kinosi haqida 2-3 jumlali qisqa uzbek tilidagi tavsif yoz. Faqat tavsifni yoz."
        }]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 256}
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=payload,
                                     headers={"Content-Type":"application/json"})
            data = resp.json()
        if "candidates" in data:
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except:
        pass
    return "Tavsif mavjud emas"

# ═══════════════════════════════════════════════════
#  MAJBURIY OBUNA
# ═══════════════════════════════════════════════════
async def get_req_channels():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM required_channels ORDER BY id")

async def add_req_channel(link, title="Kanal"):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO required_channels (link,title) VALUES ($1,$2)", link, title)

async def remove_req_channel(ch_id):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM required_channels WHERE id=$1", ch_id)
        await conn.execute("DELETE FROM user_sub_status WHERE channel_id=$1", ch_id)

def is_tg_link(link):
    return 't.me/' in link or 'telegram.me/' in link

def extract_tg_uname(link):
    try:
        part = link.split('t.me/')[-1] if 't.me/' in link else link.split('telegram.me/')[-1]
        part = part.strip().strip('/')
        if part.startswith('+') or '/' in part or not part:
            return None
        return f"@{part}"
    except:
        return None

async def check_tg_sub(uid, link):
    uname = extract_tg_uname(link)
    if not uname:
        return False
    try:
        m = await bot.get_chat_member(uname, uid)
        return m.status not in ('left','kicked','banned')
    except Exception as e:
        logger.warning(f"get_chat_member xato ({uname}): {e}")
        return False

async def get_ext_confirmed(uid, ch_id):
    async with db_pool.acquire() as conn:
        r = await conn.fetchrow("SELECT is_subscribed FROM user_sub_status WHERE user_id=$1 AND channel_id=$2", uid, ch_id)
        return bool(r and r['is_subscribed'])

async def set_ext_confirmed(uid, ch_id):
    now = datetime.now()
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_sub_status (user_id,channel_id,is_subscribed,last_checked,subscribed_at)
            VALUES ($1,$2,TRUE,$3,$3)
            ON CONFLICT (user_id,channel_id) DO UPDATE
            SET is_subscribed=TRUE,last_checked=$3,subscribed_at=COALESCE(user_sub_status.subscribed_at,$3)
        """, uid, ch_id, now)

async def track_sub(uid, uname, ch, is_sub):
    ch_id=ch['id']; ch_title=ch['title']; ch_link=ch['link']; now=datetime.now()
    async with db_pool.acquire() as conn:
        prev = await conn.fetchrow("SELECT is_subscribed FROM user_sub_status WHERE user_id=$1 AND channel_id=$2", uid, ch_id)
        prev_s = prev['is_subscribed'] if prev else None
        if is_sub:
            await conn.execute("""
                INSERT INTO user_sub_status (user_id,channel_id,is_subscribed,last_checked,subscribed_at)
                VALUES ($1,$2,TRUE,$3,$3)
                ON CONFLICT (user_id,channel_id) DO UPDATE
                SET is_subscribed=TRUE,last_checked=$3,
                    subscribed_at=CASE WHEN user_sub_status.is_subscribed=FALSE OR user_sub_status.subscribed_at IS NULL
                                       THEN $3 ELSE user_sub_status.subscribed_at END
            """, uid, ch_id, now)
        else:
            await conn.execute("""
                INSERT INTO user_sub_status (user_id,channel_id,is_subscribed,last_checked,unsubscribed_at)
                VALUES ($1,$2,FALSE,$3,$3)
                ON CONFLICT (user_id,channel_id) DO UPDATE
                SET is_subscribed=FALSE,last_checked=$3,
                    unsubscribed_at=CASE WHEN user_sub_status.is_subscribed=TRUE
                                         THEN $3 ELSE user_sub_status.unsubscribed_at END
            """, uid, ch_id, now)
        event = None
        if prev_s is None and is_sub:       event = 'first_subscribed'
        elif prev_s is None and not is_sub: event = 'checked_not_subscribed'
        elif prev_s is False and is_sub:    event = 'subscribed'
        elif prev_s is True and not is_sub: event = 'unsubscribed'
        if event:
            await conn.execute("""
                INSERT INTO sub_logs (user_id,user_name,channel_id,channel_title,channel_link,event)
                VALUES ($1,$2,$3,$4,$5,$6)
            """, uid, uname, ch_id, ch_title, ch_link, event)
            asyncio.create_task(_notify_sub(uid, uname, ch_title, ch_link, event))

async def _notify_sub(uid, uname, ch_title, ch_link, event):
    emj = {'first_subscribed':'🆕✅','subscribed':'✅','checked_not_subscribed':'❌','unsubscribed':'⚠️🔴'}.get(event,'❓')
    lbl = {'first_subscribed':"birinchi obuna",'subscribed':"qayta obuna",
           'checked_not_subscribed':"tekshirdi, emas",'unsubscribed':"OBUNANI OLIB TASHLADI!"}.get(event,event)
    try:
        await bot.send_message(ADMIN_ID,
            f"{emj} <b>Obuna hodisasi</b> | {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"👤 <b>{uname}</b> (<code>{uid}</code>)\n"
            f"📌 <a href='{ch_link}'>{ch_title}</a>\n📋 <b>{lbl}</b>",
            parse_mode="HTML", disable_web_page_preview=True)
    except: pass

async def check_all_subs(uid, uname):
    channels = await get_req_channels()
    if not channels: return []
    not_sub = []
    for ch in channels:
        is_sub = await check_tg_sub(uid, ch['link']) if is_tg_link(ch['link']) else await get_ext_confirmed(uid, ch['id'])
        await track_sub(uid, uname, ch, is_sub)
        if not is_sub: not_sub.append(ch)
    return not_sub

def build_sub_kb(channels):
    kb = InlineKeyboardBuilder()
    emj = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣"]
    for i,ch in enumerate(channels):
        kb.button(text=f"{emj[i%5]} {ch['title']} — A'zo bo'lish", url=ch['link'])
    kb.button(text="✅ Obunani Tekshirish", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()

async def send_sub_msg(uid, channels):
    lines = "".join(f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n" for i,ch in enumerate(channels,1))
    text = f"⚠️ <b>Botdan foydalanish uchun kanallarga a'zo bo'ling:</b>\n\n{lines}\nA'zo bo'lgach ✅ <b>Obunani Tekshirish</b> tugmasini bosing."
    try:
        await bot.send_message(uid, text, reply_markup=build_sub_kb(channels), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        logger.warning(f"send_sub_msg xato: {e}")

async def sub_guard(m: Message):
    u = await get_user(m.from_user.id)
    if not u: return True
    if u['is_banned']: return True
    ns = await check_all_subs(m.from_user.id, u['name'])
    if ns:
        await send_sub_msg(m.from_user.id, ns)
        return False
    return True

# ═══════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ═══════════════════════════════════════════════════
def vip_badge(vip):
    if vip == 'vip':     return "👑"
    if vip == 'premium': return "⭐"
    return "👤"

def get_main_kb(uid, vip=None):
    b = ReplyKeyboardBuilder()
    b.button(text="🎬 Kinolar Ro'yxati")
    b.button(text="🎟 Kino Sotib Olish")
    b.button(text="💰 Hisobim")
    b.button(text="🎁 Kunlik Bonus")
    b.button(text="👥 Do'st Taklif")
    b.button(text="🤖 AI Suhbat")
    b.button(text="✍️ Adminga Yozish")
    b.button(text="👑 VIP / Premium")
    if uid == ADMIN_ID:
        b.button(text="🛠 Admin Panel")
        b.button(text="📊 Statistika")
    b.adjust(2)
    return b.as_markup(resize_keyboard=True)

def get_admin_kb():
    b = InlineKeyboardBuilder()
    b.button(text="➕ Kino Qo'shish",         callback_data="adm_add_kino")
    b.button(text="🗑 Kino O'chirish",         callback_data="adm_del_kino")
    b.button(text="💰 Coin Qo'shish",          callback_data="adm_add_coin")
    b.button(text="💸 Coin Olish",             callback_data="adm_rm_coin")
    b.button(text="👑 VIP Berish",             callback_data="adm_give_vip")
    b.button(text="📢 Reklama",                callback_data="adm_broadcast")
    b.button(text="🚫 Bloklash",               callback_data="adm_ban")
    b.button(text="✅ Blokdan Chiqarish",       callback_data="adm_unban")
    b.button(text="💬 Foydalanuvchi bilan Chat",callback_data="adm_start_chat")
    b.button(text="📞 Qo'ng'iroq",             callback_data="adm_call_user")
    b.button(text="📊 To'liq Statistika",      callback_data="adm_full_stats")
    b.button(text="🔔 Majburiy Obuna",         callback_data="adm_subscription")
    b.button(text="👥 Foydalanuvchilar",       callback_data="adm_users")
    b.button(text="📋 Obuna Loglari",          callback_data="adm_sub_logs")
    b.button(text="🤖 AI Sozlamalari",         callback_data="adm_ai_settings")
    b.button(text="❌ Yopish",                  callback_data="adm_close")
    b.adjust(2)
    return b.as_markup()

def get_vip_buy_kb():
    b = InlineKeyboardBuilder()
    for k, p in VIP_PLANS.items():
        b.button(text=f"{p['name']}  —  {p['coins']} coin", callback_data=f"vip_buy_{k}")
    b.button(text="❌ Yopish", callback_data="adm_close")
    b.adjust(1)
    return b.as_markup()

def get_end_chat_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🔴 Aloqani Tugatish", callback_data="end_chat")
    return b.as_markup()

# ═══════════════════════════════════════════════════
#  FSM
# ═══════════════════════════════════════════════════
class S(StatesGroup):
    reg_name   = State()
    reg_phone  = State()
    admin_auth = State()
    kino_info  = State()
    kino_file  = State()
    buy_movie  = State()
    broadcast  = State()
    ban_id     = State()
    unban_id   = State()
    chat_target= State()
    active_chat= State()
    coin_add_id= State(); coin_add_amt= State()
    coin_rm_id = State(); coin_rm_amt = State()
    sub_link   = State(); sub_title   = State()
    call_id    = State()
    ai_chat    = State()
    vip_give_id= State()

# ═══════════════════════════════════════════════════
#  HANDLERS — START
# ═══════════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    u = await get_user(m.from_user.id)
    ref_id = None
    args = m.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            ref_id = int(args[1][3:])
            if ref_id == m.from_user.id: ref_id = None
        except: pass
    if u:
        if u['is_banned']:
            return await m.answer("🚫 Siz botdan bloklangansiz.")
        ns = await check_all_subs(m.from_user.id, u['name'])
        if ns: return await send_sub_msg(m.from_user.id, ns)
        vip = await get_vip_status(m.from_user.id)
        badge = vip_badge(vip)
        vip_txt = f"\n{'👑 VIP' if vip=='vip' else '⭐ Premium'} aktiv ✅" if vip else ""
        return await m.answer(
            f"🎬 *Xush kelibsiz, {badge} {u['name']}!*\n💰 Balans: *{u['coins']} coin*{vip_txt}\n🤖 AI Suhbat — kino haqida hamma narsani so'rang!",
            reply_markup=get_main_kb(m.from_user.id, vip), parse_mode="Markdown")
    await state.update_data(ref_id=ref_id)
    await m.answer("👋 *CineBot 2026 ga xush kelibsiz!*\n🎬 Kinolar | 🤖 AI | 👑 VIP\n\nIsmingizni kiriting:", parse_mode="Markdown")
    await state.set_state(S.reg_name)

@dp.callback_query(F.data == "check_sub")
async def check_sub_cb(c: CallbackQuery):
    await c.answer("⏳ Tekshirilmoqda...")
    u = await get_user(c.from_user.id)
    if not u: return await c.message.answer("❌ /start")
    if u['is_banned']: return await c.message.answer("🚫 Bloklangansiz.")
    chs = await get_req_channels(); not_sub = []
    for ch in chs:
        if is_tg_link(ch['link']): is_sub = await check_tg_sub(c.from_user.id, ch['link'])
        else: is_sub = True; await set_ext_confirmed(c.from_user.id, ch['id'])
        await track_sub(c.from_user.id, u['name'], ch, is_sub)
        if not is_sub: not_sub.append(ch)
    if not not_sub:
        try: await c.message.edit_text("✅ <b>Barcha kanallarga a'zo bo'ldingiz!</b>", parse_mode="HTML")
        except: pass
        vip = await get_vip_status(c.from_user.id)
        await bot.send_message(c.from_user.id, f"🎉 <b>Xush kelibsiz, {u['name']}!</b>\n💰 {u['coins']} coin",
            reply_markup=get_main_kb(c.from_user.id, vip), parse_mode="HTML")
    else:
        lines = "".join(f"{i}. <a href='{ch['link']}'>{ch['title']}</a>\n" for i,ch in enumerate(not_sub,1))
        txt = f"❌ <b>Hali {len(not_sub)} ta kanalga a'zo bo'lmadingiz:</b>\n\n{lines}\nA'zo bo'lib, <b>✅ Tekshirish</b> tugmasini qayta bosing."
        try: await c.message.edit_text(txt, reply_markup=build_sub_kb(not_sub), parse_mode="HTML", disable_web_page_preview=True)
        except: await bot.send_message(c.from_user.id, txt, reply_markup=build_sub_kb(not_sub), parse_mode="HTML", disable_web_page_preview=True)

# ═══════════════════════════════════════════════════
#  RO'YXATDAN O'TISH
# ═══════════════════════════════════════════════════
@dp.message(S.reg_name)
async def reg_name(m: Message, state: FSMContext):
    if not m.text or len(m.text) < 2: return await m.answer("⚠️ Ism kamida 2 harf!")
    await state.update_data(name=m.text.strip())
    kb = ReplyKeyboardBuilder()
    kb.button(text="📱 Raqamni Yuborish", request_contact=True)
    kb.button(text="⏭ O'tkazib yuborish")
    kb.adjust(1)
    await m.answer("📱 Telefon raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(S.reg_phone)

async def finish_reg(m: Message, state: FSMContext, name: str, phone=None):
    data = await state.get_data()
    await create_user(m.from_user.id, name, phone, data.get('ref_id'))
    await state.clear()
    asyncio.create_task(_notify_new_user(m.from_user.id, name, phone, data.get('ref_id')))
    chs = await get_req_channels()
    if chs:
        await m.answer(f"✅ *Tabriklaymiz, {name}!*\n🎉 Ro'yxatdan o'tdingiz!\n💰 *100 coin* sovg'a!\n\n⚠️ Kanallarga a'zo bo'ling:",
            parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        ns = await check_all_subs(m.from_user.id, name)
        if ns: await send_sub_msg(m.from_user.id, ns)
    else:
        await m.answer(f"✅ *Tabriklaymiz, {name}!*\n🎉 Ro'yxatdan o'tdingiz!\n💰 *100 coin* sovg'a!\n🤖 AI Suhbat orqali kino haqida so'rang!",
            reply_markup=get_main_kb(m.from_user.id), parse_mode="Markdown")

async def _notify_new_user(uid, name, phone, ref_id):
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM users")
        ref_txt = f"\n👥 Taklif: <code>{ref_id}</code>" if ref_id else ""
        ph_txt  = f"\n📱 {phone}" if phone else ""
        await bot.send_message(ADMIN_ID,
            f"🆕 <b>Yangi foydalanuvchi!</b>\n👤 <b>{name}</b>\n🔑 <code>{uid}</code>{ph_txt}{ref_txt}\n📊 Jami: <b>{total}</b>",
            parse_mode="HTML")
    except: pass

@dp.message(S.reg_phone, F.contact)
async def reg_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_reg(m, state, data['name'], m.contact.phone_number)

@dp.message(S.reg_phone, F.text == "⏭ O'tkazib yuborish")
async def reg_skip(m: Message, state: FSMContext):
    data = await state.get_data()
    await finish_reg(m, state, data['name'])

# ═══════════════════════════════════════════════════
#  🤖 AI SUHBAT
# ═══════════════════════════════════════════════════
@dp.message(F.text == "🤖 AI Suhbat")
async def ai_chat_menu(m: Message, state: FSMContext):
    if not await sub_guard(m): return
    u = await get_user(m.from_user.id)
    if not u: return await m.answer("❌ /start")
    vip = await get_vip_status(m.from_user.id)
    can, used, limit = await check_ai_limit(m.from_user.id)
    badge = vip_badge(vip)
    vip_lbl = "VIP 👑" if vip=='vip' else ("Premium ⭐" if vip=='premium' else "Oddiy")
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Xotirani Tozalash", callback_data="ai_clear")
    kb.button(text="❌ Chiqish",            callback_data="ai_exit")
    kb.adjust(2)
    await m.answer(
        f"🤖 *Gemini AI Suhbat*\n━━━━━━━━━━━━━━━━\n\n"
        f"{badge} Daraja: *{vip_lbl}*\n📊 Bugun: *{used}/{limit}* so'rov\n\n"
        f"💬 Kino haqida so'rang:\n• Kino tavsiya\n• Kino ma'lumoti\n• Aktyorlar, rejissyor\n• Janr bo'yicha qidirish\n\n"
        f"Tugash: /stop yoki ❌ Chiqish",
        parse_mode="Markdown", reply_markup=kb.as_markup())
    await state.set_state(S.ai_chat)

@dp.callback_query(F.data == "ai_clear")
async def ai_clear_cb(c: CallbackQuery):
    await c.answer()
    await clear_ai_context(c.from_user.id)
    await c.message.answer("🗑 *AI xotirasi tozalandi!*", parse_mode="Markdown")

@dp.callback_query(F.data == "ai_exit")
async def ai_exit_cb(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    vip = await get_vip_status(c.from_user.id)
    await c.message.answer("👋 AI suhbatdan chiqdingiz.", reply_markup=get_main_kb(c.from_user.id, vip))

@dp.message(S.ai_chat)
async def ai_chat_process(m: Message, state: FSMContext):
    if m.text and m.text.lower() == "/stop":
        await state.clear()
        vip = await get_vip_status(m.from_user.id)
        return await m.answer("👋 AI suhbatdan chiqdingiz.", reply_markup=get_main_kb(m.from_user.id, vip))
    if not m.text: return await m.answer("⚠️ Faqat matn yuboring!")
    can, used, limit = await check_ai_limit(m.from_user.id)
    if not can:
        vip = await get_vip_status(m.from_user.id)
        kb = InlineKeyboardBuilder()
        kb.button(text="👑 VIP / Premium Olish", callback_data="open_vip")
        kb.adjust(1)
        return await m.answer(
            f"❌ *Kunlik limit tugadi!* ({used}/{limit})\n\n"
            f"⭐ Premium: {AI_PREMIUM_LIMIT} ta/kun\n👑 VIP: Cheksiz",
            parse_mode="Markdown", reply_markup=kb.as_markup())
    thinking = await m.answer("🤖 *AI o'ylayapti...*", parse_mode="Markdown")
    answer = await ask_gemini(m.from_user.id, m.text)
    await increment_ai(m.from_user.id)
    _, used2, lim2 = await check_ai_limit(m.from_user.id)
    try: await thinking.delete()
    except: pass
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Xotira Tozalash", callback_data="ai_clear")
    kb.button(text="❌ Chiqish",          callback_data="ai_exit")
    kb.adjust(2)
    await m.answer(f"🤖 {answer}\n\n─────────\n📊 {used2}/{lim2} so'rov", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "open_vip")
async def open_vip_cb(c: CallbackQuery):
    await c.answer()
    u = await get_user(c.from_user.id)
    await c.message.answer(
        f"👑 *VIP / Premium*\n━━━━━━━━━━━━━━━━\n\n💰 Balans: *{u['coins']} coin*\n\n"
        f"⭐ Premium: {AI_PREMIUM_LIMIT} ta AI so'rov/kun\n"
        f"👑 VIP: Cheksiz AI so'rov\n\nRejan tanlang:",
        parse_mode="Markdown", reply_markup=get_vip_buy_kb())

# ═══════════════════════════════════════════════════
#  VIP / PREMIUM
# ═══════════════════════════════════════════════════
@dp.message(F.text == "👑 VIP / Premium")
async def vip_page(m: Message):
    if not await sub_guard(m): return
    u = await get_user(m.from_user.id)
    if not u: return await m.answer("❌ /start")
    vip = await get_vip_status(m.from_user.id)
    vip_info = ""
    if vip:
        exp = u['vip_expires'].strftime("%d.%m.%Y %H:%M") if u['vip_expires'] else "Muddatsiz"
        vip_info = f"\n✅ Sizda: *{'VIP 👑' if vip=='vip' else 'Premium ⭐'}* — {exp} gacha\n"
    await m.answer(
        f"👑 *VIP / Premium*\n━━━━━━━━━━━━━━━━\n💰 Balans: *{u['coins']} coin*{vip_info}\n\n"
        f"⭐ *Premium:*\n• 🤖 AI: {AI_PREMIUM_LIMIT} ta so'rov/kun\n• Kunlik bonus: +30 coin\n\n"
        f"👑 *VIP:*\n• 🤖 AI: Cheksiz ({AI_VIP_LIMIT} ta/kun)\n• Kunlik bonus: +50 coin\n\nRejan tanlang:",
        parse_mode="Markdown", reply_markup=get_vip_buy_kb())

@dp.callback_query(F.data.startswith("vip_buy_"))
async def vip_buy(c: CallbackQuery):
    await c.answer()
    plan_key = c.data[8:]
    plan = VIP_PLANS.get(plan_key)
    if not plan: return await c.message.answer("❌ Noma'lum plan!")
    u = await get_user(c.from_user.id)
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Ha, {plan['coins']} coin to'layman", callback_data=f"vip_confirm_{plan_key}")
    kb.button(text="❌ Bekor", callback_data="adm_close")
    kb.adjust(1)
    await c.message.answer(
        f"💳 *Tasdiqlash*\n\n📦 {plan['name']}\n💰 Narx: *{plan['coins']} coin*\n💳 Sizda: *{u['coins']} coin*\n\nTasdiqlaysizmi?",
        parse_mode="Markdown", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("vip_confirm_"))
async def vip_confirm(c: CallbackQuery):
    await c.answer()
    plan_key = c.data[12:]
    ok, result = await buy_vip_coins(c.from_user.id, plan_key)
    plan = VIP_PLANS.get(plan_key)
    if ok:
        exp = result.strftime("%d.%m.%Y %H:%M")
        await c.message.edit_text(f"🎉 *{plan['name']} aktivlashtirildi!*\n⏰ {exp} gacha\n🤖 AI limiti yangilandi! 🚀", parse_mode="Markdown")
        u = await get_user(c.from_user.id)
        vip = await get_vip_status(c.from_user.id)
        await bot.send_message(c.from_user.id, f"✅ *{plan['name']}* faollashdi!\n💰 Qolgan balans: *{u['coins']} coin*",
            reply_markup=get_main_kb(c.from_user.id, vip), parse_mode="Markdown")
        try:
            await bot.send_message(ADMIN_ID,
                f"💳 <b>VIP sotildi!</b>\n👤 <b>{u['name']}</b> (<code>{c.from_user.id}</code>)\n📦 {plan['name']}\n💰 {plan['coins']} coin",
                parse_mode="HTML")
        except: pass
    else:
        await c.message.edit_text(f"❌ *Xato:* {result}", parse_mode="Markdown")

# ═══════════════════════════════════════════════════
#  KINOLAR
# ═══════════════════════════════════════════════════
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def show_movies(m: Message):
    if not await sub_guard(m): return
    movies = await get_all_movies()
    if not movies: return await m.answer("📽 Hozircha kinolar mavjud emas.")
    text = "🔥 *KINOLAR RO'YXATI*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for mv in movies:
        gn = f" | 🎭 {mv['genre']}" if mv.get('genre') else ""
        text += f"🎬 *{mv['name']}*\n📅 {mv['year']}{gn}\n💎 *{mv['price']} coin* | 🆔 Kod: `{mv['id']}`\n────────────────────\n"
    text += "\n🍿 Sotib olish: 🎟 *Kino Sotib Olish*"
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎟 Kino Sotib Olish")
async def buy_movie_start(m: Message, state: FSMContext):
    if not await sub_guard(m): return
    u = await get_user(m.from_user.id)
    if not u: return await m.answer("❌ /start")
    await m.answer(f"💰 Balans: *{u['coins']} coin*\n\n🎬 Kino *kodini* yuboring:", parse_mode="Markdown")
    await state.set_state(S.buy_movie)

@dp.message(S.buy_movie)
async def process_buy(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit(): return await m.answer("⚠️ Faqat kino kodini raqamda yozing!")
    mv = await get_movie(int(m.text))
    if not mv: return await m.answer("❌ Bunday kino topilmadi!")
    u = await get_user(m.from_user.id)
    if await user_has_movie(m.from_user.id, mv['id']):
        await state.clear()
        await m.answer(f"✅ *{mv['name']}* allaqachon sotib olgansiz!", parse_mode="Markdown")
        if mv['file_id']: await bot.send_video(m.from_user.id, mv['file_id'], caption=f"🎬 {mv['name']}")
        return
    if u['coins'] < mv['price']:
        await state.clear()
        return await m.answer(f"❌ *Coinlar yetarli emas!*\n💎 Narx: {mv['price']}\n💰 Sizda: {u['coins']}", parse_mode="Markdown")
    gn = f"\n🎭 Janr: {mv['genre']}" if mv.get('genre') else ""
    kb = InlineKeyboardBuilder()
    kb.button(text=f"✅ Ha, {mv['price']} coin to'layman", callback_data=f"buy_{mv['id']}")
    kb.button(text="❌ Bekor", callback_data="cancel_buy")
    kb.adjust(1)
    await m.answer(
        f"🎬 *{mv['name']}* ({mv['year']}){gn}\n\n📝 {mv['description'] or 'Tavsif yo\'q'}\n\n"
        f"💎 Narx: *{mv['price']} coin* | 💰 Sizda: *{u['coins']} coin*\n\nTasdiqlaysizmi?",
        reply_markup=kb.as_markup(), parse_mode="Markdown")
    await state.clear()

@dp.callback_query(F.data.startswith("buy_"))
async def confirm_buy(c: CallbackQuery):
    await c.answer()
    mid = int(c.data[4:])
    mv = await get_movie(mid)
    ok = await buy_movie_db(c.from_user.id, mid, mv['price'])
    if ok:
        await c.message.edit_text(f"✅ *{mv['name']}* sotib olindi!", parse_mode="Markdown")
        if mv['file_id']: await bot.send_video(c.from_user.id, mv['file_id'], caption=f"🎬 {mv['name']}")
        else: await c.message.answer("⚠️ Kino fayli hali qo'shilmagan.")
    else:
        await c.message.edit_text("❌ Xatolik yuz berdi!")

@dp.callback_query(F.data == "cancel_buy")
async def cancel_buy(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("❌ Bekor qilindi.")

# ═══════════════════════════════════════════════════
#  HISOBIM
# ═══════════════════════════════════════════════════
@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    if not await sub_guard(m): return
    u = await get_user(m.from_user.id)
    if not u: return await m.answer("❌ /start")
    async with db_pool.acquire() as conn:
        p_cnt = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE user_id=$1", m.from_user.id)
        r_cnt = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id)
        p_num = await conn.fetchval("SELECT COUNT(*) FROM users WHERE user_id<=$1", m.from_user.id)
    vip = await get_vip_status(m.from_user.id)
    badge = vip_badge(vip)
    vip_line = ""
    if vip:
        exp = u['vip_expires'].strftime("%d.%m.%Y") if u['vip_expires'] else "Muddatsiz"
        vip_line = f"\n{'👑 VIP' if vip=='vip' else '⭐ Premium'}: *{exp}* gacha"
    _, used, limit = await check_ai_limit(m.from_user.id)
    await m.answer(
        f"{badge} *Shaxsiy Kabinet*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 Ism: *{u['name']}*\n📱 Tel: {u['phone'] or 'Kiritilmagan'}\n"
        f"💰 Balans: *{u['coins']} coin*{vip_line}\n"
        f"🤖 AI bugun: *{used}/{limit}*\n"
        f"🎬 Sotib olingan: *{p_cnt}* ta\n👥 Taklif: *{r_cnt}* ta\n"
        f"📅 Ro'yxatdan: *{u['joined_at']}*\n\n"
        f"🔑 ID: `{m.from_user.id}` | 🏷 Profil №{p_num}",
        parse_mode="Markdown")

# ═══════════════════════════════════════════════════
#  KUNLIK BONUS
# ═══════════════════════════════════════════════════
@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_bonus(m: Message):
    if not await sub_guard(m): return
    u = await get_user(m.from_user.id)
    if not u: return await m.answer("❌ /start")
    today = date.today()
    if u['last_bonus'] and u['last_bonus'] >= today:
        return await m.answer("⏳ *Bugun allaqachon bonus oldingiz!*\n\n🔄 Ertaga qaytib keling!", parse_mode="Markdown")
    vip = await get_vip_status(m.from_user.id)
    bonus = 50 if vip=='vip' else (30 if vip=='premium' else 20)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins=coins+$1,last_bonus=CURRENT_DATE WHERE user_id=$2", bonus, m.from_user.id)
    updated = await get_user(m.from_user.id)
    extra = " (VIP 👑)" if vip=='vip' else (" (Premium ⭐)" if vip=='premium' else "")
    await m.answer(f"🎉 *Kunlik Bonus!*\n\n✅ *+{bonus} coin*{extra}\n💰 Balans: *{updated['coins']} coin*", parse_mode="Markdown")

# ═══════════════════════════════════════════════════
#  DO'ST TAKLIF
# ═══════════════════════════════════════════════════
@dp.message(F.text == "👥 Do'st Taklif")
async def referral(m: Message):
    if not await sub_guard(m): return
    bi = await bot.get_me()
    link = f"https://t.me/{bi.username}?start=ref{m.from_user.id}"
    async with db_pool.acquire() as conn:
        cnt = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id=$1", m.from_user.id)
    await m.answer(f"👥 *Do'stlarni Taklif*\n━━━━━━━━━━━━━━━━━━\n\n🔗 Havola:\n`{link}`\n\n💰 Har do'st: *+50 coin*\n👤 Taklif qilingan: *{cnt}* ta", parse_mode="Markdown")

# ═══════════════════════════════════════════════════
#  ADMINGA YOZISH
# ═══════════════════════════════════════════════════
@dp.message(F.text == "✍️ Adminga Yozish")
async def write_admin(m: Message, state: FSMContext):
    if not await sub_guard(m): return
    u = await get_user(m.from_user.id)
    if not u: return await m.answer("❌ /start")
    await state.set_state(S.active_chat)
    await state.update_data(chat_with=ADMIN_ID, is_user=True)
    await m.answer("✍️ *Adminga xabar yozing:*\n\nTugash: /stop", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    try:
        await bot.send_message(ADMIN_ID, f"📩 <b>Yangi xabar!</b>\n👤 <b>{u['name']}</b> | ID: <code>{m.from_user.id}</code>", parse_mode="HTML")
    except: pass

@dp.message(S.active_chat)
async def active_chat(m: Message, state: FSMContext):
    if m.text and m.text.lower() == "/stop":
        data = await state.get_data()
        partner = data.get("chat_with")
        is_user = data.get("is_user", True)
        await state.clear()
        vip = await get_vip_status(m.from_user.id)
        await m.answer("📴 Suhbat yakunlandi.", reply_markup=get_main_kb(m.from_user.id, vip))
        if partner:
            try:
                if is_user: await bot.send_message(partner, f"📴 Foydalanuvchi ({m.from_user.id}) tugatdi.", reply_markup=get_admin_kb())
                else: await bot.send_message(partner, "📴 Admin suhbatni tugatdi.", reply_markup=get_main_kb(partner))
            except: pass
        return
    data = await state.get_data()
    partner = data.get("chat_with"); is_user = data.get("is_user", True)
    if not partner: return
    u = await get_user(m.from_user.id)
    name = u['name'] if u else m.from_user.full_name
    prefix = f"📩 *{name}* (`{m.from_user.id}`):\n\n" if is_user else "👑 *Admin:*\n\n"
    try:
        if m.text: await bot.send_message(partner, f"{prefix}{m.text}", parse_mode="Markdown")
        elif m.photo: await bot.send_photo(partner, m.photo[-1].file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        elif m.video: await bot.send_video(partner, m.video.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        elif m.document: await bot.send_document(partner, m.document.file_id, caption=f"{prefix}{m.caption or ''}", parse_mode="Markdown")
        await m.answer("✅ Yuborildi! /stop", reply_markup=get_end_chat_kb() if not is_user else None)
    except Exception as e:
        await m.answer(f"❌ Yuborilmadi: {e}")

# ═══════════════════════════════════════════════════
#  STATISTIKA
# ═══════════════════════════════════════════════════
@dp.message(F.text == "📊 Statistika")
async def stats_msg(m: Message):
    if m.from_user.id != ADMIN_ID: return
    s = await get_stats()
    await m.answer(
        f"📊 *BOT STATISTIKASI*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami: *{s['total_users']}*\n🆕 Bugun: *{s['today_users']}*\n"
        f"🚫 Bloklangan: *{s['banned_users']}*\n👑 VIP/Premium: *{s['vip_users']}*\n"
        f"🎬 Kinolar: *{s['total_movies']}*\n🛒 Sotuvlar: *{s['total_purchases']}*\n"
        f"🤖 AI sessiyalar: *{s['total_ai_msgs']}*", parse_mode="Markdown")

# ═══════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════
@dp.message(F.text == "🛠 Admin Panel")
async def admin_panel(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("🔐 Admin parolini kiriting:")
    await state.set_state(S.admin_auth)

@dp.message(S.admin_auth)
async def admin_auth(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        await state.clear()
        await m.answer("👑 *Xush kelibsiz, Admin!*", reply_markup=get_admin_kb(), parse_mode="Markdown")
    else:
        await state.clear()
        await m.answer("❌ Parol noto'g'ri!")

@dp.callback_query(F.data == "adm_close")
async def adm_close(c: CallbackQuery):
    await c.answer()
    try: await c.message.delete()
    except: pass

@dp.callback_query(F.data == "adm_full_stats")
async def adm_full_stats(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    s = await get_stats()
    await c.message.edit_text(
        f"📊 *TO'LIQ STATISTIKA*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Jami: *{s['total_users']}*\n🆕 Bugun: *{s['today_users']}*\n"
        f"🚫 Bloklangan: *{s['banned_users']}*\n👑 VIP/Premium: *{s['vip_users']}*\n"
        f"🎬 Kinolar: *{s['total_movies']}*\n🛒 Sotuvlar: *{s['total_purchases']}*\n"
        f"🤖 AI sessiyalar: *{s['total_ai_msgs']}*",
        parse_mode="Markdown", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "adm_ai_settings")
async def adm_ai_set(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardBuilder(); kb.button(text="🔙 Orqaga", callback_data="sub_back")
    await c.message.edit_text(
        f"🤖 *AI Sozlamalari*\n━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 Kunlik limitlar:\n👤 Oddiy: *{AI_FREE_LIMIT}* ta\n⭐ Premium: *{AI_PREMIUM_LIMIT}* ta\n👑 VIP: *Cheksiz ({AI_VIP_LIMIT})*\n\n"
        f"🔑 Gemini API: " + ("✅ Ulangan" if GEMINI_KEY else "❌ Sozlanmagan — GEMINI_API_KEY muhit o'zgaruvchisiga qo'shing"),
        parse_mode="Markdown", reply_markup=kb.as_markup())

# ── VIP BERISH (admin) ─────────────────────────────
@dp.callback_query(F.data == "adm_give_vip")
async def adm_give_vip(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("👑 VIP berish uchun foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(S.vip_give_id)

@dp.message(S.vip_give_id)
async def adm_give_vip_id(m: Message, state: FSMContext):
    if not m.text or not m.text.strip().isdigit(): return await m.answer("⚠️ Faqat ID kiriting!")
    uid = int(m.text.strip())
    u = await get_user(uid)
    if not u:
        await state.clear()
        return await m.answer(f"❌ ID: `{uid}` topilmadi!", parse_mode="Markdown")
    await state.clear()
    kb = InlineKeyboardBuilder()
    for k, p in VIP_PLANS.items():
        kb.button(text=p['name'], callback_data=f"gv_{uid}_{k}")
    kb.button(text="❌ Bekor", callback_data="adm_close")
    kb.adjust(2)
    await m.answer(f"👤 *{u['name']}* (ID: `{uid}`)\n\nQaysi rejani bermoqchisiz?",
        parse_mode="Markdown", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("gv_"))
async def adm_give_vip_plan(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    await c.answer()
    parts = c.data.split("_", 2)
    uid = int(parts[1]); plan_key = parts[2]
    plan = VIP_PLANS.get(plan_key)
    if not plan: return await c.message.answer("❌ Noma'lum plan!")
    expires = await set_vip(uid, plan['label'], plan['days'], "admin")
    exp = expires.strftime("%d.%m.%Y %H:%M")
    await c.message.edit_text(f"✅ *{plan['name']}* berildi!\n👤 ID: `{uid}`\n⏰ {exp} gacha",
        parse_mode="Markdown", reply_markup=get_admin_kb())
    try:
        await bot.send_message(uid,
            f"🎁 <b>Sizga {plan['name']} berildi!</b>\n⏰ <b>{exp}</b> gacha\n🤖 AI limiti oshdi! Barcha imtiyozlardan foydalaning! 🚀",
            parse_mode="HTML")
    except: pass

# ── OBUNA LOGLARI ──────────────────────────────────
@dp.callback_query(F.data == "adm_sub_logs")
async def adm_sub_logs(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    async with db_pool.acquire() as conn:
        logs = await conn.fetch("SELECT user_id,user_name,channel_title,event,event_time FROM sub_logs ORDER BY event_time DESC LIMIT 40")
    if not logs:
        kb = InlineKeyboardBuilder(); kb.button(text="🔙 Orqaga", callback_data="sub_back")
        return await c.message.edit_text("📋 Hozircha hodisalar yo'q.", reply_markup=kb.as_markup())
    emj = {'first_subscribed':'🆕✅','subscribed':'✅','checked_not_subscribed':'❌','unsubscribed':'⚠️🔴'}
    text = "📋 *Oxirgi Obuna Hodisalari*\n━━━━━━━━━━━━━━━━━━\n\n"
    for log in logs:
        t = log['event_time'].strftime("%m-%d %H:%M") if log['event_time'] else ''
        text += f"{emj.get(log['event'],'❓')} *{log['user_name']}* (`{log['user_id']}`)\n   📌 {log['channel_title']} | {t}\n"
    kb = InlineKeyboardBuilder(); kb.button(text="🔙 Orqaga", callback_data="sub_back")
    try: await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except: await bot.send_message(c.from_user.id, text, parse_mode="Markdown")

# ── FOYDALANUVCHILAR ───────────────────────────────
@dp.callback_query(F.data == "adm_users")
async def adm_users(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id,name,coins,joined_at,is_banned,vip_type FROM users ORDER BY joined_at DESC LIMIT 50")
    if not users: return await c.message.answer("📭 Foydalanuvchilar yo'q!")
    text = "👥 *FOYDALANUVCHILAR*\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, u in enumerate(users, 1):
        s = "🚫" if u['is_banned'] else ("👑" if u['vip_type']=='vip' else ("⭐" if u['vip_type']=='premium' else "✅"))
        text += f"{i}. {s} *{u['name']}*\n   🔑 `{u['user_id']}` | 💰 {u['coins']} | 📅 {u['joined_at']}\n"
    kb = InlineKeyboardBuilder(); kb.button(text="🔙 Orqaga", callback_data="sub_back")
    try: await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
    except: await bot.send_message(c.from_user.id, text, parse_mode="Markdown")

# ── MAJBURIY OBUNA ─────────────────────────────────
@dp.callback_query(F.data == "adm_subscription")
async def adm_sub_menu(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    chs = await get_req_channels()
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Kanal Qo'shish", callback_data="sub_add")
    if chs: kb.button(text="🗑 Kanal O'chirish", callback_data="sub_del_list")
    kb.button(text="🔙 Orqaga", callback_data="sub_back")
    kb.adjust(1)
    text = "🔔 *Majburiy Obuna*\n━━━━━━━━━━━━━━━━━━\n\n"
    if chs:
        text += "📋 *Kanallar:*\n"
        for ch in chs: text += f"• [{ch['title']}]({ch['link']}) — {'📱 TG' if is_tg_link(ch['link']) else '🌐 Tashqi'}\n"
    else: text += "📭 Kanallar yo'q."
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown", disable_web_page_preview=True)

@dp.callback_query(F.data == "sub_back")
async def sub_back(c: CallbackQuery):
    await c.answer()
    await c.message.edit_text("👑 *Admin Panel*", reply_markup=get_admin_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "sub_add")
async def sub_add(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("🔗 *Kanal linkini yuboring:*\n📱 Telegram: `https://t.me/kanalnom`\n🌐 Tashqi: `https://instagram.com/nom`", parse_mode="Markdown")
    await state.set_state(S.sub_link)

@dp.message(S.sub_link)
async def sub_get_link(m: Message, state: FSMContext):
    link = m.text.strip()
    if not (link.startswith('http://') or link.startswith('https://')):
        return await m.answer("⚠️ Link http:// yoki https:// bilan boshlanishi kerak!")
    await state.update_data(sub_link=link)
    await m.answer("📝 *Kanal nomini kiriting:*", parse_mode="Markdown")
    await state.set_state(S.sub_title)

@dp.message(S.sub_title)
async def sub_get_title(m: Message, state: FSMContext):
    try:
        data = await state.get_data()
        link = data.get('sub_link','')
        await add_req_channel(link, m.text.strip())
        await state.clear()
        note = "⚠️ Botni kanalga admin qilib qo'shing!" if is_tg_link(link) else "✅ Tashqi kanal."
        await m.answer(f"✅ <b>Kanal qo'shildi!</b>\n📛 {m.text.strip()}\n🔗 <code>{link}</code>\n\n{note}",
            parse_mode="HTML", disable_web_page_preview=True, reply_markup=get_admin_kb())
        asyncio.create_task(_broadcast_new_sub())
    except Exception as e:
        await state.clear()
        await m.answer(f"❌ Xatolik: {e}")

async def _broadcast_new_sub():
    try:
        all_u = await get_all_users()
        for u in all_u:
            if u['user_id'] == ADMIN_ID: continue
            try:
                user = await get_user(u['user_id'])
                if not user: continue
                ns = await check_all_subs(u['user_id'], user['name'])
                if ns: await send_sub_msg(u['user_id'], ns)
                await asyncio.sleep(0.05)
            except: pass
    except Exception as e:
        logger.error(f"broadcast_new_sub xato: {e}")

@dp.callback_query(F.data == "sub_del_list")
async def sub_del_list(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    chs = await get_req_channels()
    if not chs: return await c.message.answer("📭 Kanallar yo'q!")
    kb = InlineKeyboardBuilder()
    for ch in chs: kb.button(text=f"🗑 {ch['title']}", callback_data=f"sdel_{ch['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_subscription")
    kb.adjust(1)
    await c.message.edit_text("🗑 *O'chirmoqchi bo'lgan kanal:*", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("sdel_"))
async def sub_del(c: CallbackQuery):
    if c.from_user.id != ADMIN_ID: return await c.answer("❌ Ruxsat yo'q!", show_alert=True)
    ch_id = int(c.data[5:])
    async with db_pool.acquire() as conn:
        ch = await conn.fetchrow("SELECT title FROM required_channels WHERE id=$1", ch_id)
    await remove_req_channel(ch_id)
    await c.answer(f"✅ '{ch['title'] if ch else 'Kanal'}' o'chirildi!", show_alert=True)
    chs = await get_req_channels()
    kb = InlineKeyboardBuilder()
    for ch2 in chs: kb.button(text=f"🗑 {ch2['title']}", callback_data=f"sdel_{ch2['id']}")
    kb.button(text="🔙 Orqaga", callback_data="adm_subscription"); kb.adjust(1)
    await c.message.edit_text("🗑 *Kanal tanlang:*" if chs else "📭 *Barcha kanallar o'chirildi.*",
        reply_markup=kb.as_markup(), parse_mode="Markdown")

# ── COIN QO'SHISH ──────────────────────────────────
@dp.callback_query(F.data == "adm_add_coin")
async def adm_add_coin(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("💰 Foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(S.coin_add_id)

@dp.message(S.coin_add_id)
async def coin_add_id(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit(): return await m.answer("⚠️ Faqat ID!")
    u = await get_user(int(m.text))
    if not u:
        await state.clear()
        return await m.answer("❌ Topilmadi!")
    await state.update_data(target=int(m.text))
    await m.answer(f"👤 *{u['name']}* | 💰 {u['coins']} coin\n\nQancha coin?", parse_mode="Markdown")
    await state.set_state(S.coin_add_amt)

@dp.message(S.coin_add_amt)
async def coin_add_amt(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit() or int(m.text)<=0: return await m.answer("⚠️ Musbat son!")
    data = await state.get_data(); uid = data['target']; amount = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins=coins+$1 WHERE user_id=$2", amount, uid)
    upd = await get_user(uid)
    await state.clear()
    await m.answer(f"✅ *+{amount} coin* qo'shildi!\n💰 Yangi: *{upd['coins']} coin*", parse_mode="Markdown", reply_markup=get_admin_kb())
    try: await bot.send_message(uid, f"🎉 Sizga *+{amount} coin* qo'shildi!\n💰 Balans: *{upd['coins']} coin*", parse_mode="Markdown")
    except: pass

# ── COIN OLISH ─────────────────────────────────────
@dp.callback_query(F.data == "adm_rm_coin")
async def adm_rm_coin(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("💸 Foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(S.coin_rm_id)

@dp.message(S.coin_rm_id)
async def coin_rm_id(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit(): return await m.answer("⚠️ Faqat ID!")
    u = await get_user(int(m.text))
    if not u:
        await state.clear()
        return await m.answer("❌ Topilmadi!")
    await state.update_data(target=int(m.text))
    await m.answer(f"👤 *{u['name']}* | 💰 {u['coins']} coin\n\nQancha coin olish?", parse_mode="Markdown")
    await state.set_state(S.coin_rm_amt)

@dp.message(S.coin_rm_amt)
async def coin_rm_amt(m: Message, state: FSMContext):
    if not m.text or not m.text.isdigit() or int(m.text)<=0: return await m.answer("⚠️ Musbat son!")
    data = await state.get_data(); uid = data['target']; amount = int(m.text)
    u = await get_user(uid)
    if u['coins'] < amount:
        await state.clear()
        return await m.answer(f"⚠️ Faqat {u['coins']} coin bor!", reply_markup=get_admin_kb())
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET coins=coins-$1 WHERE user_id=$2", amount, uid)
    upd = await get_user(uid)
    await state.clear()
    await m.answer(f"✅ *-{amount} coin* yechildi!\n💰 Yangi: *{upd['coins']} coin*", parse_mode="Markdown", reply_markup=get_admin_kb())
    try: await bot.send_message(uid, f"⚠️ Sizdan *-{amount} coin* yechildi!\n💰 Balans: *{upd['coins']} coin*", parse_mode="Markdown")
    except: pass

# ── KINO QO'SHISH ──────────────────────────────────
@dp.callback_query(F.data == "adm_add_kino")
async def adm_add_kino(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer(
        "🎬 *Kino ma'lumotlarini kiriting:*\n\nFormat: `Nom | Yil | Janr | Narx`\n\nMisol:\n`Avengers | 2019 | Fantastika | 50`\n\n💡 Tavsif AI tomonidan yoziladi!",
        parse_mode="Markdown")
    await state.set_state(S.kino_info)

@dp.message(S.kino_info)
async def kino_info(m: Message, state: FSMContext):
    if not m.text: return await m.answer("⚠️ Matn formatida yuboring!")
    parts = [p.strip() for p in m.text.split('|')]
    if len(parts) != 4:
        return await m.answer("⚠️ *Format noto'g'ri!*\n\nTo'g'ri: `Nom | Yil | Janr | Narx`", parse_mode="Markdown")
    name, year, genre, price_str = parts
    if not price_str.isdigit(): return await m.answer("⚠️ Narx faqat raqam bo'lishi kerak!")
    await state.update_data(k_name=name, k_year=year, k_genre=genre, k_price=int(price_str))
    proc = await m.answer("🤖 *AI tavsif yozmoqda...*", parse_mode="Markdown")
    desc = await gemini_auto_desc(name, year)
    try: await proc.delete()
    except: pass
    await state.update_data(k_desc=desc)
    await m.answer(
        f"✅ *Ma'lumotlar:*\n🎬 *{name}* | 📅 {year} | 🎭 {genre} | 💰 {price_str} coin\n\n📝 *AI tavsif:*\n_{desc}_\n\n🎬 *Endi video faylini yuboring:*",
        parse_mode="Markdown")
    await state.set_state(S.kino_file)

@dp.message(S.kino_file, F.video)
async def kino_file(m: Message, state: FSMContext):
    data = await state.get_data()
    nid = await add_movie(data['k_name'], data['k_year'], data.get('k_desc',''), m.video.file_id, data.get('k_price',0), data.get('k_genre'))
    await state.clear()
    await m.answer(f"✅ *Kino qo'shildi!*\n🆔 Kod: `{nid}`\n🎬 {data['k_name']} | 📅 {data['k_year']} | 💰 {data.get('k_price',0)} coin",
        parse_mode="Markdown", reply_markup=get_admin_kb())

@dp.message(S.kino_file)
async def kino_file_wrong(m: Message, state: FSMContext):
    await m.answer("⚠️ *Faqat video fayl yuboring!*\n🎬 Telegram video sifatida yuboring.", parse_mode="Markdown")

# ── KINO O'CHIRISH ─────────────────────────────────
@dp.callback_query(F.data == "adm_del_kino")
async def adm_del_kino(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    mvs = await get_all_movies()
    if not mvs: return await c.message.answer("📽 Kinolar yo'q!")
    kb = InlineKeyboardBuilder()
    for mv in mvs: kb.button(text=f"🗑 {mv['name']} ({mv['id']})", callback_data=f"kdel_{mv['id']}")
    kb.button(text="❌ Bekor", callback_data="adm_close"); kb.adjust(1)
    await c.message.edit_text("🗑 *O'chirmoqchi bo'lgan kino:*", reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("kdel_"))
async def kino_del(c: CallbackQuery):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    mid = int(c.data[5:])
    async with db_pool.acquire() as conn:
        mv = await conn.fetchrow("SELECT name FROM movies WHERE id=$1", mid)
        await conn.execute("DELETE FROM movies WHERE id=$1", mid)
    await c.message.edit_text(f"✅ *{mv['name']}* o'chirildi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ── REKLAMA ────────────────────────────────────────
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("📢 *Xabarni yuboring:*", parse_mode="Markdown")
    await state.set_state(S.broadcast)

@dp.message(S.broadcast)
async def do_broadcast(m: Message, state: FSMContext):
    await state.clear()
    users = await get_all_users()
    ok = 0; fail = 0
    msg = await m.answer(f"⏳ Yuborilmoqda... 0/{len(users)}")
    for i, u in enumerate(users):
        try:
            await m.copy_to(chat_id=u['user_id']); ok += 1; await asyncio.sleep(0.05)
            if i % 20 == 0:
                try: await msg.edit_text(f"⏳ {i}/{len(users)}")
                except: pass
        except: fail += 1
    await msg.edit_text(f"✅ *Reklama yuborildi!*\n📨 Muvaffaqiyatli: *{ok}*\n❌ Yuborilmagan: *{fail}*", parse_mode="Markdown")

# ── BLOKLASH ───────────────────────────────────────
@dp.callback_query(F.data == "adm_ban")
async def adm_ban(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("🚫 Bloklash uchun foydalanuvchi *ID* sini kiriting:", parse_mode="Markdown")
    await state.set_state(S.ban_id)

@dp.message(S.ban_id)
async def do_ban(m: Message, state: FSMContext):
    await state.clear()
    if not m.text or not m.text.isdigit(): return await m.answer("⚠️ Faqat ID!")
    uid = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=TRUE WHERE user_id=$1", uid)
    try: await bot.send_message(uid, "🚫 Siz botdan bloklangansiz.", reply_markup=ReplyKeyboardRemove())
    except: pass
    await m.answer(f"✅ ID `{uid}` bloklandi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ── BLOKDAN CHIQARISH ──────────────────────────────
@dp.callback_query(F.data == "adm_unban")
async def adm_unban(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await c.message.answer("✅ Blokdan chiqarish uchun *ID* ni kiriting:", parse_mode="Markdown")
    await state.set_state(S.unban_id)

@dp.message(S.unban_id)
async def do_unban(m: Message, state: FSMContext):
    await state.clear()
    if not m.text or not m.text.isdigit(): return await m.answer("⚠️ Faqat ID!")
    uid = int(m.text)
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned=FALSE WHERE user_id=$1", uid)
    try: await bot.send_message(uid, "✅ Blokingiz olib tashlandi! /start")
    except: pass
    await m.answer(f"✅ ID `{uid}` blokdan chiqarildi!", parse_mode="Markdown", reply_markup=get_admin_kb())

# ── ADMIN CHAT ─────────────────────────────────────
@dp.callback_query(F.data == "adm_start_chat")
async def adm_start_chat(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await state.clear()
    await state.set_state(S.chat_target)
    await c.message.answer("💬 *Gaplashmoqchi bo'lgan foydalanuvchi ID:*", parse_mode="Markdown")

@dp.message(S.chat_target)
async def chat_target(m: Message, state: FSMContext):
    if not m.text or not m.text.strip().isdigit(): return await m.answer("⚠️ Faqat ID!")
    tid = int(m.text.strip())
    if tid == ADMIN_ID: return await m.answer("⚠️ O'zingizga xabar yubora olmaysiz!")
    tu = await get_user(tid)
    if not tu:
        await state.clear()
        return await m.answer(f"❌ ID `{tid}` topilmadi!", parse_mode="Markdown")
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"cy_{ADMIN_ID}")
    kb.button(text="❌ Yo'q",            callback_data=f"cn_{ADMIN_ID}")
    kb.adjust(1)
    try:
        await bot.send_message(tid, "🔔 <b>Admin siz bilan bog'lanmoqchi!</b>\n\nSuhbatga rozimisiz?",
            reply_markup=kb.as_markup(), parse_mode="HTML")
        await state.set_state(S.active_chat)
        await state.update_data(chat_with=tid, is_user=False)
        await m.answer(f"✅ So'rov yuborildi!\n👤 *{tu['name']}* | ID: `{tid}`\n\n/stop", parse_mode="Markdown", reply_markup=get_end_chat_kb())
    except Exception as e:
        await state.clear()
        await m.answer(f"❌ Xabar yuborib bo'lmadi: {e}")

@dp.callback_query(F.data.startswith("cy_"))
async def chat_yes(c: CallbackQuery, state: FSMContext):
    await c.answer("✅ Suhbat boshlandi!")
    aid = int(c.data[3:])
    await state.set_state(S.active_chat)
    await state.update_data(chat_with=aid, is_user=True)
    await c.message.edit_text("✅ <b>Aloqa o'rnatildi!</b>\n\n💬 Xabaringizni yozing.\n/stop", parse_mode="HTML")
    try:
        await bot.send_message(aid, f"✅ *Foydalanuvchi ({c.from_user.id}) suhbatga kirdi!*\n/stop",
            parse_mode="Markdown", reply_markup=get_end_chat_kb())
    except: pass

@dp.callback_query(F.data.startswith("cn_"))
async def chat_no(c: CallbackQuery):
    await c.answer("❌ Rad etildi")
    aid = int(c.data[3:])
    await c.message.edit_text("❌ Siz suhbatni rad etdingiz.")
    try: await bot.send_message(aid, f"😔 Foydalanuvchi ({c.from_user.id}) suhbatlashishni istamadi.", reply_markup=get_admin_kb())
    except: pass

@dp.callback_query(F.data == "end_chat")
async def end_chat(c: CallbackQuery, state: FSMContext):
    if c.from_user.id != ADMIN_ID: return await c.answer("❌ Faqat admin uchun!", show_alert=True)
    await c.answer()
    data = await state.get_data()
    partner = data.get("chat_with")
    await state.clear()
    try: await c.message.edit_text("🔴 *Aloqa tugadi.*", parse_mode="Markdown")
    except: pass
    await bot.send_message(c.from_user.id, "📴 Suhbat yakunlandi.", reply_markup=get_admin_kb())
    if partner:
        try: await bot.send_message(partner, "📴 Admin suhbatni tugatdi.", reply_markup=get_main_kb(partner))
        except: pass

# ── QO'NG'IROQ ─────────────────────────────────────
@dp.callback_query(F.data == "adm_call_user")
async def adm_call(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id != ADMIN_ID: return
    await state.clear()
    await state.set_state(S.call_id)
    await c.message.answer("📞 *Qo'ng'iroq qilmoqchi bo'lgan foydalanuvchi ID:*", parse_mode="Markdown")

@dp.message(S.call_id)
async def do_call(m: Message, state: FSMContext):
    if not m.text or not m.text.strip().isdigit(): return await m.answer("⚠️ Faqat ID!")
    tid = int(m.text.strip())
    if tid == ADMIN_ID:
        await state.clear()
        return await m.answer("⚠️ O'zingizga qo'ng'iroq qila olmaysiz!")
    tu = await get_user(tid)
    if not tu:
        await state.clear()
        return await m.answer(f"❌ ID `{tid}` topilmadi!", parse_mode="Markdown")
    await state.clear()
    akb = InlineKeyboardBuilder()
    akb.button(text=f"📞 {tu['name']} ni chaqirish", url=f"tg://user?id={tid}")
    akb.button(text="🔙 Admin Panel", callback_data="sub_back"); akb.adjust(1)
    await m.answer(f"📞 *{tu['name']}* | ID: `{tid}`\n\nTugmani bosib profilga o'ting, so'ng qo'ng'iroq qiling.",
        parse_mode="Markdown", reply_markup=akb.as_markup())
    ukb = InlineKeyboardBuilder(); ukb.button(text="📞 Adminga qo'ng'iroq", url=f"tg://user?id={ADMIN_ID}")
    try:
        await bot.send_message(tid, "📞 <b>Admin siz bilan qo'ng'iroq orqali bog'lanmoqchi!</b>\nQuyidagi tugmani bosing yoki adminning qo'ng'irog'ini kuting. 📲",
            parse_mode="HTML", reply_markup=ukb.as_markup())
        await m.answer(f"✅ {tu['name']} ga bildirishnoma yuborildi!", reply_markup=get_admin_kb())
    except Exception as e:
        await m.answer(f"⚠️ Xabar yuborilmadi: {e}", reply_markup=akb.as_markup())

# ═══════════════════════════════════════════════════
#  GLOBAL HANDLER
# ═══════════════════════════════════════════════════
@dp.message()
async def global_handler(m: Message, state: FSMContext):
    u = await get_user(m.from_user.id)
    if u and u['is_banned']:
        await m.answer("🚫 Siz botdan bloklangansiz.")

# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════
async def main():
    keep_alive()
    await init_db()
    logger.info("🚀 CineBot 2026 ishga tushmoqda!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
