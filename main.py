import asyncio
import json
import os
import logging
import sys
import random
import secrets
import string
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
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ================= KONFIGURATSIYA =================
TOKEN = "8366692220:AAHaJhbqksDOn_TgDp645GIliCT__4yZlUk"
ADMIN_ID = 7492227388 
ADMIN_PASS = "456"
DB_FILE = "database.json"
LOG_FILE = "bot_logs.log"

# --- FLASK (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "🚀 Bot status: Active | System: Stable"

def run():
    # Render uchun portni avtomatik aniqlash
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# Loglarni mukammal sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= MA'LUMOTLAR BAZASI (XAVFSIZLIK BILAN) =================
def load_db():
    if not os.path.exists(DB_FILE):
        initial_data = {
            "users": {},
            "banned": [],
            "movies": [],
            "total_orders": 0,
            "referrals": {},
            "daily_bonus": {},
            "promocodes": {},
            "transactions": [],
            "system_stats": {"total_visits": 0, "total_buys": 0}
        }
        save_db(initial_data)
        return initial_data
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.critical(f"BAZA YUKLASHDA XATO: {e}")
        return None

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"BAZA SAQLASHDA XATO: {e}")

# ================= FSM HOLATLARI (KENGAYTIRILGAN) =================
class BotState(StatesGroup):
    # Ro'yxatdan o'tish
    waiting_name = State()
    waiting_phone = State()
    
    # Admin Panel
    admin_auth = State()
    
    # Kino amallari
    adding_k_name = State()
    adding_k_year = State()
    adding_k_link = State()
    adding_k_price = State()
    deleting_k_id = State()
    
    # Jonli muloqot
    admin_chat_target = State()
    in_active_chat = State()
    
    # Reklama va Xabarlar
    sending_broadcast = State()
    sending_personal_msg = State()
    
    # Moliya
    transfer_id = State()
    transfer_amount = State()
    entering_promo = State()
    
    # Bloklash
    blocking_id = State()

# ================= KLAVIATURALAR TIZIMI =================
def get_main_kb(uid):
    builder = ReplyKeyboardBuilder()
    builder.button(text="🎬 Kinolar Ro'yxati")
    builder.button(text="🎟 Kino sotib olish")
    builder.button(text="💰 Hisobim")
    builder.button(text="🎁 Kunlik Bonus")
    builder.button(text="👥 Taklifnomalar")
    builder.button(text="✍️ Adminga yozish")
    builder.button(text="💳 Balansni to'ldirish")
    builder.button(text="🧧 Promokod")
    if uid == ADMIN_ID:
        builder.button(text="👑 Admin Panel")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kino Qo'shish", callback_data="adm_add_kino")
    builder.button(text="🗑 Kino O'chirish", callback_data="adm_del_kino")
    builder.button(text="💬 Jonli Muloqot", callback_data="adm_start_chat")
    builder.button(text="📢 Reklama (Hamma uchun)", callback_data="adm_broadcast")
    builder.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
    builder.button(text="🚫 Foydalanuvchini bloklash", callback_data="adm_ban")
    builder.button(text="💰 Balans berish", callback_data="adm_give_money")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(1)
    return builder.as_markup()

# ================= JONLI MULOQOT (CHAT) MODULI =================
@dp.callback_query(F.data == "adm_start_chat")
async def adm_chat_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Bog'lanmoqchi bo'lgan foydalanuvchi ID sini kiriting:")
    await state.set_state(BotState.admin_chat_target)
    await c.answer()

@dp.message(BotState.admin_chat_target)
async def adm_request_chat(m: Message, state: FSMContext):
    target_id = m.text
    if not target_id.isdigit():
        return await m.answer("⚠️ Faqat raqamli ID kiriting!")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"chat_accept_{m.from_user.id}")
    kb.button(text="❌ Yo'q, rad etaman", callback_data=f"chat_deny_{m.from_user.id}")
    
    try:
        await bot.send_message(
            target_id, 
            f"🔔 **DIQQAT! Admin ({m.from_user.id}) siz bilan jonli suhbat boshlamoqchi.**\nRozimisiz?",
            reply_markup=kb.as_markup()
        )
        await m.answer(f"⏳ So'rov yuborildi. Foydalanuvchi (ID: {target_id}) javobini kuting...")
        await state.update_data(current_chat_partner=target_id)
    except Exception as e:
        await m.answer(f"❌ Xato: Foydalanuvchi botni bloklagan yoki ID xato. {e}")
    await state.clear()

@dp.callback_query(F.data.startswith("chat_"))
async def chat_handler(c: CallbackQuery, state: FSMContext):
    action = c.data.split("_")[1]
    partner_id = int(c.data.split("_")[2])
    
    if action == "accept":
        await c.message.answer("✅ Suhbat boshlandi! Xabaringizni yozing.\n(Tugatish: /stop)")
        await bot.send_message(partner_id, f"✅ Foydalanuvchi ({c.from_user.id}) suhbatga kirdi!")
        
        # Ikkala tomonni ham holatga solamiz
        await state.set_state(BotState.in_active_chat)
        await state.update_data(chat_partner=partner_id)
        
        p_state = dp.fsm.resolve_context(bot, partner_id, partner_id)
        await p_state.set_state(BotState.in_active_chat)
        await p_state.update_data(chat_partner=c.from_user.id)
    else:
        await c.message.answer("❌ Suhbat rad etildi.")
        await bot.send_message(partner_id, "😔 Foydalanuvchi suhbatni rad etdi.")
    await c.answer()

@dp.message(BotState.in_active_chat)
async def chatting_process(m: Message, state: FSMContext):
    data = await state.get_data()
    partner = data.get("chat_partner")
    
    if m.text == "/stop":
        await m.answer("📴 Suhbat tugatildi.", reply_markup=get_main_kb(m.from_user.id))
        if partner:
            await bot.send_message(partner, "📴 Suhbatdosh aloqani uzdi.", reply_markup=get_main_kb(partner))
            p_state = dp.fsm.resolve_context(bot, partner, partner)
            await p_state.clear()
        await state.clear()
        return

    try:
        await bot.send_message(partner, f"💬 **Xabar:**\n\n{m.text}")
    except:
        await m.answer("⚠️ Xabar yetkazilmadi. Suhbatdosh botni tark etgan bo'lishi mumkin.")

# ================= ASOSIY BOT FUNKSIYALARI =================
@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    db = load_db()
    uid = str(m.from_user.id)
    
    # Taklifnoma tekshiruvi
    args = m.text.split()
    referrer = args[1] if len(args) > 1 else None

    if uid in db["users"]:
        await m.answer(f"🌟 Xush kelibsiz qaytib, {db['users'][uid]['name']}!", reply_markup=get_main_kb(m.from_user.id))
    else:
        await m.answer("👋 **Assalomu alaykum! Botimizga xush kelibsiz.**\nRo'yxatdan o'tish uchun ismingizni yozing:")
        await state.set_state(BotState.waiting_name)
        if referrer and referrer != uid:
            await state.update_data(ref=referrer)

@dp.message(BotState.waiting_name)
async def process_name(m: Message, state: FSMContext):
    if len(m.text) < 3:
        return await m.answer("⚠️ Ism juda qisqa, qayta kiriting:")
    await state.update_data(reg_name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Telefon raqamni yuborish", request_contact=True)
    await m.answer("📱 Rahmat! Endi telefon raqamingizni pastdagi tugma orqali yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.waiting_phone)

@dp.message(BotState.waiting_phone, F.contact)
async def process_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load_db()
    uid = str(m.from_user.id)
    
    db["users"][uid] = {
        "name": data["reg_name"],
        "phone": m.contact.phone_number,
        "coins": 100,
        "vip": False,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "purchased": []
    }
    
    # Referral tizimi
    ref = data.get("ref")
    if ref and ref in db["users"]:
        db["users"][ref]["coins"] += 50
        await bot.send_message(ref, "🎁 Siz taklif qilgan do'stingiz ro'yxatdan o'tdi! Sizga 50 coin berildi.")

    save_db(db)
    await m.answer(f"🎉 Tabriklaymiz {data['reg_name']}! Sizga 100 coin bonus berildi.", reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

# ================= BALANS VA BONUS TIZIMI =================
@dp.message(F.text == "💰 Hisobim")
async def show_balance(m: Message):
    db = load_db()
    u = db["users"].get(str(m.from_user.id))
    if not u: return
    
    status = "💎 VIP" if u.get("vip") else "👤 Oddiy"
    text = (
        f"💳 **HISOB MA'LUMOTLARI**\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 Foydalanuvchi: {u['name']}\n"
        f"🆔 ID: `{m.from_user.id}`\n"
        f"💰 Balans: {u['coins']} coin\n"
        f"🎖 Status: {status}\n"
        f"📅 Ro'yxatdan o'tgan: {u['date']}\n"
        f"━━━━━━━━━━━━━━"
    )
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎁 Kunlik Bonus")
async def get_daily_bonus(m: Message):
    db = load_db()
    uid = str(m.from_user.id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    if db["daily_bonus"].get(uid) == today:
        return await m.answer("⚠️ Siz bugun bonus olib bo'lgansiz. Ertaga qaytib keling!")
    
    amount = random.randint(10, 100)
    db["users"][uid]["coins"] += amount
    db["daily_bonus"][uid] = today
    save_db(db)
    await m.answer(f"🎁 Kunlik omadingiz! Sizga {amount} coin taqdim etildi!")

# ================= KINOLAR BILAN ISHLASH =================
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def movies_list_cmd(m: Message):
    db = load_db()
    if not db["movies"]:
        return await m.answer("📽 Hozircha bazada kinolar mavjud emas.")
    
    text = "🔥 **ENG SO'NGGI KINOLAR** 🔥\n━━━━━━━━━━━━━━\n"
    for k in db["movies"]:
        text += f"🎬 **Nomi:** {k['name']}\n📅 **Yili:** {k['year']}\n💰 **Narxi:** {k['price']} coin\n🆔 **Kod:** `{k['id']}`\n──────────────\n"
    
    text += "\n🍿 *Sotib olish uchun 'Kino sotib olish' tugmasini bosing!*"
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎟 Kino sotib olish")
async def buy_movie_start(m: Message, state: FSMContext):
    await m.answer("🔢 Sotib olmoqchi bo'lgan kinongiz ID kodini yozing:")
    # Bu yerda maxsus state yaratish mumkin yoki shunchaki xabar kutish

# ================= ADMIN PANEL MODULLARI =================
@dp.message(F.text == "👑 Admin Panel")
async def admin_auth_start(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("🔐 Xavfsizlik uchun parolni kiriting:")
    await state.set_state(BotState.admin_auth)

@dp.message(BotState.admin_auth)
async def admin_auth_check(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        await state.clear()
        await m.answer("🛡 **Boshqaruv paneli faol.** Kerakli amalni tanlang:", reply_markup=get_admin_kb())
    else:
        await m.answer("❌ Parol xato! Qayta urinib ko'ring:")

@dp.callback_query(F.data == "adm_full_stats")
async def admin_stats(c: CallbackQuery):
    db = load_db()
    u_count = len(db["users"])
    m_count = len(db["movies"])
    orders = db.get("total_orders", 0)
    
    text = (
        f"📊 **BOT STATISTIKASI**\n"
        f"━━━━━━━━━━━━━━\n"
        f"👥 Foydalanuvchilar: {u_count} ta\n"
        f"🎬 Kinolar: {m_count} ta\n"
        f"💸 Sotuvlar: {orders} ta\n"
        f"🕒 Server vaqti: {datetime.now().strftime('%H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━"
    )
    await c.message.edit_text(text, reply_markup=get_admin_kb())

# --- KINO QO'SHISH FUNKSIYALARI ---
@dp.callback_query(F.data == "adm_add_kino")
async def adm_k_add(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 Kino nomini kiriting:")
    await state.set_state(BotState.adding_k_name)
    await c.answer()

@dp.message(BotState.adding_k_name)
async def adm_k_y(m: Message, state: FSMContext):
    await state.update_data(kname=m.text)
    await m.answer("📅 Kino yilini kiriting:")
    await state.set_state(BotState.adding_k_year)

@dp.message(BotState.adding_k_year)
async def adm_k_l(m: Message, state: FSMContext):
    await state.update_data(kyear=m.text)
    await m.answer("🔗 Kino linkini yozing:")
    await state.set_state(BotState.adding_k_link)

@dp.message(BotState.adding_k_link)
async def adm_k_p(m: Message, state: FSMContext):
    await state.update_data(klink=m.text)
    await m.answer("💰 Kino narxini (coin) kiriting:")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def adm_k_save(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Narxni faqat raqamda yozing!")
    
    data = await state.get_data()
    db = load_db()
    kid = len(db["movies"]) + 101
    
    db["movies"].append({
        "id": kid,
        "name": data["kname"],
        "year": data["kyear"],
        "link": data["klink"],
        "price": int(m.text)
    })
    save_db(db)
    await m.answer(f"✅ Kino saqlandi! ID: {kid}", reply_markup=get_admin_kb())
    await state.clear()

# ================= XAVFSIZLIK VA YAKUNLASH =================
@dp.message(F.text == "❌ Yopish")
async def close_kb(m: Message):
    await m.answer("Menyu yopildi.", reply_markup=ReplyKeyboardRemove())

async def main_setup():
    # Renderda ishlash uchun Flaskni boshlaymiz
    keep_alive()
    logger.info("BOT TIZIMI ISHGA TUSHDI...")
    
    # Eskirgan webhooklarni tozalaymiz
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Pollingni boshlash
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main_setup())
    except (KeyboardInterrupt, SystemExit):
        logger.info("BOT TO'XTATILDI.")
