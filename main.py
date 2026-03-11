#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║         TELEGRAM GROK AI BOT — PYDROID 3 VERSIYA                          ║
# ║     Grok AI | Premium | Rasm | Quiz | Admin Panel | Xavfsizlik             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝
#
#  PYDROID 3 DA O'RNATISH:
#    pip install python-telegram-bot==20.7
#    pip install openai
#    pip install httpx
#
#  ISHGA TUSHIRISH:
#    python main_bot.py
#
# ──────────────────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
#  🔑  BARCHA TOKENLAR VA API KALITLARI — SHU YERGA KIRITING
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN      = "8628602957:AAEIg78I1ikg7hvydXiQrLWpMVS5Iebg-r0"
# Misol: BOT_TOKEN = "7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxx"

ADMIN_IDS = [
    7490516744,   # ← O'z admin ID ingizni kiriting
]

ADMIN_PASSWORD    = "456"
GROK_API_KEY      = "xai-FexnebMjXLPV8wh0RD4WdxRXactsvP47hxodhFTe0CBtPWl4mN0rVrGtHkWg7fPk9KE27ZocNraYIU1b"
# Misol: GROK_API_KEY = "xai-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# ──────────────────────────────────────────────────────────────────────────────
#  ⚙️  QO'SHIMCHA SOZLAMALAR
# ──────────────────────────────────────────────────────────────────────────────

GROK_MODEL          = "grok-3-latest"
MAX_HISTORY         = 20
MAX_TOKENS          = 2000
TEMPERATURE         = 0.7
DB_FILE             = "bot_data.db"
LOG_FILE            = "bot.log"
FREE_IMAGE_LIMIT    = 10
PREMIUM_IMAGE_LIMIT = 50
PREMIUM_PRICE_UZS   = 30000
PREMIUM_PRICE_USD   = 3

# ──────────────────────────────────────────────────────────────────────────────
#  IMPORTLAR
# ──────────────────────────────────────────────────────────────────────────────

import os
import sys
import logging
import asyncio
import sqlite3
import json
import time
import random
import traceback
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Pydroid 3 uchun event loop muammosini hal qilish
import asyncio
try:
    import asyncio.selector_events
except Exception:
    pass

_missing = []
try:
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup,
        BotCommand
    )
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        CallbackQueryHandler, filters, ContextTypes
    )
    from telegram.constants import ParseMode, ChatAction
    from telegram.error import NetworkError, TimedOut, TelegramError
except ImportError:
    _missing.append("python-telegram-bot==20.7")

try:
    from openai import AsyncOpenAI
    import openai
except ImportError:
    _missing.append("openai")

if _missing:
    print("❌ Quyidagi kutubxonalar o'rnatilmagan:")
    for lib in _missing:
        print(f"   pip install {lib}")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────────────────────
#  LOGGING — Pydroid 3 uchun soddalashtirilgan
# ──────────────────────────────────────────────────────────────────────────────

handlers = [logging.StreamHandler(sys.stdout)]
try:
    handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a"))
except Exception:
    pass

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    handlers=handlers
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logger = logging.getLogger("GrokBot")

# ──────────────────────────────────────────────────────────────────────────────
#  KONSTANTALAR
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "Siz foydali, do'stona va aqlli AI yordamchisiz — Grok (xAI). "
    "Foydalanuvchiga aniq va qisqacha javob bering. "
    "Agar savol o'zbek tilida bo'lsa, o'zbek tilida javob bering. "
    "Agar ingliz tilida bo'lsa, ingliz tilida javob bering. "
    "Har doim mehribon va professional bo'ling."
)

QUIZ_TOPICS = [
    "Tarix", "Geografiya", "Fan va texnologiya", "Sport",
    "Musiqa", "Kino", "Matematika", "Biologiya",
    "Fizika", "Adabiyot", "Oziq-ovqat", "Hayvonot"
]

TRANSLATE_LANGS = [
    ("O'zbek",   "uzbek"),
    ("Rus",      "russian"),
    ("Ingliz",   "english"),
    ("Nemis",    "german"),
    ("Fransuz",  "french"),
    ("Koreys",   "korean"),
    ("Xitoy",    "chinese"),
    ("Arab",     "arabic"),
]

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_database():
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id          INTEGER PRIMARY KEY,
            username         TEXT    DEFAULT '',
            full_name        TEXT    DEFAULT '',
            is_banned        INTEGER DEFAULT 0,
            ban_reason       TEXT    DEFAULT '',
            is_premium       INTEGER DEFAULT 0,
            premium_expires  TEXT    DEFAULT '',
            images_used      INTEGER DEFAULT 0,
            total_msgs       INTEGER DEFAULT 0,
            joined_at        TEXT    DEFAULT (datetime('now','localtime')),
            last_active      TEXT    DEFAULT (datetime('now','localtime')),
            note             TEXT    DEFAULT '',
            quiz_score       INTEGER DEFAULT 0,
            quiz_total       INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            role       TEXT    NOT NULL,
            content    TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id   INTEGER NOT NULL,
            admin_name TEXT    DEFAULT '',
            action     TEXT    NOT NULL,
            target_id  INTEGER DEFAULT 0,
            details    TEXT    DEFAULT '',
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date             TEXT PRIMARY KEY,
            new_users        INTEGER DEFAULT 0,
            total_msgs       INTEGER DEFAULT 0,
            grok_msgs        INTEGER DEFAULT 0,
            images_made      INTEGER DEFAULT 0,
            premium_requests INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            prompt     TEXT    NOT NULL,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS premium_requests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            status     TEXT    DEFAULT 'pending',
            message    TEXT    DEFAULT '',
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS blocked_words (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            word       TEXT    NOT NULL UNIQUE,
            added_by   INTEGER DEFAULT 0,
            created_at TEXT    DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user  ON conversations(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_admin ON admin_logs(admin_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_prem ON users(is_premium)")

    defaults = [
        ("bot_enabled",       "1"),
        ("image_enabled",     "1"),
        ("maintenance_msg",   "Bot hozir texnik ishlar uchun to'xtatilgan. Tez orada qaytamiz!"),
        ("welcome_msg",       "Xush kelibsiz!\n\nGrok AI bilan suhbatlashishingiz mumkin!\n\nNima qilmoqchisiz?"),
        ("admin_password",    ADMIN_PASSWORD),
        ("grok_model",        GROK_MODEL),
        ("max_tokens",        str(MAX_TOKENS)),
        ("temperature",       str(TEMPERATURE)),
        ("premium_price_uzs", str(PREMIUM_PRICE_UZS)),
        ("premium_price_usd", str(PREMIUM_PRICE_USD)),
        ("premium_payment_info", "To'lov ma'lumotlari:\n\nKarta: 8600 xxxx xxxx xxxx\nEgasi: Admin\n\nTo'lovdan so'ng chekni adminga yuboring."),
        ("rate_limit",        "30"),
    ]
    for key, val in defaults:
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (key, val))

    conn.commit()
    conn.close()
    logger.info("Database ishga tushdi")


# ──────────────────────────────────────────────────────────────────────────────
#  DB FUNKSIYALARI
# ──────────────────────────────────────────────────────────────────────────────

def db_get(key: str, default: str = "") -> str:
    try:
        conn = get_db()
        row  = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception as e:
        logger.error(f"db_get error: {e}")
        return default


def db_set(key: str, value: str) -> bool:
    try:
        conn = get_db()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES(?,?,datetime('now','localtime'))",
            (key, value)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_set error: {e}")
        return False


def db_upsert_user(user_id: int, username: str, full_name: str) -> bool:
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username    = excluded.username,
                full_name   = excluded.full_name,
                last_active = datetime('now','localtime')
        """, (user_id, username or "", full_name or ""))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_upsert_user error: {e}")
        return False


def db_get_user(user_id: int) -> Optional[Dict]:
    try:
        conn = get_db()
        row  = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"db_get_user error: {e}")
        return None


def db_is_premium(user_id: int) -> bool:
    user = db_get_user(user_id)
    if not user or not user.get("is_premium"):
        return False
    exp = user.get("premium_expires", "")
    if exp and exp < datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        try:
            conn = get_db()
            conn.execute("UPDATE users SET is_premium=0, premium_expires='' WHERE user_id=?", (user_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return False
    return True


def db_set_premium(user_id: int, active: bool, days: int = 30) -> bool:
    try:
        conn = get_db()
        if active:
            expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "UPDATE users SET is_premium=1, premium_expires=? WHERE user_id=?",
                (expires, user_id)
            )
        else:
            conn.execute(
                "UPDATE users SET is_premium=0, premium_expires='' WHERE user_id=?",
                (user_id,)
            )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_set_premium error: {e}")
        return False


def db_get_image_count(user_id: int) -> int:
    try:
        conn = get_db()
        row  = conn.execute("SELECT images_used FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return row["images_used"] if row else 0
    except Exception:
        return 0


def db_inc_image(user_id: int):
    try:
        conn = get_db()
        conn.execute("UPDATE users SET images_used=images_used+1 WHERE user_id=?", (user_id,))
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO daily_stats (date, images_made) VALUES (?,1)
            ON CONFLICT(date) DO UPDATE SET images_made=images_made+1
        """, (today,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"db_inc_image error: {e}")


def db_ban_user(user_id: int, ban: bool = True, reason: str = "") -> bool:
    try:
        conn = get_db()
        conn.execute(
            "UPDATE users SET is_banned=?, ban_reason=? WHERE user_id=?",
            (1 if ban else 0, reason, user_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_ban_user error: {e}")
        return False


def db_inc_msgs(user_id: int):
    try:
        conn = get_db()
        conn.execute(
            "UPDATE users SET total_msgs=total_msgs+1, last_active=datetime('now','localtime') WHERE user_id=?",
            (user_id,)
        )
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO daily_stats (date, total_msgs, grok_msgs) VALUES (?,1,1)
            ON CONFLICT(date) DO UPDATE SET total_msgs=total_msgs+1, grok_msgs=grok_msgs+1
        """, (today,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"db_inc_msgs error: {e}")


def db_add_msg(user_id: int, role: str, content: str) -> bool:
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (?,?,?)",
            (user_id, role, content)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_add_msg error: {e}")
        return False


def db_get_history(user_id: int, limit: int = MAX_HISTORY) -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT role, content FROM conversations
            WHERE user_id=? ORDER BY id DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        conn.close()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception as e:
        logger.error(f"db_get_history error: {e}")
        return []


def db_get_history_display(user_id: int, limit: int = 10) -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT role, content, created_at FROM conversations
            WHERE user_id=? ORDER BY id DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception:
        return []


def db_clear_history(user_id: int) -> bool:
    try:
        conn = get_db()
        conn.execute("DELETE FROM conversations WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_clear_history error: {e}")
        return False


def db_log_admin(admin_id: int, admin_name: str, action: str,
                 target_id: int = 0, details: str = "") -> bool:
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO admin_logs (admin_id, admin_name, action, target_id, details)
            VALUES (?,?,?,?,?)
        """, (admin_id, admin_name, action, target_id, details))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"db_log_admin error: {e}")
        return False


def db_get_admin_logs(limit: int = 20) -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_get_stats() -> Dict:
    try:
        conn = get_db()
        total   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        banned  = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0]
        premium = conn.execute("SELECT COUNT(*) FROM users WHERE is_premium=1").fetchone()[0]
        act24   = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > datetime('now','-1 day','localtime')"
        ).fetchone()[0]
        act7    = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_active > datetime('now','-7 day','localtime')"
        ).fetchone()[0]
        total_m = conn.execute("SELECT COUNT(*) FROM conversations WHERE role='user'").fetchone()[0]
        today_m = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE role='user' AND date(created_at)=date('now','localtime')"
        ).fetchone()[0]
        imgs    = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        pend    = conn.execute(
            "SELECT COUNT(*) FROM premium_requests WHERE status='pending'"
        ).fetchone()[0]
        conn.close()
        return {
            "total": total, "banned": banned, "premium": premium,
            "active_24": act24, "active_7": act7,
            "total_msgs": total_m, "today_msgs": today_m,
            "images": imgs, "pending_premium": pend
        }
    except Exception as e:
        logger.error(f"db_get_stats error: {e}")
        return {}


def db_get_all_users(limit: int = 50, offset: int = 0) -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_search_user(query: str) -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT * FROM users
            WHERE username LIKE ? OR full_name LIKE ? OR CAST(user_id AS TEXT) LIKE ?
            LIMIT 10
        """, (f"%{query}%", f"%{query}%", f"%{query}%")).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_get_premium_users() -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM users WHERE is_premium=1 ORDER BY premium_expires DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_add_premium_request(user_id: int, message: str = "") -> int:
    try:
        conn = get_db()
        cur  = conn.execute(
            "INSERT INTO premium_requests (user_id, message) VALUES (?,?)",
            (user_id, message)
        )
        rid  = cur.lastrowid
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO daily_stats (date, premium_requests) VALUES (?,1)
            ON CONFLICT(date) DO UPDATE SET premium_requests=premium_requests+1
        """, (today,))
        conn.commit()
        conn.close()
        return rid
    except Exception as e:
        logger.error(f"db_add_premium_request error: {e}")
        return 0


def db_get_pending_requests() -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT pr.*, u.username, u.full_name
            FROM premium_requests pr
            LEFT JOIN users u ON u.user_id = pr.user_id
            WHERE pr.status='pending'
            ORDER BY pr.created_at DESC LIMIT 20
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_update_request(req_id: int, status: str) -> bool:
    try:
        conn = get_db()
        conn.execute("UPDATE premium_requests SET status=? WHERE id=?", (status, req_id))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def db_get_blocked_words() -> List[str]:
    try:
        conn = get_db()
        rows = conn.execute("SELECT word FROM blocked_words").fetchall()
        conn.close()
        return [r["word"] for r in rows]
    except Exception:
        return []


def db_add_blocked_word(word: str, admin_id: int) -> bool:
    try:
        conn = get_db()
        conn.execute(
            "INSERT OR IGNORE INTO blocked_words (word, added_by) VALUES (?,?)",
            (word.lower(), admin_id)
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def db_del_blocked_word(word: str) -> bool:
    try:
        conn = get_db()
        conn.execute("DELETE FROM blocked_words WHERE word=?", (word.lower(),))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def db_get_daily_stats(days: int = 7) -> List[Dict]:
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def db_set_note(user_id: int, note: str) -> bool:
    try:
        conn = get_db()
        conn.execute("UPDATE users SET note=? WHERE user_id=?", (note, user_id))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def db_update_quiz(user_id: int, correct: bool):
    try:
        conn = get_db()
        if correct:
            conn.execute(
                "UPDATE users SET quiz_score=quiz_score+1, quiz_total=quiz_total+1 WHERE user_id=?",
                (user_id,)
            )
        else:
            conn.execute(
                "UPDATE users SET quiz_total=quiz_total+1 WHERE user_id=?",
                (user_id,)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"db_update_quiz error: {e}")


def db_reset_images(user_id: int) -> bool:
    try:
        conn = get_db()
        conn.execute("UPDATE users SET images_used=0 WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  GROK AI KLIENT
# ══════════════════════════════════════════════════════════════════════════════

_grok_client: Optional[AsyncOpenAI] = None

def get_grok_client() -> AsyncOpenAI:
    global _grok_client
    if _grok_client is None:
        _grok_client = AsyncOpenAI(
            api_key  = GROK_API_KEY,
            base_url = "https://api.x.ai/v1",
        )
    return _grok_client


async def grok_chat(messages: List[Dict], system: str = SYSTEM_PROMPT) -> str:
    if not GROK_API_KEY or GROK_API_KEY.startswith("BU_YERGA"):
        return "Grok API kaliti kiritilmagan! GROK_API_KEY ni to'ldiring."
    try:
        client = get_grok_client()
        full   = [{"role": "system", "content": system}] + messages
        resp   = await client.chat.completions.create(
            model       = db_get("grok_model", GROK_MODEL),
            messages    = full,
            max_tokens  = int(db_get("max_tokens", str(MAX_TOKENS))),
            temperature = float(db_get("temperature", str(TEMPERATURE))),
        )
        return resp.choices[0].message.content or "Bo'sh javob."
    except openai.AuthenticationError:
        return "Grok API kaliti noto'g'ri. https://console.x.ai/ dan tekshiring."
    except openai.RateLimitError:
        return "Grok cheklovi (Rate Limit). Biroz kuting."
    except openai.APIConnectionError:
        return "Grok serveriga ulanib bo'lmadi. Internet aloqasini tekshiring."
    except openai.BadRequestError as e:
        return f"So'rov rad etildi: {str(e)[:200]}"
    except Exception as e:
        logger.error(f"Grok error: {e}")
        return f"Grok xatoligi: {str(e)[:200]}"


async def grok_single(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    return await grok_chat([{"role": "user", "content": prompt}], system)


# ══════════════════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ══════════════════════════════════════════════════════════════════════════════

def is_admin(user_id: int, ctx: ContextTypes.DEFAULT_TYPE = None) -> bool:
    if user_id in ADMIN_IDS:
        return True
    if ctx and ctx.user_data.get("is_temp_admin"):
        return True
    return False


def check_banned(user_id: int) -> Optional[str]:
    user = db_get_user(user_id)
    if user and user.get("is_banned"):
        reason = user.get("ban_reason", "")
        msg = "Siz botdan ban qilingansiz."
        if reason:
            msg += f"\nSabab: {reason}"
        return msg
    return None


def check_bot_on(user_id: int = 0) -> Optional[str]:
    if db_get("bot_enabled") == "0" and user_id not in ADMIN_IDS:
        return db_get("maintenance_msg")
    return None


def check_blocked(text: str) -> bool:
    words = db_get_blocked_words()
    tl    = text.lower()
    return any(w in tl for w in words)


def mask_key(key: str) -> str:
    if not key or len(key) < 8 or key.startswith("BU_YERGA"):
        return "Kiritilmagan"
    return f"{key[:8]}...{key[-4:]}"


def user_badge(user: Dict) -> str:
    if user.get("is_banned"):
        return "[BAN]"
    if user.get("is_premium"):
        return "[PREMIUM]"
    return "[ODDIY]"


def safe_md(text: str) -> str:
    """Markdown belgilarini tozalash — Pydroid 3 uchun muhim"""
    if not text:
        return ""
    for ch in ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(ch, '')
    return text


def format_user_card(user: Dict) -> str:
    badge   = user_badge(user)
    name    = user.get("full_name") or user.get("username") or "Nomsiz"
    uname   = f"@{user['username']}" if user.get("username") else "-"
    prem    = "Premium" if user.get("is_premium") else "Oddiy"
    exp     = user.get("premium_expires", "")[:16] if user.get("is_premium") else "-"
    imgs    = user.get("images_used", 0)
    msgs    = user.get("total_msgs", 0)
    note    = user.get("note", "")
    text = (
        f"{badge} {name}\n"
        f"ID: {user['user_id']}\n"
        f"Username: {uname}\n"
        f"Holat: {prem}\n"
        f"Premium tugash: {exp}\n"
        f"Rasmlar: {imgs}\n"
        f"Xabarlar: {msgs}\n"
        f"Qoshilgan: {user.get('joined_at','')[:10]}\n"
        f"Faollik: {user.get('last_active','')[:16]}"
    )
    if note:
        text += f"\nIzoh: {note}"
    return text


# ══════════════════════════════════════════════════════════════════════════════
#  KLAVIATURALAR
# ══════════════════════════════════════════════════════════════════════════════

def kb_main(is_prem: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Grok bilan suhbat", callback_data="chat_start")],
        [
            InlineKeyboardButton("Rasm yaratish",  callback_data="image_mode"),
            InlineKeyboardButton("Quiz",            callback_data="quiz_menu"),
        ],
        [
            InlineKeyboardButton("Tarjima",         callback_data="translate_menu"),
            InlineKeyboardButton("Matn tahlil",     callback_data="analyze_menu"),
        ],
        [
            InlineKeyboardButton("Suhbat tarixi",   callback_data="history_menu"),
            InlineKeyboardButton("Profil",          callback_data="profile"),
        ],
    ]
    if is_prem:
        rows.append([InlineKeyboardButton("Premium funksiyalar", callback_data="premium_features")])
    else:
        rows.append([InlineKeyboardButton("Premium olish", callback_data="buy_premium")])
    rows.append([InlineKeyboardButton("Yordam", callback_data="help_menu")])
    return InlineKeyboardMarkup(rows)


def kb_premium_features() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Rasm (HD)",         callback_data="image_hd"),
            InlineKeyboardButton("Kod yozish",        callback_data="code_mode"),
        ],
        [
            InlineKeyboardButton("Email yozish",      callback_data="email_mode"),
            InlineKeyboardButton("Matn yaratish",     callback_data="content_mode"),
        ],
        [
            InlineKeyboardButton("Chuqur tahlil",     callback_data="deep_analyze"),
            InlineKeyboardButton("Ko'p til tarjima",  callback_data="multi_translate"),
        ],
        [
            InlineKeyboardButton("Biznes maslahat",   callback_data="business_advice"),
            InlineKeyboardButton("O'qish rejasi",     callback_data="study_plan"),
        ],
        [
            InlineKeyboardButton("Maqsad rejasi",     callback_data="goal_plan"),
            InlineKeyboardButton("Debat",             callback_data="debate_mode"),
        ],
        [
            InlineKeyboardButton("CV / Rezyume",      callback_data="cv_mode"),
            InlineKeyboardButton("Murakkab hisob",    callback_data="calc_mode"),
        ],
        [InlineKeyboardButton("Asosiy menyu",         callback_data="main_menu")],
    ])


def kb_quiz_menu() -> InlineKeyboardMarkup:
    btns = []
    row  = []
    for i, topic in enumerate(QUIZ_TOPICS):
        row.append(InlineKeyboardButton(topic, callback_data=f"quiz_topic_{topic}"))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([InlineKeyboardButton("Tasodifiy", callback_data="quiz_random")])
    btns.append([InlineKeyboardButton("Mening natijam", callback_data="quiz_stats")])
    btns.append([InlineKeyboardButton("Asosiy menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(btns)


def kb_translate() -> InlineKeyboardMarkup:
    btns = []
    row  = []
    for label, lang in TRANSLATE_LANGS:
        row.append(InlineKeyboardButton(label, callback_data=f"trans_{lang}"))
        if len(row) == 2:
            btns.append(row)
            row = []
    if row:
        btns.append(row)
    btns.append([InlineKeyboardButton("Asosiy menyu", callback_data="main_menu")])
    return InlineKeyboardMarkup(btns)


def kb_analyze() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Grammatika",    callback_data="anal_grammar"),
            InlineKeyboardButton("Xulosa",        callback_data="anal_summary"),
        ],
        [
            InlineKeyboardButton("Tuygu tahlili", callback_data="anal_sentiment"),
            InlineKeyboardButton("Kalit sozlar",  callback_data="anal_keywords"),
        ],
        [
            InlineKeyboardButton("Qayta yozish",  callback_data="anal_rewrite"),
            InlineKeyboardButton("Yaxshilash",    callback_data="anal_improve"),
        ],
        [InlineKeyboardButton("Asosiy menyu",     callback_data="main_menu")],
    ])


def kb_history() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Korish (oxirgi 10)", callback_data="hist_view"),
            InlineKeyboardButton("Ochirish",           callback_data="hist_clear_confirm"),
        ],
        [InlineKeyboardButton("Asosiy menyu", callback_data="main_menu")],
    ])


def kb_buy_premium() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Premium sotib olish", callback_data="prem_request")],
        [InlineKeyboardButton("Premium imtiyozlari", callback_data="prem_benefits")],
        [InlineKeyboardButton("Asosiy menyu",        callback_data="main_menu")],
    ])


def kb_back(target: str = "main_menu", label: str = "Orqaga") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=target)]])


def kb_confirm(action: str, label: str = "Ha") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{label}", callback_data=f"confirm_{action}"),
            InlineKeyboardButton("Bekor",   callback_data="main_menu"),
        ]
    ])


def kb_admin_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Statistika",           callback_data="adm_stats"),
            InlineKeyboardButton("Foydalanuvchilar",     callback_data="adm_users"),
        ],
        [
            InlineKeyboardButton("Premium boshqaruv",    callback_data="adm_premium"),
            InlineKeyboardButton("Premium sorovlar",     callback_data="adm_prem_requests"),
        ],
        [
            InlineKeyboardButton("Broadcast",            callback_data="adm_broadcast"),
            InlineKeyboardButton("Loglar",               callback_data="adm_logs"),
        ],
        [
            InlineKeyboardButton("Sozlamalar",           callback_data="adm_settings"),
            InlineKeyboardButton("Xavfsizlik",           callback_data="adm_security"),
        ],
        [
            InlineKeyboardButton("API holati",           callback_data="adm_apikeys"),
            InlineKeyboardButton("Kunlik hisobot",       callback_data="adm_daily"),
        ],
        [
            InlineKeyboardButton("Bloklangan sozlar",    callback_data="adm_blocked"),
            InlineKeyboardButton("Rasm statistika",      callback_data="adm_imgstats"),
        ],
        [
            InlineKeyboardButton("DB tozalash",          callback_data="adm_db_clean"),
            InlineKeyboardButton("Premium foydalanuvchilar", callback_data="adm_prem_list"),
        ],
    ])


def kb_admin_users() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Royxat",         callback_data="adm_userlist"),
            InlineKeyboardButton("Qidirish",       callback_data="adm_search"),
        ],
        [
            InlineKeyboardButton("Ban",            callback_data="adm_ban"),
            InlineKeyboardButton("Unban",          callback_data="adm_unban"),
        ],
        [
            InlineKeyboardButton("Izoh",           callback_data="adm_note"),
            InlineKeyboardButton("Xabar yozish",   callback_data="adm_msg_user"),
        ],
        [
            InlineKeyboardButton("Tarixni ochirish",   callback_data="adm_clear_user_hist"),
            InlineKeyboardButton("Rasm limitni reset", callback_data="adm_reset_img"),
        ],
        [InlineKeyboardButton("Admin menyu", callback_data="adm_main")],
    ])


def kb_admin_premium() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Premium berish",     callback_data="adm_give_prem"),
            InlineKeyboardButton("Premium olish",      callback_data="adm_remove_prem"),
        ],
        [
            InlineKeyboardButton("Narxni ozgartirish", callback_data="adm_change_price"),
            InlineKeyboardButton("Tolov malumoti",     callback_data="adm_change_payment"),
        ],
        [
            InlineKeyboardButton("Premium statistika",  callback_data="adm_prem_stats"),
            InlineKeyboardButton("Kutayotgan sorovlar", callback_data="adm_prem_requests"),
        ],
        [InlineKeyboardButton("Admin menyu", callback_data="adm_main")],
    ])


def kb_admin_settings() -> InlineKeyboardMarkup:
    bot_en = db_get("bot_enabled")
    img_en = db_get("image_enabled")
    onoff  = lambda v: "Yoqiq" if v == "1" else "Ochiq"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Bot: {onoff(bot_en)}",   callback_data="adm_toggle_bot")],
        [InlineKeyboardButton(f"Rasm: {onoff(img_en)}",  callback_data="adm_toggle_img")],
        [InlineKeyboardButton("Xush kelibsiz xabari",    callback_data="adm_edit_welcome")],
        [InlineKeyboardButton("Texnik ish xabari",       callback_data="adm_edit_maint")],
        [InlineKeyboardButton("Max tokenlar",            callback_data="adm_edit_maxtok")],
        [InlineKeyboardButton("Temperature",             callback_data="adm_edit_temp")],
        [InlineKeyboardButton("Grok modeli",             callback_data="adm_edit_model")],
        [InlineKeyboardButton("Admin menyu",             callback_data="adm_main")],
    ])


def kb_admin_security() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Parolni ozgartirish",  callback_data="adm_change_pass")],
        [InlineKeyboardButton("Loglarni tozalash",    callback_data="adm_clear_logs")],
        [InlineKeyboardButton("Admin ID lar",         callback_data="adm_admin_list")],
        [InlineKeyboardButton("Ban royxati",          callback_data="adm_banlist")],
        [InlineKeyboardButton("Admin menyu",          callback_data="adm_main")],
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  BUYRUQLAR
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_upsert_user(user.id, user.username or "", user.full_name or "")

    if err := check_bot_on(user.id):
        await update.message.reply_text(err)
        return
    if ban := check_banned(user.id):
        await update.message.reply_text(ban)
        return

    is_prem = db_is_premium(user.id)
    welcome = db_get("welcome_msg")
    badge   = "Premium foydalanuvchi" if is_prem else "Oddiy foydalanuvchi"
    text    = f"{welcome}\n\n{badge}"
    await update.message.reply_text(text, reply_markup=kb_main(is_prem))


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    db_upsert_user(user.id, user.username or "", user.full_name or "")
    is_prem = db_is_premium(user.id)
    await update.message.reply_text("Asosiy menyu", reply_markup=kb_main(is_prem))


async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_upsert_user(user.id, user.username or "", user.full_name or "")
    if is_admin(user.id, ctx):
        await _show_admin_panel(update, ctx)
        return
    ctx.user_data["waiting_admin_pass"] = True
    await update.message.reply_text("Admin paneli\n\nKirish uchun parolni yozing:")


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id, ctx):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    s = db_get_stats()
    await update.message.reply_text(
        f"Statistika\n\n"
        f"Jami: {s.get('total',0)}\n"
        f"Premium: {s.get('premium',0)}\n"
        f"Faol (24s): {s.get('active_24',0)}\n"
        f"Banlangan: {s.get('banned',0)}\n"
        f"Bugungi xabarlar: {s.get('today_msgs',0)}\n"
        f"Jami xabarlar: {s.get('total_msgs',0)}\n"
        f"Rasmlar: {s.get('images',0)}\n"
        f"Kutayotgan sorovlar: {s.get('pending_premium',0)}",
        reply_markup=kb_back("adm_main")
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    is_prem = db_is_premium(user.id)
    text = (
        "Bot haqida\n\n"
        "Grok AI - xAI tomonidan yaratilgan kuchli sun'iy intellekt\n\n"
        "Buyruqlar:\n"
        "/start - Botni ishga tushirish\n"
        "/menu - Asosiy menyu\n"
        "/premium - Premium haqida\n"
        "/admin - Admin paneli\n"
        "/help - Yordam\n\n"
        "Funksiyalar:\n"
        "- Grok bilan suhbat\n"
        "- Rasm yaratish\n"
        "- Quiz / Test\n"
        "- Matn tarjima\n"
        "- Matn tahlil\n"
    )
    if is_prem:
        text += (
            "\nPremium funksiyalar:\n"
            "- HD rasm yaratish\n"
            "- Kod yozish\n"
            "- Email yozish\n"
            "- Chuqur tahlil\n"
            "- Biznes maslahat\n"
            "- CV / Rezyume\n"
        )
    await update.message.reply_text(text, reply_markup=kb_back())


async def cmd_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    is_prem = db_is_premium(user.id)
    if is_prem:
        u   = db_get_user(user.id)
        exp = u.get("premium_expires", "")[:16] if u else "-"
        await update.message.reply_text(
            f"Siz Premium foydalanuvchisiz!\n\n"
            f"Tugash sanasi: {exp}\n\n"
            f"Barcha premium funksiyalar sizga ochiq!",
            reply_markup=kb_back()
        )
    else:
        price_uzs = db_get("premium_price_uzs", str(PREMIUM_PRICE_UZS))
        price_usd = db_get("premium_price_usd", str(PREMIUM_PRICE_USD))
        await update.message.reply_text(
            f"Premium obuna\n\n"
            f"Narxi: {price_uzs} som / ${price_usd}\n"
            f"Muddat: 30 kun\n\n"
            f"Premium imtiyozlari:\n"
            f"- {PREMIUM_IMAGE_LIMIT} ta rasm (oddiy: {FREE_IMAGE_LIMIT} ta)\n"
            f"- Kod yozish\n"
            f"- Email yozish\n"
            f"- Kontent yaratish\n"
            f"- Chuqur tahlil\n"
            f"- Biznes maslahat\n"
            f"- CV / Rezyume\n"
            f"- Ko'p til tarjima\n",
            reply_markup=kb_buy_premium()
        )


# ══════════════════════════════════════════════════════════════════════════════
#  XABAR HANDLERI
# ══════════════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()
    db_upsert_user(user.id, user.username or "", user.full_name or "")

    if ctx.user_data.get("waiting_admin_pass"):
        await _check_admin_pass(update, ctx, text)
        return

    if is_admin(user.id, ctx) and ctx.user_data.get("admin_action"):
        handled = await _handle_admin_text(update, ctx, text)
        if handled:
            return

    if err := check_bot_on(user.id):
        await update.message.reply_text(err)
        return

    if ban := check_banned(user.id):
        await update.message.reply_text(ban)
        return

    if check_blocked(text):
        await update.message.reply_text("Xabaringizda taqiqlangan soz mavjud.")
        return

    if ctx.user_data.get("broadcast_mode") and is_admin(user.id, ctx):
        ctx.user_data.pop("broadcast_mode", None)
        await _do_broadcast(update, ctx, text)
        return

    if ctx.user_data.get("image_mode"):
        ctx.user_data.pop("image_mode", None)
        await _do_image(update, ctx, text)
        return

    if ctx.user_data.get("prem_req_mode"):
        ctx.user_data.pop("prem_req_mode", None)
        await _submit_premium_request(update, ctx, text)
        return

    if ctx.user_data.get("quiz_waiting"):
        await _check_quiz_answer(update, ctx, text)
        return

    mode = ctx.user_data.get("chat_mode")
    if mode:
        await _handle_mode(update, ctx, text, mode)
        return

    await _handle_chat(update, ctx, text)


async def _handle_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    user = update.effective_user
    db_add_msg(user.id, "user", text)
    db_inc_msgs(user.id)

    try:
        await update.message.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass

    history = db_get_history(user.id)
    reply   = await grok_chat(history)

    if not any(reply.startswith(x) for x in ("Grok API", "Grok cheklovi", "Grok serveriga", "So'rov rad", "Grok xatoligi")):
        db_add_msg(user.id, "assistant", reply)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Tarixni ochirish", callback_data="hist_clear_confirm"),
            InlineKeyboardButton("Menyu",            callback_data="main_menu"),
        ]
    ])
    await update.message.reply_text(f"Grok:\n\n{reply}", reply_markup=kb)


async def _handle_mode(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str, mode: str):
    await update.message.chat.send_action(ChatAction.TYPING)

    prompts = {
        "translate":       lambda t: f"'{ctx.user_data.get('trans_lang','ingliz')}' tiliga tarjima qil:\n\n{t}",
        "anal_grammar":    lambda t: f"Quyidagi matnning grammatikasini tekshir va xatolarni kors:\n\n{t}",
        "anal_summary":    lambda t: f"Quyidagi matnning qisqacha xulosasini yoz:\n\n{t}",
        "anal_sentiment":  lambda t: f"Quyidagi matnning kayfiyatini (ijobiy/salbiy/neytral) aniqla:\n\n{t}",
        "anal_keywords":   lambda t: f"Quyidagi matndan asosiy kalit sozlarni ajrat:\n\n{t}",
        "anal_rewrite":    lambda t: f"Quyidagi matnni qayta yoz (mazmunni saqlab, uslubni yaxshila):\n\n{t}",
        "anal_improve":    lambda t: f"Quyidagi matnni yaxshila va takomillashtir:\n\n{t}",
        "code_mode":       lambda t: f"Dasturlash: {t}\n\nKodini yoz yoki tushuntir.",
        "email_mode":      lambda t: f"Professional email yoz: {t}",
        "content_mode":    lambda t: f"Kontent yarat: {t}",
        "deep_analyze":    lambda t: f"Chuqur tahlil qil: {t}",
        "multi_translate": lambda t: f"O'zbek, Rus, va Ingliz tillariga tarjima qil:\n\n{t}",
        "business_advice": lambda t: f"Biznes maslahat ber: {t}",
        "study_plan":      lambda t: f"O'qish rejasi tuz: {t}",
        "goal_plan":       lambda t: f"Maqsadga erishish rejasi tuz: {t}",
        "debate_mode":     lambda t: f"Mavzu: {t}\nIkkala tomonning argumentlarini keltir.",
        "cv_mode":         lambda t: f"CV / Rezyume yoz: {t}",
        "calc_mode":       lambda t: f"Hisob-kitob qil va tushuntir: {t}",
    }

    prompt_fn = prompts.get(mode)
    if not prompt_fn:
        ctx.user_data.pop("chat_mode", None)
        await _handle_chat(update, ctx, text)
        return

    ctx.user_data.pop("chat_mode", None)
    reply = await grok_single(prompt_fn(text))
    await update.message.reply_text(f"Grok javobi:\n\n{reply}", reply_markup=kb_back())


async def _do_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE, prompt: str):
    user    = update.effective_user
    is_prem = db_is_premium(user.id)
    limit   = PREMIUM_IMAGE_LIMIT if is_prem else FREE_IMAGE_LIMIT
    used    = db_get_image_count(user.id)

    if used >= limit:
        if is_prem:
            await update.message.reply_text(
                f"Premium limitingiz tugadi! ({used}/{limit} ta rasm)\nAdmin bilan boglanin.",
                reply_markup=kb_back()
            )
        else:
            price_uzs = db_get("premium_price_uzs", str(PREMIUM_PRICE_UZS))
            await update.message.reply_text(
                f"Rasm limitingiz tugadi!\n\n"
                f"Oddiy: {FREE_IMAGE_LIMIT} ta\n"
                f"Premium: {PREMIUM_IMAGE_LIMIT} ta\n\n"
                f"Premium narxi: {price_uzs} som",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Premium olish", callback_data="buy_premium")],
                    [InlineKeyboardButton("Menyu",         callback_data="main_menu")],
                ])
            )
        return

    wait_msg = await update.message.reply_text(
        f"Rasm tavsifi tayyorlanmoqda... ({used+1}/{limit})\n(10-30 soniya)"
    )

    try:
        await update.message.chat.send_action(ChatAction.TYPING)
    except Exception:
        pass

    enhanced_prompt = await grok_single(
        f"Make this image prompt more detailed and vivid for DALL-E (keep under 100 words): {prompt}",
        "You are an expert at writing image generation prompts. Return ONLY the improved prompt, nothing else."
    )
    if any(enhanced_prompt.startswith(x) for x in ("Grok", "So'rov")):
        enhanced_prompt = prompt

    try:
        await wait_msg.delete()
    except Exception:
        pass

    db_inc_image(user.id)
    try:
        conn = get_db()
        conn.execute("INSERT INTO images (user_id, prompt) VALUES (?,?)", (user.id, prompt[:500]))
        conn.commit()
        conn.close()
    except Exception:
        pass

    await update.message.reply_text(
        f"Rasm tavsifi tayyor!\n\n"
        f"Sizning sorovingiz:\n{prompt}\n\n"
        f"Yaxshilangan tavsif:\n{enhanced_prompt}\n\n"
        f"Foydalanilgan: {used+1}/{limit} ta\n\n"
        f"Bu tavsifni DALL-E, Midjourney yoki boshqa rasm generatorda ishlating!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Yana rasm", callback_data="image_mode")],
            [InlineKeyboardButton("Menyu",     callback_data="main_menu")],
        ])
    )


async def _submit_premium_request(update: Update, ctx: ContextTypes.DEFAULT_TYPE, msg: str):
    user    = update.effective_user
    req_id  = db_add_premium_request(user.id, msg[:500])
    payment = db_get("premium_payment_info")

    await update.message.reply_text(
        f"Sorovingiz qabul qilindi!\n\n"
        f"Sorov raqami: #{req_id}\n\n"
        f"{payment}\n\n"
        f"Tolovdan song admin tekshiradi va premium aktivlanadi.",
        reply_markup=kb_back()
    )

    name  = user.full_name or user.username or str(user.id)
    uname = f"@{user.username}" if user.username else "username yoq"
    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_message(
                admin_id,
                f"Yangi Premium sorov!\n\n"
                f"Foydalanuvchi: {name}\n"
                f"{uname}\n"
                f"ID: {user.id}\n"
                f"Sorov #{req_id}\n\n"
                f"Xabar: {msg}\n\n"
                f"Tasdiqlash uchun admin panelga kiring.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            f"Tasdiqlash #{req_id}",
                            callback_data=f"adm_approve_req_{req_id}_{user.id}"
                        ),
                        InlineKeyboardButton(
                            "Rad etish",
                            callback_data=f"adm_reject_req_{req_id}_{user.id}"
                        ),
                    ]
                ])
            )
        except Exception:
            pass


async def _check_quiz_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    user   = update.effective_user
    answer = ctx.user_data.get("quiz_answer", "").lower().strip()
    ctx.user_data.pop("quiz_waiting", None)
    ctx.user_data.pop("quiz_answer", None)

    if not answer:
        return

    user_ans = text.lower().strip()
    check_prompt = (
        f"Savol: {ctx.user_data.get('quiz_question','')}\n"
        f"To'g'ri javob: {answer}\n"
        f"Foydalanuvchi javobi: {user_ans}\n\n"
        f"Foydalanuvchi javobi to'g'rimi? Faqat 'HA' yoki 'YOQ' deb javob ber."
    )
    check   = await grok_single(check_prompt, "You are a quiz judge. Answer only HA or YOQ.")
    correct = "HA" in check.upper() or user_ans == answer

    db_update_quiz(user.id, correct)
    u     = db_get_user(user.id)
    score = u.get("quiz_score", 0) if u else 0
    total = u.get("quiz_total", 0) if u else 0

    if correct:
        text_out = f"Togri!\n\nJavob: {answer}\n\nNatijangiz: {score}/{total}"
    else:
        text_out = f"Notogri!\n\nTogri javob: {answer}\n\nNatijangiz: {score}/{total}"

    await update.message.reply_text(
        text_out,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Yana savol", callback_data="quiz_random"),
                InlineKeyboardButton("Menyu",      callback_data="main_menu"),
            ]
        ])
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CALLBACK HANDLERI
# ══════════════════════════════════════════════════════════════════════════════

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data    = query.data
    user    = update.effective_user
    db_upsert_user(user.id, user.username or "", user.full_name or "")
    is_prem = db_is_premium(user.id)

    if data == "main_menu":
        await query.edit_message_text("Asosiy menyu:", reply_markup=kb_main(is_prem))
        return

    if data == "chat_start":
        ctx.user_data.pop("chat_mode", None)
        await query.edit_message_text(
            "Grok bilan suhbat\n\nSavolingizni yozing. Men javob beraman!\n(Tarix avtomatik saqlanadi)",
            reply_markup=kb_back()
        )
        return

    if data in ("image_mode", "image_hd"):
        if db_get("image_enabled") == "0":
            await query.edit_message_text("Rasm yaratish hozirda ochiq.", reply_markup=kb_back())
            return
        used  = db_get_image_count(user.id)
        limit = PREMIUM_IMAGE_LIMIT if is_prem else FREE_IMAGE_LIMIT
        ctx.user_data["image_mode"] = True
        await query.edit_message_text(
            f"Rasm yaratish\n\n"
            f"Foydalanilgan: {used}/{limit} ta\n\n"
            f"Rasmni tasvirlab yozing:\n"
            f"Misol: A futuristic city at night, colorful, detailed\n\n"
            f"Tavsifingizni yozing:",
            reply_markup=kb_back()
        )
        return

    if data == "quiz_menu":
        await query.edit_message_text(
            "Quiz — Bilimingizni sinang!\n\nMavzu tanlang:",
            reply_markup=kb_quiz_menu()
        )
        return

    if data.startswith("quiz_topic_") or data == "quiz_random":
        topic = data.replace("quiz_topic_", "") if data != "quiz_random" else random.choice(QUIZ_TOPICS)
        await query.edit_message_text(f"{topic} — savol tayyorlanmoqda...")
        question = await grok_single(
            f"'{topic}' mavzusida qiziqarli bir savol ber. "
            f"Format: SAVOL: [savol matni]\nJAVOB: [togri javob]\n"
            f"Faqat shu formatda yaz, boshqa narsa yozma.",
            "You are a quiz master. Follow the format exactly."
        )
        lines  = question.strip().split("\n")
        q_text = ""
        a_text = ""
        for line in lines:
            if line.upper().startswith("SAVOL:"):
                q_text = line.split(":", 1)[1].strip()
            elif line.upper().startswith("JAVOB:"):
                a_text = line.split(":", 1)[1].strip()
        if not q_text:
            q_text = question
            a_text = "-"

        ctx.user_data["quiz_waiting"]  = True
        ctx.user_data["quiz_answer"]   = a_text.lower()
        ctx.user_data["quiz_question"] = q_text

        await query.edit_message_text(
            f"Quiz — {topic}\n\n{q_text}\n\nJavobingizni yozing:",
            reply_markup=kb_back()
        )
        return

    if data == "quiz_stats":
        u     = db_get_user(user.id)
        score = u.get("quiz_score", 0) if u else 0
        total = u.get("quiz_total", 0) if u else 0
        pct   = int(score / total * 100) if total > 0 else 0
        await query.edit_message_text(
            f"Quiz natijalaringiz\n\nTogri: {score}\nJami: {total}\nFoiz: {pct}%",
            reply_markup=kb_back("quiz_menu", "Quiz menyusi")
        )
        return

    if data == "translate_menu":
        await query.edit_message_text(
            "Tarjima\n\nQaysi tilga tarjima qilmoqchisiz?",
            reply_markup=kb_translate()
        )
        return

    if data.startswith("trans_"):
        lang = data[6:]
        ctx.user_data["chat_mode"]  = "translate"
        ctx.user_data["trans_lang"] = lang
        lang_label = next((k for k, v in TRANSLATE_LANGS if v == lang), lang)
        await query.edit_message_text(
            f"{lang_label} tiliga tarjima\n\nMatingizni yozing:",
            reply_markup=kb_back("translate_menu")
        )
        return

    if data == "analyze_menu":
        await query.edit_message_text("Matn tahlil\n\nQanday tahlil kerak?", reply_markup=kb_analyze())
        return

    for anal_type in ("grammar", "summary", "sentiment", "keywords", "rewrite", "improve"):
        if data == f"anal_{anal_type}":
            labels = {
                "grammar":   "Grammatika tekshirish",
                "summary":   "Xulosa chiqarish",
                "sentiment": "Tuygu tahlili",
                "keywords":  "Kalit sozlar",
                "rewrite":   "Qayta yozish",
                "improve":   "Yaxshilash",
            }
            ctx.user_data["chat_mode"] = f"anal_{anal_type}"
            await query.edit_message_text(
                f"{labels[anal_type]}\n\nMatingizni yozing:",
                reply_markup=kb_back("analyze_menu")
            )
            return

    if data == "history_menu":
        history = db_get_history_display(user.id, 8)
        if not history:
            await query.edit_message_text("Suhbat tarixi yoq.", reply_markup=kb_back())
            return
        lines = ["Oxirgi suhbat\n"]
        for msg in history:
            role  = msg["role"]
            icon  = "[Siz]" if role == "user" else "[Grok]"
            short = msg["content"][:120]
            if len(msg["content"]) > 120:
                short += "..."
            t = msg.get("created_at", "")[:16]
            lines.append(f"{icon} {t}\n{short}\n")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_history())
        return

    if data == "hist_view":
        history = db_get_history_display(user.id, 8)
        if not history:
            await query.edit_message_text("Suhbat tarixi yoq.", reply_markup=kb_back())
            return
        lines = ["Oxirgi suhbat\n"]
        for msg in history:
            role  = msg["role"]
            icon  = "[Siz]" if role == "user" else "[Grok]"
            short = msg["content"][:120]
            if len(msg["content"]) > 120:
                short += "..."
            t = msg.get("created_at", "")[:16]
            lines.append(f"{icon} {t}\n{short}\n")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_history())
        return

    if data == "hist_clear_confirm":
        await query.edit_message_text(
            "Suhbat tarixini ochirmoqchimisiz?",
            reply_markup=kb_confirm("do_clear_hist", "Ha, ochirish")
        )
        return

    if data == "confirm_do_clear_hist":
        db_clear_history(user.id)
        await query.edit_message_text("Suhbat tarixi ochirildi.", reply_markup=kb_back())
        return

    if data == "profile":
        u      = db_get_user(user.id)
        used   = db_get_image_count(user.id)
        limit  = PREMIUM_IMAGE_LIMIT if is_prem else FREE_IMAGE_LIMIT
        prem_s = "Premium" if is_prem else "Oddiy"
        prem_e = u.get("premium_expires", "")[:16] if u and is_prem else "-"
        score  = u.get("quiz_score", 0) if u else 0
        qtotal = u.get("quiz_total", 0) if u else 0
        msgs   = u.get("total_msgs", 0) if u else 0
        joined = u.get("joined_at", "")[:10] if u else "-"

        await query.edit_message_text(
            f"Profiling\n\n"
            f"ID: {user.id}\n"
            f"Ism: {user.full_name or '-'}\n"
            f"Username: @{user.username or '-'}\n"
            f"Holat: {prem_s}\n"
            f"Premium tugash: {prem_e}\n\n"
            f"Statistika:\n"
            f"Xabarlar: {msgs}\n"
            f"Rasmlar: {used}/{limit}\n"
            f"Quiz: {score}/{qtotal}\n"
            f"Qoshilgan: {joined}",
            reply_markup=kb_back()
        )
        return

    if data == "buy_premium":
        price_uzs = db_get("premium_price_uzs", str(PREMIUM_PRICE_UZS))
        price_usd = db_get("premium_price_usd", str(PREMIUM_PRICE_USD))
        await query.edit_message_text(
            f"Premium obuna\n\n"
            f"Narxi: {price_uzs} som / ${price_usd}\n"
            f"Muddat: 30 kun\n\n"
            f"Imtiyozlari:\n"
            f"- {PREMIUM_IMAGE_LIMIT} ta rasm (oddiy: {FREE_IMAGE_LIMIT} ta)\n"
            f"- Kod yozish\n"
            f"- Email yozish\n"
            f"- Kontent yaratish\n"
            f"- Chuqur tahlil\n"
            f"- Biznes maslahat\n"
            f"- CV / Rezyume\n"
            f"- Ko'p til tarjima\n",
            reply_markup=kb_buy_premium()
        )
        return

    if data == "prem_benefits":
        await query.edit_message_text(
            f"Premium imtiyozlari batafsil\n\n"
            f"Rasm yaratish: {PREMIUM_IMAGE_LIMIT} ta (oddiy {FREE_IMAGE_LIMIT} ta)\n\n"
            f"Kod yozish: Python, JS va boshqalar\n\n"
            f"Email/Xat: Professional xatlar\n\n"
            f"Kontent: Blog, post, maqola\n\n"
            f"Chuqur tahlil: Matn, hujjat\n\n"
            f"Biznes: Strategiya, marketing\n\n"
            f"O'qish: Dars rejasi\n\n"
            f"CV/Rezyume: Professional hujjat\n\n"
            f"Ko'p til: Bir vaqtda 3 tilga",
            reply_markup=kb_buy_premium()
        )
        return

    if data == "prem_request":
        ctx.user_data["prem_req_mode"] = True
        payment = db_get("premium_payment_info")
        await query.edit_message_text(
            f"Premium sotib olish\n\n"
            f"{payment}\n\n"
            f"Tolov haqida xabar yozing (masalan: tolov raqami, vaqti):",
            reply_markup=kb_back()
        )
        return

    if data == "premium_features":
        if not is_prem:
            await query.edit_message_text(
                "Bu funksiya faqat premium foydalanuvchilar uchun!",
                reply_markup=kb_buy_premium()
            )
            return
        await query.edit_message_text(
            "Premium funksiyalar\n\nNimani qilmoqchisiz?",
            reply_markup=kb_premium_features()
        )
        return

    prem_modes = {
        "code_mode": "Kod yozish",
        "email_mode": "Email yozish",
        "content_mode": "Kontent yaratish",
        "deep_analyze": "Chuqur tahlil",
        "multi_translate": "Kop til tarjima",
        "business_advice": "Biznes maslahat",
        "study_plan": "Oquish rejasi",
        "goal_plan": "Maqsad rejasi",
        "debate_mode": "Debat",
        "cv_mode": "CV / Rezyume",
        "calc_mode": "Murakkab hisob",
    }
    if data in prem_modes:
        if not is_prem:
            await query.edit_message_text(
                "Bu funksiya faqat premium foydalanuvchilar uchun!",
                reply_markup=kb_buy_premium()
            )
            return
        ctx.user_data["chat_mode"] = data
        await query.edit_message_text(
            f"{prem_modes[data]}\n\nSorovingizni yozing:",
            reply_markup=kb_back("premium_features")
        )
        return

    if data == "help_menu":
        await query.edit_message_text(
            "Yordam\n\n"
            "Grok — xAI ning kuchli AI modeli\n\n"
            "Asosiy funksiyalar:\n"
            "- Suhbat — istalgan savol\n"
            "- Rasm — AI tavsif yaratish\n"
            "- Quiz — bilim sinash\n"
            "- Tarjima — 8 ta til\n"
            "- Tahlil — matn tahlili\n\n"
            "Buyruqlar:\n"
            "/start /menu /premium /help /admin\n\n"
            "Premium uchun: /premium",
            reply_markup=kb_back()
        )
        return

    if data.startswith("adm_") or data == "adm_main":
        await _handle_admin_cb(update, ctx, data)
        return

    if data.startswith("adm_approve_req_") or data.startswith("adm_reject_req_"):
        if not is_admin(user.id, ctx):
            await query.answer("Ruxsat yoq!", show_alert=True)
            return
        parts    = data.split("_")
        approved = "approve" in data
        req_id   = int(parts[3])
        target   = int(parts[4])
        db_update_request(req_id, "approved" if approved else "rejected")
        if approved:
            db_set_premium(target, True, 30)
            db_log_admin(user.id, user.full_name or "", "give_premium_req", target, f"req#{req_id}")
            try:
                await ctx.bot.send_message(
                    target,
                    f"Tabriklaymiz!\n\n"
                    f"Sizga 30 kunlik Premium berildi!\n\n"
                    f"Barcha premium funksiyalar faollashdi!"
                )
            except Exception:
                pass
            await query.edit_message_text(f"#{req_id} sorov tasdiqlandi. {target} ga premium berildi.")
        else:
            try:
                await ctx.bot.send_message(target, "Sorovingiz rad etildi.\n\nMuammo bolsa admin bilan boglanin.")
            except Exception:
                pass
            await query.edit_message_text(f"#{req_id} sorov rad etildi.")
        return


# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

async def _show_admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    s    = db_get_stats()
    text = (
        f"Admin Panel\n\n"
        f"Jami: {s.get('total',0)} | "
        f"Premium: {s.get('premium',0)} | "
        f"Ban: {s.get('banned',0)}\n"
        f"Faol(24s): {s.get('active_24',0)} | "
        f"Bugun: {s.get('today_msgs',0)}\n"
        f"Rasmlar: {s.get('images',0)} | "
        f"Kutayotgan: {s.get('pending_premium',0)}"
    )
    kb = kb_admin_main()
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    elif update.message:
        await update.message.reply_text(text, reply_markup=kb)


async def _check_admin_pass(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    ctx.user_data.pop("waiting_admin_pass", None)
    pw = db_get("admin_password", ADMIN_PASSWORD)
    if text == pw:
        ctx.user_data["is_temp_admin"] = True
        db_log_admin(update.effective_user.id, update.effective_user.full_name or "", "login_pass")
        await _show_admin_panel(update, ctx)
    else:
        db_log_admin(update.effective_user.id, update.effective_user.full_name or "",
                     "login_fail", 0, "notogri parol")
        await update.message.reply_text("Notogri parol!")


async def _handle_admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    user  = update.effective_user

    if not is_admin(user.id, ctx):
        await query.edit_message_text("Sizda admin huquqi yoq!")
        return

    if data == "adm_main":
        await _show_admin_panel(update, ctx)
        return

    if data == "adm_stats":
        s = db_get_stats()
        await query.edit_message_text(
            f"Bot statistikasi\n\n"
            f"Jami: {s.get('total',0)}\n"
            f"Premium: {s.get('premium',0)}\n"
            f"Faol (24s): {s.get('active_24',0)}\n"
            f"Haftalik faol: {s.get('active_7',0)}\n"
            f"Banlangan: {s.get('banned',0)}\n"
            f"Bugungi xabarlar: {s.get('today_msgs',0)}\n"
            f"Jami xabarlar: {s.get('total_msgs',0)}\n"
            f"Rasmlar: {s.get('images',0)}\n"
            f"Kutayotgan premium: {s.get('pending_premium',0)}",
            reply_markup=kb_back("adm_main")
        )
        return

    if data == "adm_users":
        await query.edit_message_text("Foydalanuvchilar boshqaruvi", reply_markup=kb_admin_users())
        return

    if data == "adm_userlist":
        users = db_get_all_users(20)
        lines = ["Foydalanuvchilar (oxirgi 20)\n"]
        for u in users:
            badge = "[P]" if u["is_premium"] else ("[B]" if u["is_banned"] else "[-]")
            name  = u.get("full_name") or u.get("username") or str(u["user_id"])
            msgs  = u.get("total_msgs", 0)
            imgs  = u.get("images_used", 0)
            lines.append(f"{badge} {name[:20]} | {u['user_id']} | msg:{msgs} img:{imgs}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_users"))
        return

    if data == "adm_search":
        ctx.user_data["admin_action"] = "search_user"
        await query.edit_message_text("Foydalanuvchi ID, username yoki ism yozing:", reply_markup=kb_back("adm_users"))
        return

    if data == "adm_ban":
        ctx.user_data["admin_action"] = "ban_user"
        await query.edit_message_text(
            "Ban qilish\n\nFormat: ID sabab\nMisol: 123456789 Spam",
            reply_markup=kb_back("adm_users")
        )
        return

    if data == "adm_unban":
        ctx.user_data["admin_action"] = "unban_user"
        await query.edit_message_text("Unban\n\nFoydalanuvchi ID sini yozing:", reply_markup=kb_back("adm_users"))
        return

    if data == "adm_note":
        ctx.user_data["admin_action"] = "set_note"
        await query.edit_message_text("Izoh\n\nFormat: ID izoh matni", reply_markup=kb_back("adm_users"))
        return

    if data == "adm_msg_user":
        ctx.user_data["admin_action"] = "msg_user"
        await query.edit_message_text("Foydalanuvchiga xabar\n\nFormat: ID xabar matni", reply_markup=kb_back("adm_users"))
        return

    if data == "adm_clear_user_hist":
        ctx.user_data["admin_action"] = "clear_user_hist"
        await query.edit_message_text("Foydalanuvchi tarixini ochirish\n\nID yozing:", reply_markup=kb_back("adm_users"))
        return

    if data == "adm_reset_img":
        ctx.user_data["admin_action"] = "reset_img"
        await query.edit_message_text("Rasm limitini reset\n\nFoydalanuvchi ID sini yozing:", reply_markup=kb_back("adm_users"))
        return

    if data == "adm_banlist":
        bans = [u for u in db_get_all_users(100) if u["is_banned"]]
        if not bans:
            await query.edit_message_text("Banlangan foydalanuvchi yoq.", reply_markup=kb_back("adm_security"))
            return
        lines = ["Banlangan foydalanuvchilar\n"]
        for u in bans:
            name   = u.get("full_name") or u.get("username") or str(u["user_id"])
            reason = u.get("ban_reason", "-")
            lines.append(f"[B] {name} | {u['user_id']} | {reason}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_security"))
        return

    if data == "adm_premium":
        await query.edit_message_text("Premium boshqaruv", reply_markup=kb_admin_premium())
        return

    if data == "adm_give_prem":
        ctx.user_data["admin_action"] = "give_premium"
        await query.edit_message_text(
            "Premium berish\n\nFormat: ID kun\nMisol: 123456789 30",
            reply_markup=kb_back("adm_premium")
        )
        return

    if data == "adm_remove_prem":
        ctx.user_data["admin_action"] = "remove_premium"
        await query.edit_message_text("Premium olib tashlash\n\nFoydalanuvchi ID sini yozing:", reply_markup=kb_back("adm_premium"))
        return

    if data == "adm_change_price":
        ctx.user_data["admin_action"] = "change_price"
        p_uzs = db_get("premium_price_uzs")
        p_usd = db_get("premium_price_usd")
        await query.edit_message_text(
            f"Narxni ozgartirish\n\nJoriy: {p_uzs} som / ${p_usd}\n\nFormat: uzs_narx usd_narx\nMisol: 50000 5",
            reply_markup=kb_back("adm_premium")
        )
        return

    if data == "adm_change_payment":
        ctx.user_data["admin_action"] = "change_payment"
        cur = db_get("premium_payment_info")
        await query.edit_message_text(
            f"Tolov malumotini ozgartirish\n\nJoriy:\n{cur}\n\nYangi malumotni yozing:",
            reply_markup=kb_back("adm_premium")
        )
        return

    if data == "adm_prem_stats":
        prems = db_get_premium_users()
        lines = [f"Premium statistika\n\nJami premium: {len(prems)}\n"]
        for u in prems[:15]:
            name = u.get("full_name") or u.get("username") or str(u["user_id"])
            exp  = u.get("premium_expires", "")[:10]
            lines.append(f"[P] {name[:20]} | {u['user_id']} | {exp}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_premium"))
        return

    if data == "adm_prem_list":
        prems = db_get_premium_users()
        if not prems:
            await query.edit_message_text("Premium foydalanuvchi yoq.", reply_markup=kb_back("adm_main"))
            return
        lines = ["Premium foydalanuvchilar\n"]
        for u in prems:
            name = u.get("full_name") or u.get("username") or str(u["user_id"])
            exp  = u.get("premium_expires", "")[:10]
            lines.append(f"[P] {name[:20]} | {u['user_id']} | {exp}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_main"))
        return

    if data == "adm_prem_requests":
        reqs = db_get_pending_requests()
        if not reqs:
            await query.edit_message_text("Kutayotgan premium sorovlar yoq.", reply_markup=kb_back("adm_main"))
            return
        lines = [f"Kutayotgan sorovlar ({len(reqs)} ta)\n"]
        btns  = []
        for r in reqs[:10]:
            name  = r.get("full_name") or r.get("username") or str(r["user_id"])
            uname = f"@{r['username']}" if r.get("username") else "-"
            lines.append(
                f"#{r['id']} {name} ({uname})\n"
                f"ID: {r['user_id']} | {r['created_at'][:10]}\n"
                f"{r.get('message','')[:80]}\n"
            )
            btns.append([
                InlineKeyboardButton(
                    f"Tasdiqlash #{r['id']}",
                    callback_data=f"adm_approve_req_{r['id']}_{r['user_id']}"
                ),
                InlineKeyboardButton(
                    "Rad",
                    callback_data=f"adm_reject_req_{r['id']}_{r['user_id']}"
                ),
            ])
        btns.append([InlineKeyboardButton("Admin menyu", callback_data="adm_main")])
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(btns)
        )
        return

    if data == "adm_broadcast":
        ctx.user_data["broadcast_mode"] = True
        await query.edit_message_text(
            "Broadcast\n\nBarcha foydalanuvchilarga yuboriladigan xabarni yozing:",
            reply_markup=kb_back("adm_main")
        )
        return

    if data == "adm_logs":
        logs = db_get_admin_logs(15)
        if not logs:
            await query.edit_message_text("Loglar yoq.", reply_markup=kb_back("adm_main"))
            return
        lines = ["Oxirgi admin loglari\n"]
        for l in logs:
            t = l.get("created_at", "")[:16]
            lines.append(f"{t} | {l['action']} | {l.get('admin_name','?')} -> {l.get('target_id',0)}")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_main"))
        return

    if data == "adm_settings":
        await query.edit_message_text("Bot sozlamalari", reply_markup=kb_admin_settings())
        return

    if data == "adm_toggle_bot":
        cur = db_get("bot_enabled")
        new = "0" if cur == "1" else "1"
        db_set("bot_enabled", new)
        s = "yoqildi" if new == "1" else "ochirildi"
        await query.edit_message_text(f"Bot {s}", reply_markup=kb_admin_settings())
        return

    if data == "adm_toggle_img":
        cur = db_get("image_enabled")
        new = "0" if cur == "1" else "1"
        db_set("image_enabled", new)
        s = "yoqildi" if new == "1" else "ochirildi"
        await query.edit_message_text(f"Rasm {s}", reply_markup=kb_admin_settings())
        return

    settings_actions = {
        "adm_edit_welcome": ("edit_welcome", "Xush kelibsiz xabari", "welcome_msg"),
        "adm_edit_maint":   ("edit_maint",   "Texnik ish xabari",   "maintenance_msg"),
        "adm_edit_maxtok":  ("edit_maxtok",  "Max tokens",          "max_tokens"),
        "adm_edit_temp":    ("edit_temp",    "Temperature (0.0-1.0)","temperature"),
        "adm_edit_model":   ("edit_model",   "Grok modeli",         "grok_model"),
    }
    if data in settings_actions:
        act_key, label, db_key = settings_actions[data]
        ctx.user_data["admin_action"] = act_key
        cur_val = db_get(db_key)
        await query.edit_message_text(
            f"{label}\n\nJoriy: {cur_val}\n\nYangi qiymatni yozing:",
            reply_markup=kb_back("adm_settings")
        )
        return

    if data == "adm_security":
        await query.edit_message_text(
            f"Xavfsizlik paneli\n\n"
            f"Doimiy adminlar: {len(ADMIN_IDS)} ta\n"
            f"Barcha harakatlar loglanadi\n"
            f"Parol himoyasi aktiv",
            reply_markup=kb_admin_security()
        )
        return

    if data == "adm_change_pass":
        ctx.user_data["admin_action"] = "change_pass"
        await query.edit_message_text("Yangi parolni yozing (min 6 belgi):", reply_markup=kb_back("adm_security"))
        return

    if data == "adm_clear_logs":
        conn = get_db()
        conn.execute("DELETE FROM admin_logs")
        conn.commit()
        conn.close()
        await query.edit_message_text("Loglar tozalandi.", reply_markup=kb_back("adm_security"))
        return

    if data == "adm_admin_list":
        lines = [f"  {aid}" for aid in ADMIN_IDS]
        await query.edit_message_text(
            "Doimiy adminlar:\n\n" + "\n".join(lines) +
            "\n\n(Ozgartirish uchun ADMIN_IDS ni tahrirlang)",
            reply_markup=kb_back("adm_security")
        )
        return

    if data == "adm_apikeys":
        await query.edit_message_text(
            f"API kalitlari holati\n\n"
            f"Grok (xAI):\n  {mask_key(GROK_API_KEY)}\n\n"
            f"Kalitni ozgartirish uchun:\nmain_bot.py faylining yuqori qismini tahrirlang.",
            reply_markup=kb_back("adm_main")
        )
        return

    if data == "adm_daily":
        stats = db_get_daily_stats(7)
        if not stats:
            await query.edit_message_text("Malumot yoq.", reply_markup=kb_back("adm_main"))
            return
        lines = ["Oxirgi 7 kun\n"]
        for s in stats:
            lines.append(
                f"{s['date']}\n"
                f"  Yangi: {s['new_users']} | Xabar: {s['total_msgs']}\n"
                f"  Rasm: {s['images_made']} | Prem req: {s.get('premium_requests',0)}\n"
            )
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_main"))
        return

    if data == "adm_blocked":
        words = db_get_blocked_words()
        text  = "Bloklangan sozlar\n\n"
        if words:
            text += "\n".join(f"- {w}" for w in words[:50])
        else:
            text += "Hali soz yoq"
        text += "\n\nQoshish: sozni yozing | Ochirish: -soz"
        ctx.user_data["admin_action"] = "blocked_words"
        await query.edit_message_text(text, reply_markup=kb_back("adm_main"))
        return

    if data == "adm_imgstats":
        conn      = get_db()
        total_img = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        today_img = conn.execute(
            "SELECT COUNT(*) FROM images WHERE date(created_at)=date('now','localtime')"
        ).fetchone()[0]
        top_users = conn.execute(
            "SELECT user_id, images_used FROM users ORDER BY images_used DESC LIMIT 5"
        ).fetchall()
        conn.close()
        lines = [
            f"Rasm statistika\n\n"
            f"Jami: {total_img}\n"
            f"Bugun: {today_img}\n\n"
            f"Top 5 foydalanuvchi:\n"
        ]
        for r in top_users:
            lines.append(f"  {r['user_id']} — {r['images_used']} ta rasm")
        await query.edit_message_text("\n".join(lines), reply_markup=kb_back("adm_main"))
        return

    if data == "adm_db_clean":
        await query.edit_message_text(
            "DB Tozalash\n\nNimani tozalash?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("30 kundan eski suhbatlar", callback_data="adm_clean_old_conv")],
                [InlineKeyboardButton("Eski premium sorovlar",    callback_data="adm_clean_old_reqs")],
                [InlineKeyboardButton("Barcha loglar",            callback_data="adm_clear_logs")],
                [InlineKeyboardButton("Admin menyu",              callback_data="adm_main")],
            ])
        )
        return

    if data == "adm_clean_old_conv":
        conn = get_db()
        cnt  = conn.execute(
            "DELETE FROM conversations WHERE created_at < datetime('now','-30 days','localtime')"
        ).rowcount
        conn.commit()
        conn.close()
        await query.edit_message_text(f"{cnt} ta eski suhbat ochirildi.", reply_markup=kb_back("adm_main"))
        return

    if data == "adm_clean_old_reqs":
        conn = get_db()
        cnt  = conn.execute(
            "DELETE FROM premium_requests WHERE status != 'pending' AND created_at < datetime('now','-30 days','localtime')"
        ).rowcount
        conn.commit()
        conn.close()
        await query.edit_message_text(f"{cnt} ta eski sorov ochirildi.", reply_markup=kb_back("adm_main"))
        return


# ──────────────────────────────────────────────────────────────────────────────
#  ADMIN TEXT ACTIONS
# ──────────────────────────────────────────────────────────────────────────────

async def _handle_admin_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    action = ctx.user_data.get("admin_action")
    if not action:
        return False

    ctx.user_data.pop("admin_action", None)
    user = update.effective_user

    if action == "search_user":
        results = db_search_user(text)
        if not results:
            await update.message.reply_text(f"'{text}' topilmadi.", reply_markup=kb_back("adm_users"))
        else:
            lines = [f"'{text}' natijalari:\n"]
            for u in results:
                lines.append(format_user_card(u) + "\n")
            await update.message.reply_text("\n".join(lines), reply_markup=kb_back("adm_users"))
        return True

    if action == "ban_user":
        parts  = text.split(maxsplit=1)
        reason = parts[1] if len(parts) > 1 else ""
        try:
            uid = int(parts[0])
            db_ban_user(uid, True, reason)
            db_log_admin(user.id, user.full_name or "", "ban", uid, reason)
            await update.message.reply_text(
                f"{uid} banlandi." + (f"\nSabab: {reason}" if reason else ""),
                reply_markup=kb_back("adm_users")
            )
        except ValueError:
            await update.message.reply_text("Notogri ID format.")
        return True

    if action == "unban_user":
        try:
            uid = int(text.strip())
            db_ban_user(uid, False)
            db_log_admin(user.id, user.full_name or "", "unban", uid)
            await update.message.reply_text(f"{uid} banlandan chiqarildi.", reply_markup=kb_back("adm_users"))
        except ValueError:
            await update.message.reply_text("Notogri ID.")
        return True

    if action == "set_note":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Format: ID izoh")
            return True
        try:
            uid  = int(parts[0])
            note = parts[1]
            db_set_note(uid, note)
            db_log_admin(user.id, user.full_name or "", "set_note", uid, note[:50])
            await update.message.reply_text(f"{uid} ga izoh qoshildi.", reply_markup=kb_back("adm_users"))
        except ValueError:
            await update.message.reply_text("Notogri ID.")
        return True

    if action == "msg_user":
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await update.message.reply_text("Format: ID xabar")
            return True
        try:
            uid = int(parts[0])
            msg = parts[1]
            await ctx.bot.send_message(uid, f"Admin xabari:\n\n{msg}")
            db_log_admin(user.id, user.full_name or "", "msg_user", uid, msg[:50])
            await update.message.reply_text(f"{uid} ga xabar yuborildi.", reply_markup=kb_back("adm_users"))
        except ValueError:
            await update.message.reply_text("Notogri ID.")
        except Exception as e:
            await update.message.reply_text(f"Yuborib bolmadi: {e}")
        return True

    if action == "clear_user_hist":
        try:
            uid = int(text.strip())
            db_clear_history(uid)
            db_log_admin(user.id, user.full_name or "", "clear_user_hist", uid)
            await update.message.reply_text(f"{uid} suhbat tarixi ochirildi.", reply_markup=kb_back("adm_users"))
        except ValueError:
            await update.message.reply_text("Notogri ID.")
        return True

    if action == "reset_img":
        try:
            uid = int(text.strip())
            db_reset_images(uid)
            db_log_admin(user.id, user.full_name or "", "reset_img", uid)
            await update.message.reply_text(f"{uid} rasm limiti reset qilindi.", reply_markup=kb_back("adm_users"))
        except ValueError:
            await update.message.reply_text("Notogri ID.")
        return True

    if action == "give_premium":
        parts = text.split()
        try:
            uid  = int(parts[0])
            days = int(parts[1]) if len(parts) > 1 else 30
            db_set_premium(uid, True, days)
            db_log_admin(user.id, user.full_name or "", "give_premium", uid, f"{days} days")
            try:
                await ctx.bot.send_message(
                    uid,
                    f"Tabriklaymiz!\n\n{days} kunlik Premium berildi!\nBarcha premium funksiyalar faollashdi!"
                )
            except Exception:
                pass
            await update.message.reply_text(f"{uid} ga {days} kunlik premium berildi.", reply_markup=kb_back("adm_premium"))
        except (ValueError, IndexError):
            await update.message.reply_text("Format: ID kun (masalan: 123456789 30)")
        return True

    if action == "remove_premium":
        try:
            uid = int(text.strip())
            db_set_premium(uid, False)
            db_log_admin(user.id, user.full_name or "", "remove_premium", uid)
            try:
                await ctx.bot.send_message(uid, "Sizning premium obunangiz ochirildi.")
            except Exception:
                pass
            await update.message.reply_text(f"{uid} dan premium olib tashlandi.", reply_markup=kb_back("adm_premium"))
        except ValueError:
            await update.message.reply_text("Notogri ID.")
        return True

    if action == "change_price":
        parts = text.split()
        try:
            uzs = parts[0]
            usd = parts[1] if len(parts) > 1 else "-"
            db_set("premium_price_uzs", uzs)
            if usd != "-":
                db_set("premium_price_usd", usd)
            await update.message.reply_text(f"Narx yangilandi: {uzs} som / ${usd}", reply_markup=kb_back("adm_premium"))
        except Exception as e:
            await update.message.reply_text(f"Xato: {e}")
        return True

    if action == "change_payment":
        db_set("premium_payment_info", text)
        await update.message.reply_text("Tolov malumoti yangilandi!", reply_markup=kb_back("adm_premium"))
        return True

    if action == "edit_welcome":
        db_set("welcome_msg", text)
        await update.message.reply_text("Xush kelibsiz xabari yangilandi!", reply_markup=kb_back("adm_settings"))
        return True

    if action == "edit_maint":
        db_set("maintenance_msg", text)
        await update.message.reply_text("Texnik ish xabari yangilandi!", reply_markup=kb_back("adm_settings"))
        return True

    if action == "edit_maxtok":
        try:
            val = int(text)
            if not 100 <= val <= 8000:
                raise ValueError
            db_set("max_tokens", str(val))
            await update.message.reply_text(f"max_tokens: {val}", reply_markup=kb_back("adm_settings"))
        except ValueError:
            await update.message.reply_text("100 dan 8000 gacha raqam kiriting.")
        return True

    if action == "edit_temp":
        try:
            val = float(text)
            if not 0.0 <= val <= 1.0:
                raise ValueError
            db_set("temperature", str(val))
            await update.message.reply_text(f"temperature: {val}", reply_markup=kb_back("adm_settings"))
        except ValueError:
            await update.message.reply_text("0.0 dan 1.0 gacha son kiriting.")
        return True

    if action == "edit_model":
        db_set("grok_model", text.strip())
        await update.message.reply_text(f"Grok modeli: {text.strip()}", reply_markup=kb_back("adm_settings"))
        return True

    if action == "change_pass":
        if len(text) < 6:
            await update.message.reply_text("Parol kamida 6 belgi bolishi kerak.")
            return True
        db_set("admin_password", text)
        global ADMIN_PASSWORD
        ADMIN_PASSWORD = text
        db_log_admin(user.id, user.full_name or "", "change_password")
        await update.message.reply_text("Parol muvaffaqiyatli ozgartirildi!", reply_markup=kb_back("adm_security"))
        return True

    if action == "blocked_words":
        word = text.strip()
        if word.startswith("-"):
            w = word[1:].lower().strip()
            db_del_blocked_word(w)
            db_log_admin(user.id, user.full_name or "", "del_blocked_word", 0, w)
            await update.message.reply_text(f"'{w}' ochirildi.", reply_markup=kb_back("adm_main"))
        else:
            db_add_blocked_word(word.lower(), user.id)
            db_log_admin(user.id, user.full_name or "", "add_blocked_word", 0, word.lower())
            await update.message.reply_text(f"'{word.lower()}' qoshildi.", reply_markup=kb_back("adm_main"))
        return True

    return False


# ──────────────────────────────────────────────────────────────────────────────
#  BROADCAST
# ──────────────────────────────────────────────────────────────────────────────

async def _do_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    user  = update.effective_user
    users = db_get_all_users(10000)
    sent  = 0
    fail  = 0
    total = len(users)

    prog = await update.message.reply_text(f"Yuborilmoqda... 0/{total}")

    for i, u in enumerate(users, 1):
        if u["user_id"] == user.id:
            continue
        try:
            await ctx.bot.send_message(u["user_id"], f"Admin xabari:\n\n{text}")
            sent += 1
        except Exception:
            fail += 1

        if i % 50 == 0:
            try:
                await prog.edit_text(f"Yuborilmoqda... {i}/{total}")
            except Exception:
                pass
        if i % 30 == 0:
            await asyncio.sleep(1)

    db_log_admin(user.id, user.full_name or "", "broadcast", 0, f"sent={sent} fail={fail}")
    try:
        await prog.edit_text(
            f"Broadcast tugadi!\n\nYuborildi: {sent}\nXato: {fail}\nJami: {total}"
        )
    except Exception:
        await update.message.reply_text(f"Yuborildi: {sent}, Xato: {fail}")


# ══════════════════════════════════════════════════════════════════════════════
#  XATO HANDLERI
# ══════════════════════════════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, (NetworkError, TimedOut)):
        logger.warning(f"Tarmoq xatosi: {type(err).__name__}")
        return
    if isinstance(err, TelegramError):
        logger.error(f"Telegram xatosi: {err}")
        return
    logger.error(f"Kutilmagan xato: {err}")
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Texnik xatolik. /start bosing.")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN — PYDROID 3 UCHUN OPTIMALLASHTIRILGAN
# ══════════════════════════════════════════════════════════════════════════════

def check_config():
    print("=" * 50)
    print("TELEGRAM GROK BOT — Konfiguratsiya tekshiruvi")
    print("=" * 50)
    errors   = []
    warnings = []

    if not BOT_TOKEN or BOT_TOKEN.startswith("BU_YERGA"):
        errors.append("BOT_TOKEN kiritilmagan!")
    else:
        print(f"BOT_TOKEN: ...{BOT_TOKEN[-10:]}")

    if not ADMIN_IDS or ADMIN_IDS == [123456789]:
        warnings.append("ADMIN_IDS ozgartirilmagan!")
    else:
        print(f"ADMIN_IDS: {ADMIN_IDS}")

    if ADMIN_PASSWORD in ("adminparol123", "admin123", "password"):
        warnings.append("ADMIN_PASSWORD zaif parol!")
    else:
        print(f"ADMIN_PASSWORD: ***{ADMIN_PASSWORD[-3:]}")

    if not GROK_API_KEY or GROK_API_KEY.startswith("BU_YERGA"):
        errors.append("GROK_API_KEY kiritilmagan!")
    else:
        print(f"GROK_API_KEY: {GROK_API_KEY[:8]}...{GROK_API_KEY[-4:]}")

    for w in warnings:
        print(f"OGOHLANTIRISH: {w}")

    if errors:
        for e in errors:
            print(f"XATO: {e}")
        print("\nmain_bot.py faylining yuqori qismini tahrirlang.")
        print("=" * 50)
        return False
    print("=" * 50)
    return True


def main():
    if not check_config():
        sys.exit(1)

    print("\nDatabase ishga tushirilmoqda...")
    init_database()
    print("Bot ishga tushirilmoqda...")
    print(f"DB: {DB_FILE} | Log: {LOG_FILE}")
    print()

    # Pydroid 3 uchun event loop sozlash
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        pass

    async def post_init(application: Application) -> None:
        commands = [
            BotCommand("start",   "Botni ishga tushirish"),
            BotCommand("menu",    "Asosiy menyu"),
            BotCommand("premium", "Premium haqida"),
            BotCommand("help",    "Yordam"),
            BotCommand("admin",   "Admin paneli"),
        ]
        try:
            await application.bot.set_my_commands(commands)
            logger.info("Bot buyruqlari onatildi")
        except Exception as e:
            logger.warning(f"Buyruqlar onatilmadi: {e}")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(60)
        .read_timeout(60)
        .write_timeout(60)
        .pool_timeout(60)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("menu",    cmd_menu))
    app.add_handler(CommandHandler("premium", cmd_premium))
    app.add_handler(CommandHandler("help",    cmd_help))
    app.add_handler(CommandHandler("admin",   cmd_admin))
    app.add_handler(CommandHandler("stats",   cmd_stats))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("Bot muvaffaqiyatli ishga tushdi!")
    print("Xabarlarni kutmoqda...")
    print("Totxtatish uchun Ctrl+C\n")
    logger.info("Bot polling boshlandi")

    app.run_polling(
        poll_interval        = 2.0,
        timeout              = 60,
        drop_pending_updates = True,
        allowed_updates      = Update.ALL_TYPES,
        close_loop           = False,
    )


if __name__ == "__main__":
    main()
