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
    CallbackQuery, Message, ContentType, 
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
)

# ================= 1. KONFIGURATSIYA =================
TOKEN = "8366692220:AAHaJhbqksDOn_TgDp645GIliCT__4yZlUk"
ADMIN_ID = 7492227388 
DB_FILE = "cinema_v5_pro.json"

# --- WEB SERVER (KEEP ALIVE) ---
app = Flask(__name__)
@app.route('/')
def home():
    return f"🚀 BOT CORE V5: ONLINE | {datetime.now().strftime('%H:%M:%S')}"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# --- LOGGING ---
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
                "stats": {"total_sales": 0, "revenue": 0},
                "chats": {} # Jonli chat sessiyalari uchun
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

# ================= 3. FSM (HOLATLAR) TIZIMI =================
class BotState(StatesGroup):
    # Registration
    wait_name = State()
    wait_phone = State()
    
    # User Features
    search_movie = State()
    fill_balance = State()
    
    # Live Chat System
    chat_request = State() # Foydalanuvchi javobini kutish
    active_chat = State()  # Jonli suhbat jarayoni
    
    # Admin - Kino qo'shish
    adm_name = State()
    adm_year = State()
    adm_lang = State()
    adm_code = State()
    adm_link = State()
    adm_price = State()
    
    # Admin - Boshqaruv
    adm_broadcast = State()
    adm_give_id = State()
    adm_give_amount = State()
    adm_take_id = State()
    adm_take_amount = State()
    adm_ban_id = State()
    adm_chat_target = State() # Qaysi user bilan gaplashmoqchi
    adm_del_movie = State()

# ================= 4. KLAVIATURA (UI) TIZIMI =================
class UI:
    @staticmethod
    def main_menu(uid):
        kb = ReplyKeyboardBuilder()
        kb.button(text="🎬 Kinolar Ro'yxati")
        kb.button(text="📥 Kino Qidirish")
        kb.button(text="💳 Mening Hisobim")
        kb.button(text="💰 Balans To'ldirish")
        kb.button(text="🎁 Kunlik Bonus")
        kb.button(text="☎️ Admin bilan Aloqa")
        if int(uid) == ADMIN_ID:
            kb.button(text="👑 Admin Panel")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def admin_panel():
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Kino Qo'shish", callback_data="adm_add")
        kb.button(text="❌ Kino O'chirish", callback_data="adm_del")
        kb.button(text="💰 Coin Berish", callback_data="adm_give")
        kb.button(text="💸 Coin Olish", callback_data="adm_take")
        kb.button(text="🚫 Bloklash", callback_data="adm_ban")
        kb.button(text="📢 Reklama", callback_data="adm_ads")
        kb.button(text="💬 Jonli Chat", callback_data="adm_chat")
        kb.adjust(2)
        return kb.as_markup()

    @staticmethod
    def chat_confirm():
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Ha, gaplashaman", callback_data="chat_yes")
        kb.button(text="❌ Yo'q, rad etaman", callback_data="chat_no")
        kb.adjust(2)
        return kb.as_markup()

# ================= 5. START VA RO'YXATDAN O'TISH =================
@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    db = Database.load()
    uid = str(m.from_user.id)

    if uid in db.get("banned", []):
        return await m.answer("⛔️ Siz bloklangansiz!")

    if uid in db["users"]:
        await m.answer(f"🌟 Xush kelibsiz qaytib, {db['users'][uid]['name']}!", reply_markup=UI.main_menu(uid))
    else:
        await m.answer("👋 Botga xush kelibsiz! Ismingizni kiriting:")
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
    
    # ID Generatsiyasi
    user_id_code = f"UC{random.randint(1000, 9999)}"
    
    db["users"][uid] = {
        "name": data["name"],
        "phone": m.contact.phone_number,
        "balance": 100,
        "u_id": user_id_code,
        "movies": [],
        "joined": datetime.now().strftime("%Y-%m-%d")
    }
    Database.save(db)

    # Adminga habar
    await bot.send_message(ADMIN_ID, f"🔔 **Yangi foydalanuvchi!**\n👤 Ism: {data['name']}\n🆔 ID: `{uid}`\n🔑 Kod: {user_id_code}\n📞 {m.contact.phone_number}")

    await m.answer(f"🎉 Ro'yxatdan o'tdingiz! Sizga 100 coin berildi.\nSizning ID kodingiz: {user_id_code}", reply_markup=UI.main_menu(uid))
    await state.clear()

# ================= 6. JONLI CHAT TIZIMI (PROFESSIONAL) =================
@dp.callback_query(F.data == "adm_chat")
async def adm_chat_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Gaplashmoqchi bo'lgan foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.adm_chat_target)

@dp.message(BotState.adm_chat_target)
async def adm_chat_req(m: Message, state: FSMContext):
    target_id = m.text
    db = Database.load()
    if target_id not in db["users"]:
        return await m.answer("❌ Foydalanuvchi topilmadi!")
    
    await state.update_data(chat_with=target_id)
    await m.answer(f"⏳ {target_id} ga so'rov yuborildi. Javobini kuting...")
    
    await bot.send_message(target_id, "🔔 **Admin siz bilan jonli muloqot qilmoqchi.**\nQabul qilasizmi?", reply_markup=UI.chat_confirm())

@dp.callback_query(F.data.startswith("chat_"))
async def user_chat_res(c: CallbackQuery, state: FSMContext):
    res = c.data.split("_")[1]
    db = Database.load()
    
    if res == "yes":
        await c.message.edit_text("✅ Muloqot boshlandi. Xabar yozishingiz mumkin.")
        await bot.send_message(ADMIN_ID, f"✅ Foydalanuvchi ({c.from_user.id}) muloqotni qabul qildi.\nSuhbatni tugatish uchun /stop_chat yozing.")
        
        # Har ikki tarafni Active Chat holatiga o'tkazamiz
        await state.set_state(BotState.active_chat)
        # Admin holatini ham o'zgartirish kerak (bu yerda soddalashtirilgan)
    else:
        await c.message.edit_text("❌ Rad etildi.")
        await bot.send_message(ADMIN_ID, f"⚠️ Foydalanuvchi ({c.from_user.id}) muloqotni rad etdi.")

@dp.message(BotState.active_chat)
async def live_chatting(m: Message, state: FSMContext):
    if m.text == "/stop_chat":
        await m.answer("📴 Muloqot yakunlandi.")
        await bot.send_message(ADMIN_ID if m.from_user.id != ADMIN_ID else "USER_ID", "📴 Admin muloqotni yakunladi.")
        return await state.clear()

    # Xabarni yetkazish logicasi
    target = ADMIN_ID if m.from_user.id != ADMIN_ID else (await state.get_data())['chat_with']
    await bot.send_message(target, f"💬 **Yangi xabar:**\n{m.text}")

# ================= 7. KINO BOSHQARUVI (ADD/DEL/SEARCH) =================
@dp.callback_query(F.data == "adm_add")
async def adm_add_1(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 Kino nomi:")
    await state.set_state(BotState.adm_name)

@dp.message(BotState.adm_name)
async def adm_add_2(m: Message, state: FSMContext):
    await state.update_data(n=m.text)
    await m.answer("🔢 Kino kodi:")
    await state.set_state(BotState.adm_code)

@dp.message(BotState.adm_code)
async def adm_add_3(m: Message, state: FSMContext):
    await state.update_data(c=m.text)
    await m.answer("📅 Yili:")
    await state.set_state(BotState.adm_year)

@dp.message(BotState.adm_year)
async def adm_add_4(m: Message, state: FSMContext):
    await state.update_data(y=m.text)
    await m.answer("🌐 Tili:")
    await state.set_state(BotState.adm_lang)

@dp.message(BotState.adm_lang)
async def adm_add_5(m: Message, state: FSMContext):
    await state.update_data(t=m.text)
    await m.answer("🔗 Link (Havola):")
    await state.set_state(BotState.adm_link)

@dp.message(BotState.adm_link)
async def adm_add_6(m: Message, state: FSMContext):
    await state.update_data(l=m.text)
    await m.answer("💰 Narxi (Coin):")
    await state.set_state(BotState.adm_price)

@dp.message(BotState.adm_price)
async def adm_add_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    db["movies"].append({
        "name": data['n'], "code": data['c'], "year": data['y'], 
        "lang": data['t'], "link": data['l'], "price": int(m.text)
    })
    Database.save(db)
    await m.answer("✅ Kino qo'shildi!")
    await state.clear()

@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def user_movies(m: Message):
    db = Database.load()
    if not db["movies"]: return await m.answer("Hozircha bo'sh.")
    
    res = "🎬 **Kinolar ro'yxati:**\n\n"
    for k in db["movies"]:
        res += f"🎥 **{k['name']}**\n🏷 Kod: `{k['code']}` | 📅 {k['year']}\n🌐 Til: {k['lang']} | 💰 {k['price']} coin\n"
        res += "----------------------\n"
    await m.answer(res)

# ================= 8. COIN VA BALANS BOSHQARUVI =================
@dp.callback_query(F.data == "adm_give")
async def adm_give_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🆔 Foydalanuvchi ID sini yozing:")
    await state.set_state(BotState.adm_give_id)

@dp.message(BotState.adm_give_id)
async def adm_give_1(m: Message, state: FSMContext):
    await state.update_data(target=m.text)
    await m.answer("💰 Miqdorni yozing:")
    await state.set_state(BotState.adm_give_amount)

@dp.message(BotState.adm_give_amount)
async def adm_give_final(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = data['target']
    if uid in db["users"]:
        db["users"][uid]["balance"] += int(m.text)
        Database.save(db)
        await m.answer("✅ Coin berildi!")
        await bot.send_message(uid, f"🎁 Admin sizga {m.text} coin berdi!")
    await state.clear()

@dp.message(F.text == "💳 Mening Hisobim")
async def user_acc(m: Message):
    db = Database.load()
    u = db["users"].get(str(m.from_user.id))
    if u:
        await m.answer(f"👤 **Profilingiz:**\n\n🆔 Kod: {u['u_id']}\n💰 Balans: {u['balance']} coin\n🎬 Xaridlar: {len(u['movies'])} ta")

# ================= 9. REKLAMA VA BLOKLASH =================
@dp.callback_query(F.data == "adm_ads")
async def adm_ads_start(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Reklama matnini yuboring:")
    await state.set_state(BotState.adm_broadcast)

@dp.message(BotState.adm_broadcast)
async def adm_ads_exec(m: Message, state: FSMContext):
    db = Database.load()
    count = 0
    for uid in db["users"]:
        try:
            await m.copy_to(uid)
            count += 1
            await asyncio.sleep(0.1)
        except: continue
    await m.answer(f"✅ {count} kishiga yuborildi.")
    await state.clear()

# ================= 10. ISHGA TUSHIRISH =================
async def main():
    Database.initialize()
    Thread(target=run_flask, daemon=True).start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except:
        print("Xatolik yuz berdi!")
