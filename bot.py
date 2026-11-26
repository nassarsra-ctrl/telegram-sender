import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("9036646897:AAEUxlHmqkA5uZdxwzCzO8JIVLyGgiby67E", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://telegram-sender-cz75.onrender.com")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ich Bin Kein Roboter", web_app=WebAppInfo(url=MINI_APP_URL))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "✅ Drücke hier um dich zu verifizieren"
    await update.message.reply_text(text, reply_markup=reply_markup)

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN fehlt")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot startet...")
    print(f"Mini-App URL: {MINI_APP_URL}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
