import asyncio
import json
import os
import logging
import sys
from datetime import datetime
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardRemove, 
    CallbackQuery, 
    Message, 
    ContentType,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

# ================= KONFIGURATSIYA =================
# Botingiz sozlamalari
TOKEN = "8366692220:AAFxf6YFAa9SqmjL04pd7dmLn1oMs1W6w7U"
ADMIN_ID = 7492227388 
ADMIN_PASS = "456"
DB_FILE = "database.json"

# --- FLASK QISMI (RENDERDA BOTNI DOIMIY ISHLATISH UCHUN) ---
# Bu qism botni 503 xatosidan saqlaydi
app = Flask('')

@app.route('/')
def home():
    return "✅ Bot muvaffaqiyatli ishlayapti!"

def run():
    # Render portni o'zi tayinlaydi
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Loglarni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= MA'LUMOTLAR BAZASI BILAN ISHLASH =================
def load_db():
    if not os.path.exists(DB_FILE):
        initial_data = {
            "users": {},
            "banned": [],
            "movies": [],
            "total_orders": 0,
            "logs": [],
            "stats": {"visits": 0, "buys": 0}
        }
        save_db(initial_data)
        return initial_data
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Baza yuklashda xato: {e}")
        return {"users": {}, "banned": [], "movies": [], "total_orders": 0}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Baza saqlashda xato: {e}")

# ================= FSM HOLATLARINI BELGILASH =================
class BotState(StatesGroup):
    # Ro'yxatdan o'tish
    waiting_name = State()
    waiting_phone = State()
    
    # Admin paneli
    admin_auth = State()
    
    # Kino qo'shish
    adding_k_name = State()
    adding_k_year = State()
    adding_k_link = State()
    adding_k_price = State()
    
    # Jonli muloqot (Admin Chat)
    admin_chat_target = State()
    in_active_chat = State()
    
    # Boshqa admin amallari
    sending_broadcast = State()
    blocking_id = State()

# ================= KLAVIATURALARNI YARATISH =================
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
        builder.button(text="📊 Statistika")
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_admin_inline():
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kino Qo'shish", callback_data="adm_add_kino")
    builder.button(text="💬 Foydalanuvchi bilan gaplashish", callback_data="adm_start_chat")
    builder.button(text="📢 Reklama yuborish", callback_data="adm_broadcast")
    builder.button(text="🚫 Bloklash", callback_data="adm_ban")
    builder.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
    builder.button(text="❌ Yopish", callback_data="adm_close")
    builder.adjust(1)
    return builder.as_markup()

# ================= JONLI MULOQOT (CHAT) TIZIMI =================
# Admin muloqotni boshlaydi
@dp.callback_query(F.data == "adm_start_chat")
async def adm_chat_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Gaplashmoqchi bo'lgan foydalanuvchi ID sini kiriting:")
    await state.set_state(BotState.admin_chat_target)
    await c.answer()

@dp.message(BotState.admin_chat_target)
async def adm_ask_user(m: Message, state: FSMContext):
    target_id = m.text
    if not target_id.isdigit():
        return await m.answer("⚠️ Faqat ID raqamlardan iborat bo'ladi!")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, gaplashaman", callback_data=f"chat_ok_{m.from_user.id}")
    kb.button(text="❌ Yo'q, hozir emas", callback_data=f"chat_no_{m.from_user.id}")
    
    try:
        await bot.send_message(
            target_id, 
            "🔔 **Diqqat! Admin siz bilan jonli bog'lanmoqchi.**\nSuhbatni boshlashga rozimisiz?",
            reply_markup=kb.as_markup()
        )
        await m.answer(f"⏳ So'rov yuborildi. Foydalanuvchi (ID: {target_id}) javobini kuting...")
        await state.update_data(current_chat_partner=target_id)
    except:
        await m.answer("❌ Xatolik! Foydalanuvchi botni bloklagan yoki ID noto'g'ri.")
    await state.clear()

@dp.callback_query(F.data.startswith("chat_"))
async def chat_answer(c: CallbackQuery, state: FSMContext):
    answer_type = c.data.split("_")[1]
    admin_id = int(c.data.split("_")[2])
    
    if answer_type == "ok":
        await c.message.answer("✅ Aloqa o'rnatildi! Endi xabaringizni yozishingiz mumkin.\n\n(Suhbatni yakunlash uchun /stop deb yozing)")
        await bot.send_message(admin_id, f"✅ Foydalanuvchi ({c.from_user.id}) suhbatga kirdi. Xabar yozishingiz mumkin!")
        await state.set_state(BotState.in_active_chat)
        await state.update_data(chat_with=admin_id)
    else:
        await c.message.answer("❌ Suhbat rad etildi.")
        await bot.send_message(admin_id, f"😔 Foydalanuvchi ({c.from_user.id}) suhbatlashishni istamadi.")
    await c.answer()

@dp.message(BotState.in_active_chat)
async def process_chat_messages(m: Message, state: FSMContext):
    if m.text == "/stop":
        await m.answer("📴 Suhbat yakunlandi.", reply_markup=get_main_kb(m.from_user.id))
        data = await state.get_data()
        partner = data.get("chat_with") or ADMIN_ID
        await bot.send_message(partner, "📴 Suhbatdosh aloqani uzdi.", reply_markup=get_main_kb(partner))
        await state.clear()
        return

    data = await state.get_data()
    partner = data.get("chat_with") or (ADMIN_ID if m.from_user.id != ADMIN_ID else None)
    
    if partner:
        await bot.send_message(partner, f"💬 **Xabar:**\n\n{m.text}")

# ================= ASOSIY BOT LOGIKASI =================
@dp.message(CommandStart())
async def start_cmd(m: Message, state: FSMContext):
    await state.clear()
    db = load_db()
    uid = str(m.from_user.id)
    
    if uid in db["users"]:
        await m.answer(f"🌟 **Xush kelibsiz qaytib, {db['users'][uid]['name']}!**", reply_markup=get_main_kb(m.from_user.id))
    else:
        await m.answer("👋 **Assalomu alaykum! Botimizga xush kelibsiz.**\n\nIltimos, ismingizni kiriting:")
        await state.set_state(BotState.waiting_name)

@dp.message(BotState.waiting_name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Raqamni yuborish", request_contact=True)
    await m.answer("📱 Rahmat! Endi telefon raqamingizni pastdagi tugma orqali yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.waiting_phone)

@dp.message(BotState.waiting_phone, F.contact)
async def reg_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    db = load_db()
    db["users"][str(m.from_user.id)] = {
        "name": data["name"],
        "phone": m.contact.phone_number,
        "coins": 100,
        "joined": datetime.now().strftime("%Y-%m-%d")
    }
    save_db(db)
    await m.answer("✅ Tabriklaymiz! Ro'yxatdan o'tdingiz va sizga 100 coin sovg'a qilindi.", reply_markup=get_main_kb(m.from_user.id))
    await state.clear()

# --- CHIROYLI KINOLAR RO'YXATI ---
@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def show_movie_list(m: Message):
    db = load_db()
    if not db["movies"]:
        return await m.answer("📽 Hozircha bazada kinolar mavjud emas.")
    
    text = "🔥 **ENG SO'NGGI PREMYERALAR** 🔥\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    for k in db["movies"]:
        text += f"🎬 **Nomi:** {k['name']}\n"
        text += f"📅 **Yili:** {k['year']}\n"
        text += f"💎 **Narxi:** {k['price']} coin\n"
        text += f"🆔 **KODI:** `{k['id']}`\n"
        text += "────────────────────\n"
    text += "\n🍿 *Kino sotib olish uchun ID kodidan foydalaning!*"
    await m.answer(text, parse_mode="Markdown")

# --- ADMIN PANELIGA KIRISH ---
@dp.message(F.text == "👑 Admin Panel")
async def request_admin(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return
    await m.answer("🔐 Admin paneliga kirish uchun parolni kiriting:")
    await state.set_state(BotState.admin_auth)

@dp.message(BotState.admin_auth)
async def verify_admin(m: Message, state: FSMContext):
    if m.text == ADMIN_PASS:
        await state.clear()
        await m.answer("🛡 **Xush kelibsiz, xo'jayin!**\nBoshqaruv paneli ishga tayyor:", reply_markup=get_admin_inline())
    else:
        await m.answer("❌ Parol noto'g'ri! Qayta urinib ko'ring:")

# --- REKLAMA YUBORISH ---
@dp.callback_query(F.data == "adm_broadcast")
async def start_broadcast(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni (rasm, matn, video) yuboring:")
    await state.set_state(BotState.sending_broadcast)
    await c.answer()

@dp.message(BotState.sending_broadcast)
async def process_broadcast(m: Message, state: FSMContext):
    db = load_db()
    users = db.get("users", {})
    count = 0
    for uid in users:
        try:
            await m.copy_to(chat_id=uid)
            count += 1
            await asyncio.sleep(0.05)
        except:
            continue
    await m.answer(f"✅ Reklama {count} ta foydalanuvchiga muvaffaqiyatli yuborildi!")
    await state.clear()

# --- KINO QO'SHISH ---
@dp.callback_query(F.data == "adm_add_kino")
async def start_add_kino(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 **Kino nomini kiriting:**")
    await state.set_state(BotState.adding_k_name)
    await c.answer()

@dp.message(BotState.adding_k_name)
async def set_kino_name(m: Message, state: FSMContext):
    await state.update_data(k_name=m.text)
    await m.answer("📅 **Kino ishlab chiqarilgan yilni kiriting:**")
    await state.set_state(BotState.adding_k_year)

@dp.message(BotState.adding_k_year)
async def set_kino_year(m: Message, state: FSMContext):
    await state.update_data(k_year=m.text)
    await m.answer("🔗 **Kino linkini (Telegram yoki web) yuboring:**")
    await state.set_state(BotState.adding_k_link)

@dp.message(BotState.adding_k_link)
async def set_kino_link(m: Message, state: FSMContext):
    await state.update_data(k_link=m.text)
    await m.answer("💰 **Kino narxini (coin) kiriting:**")
    await state.set_state(BotState.adding_k_price)

@dp.message(BotState.adding_k_price)
async def save_new_kino(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Iltimos, narxni faqat raqamda yozing!")
    
    data = await state.get_data()
    db = load_db()
    new_id = len(db["movies"]) + 101 # ID 101 dan boshlanadi
    
    new_movie = {
        "id": new_id,
        "name": data["k_name"],
        "year": data["k_year"],
        "link": data["k_link"],
        "price": int(m.text)
    }
    
    db["movies"].append(new_movie)
    save_db(db)
    await m.answer(f"✅ Yangi kino qo'shildi!\n🆔 Kodi: `{new_id}`\n🎬 Nomi: {data['k_name']}")
    await state.clear()

# ================= BOTNI ISHGA TUSHIRISH (RUN) =================
async def main_async():
    # Renderda o'chib qolmaslik uchun Flaskni alohida threadda yoqamiz
    keep_alive()
    logger.info("Bot ishga tushmoqda...")
    # Barcha xabarlarni o'qib bo'lingandan keyin yangilarini kutish
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi!")
