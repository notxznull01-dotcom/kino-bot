import asyncio
import json
import os
import logging
import sys
import random
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove, 
    CallbackQuery, 
    Message, 
    ContentType,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)

# ================= KONFIGURATSIYA =================
TOKEN = "8366692220:AAFxf6YFAa9SqmjL04pd7dmLn1oMs1W6w7U"
ADMIN_ID = 7492227388 
ADMIN_PASS = "456"
DB_FILE = "database.json"

# --- FLASK (KEEP ALIVE) ---
app = Flask('')
@app.route('/')
def home():
    return "✅ Bot 24/7 rejimida ishlamoqda!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

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
            "total_orders": 0,
            "referrals": {},
            "daily_bonus": {}
        }
        save_db(initial_data)
        return initial_data
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Baza yuklashda xato: {e}")
        return {"users": {}, "banned": [], "movies": []}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Baza saqlashda xato: {e}")

# ================= FSM HOLATLAR =================
class BotState(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
    admin_auth = State()
    adding_k_name = State()
    adding_k_year = State()
    adding_k_link = State()
    adding_k_price = State()
    # ADMIN CHAT HOLATLARI
    admin_chat_target = State()
    in_active_chat = State()
    # REKLAMA
    sending_broadcast = State()
    # PUL O'TKAZISH
    transfer_id = State()
    transfer_amount = State()

# ================= KLAVIATURALAR =================
def get_main_kb(uid):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Kinolar Ro'yxati")
    builder.button(text="🎟 Kino sotib olish")
    builder.button(text="💰 Hisobim")
    builder.button(text="🎁 Kunlik Bonus")
    builder.button(text="👥 Taklifnomalar")
    builder.button(text="✍️ Adminga yozish")
    builder.button(text="💸 Pul o'tkazish")
    if uid == ADMIN_ID:
        builder.button(text="👑 Admin Panel")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_inline():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kino Qo'shish", callback_data="adm_add_kino")
    builder.button(text="💬 Foydalanuvchi bilan gaplashish", callback_data="adm_start_chat")
    builder.button(text="📢 Reklama", callback_data="adm_broadcast")
    builder.button(text="📊 Statistika", callback_data="adm_full_stats")
    builder.button(text="🚫 Bloklash", callback_data="adm_ban_user")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(1)
    return builder.as_markup()

# ================= JONLI MULOQOT (ADMIN CHAT) =================
@dp.callback_query(F.data == "adm_start_chat")
async def adm_chat_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("💬 Gaplashmoqchi bo'lgan foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.admin_chat_target)
    await c.answer()

@dp.message(BotState.admin_chat_target)
async def adm_request_chat(m: Message, state: FSMContext):
    target_id = m.text
    if not target_id.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data=f"chat_accept_{m.from_user.id}")
    kb.button(text="❌ Yo'q", callback_data=f"chat_reject_{m.from_user.id}")
    
    try:
        await bot.send_message(
            target_id, 
            f"🔔 **Admin ({m.from_user.id}) siz bilan bog'lanmoqchi.**\nSuhbatni boshlaysizmi?",
            reply_markup=kb.as_markup()
        )
        await m.answer(f"⏳ ID {target_id} ga so'rov yuborildi...")
    except:
        await m.answer("❌ Bot bloklangan yoki ID xato.")
    await state.clear()

@dp.callback_query(F.data.startswith("chat_"))
async def chat_handler(c: CallbackQuery, state: FSMContext):
    action = c.data.split("_")[1]
    partner_id = int(c.data.split("_")[2])
    
    if action == "accept":
        await c.message.answer("✅ Suhbat boshlandi! Yakunlash: /stop")
        await bot.send_message(partner_id, f"✅ Foydalanuvchi {c.from_user.id} suhbatga kirdi!")
        await state.set_state(BotState.in_active_chat)
        await state.update_data(chat_partner=partner_id)
        
        # Partner uchun ham holatni yoqish kerak
        partner_state = dp.fsm.resolve_context(bot, partner_id, partner_id)
        await partner_state.set_state(BotState.in_active_chat)
        await partner_state.update_data(chat_partner=c.from_user.id)
    else:
        await c.message.answer("❌ Rad etildi.")
        await bot.send_message(partner_id, "😔 Foydalanuvchi rad etdi.")
    await c.answer()

@dp.message(BotState.in_active_chat)
async def chatting(m: Message, state: FSMContext):
    data = await state.get_data()
    partner = data.get("chat_partner")
    
    if m.text == "/stop":
        await m.answer("📴 Aloqa uzildi.", reply_markup=get_main_kb(m.from_user.id))
        await bot.send_message(partner, "📴 Suhbatdosh suhbatni yakunladi.", reply_markup=get_main_kb(partner))
        await state.clear()
        partner_state = dp.fsm.resolve_context(bot, partner, partner)
        await partner_state.clear()
        return

    try:
        await bot.send_message(partner, f"💬 **Xabar:**\n{m.text}")
    except:
        await m.answer("⚠️ Xabar yetkazilmadi.")

# ================= ASOSIY LOGIKA =================
@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    db = load_db()
    uid = str(m.from_user.id)
    
    if uid in db["users"]:
        await m.answer(f"🌟 Xush kelibsiz, {db['users'][uid]['name']}!", reply_markup=get_main_kb(m.from_user.id))
    else:
        await m.answer("👋 Salom! Ismingizni kiriting:")
        await state.set_state(BotState.waiting_name)

@dp.message(BotState.waiting_name)
async def name_step(m: Message, state: FSMContext):
    await state.update_data(n=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Raqam yuborish", request_contact=True)
    await m.answer("📱 Telefon raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.waiting_phone)

@dp.message(BotState.waiting_phone, F.contact)
async def phone_step(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load_db()
    db["users"][str(m.from_user.id)] = {
        "name": data["n"],
        "phone": m.contact.phone_number,
        "coins": 50,
        "date": str(datetime.now())
    }
    save_db(db)
    await m.answer("🎉 Ro'yxatdan o'tdingiz va 50 coin oldingiz!", reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

# ================= BONUS VA HISOB =================
@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_bonus(m: Message):
    db = load_db()
    uid = str(m.from_user.id)
    today = str(datetime.now().date())
    
    if db["daily_bonus"].get(uid) == today:
        await m.answer("⚠️ Bugun bonus olgansiz! Ertaga qaytib keling.")
    else:
        bonus = random.randint(10, 50)
        db["users"][uid]["coins"] += bonus
        db["daily_bonus"][uid] = today
        save_db(db)
        await m.answer(f"🎁 Tabriklaymiz! Sizga {bonus} coin berildi!")

@dp.message(F.text == "💰 Hisobim")
async def my_account(m: Message):
    db = load_db()
    u = db["users"].get(str(m.from_user.id))
    text = f"👤 **Foydalanuvchi:** {u['name']}\n"
    text += f"🆔 **ID:** `{m.from_user.id}`\n"
    text += f"💰 **Balans:** {u['coins']} coin\n"
    text += f"📱 **Tel:** {u['phone']}"
    await m.answer(text, parse_mode="Markdown")

# ================= KINOLAR =================
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def list_movies(m: Message):
    db = load_db()
    if not db["movies"]:
        return await m.answer("📽 Hozircha kinolar yo'q.")
    
    res = "🎥 **MAVJUD KINOLAR** 🎥\n\n"
    for k in db["movies"]:
        res += f"🎬 {k['name']} ({k['year']})\n💎 {k['price']} coin | ID: `{k['id']}`\n───\n"
    await m.answer(res, parse_mode="Markdown")

# ================= ADMIN PANEL =================
@dp.message(F.text == "👑 Admin Panel")
async def admin_entry(m: Message, state: FSMContext):
    if m.from_user.id == ADMIN_ID:
        await m.answer("🔐 Admin parolini kiriting:")
        await state.set_state(BotState.admin_auth)

@dp.message(BotState.admin_auth)
async def admin_login(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        await state.clear()
        await m.answer("🛡 Admin Boshqaruv Markazi:", reply_markup=get_admin_inline())
    else:
        await m.answer("❌ Parol xato!")

@dp.callback_query(F.data == "adm_full_stats")
async def full_stats(c: CallbackQuery):
    db = load_db()
    u_count = len(db["users"])
    m_count = len(db["movies"])
    text = "📊 **TO'LIQ STATISTIKA**\n\n"
    text += f"👥 Foydalanuvchilar: {u_count} ta\n"
    text += f"🎬 Kinolar: {m_count} ta\n"
    text += f"🕒 Vaqt: {datetime.now().strftime('%H:%M:%S')}"
    await c.message.edit_text(text, reply_markup=get_admin_inline())

# --- KINO QO'SHISH ---
@dp.callback_query(F.data == "adm_add_kino")
async def add_k_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Nomini yozing:")
    await state.set_state(BotState.adding_k_name)

@dp.message(BotState.adding_k_name)
async def add_k_n(m: Message, state: FSMContext):
    await state.update_data(kn=m.text)
    await m.answer("Yilini yozing:")
    await state.set_state(BotState.adding_k_year)

@dp.message(BotState.adding_k_year)
async def add_k_y(m: Message, state: FSMContext):
    await state.update_data(ky=m.text)
    await m.answer("Linkni yozing:")
    await state.set_state(BotState.adding_k_link)

@dp.message(BotState.adding_k_link)
async def add_k_l(m: Message, state: FSMContext):
    await state.update_data(kl=m.text)
    await m.answer("Narxini yozing:")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def add_k_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load_db()
    kid = len(db["movies"]) + 1001
    db["movies"].append({
        "id": kid, "name": data["kn"], "year": data["ky"],
        "link": data["kl"], "price": int(m.text)
    })
    save_db(db)
    await m.answer(f"✅ Kino qo'shildi! ID: {kid}")
    await state.clear()

# ================= RUN =================
async def main_run():
    keep_alive()
    logger.info("Bot ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main_run())
    except:
        logger.error("Bot to'xtadi!")
