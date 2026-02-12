import asyncio
import json
import os
import logging
import sys
import random
import secrets
import string
import uuid
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
    InlineKeyboardMarkup
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

# ================= 1. KONFIGURATSIYA VA TIZIM SOZLAMALARI =================
TOKEN = "8366692220:AAFxf6YFAa9SqmjL04pd7dmLn1oMs1W6w7U"
ADMIN_ID = 7492227388 
ADMIN_PASS = "456"
DB_FILE = "cinema_ultra_db.json"
LOG_FILE = "system_runtime.log"

# --- RENDER KEEP ALIVE TIZIMI ---
app = Flask(__name__)
@app.route('/')
def home():
    return f"🚀 CINEMA BOT CORE: ONLINE | TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def start_keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- LOGGING SOZLAMALARI ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE)]
)
logger = logging.getLogger("UltraBot")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= 2. MA'LUMOTLAR BAZASI (KENGAYTIRILGAN) =================
class Database:
    @staticmethod
    def load():
        if not os.path.exists(DB_FILE):
            data = {
                "users": {},
                "movies": [],
                "banned": [],
                "orders": [],
                "promos": {},
                "system": {"visits": 0, "sales": 0, "total_coins": 0}
            }
            Database.save(data)
            return data
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save(data):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

# ================= 3. FSM (HOLATLAR) TIZIMI =================
class BotState(StatesGroup):
    # Ro'yxatdan o'tish
    reg_name = State()
    reg_phone = State()
    
    # Admin Panel
    admin_login = State()
    
    # Kino Boshqaruvi
    add_name = State()
    add_year = State()
    add_code = State()
    add_link = State()
    add_price = State()
    
    # Moliya va Bloklash
    manage_user_id = State()
    manage_amount = State()
    target_ban_id = State()
    
    # Aloqa va Reklama
    broadcast_msg = State()
    private_chat = State()
    chat_partner_id = State()

# ================= 4. KLAVIATURA KONSTRUKTORLARI =================
class Keyboards:
    @staticmethod
    def main(uid):
        kb = ReplyKeyboardBuilder()
        kb.button(text="🎬 Kinolar Ro'yxati")
        kb.button(text="💳 Mening Hisobim")
        kb.button(text="📥 Kino Sotib Olish")
        kb.button(text="🎁 Kunlik Bonus")
        kb.button(text="☎️ Admin bilan Aloqa")
        kb.button(text="📈 Statistika")
        if uid == ADMIN_ID:
            kb.button(text="👑 Admin Boshqaruv Paneli")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def admin_inline():
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Yangi Kino", callback_data="adm_kino_add")
        kb.button(text="💰 Coin Berish", callback_data="adm_coin_give")
        kb.button(text="💸 Coin Olish", callback_data="adm_coin_take")
        kb.button(text="🚫 Bloklash", callback_data="adm_user_ban")
        kb.button(text="✅ Blokdan Chiqarish", callback_data="adm_user_unban")
        kb.button(text="📢 Reklama Tarqatish", callback_data="adm_send_ads")
        kb.button(text="👥 Foydalanuvchilar Ro'yxati", callback_data="adm_list_users")
        kb.button(text="💬 Chat Boshlash", callback_data="adm_chat_start")
        kb.adjust(1)
        return kb.as_markup()

# ================= 5. ASOSIY LOGIKA (START VA RO'YXAT) =================
@dp.message(CommandStart())
async def start_handler(m: Message, state: FSMContext):
    db = Database.load()
    uid = str(m.from_user.id)
    
    if uid in db["banned"]:
        return await m.answer("⚠️ Kechirasiz, siz botdan bloklangansiz!")

    if uid in db["users"]:
        await m.answer(f"🌟 Xush kelibsiz qaytib, {db['users'][uid]['name']}!", 
                      reply_markup=Keyboards.main(m.from_user.id))
    else:
        await m.answer("👋 Assalomu alaykum! Botga xush kelibsiz.\nRo'yxatdan o'tish uchun ismingizni yozing:")
        await state.set_state(BotState.reg_name)

@dp.message(BotState.reg_name)
async def get_name(m: Message, state: FSMContext):
    await state.update_data(user_name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Telefon raqamni yuborish", request_contact=True)
    await m.answer("Rahmat! Endi telefon raqamingizni yuboring:", 
                  reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.reg_phone)

@dp.message(BotState.reg_phone, F.contact)
async def get_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = str(m.from_user.id)
    
    db["users"][uid] = {
        "name": data["user_name"],
        "phone": m.contact.phone_number,
        "coins": 100,
        "purchased": [],
        "joined": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    Database.save(db)
    await m.answer(f"🎉 Tabriklaymiz {data['user_name']}! Sizga 100 coin bonus berildi.", 
                  reply_markup=Keyboards.main(m.from_user.id))
    await state.clear()

# ================= 6. ADMIN KINO QO'SHISH (MUKAMMAL) =================
@dp.callback_query(F.data == "adm_kino_add")
async def add_kino_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 Kino nomini kiriting:")
    await state.set_state(BotState.add_name)

@dp.message(BotState.add_name)
async def add_kino_name(m: Message, state: FSMContext):
    await state.update_data(kn=m.text)
    await m.answer("📅 Kino yilini kiriting:")
    await state.set_state(BotState.add_year)

@dp.message(BotState.add_year)
async def add_kino_year(m: Message, state: FSMContext):
    await state.update_data(ky=m.text)
    await m.answer("🔢 Kino uchun noyob KOD (masalan: 123) kiriting:")
    await state.set_state(BotState.add_code)

@dp.message(BotState.add_code)
async def add_kino_code(m: Message, state: FSMContext):
    await state.update_data(kc=m.text)
    await m.answer("🔗 Kino linkini (Telegram file link) kiriting:")
    await state.set_state(BotState.add_link)

@dp.message(BotState.add_link)
async def add_kino_link(m: Message, state: FSMContext):
    await state.update_data(kl=m.text)
    await m.answer("💰 Kino narxini (coinlarda) belgilang:")
    await state.set_state(BotState.add_price)

@dp.message(BotState.add_price)
async def add_kino_final(m: Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.answer("⚠️ Faqat raqam kiriting!")
    
    data = await state.get_data()
    db = Database.load()
    
    new_movie = {
        "id": data["kc"],
        "name": data["kn"],
        "year": data["ky"],
        "link": data["kl"],
        "price": int(m.text)
    }
    
    db["movies"].append(new_movie)
    Database.save(db)
    await m.answer(f"✅ Kino muvaffaqiyatli qo'shildi!\nNomi: {data['kn']}\nKod: {data['kc']}")
    await state.clear()

# ================= 7. FOYDALANUVCHINI BOSHQARISH (COIN & BAN) =================
@dp.callback_query(F.data == "adm_coin_give")
async def coin_give_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("👤 Coin beriladigan foydalanuvchi ID sini yozing:")
    await state.update_data(action="give")
    await state.set_state(BotState.manage_user_id)

@dp.callback_query(F.data == "adm_coin_take")
async def coin_take_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("👤 Coin olinadigan foydalanuvchi ID sini yozing:")
    await state.update_data(action="take")
    await state.set_state(BotState.manage_user_id)

@dp.message(BotState.manage_user_id)
async def manage_uid(m: Message, state: FSMContext):
    await state.update_data(tid=m.text)
    await m.answer("💰 Miqdorni kiriting:")
    await state.set_state(BotState.manage_amount)

@dp.message(BotState.manage_amount)
async def manage_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = data["tid"]
    amount = int(m.text)
    
    if uid in db["users"]:
        if data["action"] == "give":
            db["users"][uid]["coins"] += amount
            msg = f"✅ {uid} ga {amount} coin qo'shildi."
            await bot.send_message(uid, f"🎁 Admin sizga {amount} coin berdi!")
        else:
            db["users"][uid]["coins"] -= amount
            msg = f"✅ {uid} dan {amount} coin olindi."
        
        Database.save(db)
        await m.answer(msg)
    else:
        await m.answer("❌ Foydalanuvchi topilmadi!")
    await state.clear()

# ================= 8. JONLI CHAT (ADMIN VA FOYDALANUVCHI) =================
@dp.callback_query(F.data == "adm_chat_start")
async def admin_chat_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Bog'lanmoqchi bo'lgan foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.chat_partner_id)

@dp.message(BotState.chat_partner_id)
async def start_chat_session(m: Message, state: FSMContext):
    await state.update_data(partner=m.text)
    await m.answer(f"✅ {m.text} bilan chat faollashdi. Xabar yozing.\nTugatish: /stop")
    await state.set_state(BotState.private_chat)

@dp.message(BotState.private_chat)
async def chatting(m: Message, state: FSMContext):
    data = await state.get_data()
    partner = data.get("partner")
    
    if m.text == "/stop":
        await m.answer("📴 Chat yopildi.")
        await state.clear()
        return

    try:
        await bot.send_message(partner, f"📩 **Admin:** {m.text}")
        await m.answer("✅ Yuborildi.")
    except:
        await m.answer("❌ Xatolik!")

# ================= 9. STATISTIKA VA REKLAMA =================
@dp.callback_query(F.data == "adm_list_users")
async def list_users(c: CallbackQuery):
    db = Database.load()
    res = "👥 **BOT FOYDALANUVCHILARI:**\n\n"
    for uid, info in db["users"].items():
        res += f"🆔 `{uid}` | 👤 {info['name']} | 📞 {info['phone']}\n"
    
    if len(res) > 4000:
        for x in range(0, len(res), 4000):
            await c.message.answer(res[x:x+4000])
    else:
        await c.message.answer(res)

@dp.callback_query(F.data == "adm_send_ads")
async def ads_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Reklama xabarini yozing:")
    await state.set_state(BotState.broadcast_msg)

@dp.message(BotState.broadcast_msg)
async def ads_send(m: Message, state: FSMContext):
    db = Database.load()
    count = 0
    for uid in db["users"]:
        try:
            await bot.send_message(uid, m.text)
            count += 1
        except: continue
    await m.answer(f"✅ Reklama {count} kishiga yuborildi.")
    await state.clear()

# ================= 10. TIZIMNI ISHGA TUSHIRISH =================
async def main_engine():
    Database.load() # Bazani tekshirish
    start_keep_alive() # Flaskni yoqish
    logger.info("--- SYSTEM BOOTING UP ---")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main_engine())
    except (KeyboardInterrupt, SystemExit):
        logger.error("SYSTEM SHUTDOWN.")
