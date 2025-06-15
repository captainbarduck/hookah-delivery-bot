import os
from quart import Quart, request
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CallbackContext,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", 8443))

app = Quart(__name__)
bot = Bot(token=TOKEN)
telegram_app = Application.builder().token(TOKEN).build()

# === Хэндлеры ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для заказа кальянов 🚬")

# === Регистрация хэндлеров ===
telegram_app.add_handler(CommandHandler("start", start))

# === Webhook endpoint ===
@app.post(f"/{WEBHOOK_SECRET}")
async def webhook() -> str:
    data = await request.get_data()
    update = Update.de_json(data.decode("utf-8"), bot)
    await telegram_app.update_queue.put(update)
    return "OK"

# === Хуки запуска/остановки ===
@app.before_serving
async def startup():
    await telegram_app.initialize()
    await telegram_app.start()
    webhook_url = os.getenv("WEBHOOK_URL")
    await bot.set_webhook(url=webhook_url, secret_token=WEBHOOK_SECRET)

@app.after_serving
async def shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()

# === Запуск приложения ===
if __name__ == "__main__":
    app.run(port=PORT)