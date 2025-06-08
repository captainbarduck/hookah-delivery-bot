import asyncio
import os
import logging
from flask import Flask, request, abort
from dotenv import load_dotenv

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Проверка
if not all([BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL]):
    raise RuntimeError("Переменные окружения не заданы корректно!")

# Логгирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask-приложение
app = Flask(__name__)

# Telegram-приложение
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Хранилище заказов в памяти
user_orders = {}

# === Хендлеры ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("\U0001F6D2 Заказать кальян")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет \U0001F44B! Я помогу тебе заказать кальян с доставкой по Минску.\nНажми кнопку ниже, чтобы начать \U0001F447",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "\U0001F6D2 Заказать кальян":
        await update.message.reply_text("Выберите кальян из списка:\n1. DarkSide Strong \U0001F347 – 40 BYN\n2. MustHave Citrus \U0001F34B – 35 BYN\n\nНапиши номер или название.")
        user_orders[user_id] = {"step": "choosing_hookah"}
        return

    state = user_orders.get(user_id, {}).get("step")

    if state == "choosing_hookah":
        user_orders[user_id]["hookah"] = text
        user_orders[user_id]["step"] = "address"
        await update.message.reply_text("Укажи адрес доставки (только по Минску):")

    elif state == "address":
        if "минск" not in text.lower():
            await update.message.reply_text("Мы доставляем только по Минску. Пожалуйста, укажи минский адрес.")
            return
        user_orders[user_id]["address"] = text
        user_orders[user_id]["step"] = "time"
        await update.message.reply_text("Укажи удобное время доставки (например, 20:00):")

    elif state == "time":
        user_orders[user_id]["time"] = text
        user_orders[user_id]["step"] = "phone"
        await update.message.reply_text("Оставь, пожалуйста, свой номер телефона \U0001F4DE:")

    elif state == "phone":
        user_orders[user_id]["phone"] = text
        order = user_orders[user_id]
        summary = (
            f"\u2705 Твой заказ:\n"
            f"• Кальян: {order['hookah']}\n"
            f"• Адрес: {order['address']}\n"
            f"• Время: {order['time']}\n"
            f"• Телефон: {order['phone']}\n\n"
            "Спасибо! Мы свяжемся с тобой в ближайшее время \U0001F64C"
        )
        await update.message.reply_text(summary)
        user_orders[user_id]["step"] = "done"

    else:
        await update.message.reply_text("Нажми \U0001F6D2 Заказать кальян, чтобы начать новый заказ.")

# Регистрация хендлеров
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === Webhook эндпоинт ===
@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "ok"

# Проверочный GET-запрос
@app.route("/", methods=["GET"])
def index():
    return "Telegram hookah bot is running."

# === Запуск ===
if __name__ == "__main__":
    # Установка webhook
    async def setup_webhook():
        await telegram_app.bot.set_webhook(
            url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET}",
            secret_token=WEBHOOK_SECRET
        )

    asyncio.run(setup_webhook())

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))