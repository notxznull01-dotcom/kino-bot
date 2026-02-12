import asyncio
import json
import os
import logging
import sys
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

# ================= 1. SOZLAMALAR =================
TOKEN = "8366692220:AAHaJhbqksDOn_TgDp645GIliCT__4yZlUk"
ADMIN_ID = 7492227388 
DB_FILE = "cinema_pro_v3.json"

# --- WEB SERVER ---
app = Flask(__name__)
@app.route('/')
def home(): return "🚀 CORE ONLINE"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(message)s")
logger = logging.getLogger("UltraCinema")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= 2. PROFESSIONAL DATABASE MODULE =================
class Database:
    @staticmethod
    def init():
        if not os.path.exists(DB_FILE):
            data = {
                "users": {},
                "movies": [],
                "banned": [],
                "stats": {"total_visits": 0, "total_sales": 0},
                "promo_codes": {}
            }
            Database.save(data)
            return data
        return Database.load()

    @staticmethod
    def load():
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save(data):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

# ================= 3. FSM TIZIMI (HOLATLAR) =================
class BotState(StatesGroup):
    # Registration
    wait_name = State()
    wait_phone = State()
    # User features
    search_movie = State()
    apply_promo = State()
    # Admin features
    adm_add_name = State()
    adm_add_year = State()
    adm_add_code = State()
    adm_add_link = State()
    adm_add_price = State()
    adm_broadcast = State()
    adm_give_coin_id = State()
    adm_give_coin_amount = State()
    adm_ban_user = State()

# ================= 4. PROFESSIONAL KEYBOARDS =================
class UI:
    @staticmethod
    def main_menu(uid):
        kb = ReplyKeyboardBuilder()
        buttons = [
            "🎬 Kinolar Ro'yxati", "📥 Kino Qidirish",
            "💳 Mening Hisobim", "🎁 Kunlik Bonus",
            "📈 Statistika", "☎️ Bog'lanish"
        ]
        for btn in buttons: kb.button(text=btn)
        if uid == ADMIN_ID: kb.button(text="👑 Admin Panel")
        kb.adjust(2)
        return kb.as_markup(resize_keyboard=True)

    @staticmethod
    def admin_menu():
        kb = InlineKeyboardBuilder()
        kb.button(text="➕ Yangi Kino", callback_data="adm_kino_add")
        kb.button(text="💰 Coin Berish", callback_data="adm_coin_give")
        kb.button(text="🚫 Foydalanuvchini Bloklash", callback_data="adm_user_ban")
        kb.button(text="📢 Reklama Tarqatish", callback_data="adm_send_ads")
        kb.button(text="📊 To'liq Statistika", callback_data="adm_full_stats")
        kb.adjust(1)
        return kb.as_markup()

    @staticmethod
    def movie_action(m_id):
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Sotib Olish", callback_data=f"buy_{m_id}")
        return kb.as_markup()

# ================= 5. START VA REGISTRATSIYA =================
@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    db = Database.load()
    uid = str(m.from_user.id)

    if uid in db["banned"]:
        return await m.answer("❌ Siz botdan chetlatilgansiz!")

    if uid in db["users"]:
        await m.answer(f"🌟 Qayta xush kelibsiz, {db['users'][uid]['name']}!", reply_markup=UI.main_menu(m.from_user.id))
    else:
        await m.answer("👋 Xush kelibsiz! Botdan foydalanish uchun ro'yxatdan o'ting.\n\nIsmingizni kiriting:")
        await state.set_state(BotState.wait_name)

@dp.message(BotState.wait_name)
async def process_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text)
    kb = ReplyKeyboardBuilder().button(text="📱 Raqamni yuborish", request_contact=True)
    await m.answer(f"Rahmat {m.text}, endi telefon raqamingizni yuboring:", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(BotState.wait_phone)

@dp.message(BotState.wait_phone, F.contact)
async def process_phone(m: Message, state: FSMContext):
    data = await state.get_data()
    db = Database.load()
    uid = str(m.from_user.id)
    
    # User Data
    db["users"][uid] = {
        "name": data["name"],
        "phone": m.contact.phone_number,
        "balance": 100,
        "movies": [],
        "last_bonus": None,
        "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    db["stats"]["total_visits"] += 1
    Database.save(db)

    # Admin notification
    await bot.send_message(ADMIN_ID, f"🆕 **Yangi foydalanuvchi!**\n👤 {data['name']}\n🆔 {uid}\n📞 {m.contact.phone_number}")

    await m.answer(f"🎉 Ro'yxatdan o'tdingiz! Sizga 100 bonus coin berildi.", reply_markup=UI.main_menu(m.from_user.id))
    await state.clear()

# ================= 6. USER FEATURES =================
@dp.message(F.text == "💳 Mening Hisobim")
async def show_profile(m: Message):
    db = Database.load()
    u = db["users"].get(str(m.from_user.id))
    if not u: return
    
    text = (f"👤 **Profil:** {u['name']}\n"
            f"🆔 **ID:** `{m.from_user.id}`\n"
            f"💰 **Balans:** {u['balance']} coin\n"
            f"🎬 **Sotib olinganlar:** {len(u['movies'])} ta")
    await m.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🎬 Kinolar Ro'yxati")
async def list_movies(m: Message):
    db = Database.load()
    if not db["movies"]:
        return await m.answer("📂 Hozircha bazada kinolar yo'q.")
    
    res = "🎬 **Barcha kinolar:**\n\n"
    for m_item in db["movies"]:
        res += f"🔹 **{m_item['name']}** ({m_item['year']})\n└ Kod: `{m_item['code']}` | Narxi: {m_item['price']} coin\n\n"
    await m.answer(res, parse_mode="Markdown")

@dp.message(F.text == "📥 Kino Qidirish")
async def search_movie_init(m: Message, state: FSMContext):
    await m.answer("🔍 Kino kodini kiriting:")
    await state.set_state(BotState.search_movie)

@dp.message(BotState.search_movie)
async def search_movie_exec(m: Message, state: FSMContext):
    db = Database.load()
    movie = next((item for item in db["movies"] if str(item["code"]) == m.text), None)
    
    if movie:
        text = (f"🎬 **Nomi:** {movie['name']}\n"
                f"📅 **Yili:** {movie['year']}\n"
                f"💰 **Narxi:** {movie['price']} coin")
        await m.answer(text, reply_markup=UI.movie_action(movie['code']))
    else:
        await m.answer("❌ Bunday kodli kino topilmadi.")
    await state.clear()

@dp.message(F.text == "🎁 Kunlik Bonus")
async def daily_bonus(m: Message):
    db = Database.load()
    uid = str(m.from_user.id)
    u = db["users"][uid]
    
    now = datetime.now()
    if u["last_bonus"]:
        last = datetime.strptime(u["last_bonus"], "%Y-%m-%d %H:%M:%S")
        if now - last < timedelta(days=1):
            diff = timedelta(days=1) - (now - last)
            return await m.answer(f"⚠️ Bonusni {diff.seconds // 3600} soatdan keyin olishingiz mumkin.")

    bonus = random.randint(10, 50)
    u["balance"] += bonus
    u["last_bonus"] = now.strftime("%Y-%m-%d %H:%M:%S")
    Database.save(db)
    await m.answer(f"🎁 Sizga {bonus} coin bonus berildi!\nYangi balans: {u['balance']}")

# ================= 7. ADMIN PANEL LOGIC =================
@dp.message(F.text == "👑 Admin Panel")
async def adm_panel_open(m: Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("🛠 Boshqaruv paneli:", reply_markup=UI.admin_menu())

@dp.callback_query(F.data == "adm_kino_add")
async def adm_kino_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎬 Kino nomini yozing:")
    await state.set_state(BotState.adm_add_name)

@dp.message(BotState.adm_add_name)
async def adm_kino_n(m: Message, state: FSMContext):
    await state.update_data(n=m.text)
    await m.answer("📅 Yili:")
    await state.set_state(BotState.adm_add_year)

@dp.message(BotState.adm_add_year)
async def adm_kino_y(m: Message, state: FSMContext):
    await state.update_data(y=m.text)
    await m.answer("🔢 Kino kodi (masalan 100):")
    await state.set_state(BotState.adm_add_code)

@dp.message(BotState.adm_add_code)
async def adm_kino_c(m: Message, state: FSMContext):
    await state.update_data(c=m.text)
    await m.answer("🔗 Telegram file linki:")
    await state.set_state(BotState.adm_add_link)

@dp.message(BotState.adm_add_link)
async def adm_kino_l(m: Message, state: FSMContext):
    await state.update_data(l=m.text)
    await m.answer("💰 Narxi (coin):")
    await state.set_state(BotState.adm_add_price)

@dp.message(BotState.adm_add_price)
async def adm_kino_final(m: Message, state: FSMContext):
    if not m.text.isdigit(): return await m.answer("Faqat raqam yozing!")
    data = await state.get_data()
    db = Database.load()
    db["movies"].append({
        "name": data["n"], "year": data["y"], "code": data["c"],
        "link": data["l"], "price": int(m.text)
    })
    Database.save(db)
    await m.answer("✅ Kino muvaffaqiyatli qo'shildi!")
    await state.clear()

@dp.callback_query(F.data == "adm_send_ads")
async def adm_ads_init(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📢 Reklama matnini yuboring:")
    await state.set_state(BotState.adm_broadcast)

@dp.message(BotState.adm_broadcast)
async def adm_ads_exec(m: Message, state: FSMContext):
    db = Database.load()
    users = db["users"].keys()
    count = 0
    for u_id in users:
        try:
            await bot.send_message(u_id, m.text)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await m.answer(f"✅ Reklama {count} kishiga yuborildi.")
    await state.clear()

# ================= 8. MOVIE BUY LOGIC =================
@dp.callback_query(F.data.startswith("buy_"))
async def buy_movie(c: CallbackQuery):
    db = Database.load()
    m_code = c.data.split("_")[1]
    uid = str(c.from_user.id)
    
    movie = next((item for item in db["movies"] if str(item["code"]) == m_code), None)
    user = db["users"].get(uid)
    
    if not movie or not user: return
    
    if m_code in user["movies"]:
        return await c.message.answer(f"✅ Siz bu kinoni sotib olgansiz:\n{movie['link']}")

    if user["balance"] >= movie["price"]:
        user["balance"] -= movie["price"]
        user["movies"].append(m_code)
        db["stats"]["total_sales"] += 1
        Database.save(db)
        await c.message.answer(f"🎉 Xarid muvaffaqiyatli!\n🎬 {movie['name']}\n🔗 Link: {movie['link']}")
    else:
        await c.message.answer("❌ Mablag' yetarli emas!")

# ================= 9. SYSTEM RUN =================
async def main():
    Database.init()
    # Start Flask thread
    Thread(target=run_flask, daemon=True).start()
    logger.info("Bot is starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.error("Bot stopped")
