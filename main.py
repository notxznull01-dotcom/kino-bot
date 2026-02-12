import asyncio
import json
import os
import logging
import sys
import random
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
    CallbackQuery, Message, ContentType, 
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)

# ================= 1. ASOSIY KONFIGURATSIYA =================
TOKEN = "8366692220:AAHaJhbqksDOn_TgDp645GIliCT__4yZlUk"
ADMIN_ID = 7492227388 
DB_FILE = "cinema_v10_ultimate.json"

# --- SERVERNI TIRIK SAQLASH ---
app = Flask(__name__)
@app.route('/')
def home():
    return f"🌕 SERVER STATUS: STABLE\n⏰ TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🤖 BOT: V10 ONLINE"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= 2. PROFESSIONAL MA'LUMOTLAR BAZASI =================
class Database:
    @staticmethod
    def initialize():
        if not os.path.exists(DB_FILE):
            data = {
                "users": {},
                "movies": [],
                "banned": [],
                "logs": [],
                "transactions": [],
                "stats": {"total_revenue": 0, "total_users": 0}
            }
            Database.save(data)
        return Database.load()

    @staticmethod
    def load():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save(data):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

# ================= 3. FSM HOLATLARI (MAXSUS TIZIM) =================
class BotState(StatesGroup):
    # Ro'yxatdan o'tish
    wait_name = State()
    wait_phone = State()
    
    # User paneli
    movie_search = State()
    balance_fill = State()
    
    # Jonli Chat (Admin & User)
    active_chat = State()
    chat_request = State()
    adm_chat_target = State()
    
    # Admin - Kino Boshqaruvi
    adm_m_name = State()
    adm_m_code = State()
    adm_m_year = State()
    adm_m_lang = State()
    adm_m_link = State()
    adm_m_price = State()
    adm_m_delete = State()
    
    # Admin - Moliya (Coin)
    adm_give_id = State()
    adm_give_amt = State()
    adm_take_id = State()
    adm_take_amt = State()
    
    # Admin - User Boshqaruvi
    adm_ban_id = State()
    adm_unban_id = State()
    adm_broadcast = State()

# ================= 4. DINAMIK INTERFEYS (UI) =================
class UI:
    @staticmethod
    def main_menu(uid):
        kb = ReplyKeyboardBuilder()
        kb.button(text="🎬 Kinolar Ro'yxati")
        kb.button(text="📥 Kino Qidirish")
        kb.button(text="👤 Shaxsiy Kabinet")
        kb.button(text="🤝 Do'stlarni Taklif Qilish")
        kb.button(text="📅 Bugungi Yangiliklar")
        kb.button(text="💰 Balans To'ldirish")
        kb.button(text="☎️ Admin bilan Aloqa")
        if int(uid) == ADMIN_ID:
            kb.button(text="👑 Admin Panel")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def admin_menu():
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Kino Qo'shish", callback_data="adm_add")
        kb.button(text="❌ Kino O'chirish", callback_data="adm_del")
        kb.button(text="💰 Coin Berish", callback_data="adm_give")
        kb.button(text="💸 Coin Olish", callback_data="adm_take")
        kb.button(text="🚫 Bloklash", callback_data="adm_ban")
        kb.button(text="✅ Blokdan Chiqarish", callback_data="adm_unban")
        kb.button(text="📢 Reklama", callback_data="adm_ads")
        kb.button(text="💬 Jonli Chat", callback_data="adm_chat")
        kb.button(text="📊 Statistika", callback_data="adm_stats")
        kb.adjust(2)
        return kb.as_markup()

    @staticmethod
    def chat_confirm_kb():
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Ha, Gaplashaman", callback_data="chat_ok")
        kb.button(text="❌ Rad Etish", callback_data="chat_no")
        kb.adjust(1)
        return kb.as_markup()

# 

# ================= 5. START VA REGISTRATSIYA =================
@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    db = Database.load()
    uid = str(m.from_user.id)
    
    if uid in db["banned"]:
        return await m.answer("⛔️ Siz botdan chetlatilgansiz!")

    # Referal tizimi
    ref_id = m.text.split()[1] if len(m.text.split()) > 1 else None

    if uid in db["users"]:
        await m.answer(f"🌟 Xush kelibsiz qaytib, {db['users'][uid]['name']}!", reply_markup=UI.main_menu(uid))
    else:
        await state.update_data(ref=ref_id)
        await m.answer("👋 Salom! Botdan to'liq foydalanish uchun ro'yxatdan o'ting.\n\nIsmingizni kiriting:")
        await state.set_state(BotState.wait_name)

@dp.message(BotState.wait_name)
async def get_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Telefon raqamni yuborish", request_contact=True)
    await m.answer("Rahmat! Endi pastdagi tugma orqali raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.wait_phone)

@dp.message(BotState.wait_phone, F.contact)
async def get_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = str(m.from_user.id)
    u_code = f"USER-{random.randint(100000, 999999)}"
    
    db["users"][uid] = {
        "name": data["name"], "phone": m.contact.phone_number,
        "balance": 100, "u_id": u_code, "movies": [],
        "joined": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    # Referal Bonus
    if data.get("ref") and data["ref"] in db["users"] and data["ref"] != uid:
        db["users"][data["ref"]]["balance"] += 50
        await bot.send_message(data["ref"], f"🎁 Do'stingiz ({data['name']}) qo'shildi! Sizga 50 coin berildi.")

    Database.save(db)
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi Foydalanuvchi!**\n👤 {data['name']}\n🆔 `{uid}`\n🔑 Kod: {u_code}")
    await m.answer(f"🎉 Tabriklaymiz! Ro'yxatdan o'tdingiz.\n💰 Sizga 100 coin sovg'a qilindi.\n🔑 ID Kod: {u_code}", reply_markup=UI.main_menu(uid))
    await state.clear()

# ================= 6. JONLI CHAT (LIVE CHAT MODULI) =================
@dp.callback_query(F.data == "adm_chat")
async def adm_chat_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Gaplashmoqchi bo'lgan foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.adm_chat_target)

@dp.message(BotState.adm_chat_target)
async def adm_chat_req(m: Message, state: FSMContext):
    target = m.text
    db = Database.load()
    if target not in db["users"]:
        return await m.answer("❌ Bunday ID li foydalanuvchi topilmadi!")
    
    await state.update_data(target=target)
    await m.answer(f"⏳ {target} ga so'rov yuborildi. Javob kutilyapti...")
    await bot.send_message(target, "🔔 **Admin siz bilan bog'lanmoqchi.**\nQabul qilasizmi?", reply_markup=UI.chat_confirm_kb())

@dp.callback_query(F.data == "chat_ok")
async def chat_start_final(c: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.active_chat)
    await c.message.edit_text("✅ Muloqot boshlandi. Xabar yozishingiz mumkin.\nSuhbatni yakunlash uchun: /stop_chat")
    await bot.send_message(ADMIN_ID, f"✅ User ({c.from_user.id}) muloqotga rozi bo'ldi. Yozing...")

@dp.callback_query(F.data == "chat_no")
async def chat_reject(c: CallbackQuery, state: FSMContext):
    await c.message.edit_text("❌ Muloqot rad etildi.")
    await bot.send_message(ADMIN_ID, f"⚠️ User ({c.from_user.id}) muloqotni rad etdi.")

@dp.message(BotState.active_chat)
async def chat_engine(m: Message, state: FSMContext):
    if m.text == "/stop_chat":
        await state.clear()
        await m.answer("📴 Muloqot yakunlandi.")
        target = ADMIN_ID if m.from_user.id != ADMIN_ID else (await state.get_data()).get("target")
        return await bot.send_message(target, "📴 Muloqot admin tomonidan yakunlandi.")
    
    data = await state.get_data()
    target = ADMIN_ID if m.from_user.id != ADMIN_ID else data.get("target")
    await bot.send_message(target, f"💬 **Xabar:** {m.text}")

# ================= 7. KINO BOSHQARUV (ADD/DEL/BUY) =================
@dp.callback_query(F.data == "adm_add")
async def kino_add_1(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 Kino nomi:")
    await state.set_state(BotState.adm_m_name)

@dp.message(BotState.adm_m_name)
async def kino_add_2(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    await m.answer("🔢 Kino kodi (Katalog uchun):")
    await state.set_state(BotState.adm_m_code)

@dp.message(BotState.adm_m_code)
async def kino_add_3(m: Message, state: FSMContext):
    await state.update_data(code=m.text)
    await m.answer("📅 Chiqarilgan yili:")
    await state.set_state(BotState.adm_m_year)

@dp.message(BotState.adm_m_year)
async def kino_add_4(m: Message, state: FSMContext):
    await state.update_data(year=m.text)
    await m.answer("🌐 Dublyaj tili:")
    await state.set_state(BotState.adm_m_lang)

@dp.message(BotState.adm_m_lang)
async def kino_add_5(m: Message, state: FSMContext):
    await state.update_data(lang=m.text)
    await m.answer("🔗 Video havola (Link):")
    await state.set_state(BotState.adm_m_link)

@dp.message(BotState.adm_m_link)
async def kino_add_6(m: Message, state: FSMContext):
    await state.update_data(link=m.text)
    await m.answer("💰 Narxi (Coinlarda):")
    await state.set_state(BotState.adm_m_price)

@dp.message(BotState.adm_m_price)
async def kino_add_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    db["movies"].append({
        "name": data['name'], "code": data['code'], "year": data['year'],
        "lang": data['lang'], "link": data['link'], "price": int(m.text),
        "added": datetime.now().strftime("%Y-%m-%d")
    })
    Database.save(db)
    await m.answer("✅ Kino muvaffaqiyatli bazaga qo'shildi!")
    await state.clear()

@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def list_movies(m: Message):
    db = Database.load()
    if not db["movies"]: return await m.answer("📭 Hozircha kinolar yo'q.")
    
    text = "📂 **Kino Katalogi:**\n\n"
    for m_data in db["movies"][-10:]: # Oxirgi 10 ta
        text += f"🎥 **{m_data['name']}**\n🔑 Kod: `{m_data['code']}` | 📅 {m_data['year']}\n💰 {m_data['price']} coin\n-----------\n"
    await m.answer(text)

# ================= 8. COIN VA MOLIYA BOSHQARUVI =================
@dp.callback_query(F.data == "adm_give")
async def adm_coin_give_1(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🆔 Foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.adm_give_id)

@dp.message(BotState.adm_give_id)
async def adm_coin_give_2(m: Message, state: FSMContext):
    await state.update_data(t_id=m.text)
    await m.answer("💰 Qancha coin bermoqchisiz?")
    await state.set_state(BotState.adm_give_amt)

@dp.message(BotState.adm_give_amt)
async def adm_coin_give_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    u_id = data['t_id']
    if u_id in db["users"]:
        db["users"][u_id]["balance"] += int(m.text)
        Database.save(db)
        await m.answer(f"✅ {u_id} ga {m.text} coin qo'shildi.")
        await bot.send_message(u_id, f"🎁 Admin tomonidan hisobingizga {m.text} coin qo'shildi!")
    await state.clear()

@dp.callback_query(F.data == "adm_take")
async def adm_coin_take_1(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🆔 Foydalanuvchi ID sini yozing (Coin olish uchun):")
    await state.set_state(BotState.adm_take_id)

@dp.message(BotState.adm_take_id)
async def adm_coin_take_2(m: Message, state: FSMContext):
    await state.update_data(t_id=m.text)
    await m.answer("💸 Qancha coin olib tashlaymiz?")
    await state.set_state(BotState.adm_take_amt)

@dp.message(BotState.adm_take_amt)
async def adm_coin_take_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    u_id = data['t_id']
    if u_id in db["users"]:
        db["users"][u_id]["balance"] -= int(m.text)
        Database.save(db)
        await m.answer(f"✅ {u_id} ning hisobidan {m.text} coin olib tashlandi.")
    await state.clear()

# ================= 9. ADMIN PANEL VA REKLAMA =================
@dp.message(F.text == "👑 Admin Panel")
async def admin_main(m: Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("🛠 **Boshqaruv Paneli:**", reply_markup=UI.admin_menu())

@dp.callback_query(F.data == "adm_ads")
async def adm_ads_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Reklama xabarini yuboring (Rasm, matn, video...):")
    await state.set_state(BotState.adm_broadcast)

@dp.message(BotState.adm_broadcast)
async def adm_ads_send(m: Message, state: FSMContext):
    db = Database.load()
    count = 0
    for uid in db["users"]:
        try:
            await m.copy_to(uid)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await m.answer(f"✅ Reklama {count} kishiga muvaffaqiyatli yuborildi.")
    await state.clear()

# ================= 10. SYSTEM LAUNCHER =================
async def main():
    Database.initialize()
    Thread(target=run_flask, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 BOT IS LIVE!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Bot stopped!")
