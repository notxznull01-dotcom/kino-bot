import asyncio
import json
import os
import logging
import sys
from datetime import datetime
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
            "movies": [],
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
            if "movies" not in data: data["movies"] = []
            if "stats" not in data: data["stats"] = {"visits": 0, "buys": 0}
            return data
    except Exception as e:
        logger.error(f"Baza yuklashda xato: {e}")
        return {"users": {}, "banned": [], "movies": [], "kino_narxi": 99, "logs": []}

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
    giving_coin_id = State()
    giving_coin_amount = State()
    taking_coin_id = State()
    taking_coin_amount = State()
    blocking_id = State()
    unblocking_id = State()
    changing_price = State()
    sending_broadcast = State()
    writing_to_admin = State()
    
    # KINO QO'SHISH UCHUN HOLATLAR
    adding_k_name = State()
    adding_k_year = State()
    adding_k_link = State()
    adding_k_price = State()

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
    builder.button(text="➕ Kino Qo'shish", callback_data="adm_add_kino")
    builder.button(text="📢 Reklama", callback_data="adm_broadcast")
    builder.button(text="➕ Coin Berish", callback_data="adm_give_coin")
    builder.button(text="➖ Coin Olish", callback_data="adm_take_coin")
    builder.button(text="🚫 Bloklash", callback_data="adm_ban")
    builder.button(text="🔓 Blokdan Ochish", callback_data="adm_unban")
    builder.button(text="📊 Statistika", callback_data="adm_full_stats")
    builder.button(text="📜 Foydalanuvchilar", callback_data="adm_list_users")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(2)
    return builder.as_markup()

# ================= GLOBAL TEKSHIRUV =================
async def check_access(m: Message):
    db = load_db()
    if str(m.from_user.id) in db["banned"]:
        await m.answer("❌ **Siz botdan chetlatilgansiz!**")
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
        await m.answer(f"🌟 **Xush kelibsiz, {db['users'][uid]['name']}!**", reply_markup=get_main_kb(m.from_user.id))
    else:
        await state.update_data(referer=ref_id)
        await m.answer("👋 **Salom! Ismingizni kiriting:**")
        await state.set_state(BotState.waiting_name)

@dp.message(BotState.waiting_name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Raqamni yuborish", request_contact=True)
    await m.answer("📱 Telefon raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.waiting_phone)

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    uid = str(m.from_user.id)
    db = load_db()
    db["users"][uid] = {"name": data["name"], "phone": m.contact.phone_number, "coins": 100, "joined": datetime.now().strftime("%Y-%m-%d"), "refs": 0}
    ref = data.get("referer")
    if ref and ref in db["users"] and ref != uid:
        db["users"][ref]["coins"] += 50
        db["users"][ref]["refs"] += 1
    save_db(db)
    await m.answer("✅ Ro'yxatdan o'tdingiz!", reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

# ================= ADMIN PANEL =================
@dp.message(F.text == "👑 Admin Panel")
async def admin_auth_request(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("🔐 Parolni kiriting:")
    await state.set_state(BotState.admin_auth)

@dp.message(BotState.admin_auth)
async def admin_verify(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        await state.clear()
        await m.answer("🛡 Admin Panel:", reply_markup=get_admin_inline())
    else: await m.answer("❌ Xato!")

# 🎬 KINO QO'SHISH TIZIMI
@dp.callback_query(F.data == "adm_add_kino")
async def adm_add_kino_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 **Kino nomini kiriting:**")
    await state.set_state(BotState.adding_k_name)
    await c.answer()

@dp.message(BotState.adding_k_name)
async def adm_k_name(m: Message, state: FSMContext):
    await state.update_data(k_name=m.text)
    await m.answer("📅 **Yilini kiriting:**")
    await state.set_state(BotState.adding_k_year)

@dp.message(BotState.adding_k_year)
async def adm_k_year(m: Message, state: FSMContext):
    await state.update_data(k_year=m.text)
    await m.answer("🔗 **Kino linkini yuboring:**")
    await state.set_state(BotState.adding_k_link)

@dp.message(BotState.adding_k_link)
async def adm_k_link(m: Message, state: FSMContext):
    await state.update_data(k_link=m.text)
    await m.answer("💰 **Narxini kiriting (coin):**")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def adm_k_final(m: Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("⚠️ Faqat raqam!")
    data = await state.get_data()
    db = load_db()
    kino = {
        "id": len(db["movies"]) + 1,
        "name": data["k_name"],
        "year": data["k_year"],
        "link": data["k_link"],
        "price": int(m.text)
    }
    db["movies"].append(kino)
    save_db(db)
    await m.answer(f"✅ Kino qo'shildi! ID: `{kino['id']}`")
    await state.clear()

# 📢 REKLAMA
@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Reklama xabarini yuboring:")
    await state.set_state(BotState.sending_broadcast)
    await c.answer()

@dp.message(BotState.sending_broadcast)
async def adm_broadcast_send(m: Message, state: FSMContext):
    db = load_db()
    users = db.get("users", {})
    count = 0
    for uid in users:
        try:
            await m.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await m.answer(f"✅ {count} kishiga yuborildi.")
    await state.clear()

# ================= FOYDALANUVCHI AMALLARI =================

@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def movies_list(m: Message):
    if not await check_access(m): return
    db = load_db()
    movies = db.get("movies", [])
    if not movies: return await m.answer("📭 Hozircha kinolar yo'q.")
    
    text = "🎬 **KINOLAR KATALOGI**\n\n"
    for k in movies:
        text += f"🎥 {k['name']} ({k['year']})\n🎙 Dublyaj: O'zbek ✅\n🆔 Kod: `{k['id']}`\n💰 {k['price']} coin\n───────────────\n"
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎟 Kino sotib olish")
async def buy_movie_request(m: Message):
    await m.answer("🎬 Sotib olmoqchi bo'lgan kinoning **ID (Kodi)** raqamini yozing:")

@dp.message(F.text.isdigit())
async def process_buy(m: Message):
    if not await check_access(m): return
    db = load_db()
    uid = str(m.from_user.id)
    kid = int(m.text)
    
    movie = next((k for k in db["movies"] if k["id"] == kid), None)
    if not movie: return await m.answer("❌ Kino topilmadi.")
    
    if db["users"][uid]["coins"] >= movie["price"]:
        db["users"][uid]["coins"] -= movie["price"]
        db["total_orders"] += 1
        save_db(db)
        await m.answer(f"✅ **Sotib olindi!**\n🎬 {movie['name']}\n🔗 [TOMOSHA QILISH]({movie['link']})", parse_mode="Markdown")
    else:
        await m.answer(f"❌ Mablag' yetarli emas! Narxi: {movie['price']} coin")

@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    db = load_db()
    u = db["users"].get(str(m.from_user.id))
    if u: await m.answer(f"👤 Profil: {u['name']}\n💎 Balans: {u['coins']} coin\n🆔 ID: `{m.from_user.id}`")

@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_gift(m: Message):
    db = load_db()
    uid = str(m.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    if db["users"][uid].get("last_bonus") == today: return await m.answer("❌ Bugun olgansiz.")
    db["users"][uid]["coins"] += 20
    db["users"][uid]["last_bonus"] = today
    save_db(db)
    await m.answer("🎁 +20 coin berildi!")

# --- ADMIN QO'SHIMCHA ---
@dp.callback_query(F.data == "adm_close")
async def close_adm(c: CallbackQuery):
    await c.message.delete()
    await c.answer()

@dp.callback_query(F.data == "adm_full_stats")
async def adm_stats(c: CallbackQuery):
    db = load_db()
    await c.message.answer(f"📊 Statistika:\nUsers: {len(db['users'])}\nOrders: {db['total_orders']}")
    await c.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
