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
    InlineKeyboardMarkup
)

# ================= 1. ASOSIY KONFIGURATSIYA =================
# SIZ SO'RAGAN YANGI TOKEN
TOKEN = "8366692220:AAFxf6YFAa9SqmjL04pd7dmLn1oMs1W6w7U"
ADMIN_ID = 7492227388 
DB_FILE = "cinema_ultimate_v15.json"

# --- WEB SERVER (KEEP ALIVE) ---
app = Flask('')
@app.route('/')
def home():
    return f"🟢 BOT STATUS: ACTIVE | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run_server, daemon=True).start()

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= 2. PROFESSIONAL DATABASE MODULI =================
class Database:
    @staticmethod
    def initialize():
        if not os.path.exists(DB_FILE):
            data = {
                "users": {},
                "banned": [],
                "movies": [
                    {
                        "id": 1001,
                        "name": "Anime Donx",
                        "year": "2034",
                        "lang": "Uzbek",
                        "link": "https://kino-bot-ga9m.onrender.com",
                        "price": 70,
                        "category": "Anime"
                    }
                ],
                "stats": {"total_revenue": 0, "total_users": 0},
                "daily_bonus": {}
            }
            Database.save(data)
        return Database.load()

    @staticmethod
    def load():
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"users": {}, "movies": [], "banned": []}

    @staticmethod
    def save(data):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

# ================= 3. FSM (HOLATLAR) TIZIMI =================
class BotState(StatesGroup):
    # Ro'yxatdan o'tish
    wait_name = State()
    wait_phone = State()
    
    # User paneli
    movie_search = State()
    
    # Admin - Kino Boshqaruvi
    adm_m_name = State()
    adm_m_code = State()
    adm_m_year = State()
    adm_m_lang = State()
    adm_m_link = State()
    adm_m_price = State()
    
    # Admin - Coin & User Boshqaruvi
    adm_give_id = State()
    adm_give_amt = State()
    adm_take_id = State()
    adm_take_amt = State()
    adm_ban_id = State()
    adm_unban_id = State()
    
    # Live Chat
    active_chat = State()
    chat_target = State()
    broadcast = State()

# ================= 4. KLAVIATURALAR (PROFESSIONAL UI) =================
class UI:
    @staticmethod
    def main_menu(uid):
        kb = ReplyKeyboardBuilder()
        kb.button(text="🎬 Kinolar Ro'yxati")
        kb.button(text="📥 Kino Qidirish")
        kb.button(text="👤 Hisobim")
        kb.button(text="🎁 Kunlik Bonus")
        kb.button(text="🤝 Do'stlarni taklif qilish")
        kb.button(text="☎️ Admin bilan Aloqa")
        if int(uid) == ADMIN_ID:
            kb.button(text="👑 Admin Panel")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def admin_panel():
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Kino Qo'shish", callback_data="a_add")
        kb.button(text="💰 Coin Berish", callback_data="a_give")
        kb.button(text="💸 Coin Olish", callback_data="a_take")
        kb.button(text="🚫 Bloklash", callback_data="a_ban")
        kb.button(text="✅ Blokdan ochish", callback_data="a_unban")
        kb.button(text="💬 Jonli Chat", callback_data="a_chat")
        kb.button(text="📢 Reklama", callback_data="a_ads")
        kb.adjust(2)
        return kb.as_markup()



# ================= 5. START VA RO'YXATDAN O'TISH =================
@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    db = Database.load()
    uid = str(m.from_user.id)

    if uid in db.get("banned", []):
        return await m.answer("⛔️ Siz botdan bloklangansiz!")

    # Referal tizimi
    ref_id = m.text.split()[1] if len(m.text.split()) > 1 else None

    if uid in db["users"]:
        await m.answer(f"🌟 Xush kelibsiz, {db['users'][uid]['name']}!", reply_markup=UI.main_menu(uid))
    else:
        await state.update_data(ref=ref_id)
        await m.answer("👋 Salom! Ismingizni kiriting:")
        await state.set_state(BotState.wait_name)

@dp.message(BotState.wait_name)
async def reg_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Raqamni yuborish", request_contact=True)
    await m.answer(f"Rahmat {m.text}, raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.wait_phone)

@dp.message(BotState.wait_phone, F.contact)
async def reg_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = str(m.from_user.id)
    u_code = f"UC{random.randint(1000, 9999)}"
    
    db["users"][uid] = {
        "name": data["name"],
        "phone": m.contact.phone_number,
        "balance": 100,
        "u_id": u_code,
        "joined": datetime.now().strftime("%Y-%m-%d")
    }

    if data.get("ref") and data["ref"] in db["users"] and data["ref"] != uid:
        db["users"][data["ref"]]["balance"] += 50
        await bot.send_message(data["ref"], "🎁 Do'stingiz qo'shildi! Sizga 50 coin berildi.")

    Database.save(db)
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi foydalanuvchi!**\n👤 Ism: {data['name']}\n🆔 ID: {uid}\n🔑 Kod: {u_code}")
    await m.answer(f"🎉 Ro'yxatdan o'tdingiz! Sizga 100 coin berildi.\nSizning ID kodingiz: {u_code}", reply_markup=UI.main_menu(uid))
    await state.clear()

# ================= 6. JONLI CHAT (LIVE CHAT) =================
@dp.callback_query(F.data == "a_chat")
async def adm_chat_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.chat_target)

@dp.message(BotState.chat_target)
async def adm_chat_req(m: Message, state: FSMContext):
    target = m.text
    db = Database.load()
    if target not in db["users"]:
        return await m.answer("❌ Foydalanuvchi topilmadi!")
    
    await state.update_data(target=target)
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha", callback_data="c_ok")
    kb.button(text="❌ Yo'q", callback_data="c_no")
    await bot.send_message(target, "🔔 **Admin siz bilan bog'lanmoqchi.** Qabul qilasizmi?", reply_markup=kb.as_markup())
    await m.answer(f"⏳ {target} ga so'rov yuborildi.")

@dp.callback_query(F.data == "c_ok")
async def chat_ok(c: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.active_chat)
    await c.message.answer("✅ Muloqot boshlandi. Tugatish uchun /stop")
    await bot.send_message(ADMIN_ID, "✅ Foydalanuvchi rozi bo'ldi. Yozishingiz mumkin.")

@dp.message(BotState.active_chat)
async def live_chat(m: Message, state: FSMContext):
    if m.text == "/stop":
        await state.clear()
        return await m.answer("📴 Suhbat tugadi.")
    
    data = await state.get_data()
    target = ADMIN_ID if m.from_user.id != ADMIN_ID else data.get("target")
    await bot.send_message(target, f"💬 **Xabar:** {m.text}")

# ================= 7. KINO VA COIN BOSHQARUVI =================
@dp.callback_query(F.data == "a_add")
async def adm_add_kino(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 Kino nomi:")
    await state.set_state(BotState.adm_m_name)

@dp.message(BotState.adm_m_name)
async def adm_k_1(m: Message, state: FSMContext):
    await state.update_data(n=m.text)
    await m.answer("🔢 Kino kodi:")
    await state.set_state(BotState.adm_m_code)

@dp.message(BotState.adm_m_code)
async def adm_k_2(m: Message, state: FSMContext):
    await state.update_data(c=m.text)
    await m.answer("📅 Yili:")
    await state.set_state(BotState.adm_m_year)

@dp.message(BotState.adm_m_year)
async def adm_k_3(m: Message, state: FSMContext):
    await state.update_data(y=m.text)
    await m.answer("🌐 Dublyaj tili:")
    await state.set_state(BotState.adm_m_lang)

@dp.message(BotState.adm_m_lang)
async def adm_k_4(m: Message, state: FSMContext):
    await state.update_data(l=m.text)
    await m.answer("🔗 Havola (Link):")
    await state.set_state(BotState.adm_m_link)

@dp.message(BotState.adm_m_link)
async def adm_k_5(m: Message, state: FSMContext):
    await state.update_data(link=m.text)
    await m.answer("💰 Narxi (Coin):")
    await state.set_state(BotState.adm_m_price)

@dp.message(BotState.adm_m_price)
async def adm_k_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    db["movies"].append({
        "id": data['c'], "name": data['n'], "year": data['y'],
        "lang": data['l'], "link": data['link'], "price": int(m.text)
    })
    Database.save(db)
    await m.answer("✅ Kino qo'shildi!")
    await state.clear()

@dp.callback_query(F.data == "a_take")
async def adm_take_coin(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🆔 Kimdan coin olib tashlaymiz? (ID):")
    await state.set_state(BotState.adm_take_id)

@dp.message(BotState.adm_take_id)
async def adm_t_1(m: Message, state: FSMContext):
    await state.update_data(target=m.text)
    await m.answer("💸 Miqdorni yozing:")
    await state.set_state(BotState.adm_take_amt)

@dp.message(BotState.adm_take_amt)
async def adm_t_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = data['target']
    if uid in db["users"]:
        db["users"][uid]["balance"] -= int(m.text)
        Database.save(db)
        await m.answer(f"✅ {uid} hisobidan {m.text} coin olindi.")
    await state.clear()

# ================= 8. SYSTEM RUN =================
async def main():
    Database.initialize()
    keep_alive()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
