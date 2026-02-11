import asyncio
import json
import os
import logging
import sys
from datetime import datetime

# --- FLASK QISMI (BOT O'CHIB QOLMASLIGI UCHUN) ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot tirik!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# -----------------------------------------------

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove, 
    CallbackQuery, 
    Message, 
    InputFile, 
    FSInputFile
)

# ================= KONFIGURATSIYA =================
TOKEN = "8366692220:AAFxf6YFAa9SqmjL04pd7dmLn1oMs1W6w7U"
ADMIN_ID = 7492227388 
ADMIN_PASS = "456"
DB_FILE = "database.json"
KINO_LINK = "https://disk.yandex.uz/d/t_Ewb5pmNbJYlA"

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= MA'LUMOTLAR BAZASI =================
def load_db():
    if not os.path.exists(DB_FILE):
        initial_data = {
            "users": {},
            "banned": [],
            "kino_narxi": 99,
            "total_orders": 0,
            "logs": [],
            "stats": {"visits": 0, "buys": 0}
        }
        save_db(initial_data)
        return initial_data
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "logs" not in data: data["logs"] = []
            if "stats" not in data: data["stats"] = {"visits": 0, "buys": 0}
            return data
    except Exception as e:
        logger.error(f"Baza yuklashda xato: {e}")
        return {"users": {}, "banned": [], "kino_narxi": 99, "logs": []}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Baza saqlashda xato: {e}")

def add_log(event):
    db = load_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db["logs"].append(f"⏰ {now} | {event}")
    if len(db["logs"]) > 500:
        db["logs"] = db["logs"][-500:]
    save_db(db)

# ================= FSM HOLATLAR =================
class BotState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    admin_auth = State()
    admin_menu = State()
    giving_coin_id = State()
    giving_coin_amount = State()
    taking_coin_id = State()
    taking_coin_amount = State()
    blocking_id = State()
    unblocking_id = State()
    changing_price = State()
    sending_broadcast = State()
    writing_to_admin = State()
    rating_movie = State()

# ================= KLAVIATURALAR =================
def get_main_kb(uid):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Kinolar Ro'yxati")
    builder.button(text="🎟 Kino sotib olish")
    builder.button(text="💰 Hisobim")
    builder.button(text="🎁 Kunlik Bonus")
    builder.button(text="👥 Do'stlarni taklif qilish")
    builder.button(text="✍️ Adminga yozish")
    if uid == ADMIN_ID:
        builder.button(text="👑 Admin Panel")
        builder.button(text="📅 Bugun nima bo'ldi?")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_inline():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Coin Berish", callback_data="adm_give_coin")
    builder.button(text="➖ Coin Olish", callback_data="adm_take_coin")
    builder.button(text="🚫 Foydalanuvchini Bloklash", callback_data="adm_ban")
    builder.button(text="🔓 Blokdan Chiqarish", callback_data="adm_unban")
    builder.button(text="📢 Reklama Tarqatish", callback_data="adm_broadcast")
    builder.button(text="⚙️ Kino Narxini O'zgartirish", callback_data="adm_set_price")
    builder.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
    builder.button(text="📜 Barcha Foydalanuvchilar", callback_data="adm_list_users")
    builder.button(text="❌ Panelni Yopish", callback_data="adm_close")
    builder.adjust(2)
    return builder.as_markup()

# ================= GLOBAL TEKSHIRUV =================
async def check_access(m: Message):
    db = load_db()
    if str(m.from_user.id) in db["banned"]:
        await m.answer("❌ **Siz botdan chetlatilgansiz!**\nAdmin bilan bog'laning.")
        return False
    return True

# ================= START VA REGISTRATSIYA =================
@dp.message(CommandStart())
async def start_cmd(m: Message, state: FSMContext):
    await state.clear()
    if not await check_access(m): return
    db = load_db()
    uid = str(m.from_user.id)
    args = m.text.split()
    ref_id = args[1] if len(args) > 1 else None
    if uid in db["users"]:
        db["stats"]["visits"] += 1
        save_db(db)
        await m.answer(f"🌟 **Xush kelibsiz qaytib, {db['users'][uid]['name']}!**", reply_markup=get_main_kb(m.from_user.id))
    else:
        await state.update_data(referer=ref_id)
        await m.answer("👋 **Salom! Botimizga xush kelibsiz.**\n\nDavom etish uchun **Ismingizni** kiriting:")
        await state.set_state(BotState.waiting_name)

@dp.message(BotState.waiting_name)
async def reg_name(m: Message, state: FSMContext):
    if len(m.text) < 2:
        return await m.answer("⚠️ Iltimos, haqiqiy ismingizni kiriting:")
    await state.update_data(name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Telefon raqamni yuborish", request_contact=True)
    await m.answer(f"🤝 Rahmat, **{m.text}**! Endi pastdagi tugma orqali raqamingizni yuboring:", 
                   reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.waiting_phone)

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    uid = str(m.from_user.id)
    db = load_db()
    db["users"][uid] = {
        "name": data["name"],
        "phone": m.contact.phone_number,
        "coins": 100,
        "joined": datetime.now().strftime("%Y-%m-%d"),
        "refs": 0
    }
    ref = data.get("referer")
    if ref and ref in db["users"] and ref != uid:
        db["users"][ref]["coins"] += 50
        db["users"][ref]["refs"] += 1
        try:
            await bot.send_message(ref, f"🎊 **Tabriklaymiz!** Taklifingiz orqali yangi foydalanuvchi qo'shildi. Sizga **50 coin** berildi.")
        except: pass
    save_db(db)
    add_log(f"🆕 Yangi foydalanuvchi: {data['name']} (ID: {uid})")
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi foydalanuvchi!**\n👤 Ism: {data['name']}\n🆔 ID: `{uid}`\n📞 Tel: {m.contact.phone_number}")
    await m.answer("✅ **Ro'yxatdan muvaffaqiyatli o'tdingiz!**\nSizga **100 coin** bonus berildi.", reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

# ================= ADMIN PANEL KIRISH =================
@dp.message(F.text == "👑 Admin Panel")
async def admin_auth_request(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("🔐 **ADMIN KIRISH**\n\nIltimos, maxfiy parolni kiriting:")
    await state.set_state(BotState.admin_auth)

@dp.message(BotState.admin_auth)
async def admin_verify(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        db = load_db()
        if str(ADMIN_ID) in db["banned"]:
            db["banned"].remove(str(ADMIN_ID))
            save_db(db)
        await state.clear()
        await m.answer("🛡 **ADMIN PANEL!**\nKerakli amalni tanlang:", reply_markup=get_admin_inline())
    else:
        await m.answer("❌ **Parol noto'g'ri!**")

# ================= ADMIN FUNKSIYALARI =================

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 **Reklama xabarini yuboring.**")
    await state.set_state(BotState.sending_broadcast)
    await c.answer()

@dp.message(BotState.sending_broadcast)
async def adm_broadcast_send(m: Message, state: FSMContext):
    db = load_db()
    users = db.get("users", {})
    count = 0
    error_count = 0
    status_msg = await m.answer("⏳ Reklama tarqatilmoqda...")
    for uid in users:
        try:
            await m.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.05)
        except:
            error_count += 1
    await status_msg.edit_text(f"✅ Bajarildi: {count} ta.")
    add_log(f"Admin reklama tarqatdi.")
    await state.clear()

@dp.callback_query(F.data == "adm_list_users")
async def adm_list_users_handler(c: CallbackQuery):
    db = load_db()
    users = db.get("users", {})
    if not users: return await c.message.answer("📭 Bo'sh.")
    msg = "📜 **Foydalanuvchilar:**\n\n"
    for uid, data in users.items():
        msg += f"👤 {data['name']} | 🆔 `{uid}` | 💰 {data['coins']}\n"
        if len(msg) > 3500:
            await c.message.answer(msg, parse_mode="Markdown")
            msg = ""
    if msg: await c.message.answer(msg, parse_mode="Markdown")
    await c.answer()

@dp.callback_query(F.data == "adm_give_coin")
async def adm_give_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Coin berish uchun **ID** raqamini yozing:")
    await state.set_state(BotState.giving_coin_id)
    await c.answer()

@dp.message(BotState.giving_coin_id)
async def adm_give_id(m: Message, state: FSMContext):
    db = load_db()
    if m.text in db["users"]:
        await state.update_data(target_id=m.text)
        await m.answer(f"💰 Qancha coin qo'shmoqchisiz?")
        await state.set_state(BotState.giving_coin_amount)
    else:
        await m.answer("❌ ID topilmadi.")

@dp.message(BotState.giving_coin_amount)
async def adm_give_final(m: Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("⚠️ Faqat son!")
    data = await state.get_data()
    db = load_db()
    tid, amt = data["target_id"], int(m.text)
    db["users"][tid]["coins"] += amt
    save_db(db)
    await m.answer(f"✅ Bajarildi!")
    try: await bot.send_message(tid, f"🎁 **Admin sizga {amt} coin sovg'a qildi!**")
    except: pass
    await state.clear()

@dp.callback_query(F.data == "adm_take_coin")
async def adm_take_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Coin olib qo'yish uchun **ID** yozing:")
    await state.set_state(BotState.taking_coin_id)
    await c.answer()

@dp.message(BotState.taking_coin_id)
async def adm_take_id(m: Message, state: FSMContext):
    db = load_db()
    if m.text in db["users"]:
        await state.update_data(target_id=m.text)
        await m.answer(f"Qancha olib qo'yiladi?")
        await state.set_state(BotState.taking_coin_amount)
    else:
        await m.answer("❌ ID xato.")

@dp.message(BotState.taking_coin_amount)
async def adm_take_final(m: Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("⚠️ Faqat son!")
    data = await state.get_data()
    db = load_db()
    tid, amt = data["target_id"], int(m.text)
    db["users"][tid]["coins"] = max(0, db["users"][tid]["coins"] - amt)
    save_db(db)
    await m.answer(f"✅ Olib qo'yildi.")
    await state.clear()

@dp.callback_query(F.data == "adm_ban")
async def adm_ban_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🚫 Bloklash uchun **ID** yozing:")
    await state.set_state(BotState.blocking_id)
    await c.answer()

@dp.message(BotState.blocking_id)
async def adm_ban_final(m: Message, state: FSMContext):
    target = m.text.strip()
    db = load_db()
    if target not in db["banned"]:
        db["banned"].append(target)
        save_db(db)
        await m.answer(f"✅ Bloklandi.")
    await state.clear()

@dp.callback_query(F.data == "adm_unban")
async def adm_unban_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🔓 Blokdan ochish uchun **ID** yozing:")
    await state.set_state(BotState.unblocking_id)
    await c.answer()

@dp.message(BotState.unblocking_id)
async def adm_unban_final(m: Message, state: FSMContext):
    target = m.text.strip()
    db = load_db()
    if target in db["banned"]:
        db["banned"].remove(target)
        save_db(db)
        await m.answer(f"✅ Blokdan ochildi.")
    await state.clear()

@dp.callback_query(F.data == "adm_set_price")
async def adm_price_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer(f"⚙️ Yangi narxni yozing:")
    await state.set_state(BotState.changing_price)
    await c.answer()

@dp.message(BotState.changing_price)
async def adm_price_final(m: Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("⚠️ Raqam yozing!")
    db = load_db()
    db["kino_narxi"] = int(m.text)
    save_db(db)
    await m.answer(f"✅ Narx o'zgardi.")
    await state.clear()

@dp.callback_query(F.data == "adm_full_stats")
async def adm_stats(c: CallbackQuery):
    db = load_db()
    text = (f"📊 STATISTIKA\n👥 Foydalanuvchilar: {len(db['users'])}\n🎬 Sotuvlar: {db['total_orders']}")
    await c.message.answer(text)
    await c.answer()

@dp.message(F.text == "📅 Bugun nima bo'ldi?")
async def show_logs(m: Message):
    if m.from_user.id != ADMIN_ID: return
    db = load_db()
    if not db["logs"]: return await m.answer("📭 Bo'sh.")
    report = "📜 **OXIRGI HARAKATLAR:**\n\n" + "\n".join(db["logs"][-15:])
    await m.answer(report)

# ================= FOYDALANUVCHI AMALLARI =================

@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def movies_list(m: Message):
    if not await check_access(m): return
    db = load_db()
    text = (f"🎬 KINOLAR KATALOGI\n💰 Narxi: {db['kino_narxi']} coin")
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎟 Kino sotib olish")
async def buy_movie(m: Message):
    if not await check_access(m): return
    db = load_db()
    uid = str(m.from_user.id)
    price = db["kino_narxi"]
    if db["users"][uid]["coins"] >= price:
        db["users"][uid]["coins"] -= price
        db["total_orders"] += 1
        save_db(db)
        await m.answer(f"✅ XARID QILINDI!\n🍿 [TOMOSHA QILISH]({KINO_LINK})", parse_mode="Markdown")
    else:
        await m.answer(f"❌ Mablag' yetarli emas.")

@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    if not await check_access(m): return
    db = load_db()
    u = db["users"].get(str(m.from_user.id))
    if u:
        text = f"👤 PROFIL\n💎 Balans: {u['coins']} coin"
        await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_gift(m: Message):
    if not await check_access(m): return
    db = load_db()
    uid = str(m.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    if db["users"][uid].get("last_bonus") == today:
        return await m.answer("❌ Bugun olgansiz.")
    db["users"][uid]["coins"] += 20
    db["users"][uid]["last_bonus"] = today
    save_db(db)
    await m.answer("🎁 +20 coin berildi!")

@dp.message(F.text == "👥 Do'stlarni taklif qilish")
async def referral_info(m: Message):
    if not await check_access(m): return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={m.from_user.id}"
    await m.answer(f"🔗 `{link}`\n\nHar bir taklif uchun 50 coin!")

@dp.message(F.text == "✍️ Adminga yozish")
async def write_to_adm(m: Message, state: FSMContext):
    await m.answer("💬 Xabaringizni yozing:")
    await state.set_state(BotState.writing_to_admin)

@dp.message(BotState.writing_to_admin)
async def send_to_adm(m: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 Xabar: {m.text}\n🆔: `{m.from_user.id}`")
    await m.answer("✅ Yuborildi.")
    await state.clear()

@dp.callback_query(F.data == "adm_close")
async def close_adm_panel(c: CallbackQuery):
    await c.message.delete()
    await c.answer()

async def on_startup():
    add_log("🤖 Bot ishga tushirildi.")

async def main():
    # Keep_alive funksiyasini chaqiramiz
    keep_alive()
    dp.startup.register(on_startup)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Xato: {e}")
