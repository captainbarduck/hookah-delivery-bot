import asyncio
import os
import sys
from datetime import datetime

import pytz
from dotenv import load_dotenv
from loguru import logger
from quart import Quart, request, abort
from hypercorn.asyncio import serve
from hypercorn.config import Config

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

from database import init_db, is_limit_reached, save_order

# =============================
# Логирование setup
logger.remove()  # Убрать дефолтный логгер
logger.add(sys.stdout, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <level>{message}</level>")
logger.add("logs/debug.log", rotation="500 KB", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}")

# =============================
# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID"))

if WEBHOOK_URL and WEBHOOK_URL.endswith('/'):
    WEBHOOK_URL = WEBHOOK_URL.rstrip('/')

if not all([BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL, OWNER_CHAT_ID]):
    logger.error("Переменные окружения не заданы корректно!")
    raise RuntimeError("Переменные окружения не заданы корректно!")

# =============================
# Таймзона
MINSK_TZ = pytz.timezone("Europe/Minsk")

# =============================
# Метрики мониторинга
metrics = {
    "webhook_requests_total": 0,
    "webhook_requests_success": 0,
    "webhook_requests_failed": 0,
    "orders_received": 0,
}

# =============================
# Инициализация приложений
app = Quart(__name__)

telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)

user_orders = {}

# =============================
# Хендлеры Telegram

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today_minsk = datetime.now(MINSK_TZ).date()

    if await is_limit_reached(user_id, today_minsk):
        await update.message.reply_text(
            "Сегодня вы уже оставляли заказ. Лимит заказов в сутки: 1"
        )
        logger.info(f"User {user_id} попытался начать новый заказ, но лимит достигнут")
        return

    logger.info(f"User {user_id} запустил команду /start")

    keyboard = [[InlineKeyboardButton("\U0001F6D2 Заказать кальян", callback_data="order_hookah")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Я помогу тебе заказать кальян с доставкой по Минску.\nНажми кнопку ниже, чтобы начать \U0001F447",
        reply_markup=reply_markup
    )

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    today_minsk = datetime.now(MINSK_TZ).date()

    if await is_limit_reached(user_id, today_minsk):
        await query.edit_message_text("Сегодня вы уже оставляли заказ. Лимит заказов в сутки: 1")
        logger.info(f"User {user_id} нажал кнопку, но лимит достигнут")
        return

    if query.data == "order_hookah":
        await query.message.reply_text(
            "Выберите нужную услугу:\n1. Аренда одного кальяна на сутки – 30 BYN\n(в комплект входит: кальян, одна лёгкая забивка, калауд, щипцы, плитка для розжига угля, мундштуки)\n2. Дополнительные сутки аренды – 15 BYN\n3. Дополнительная забивка табака (+уголь) – 12 BYN\n\n * Доставка оплачивается отдельно: привезти и забрать кальян – 20 BYN\n * При доставке за МКАД считается стоимость доставки + 0.5BYN/км от МКАД до точки доставки\n\nНапишите количество кальянов и дней аренды. Укажи дополнительную информацию по забивкам и доставке за МКАД, если требуется"
        )
        user_orders[user_id] = {"step": "choosing_hookah"}
        logger.info(f"User {user_id} начал оформление заказа через кнопку")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    today_minsk = datetime.now(MINSK_TZ).date()

    logger.debug(f"User {user_id} sent message: {text}")

    if user_id in user_orders and await is_limit_reached(user_id, today_minsk):
        await update.message.reply_text("Сегодня вы уже оставляли заказ. Лимит заказов в сутки: 1")
        logger.info(f"User {user_id} отправил сообщение, но лимит достигнут")
        return

    if text == "\U0001F6D2 Заказать кальян":
        await update.message.reply_text(
            "Выберите нужную услугу:\n1. Аренда одного кальяна на сутки – 30 BYN\n(в комплект входит: кальян, одна лёгкая забивка, калауд, щипцы, плитка для розжига угля, мундштуки)\n2. Дополнительные сутки аренды – 15 BYN\n3. Дополнительная забивка табака (+уголь) – 12 BYN\n\n * Доставка оплачивается отдельно: привезти и забрать кальян – 20 BYN\n * При доставке за МКАД считается стоимость доставки + 0.5BYN/км от МКАД до точки доставки\n\nНапишите количество кальянов и дней аренды. Укажи дополнительную информацию по забивкам и доставке за МКАД, если требуется"
        )
        user_orders[user_id] = {"step": "choosing_hookah"}
        logger.info(f"User {user_id} начал новый заказ через сообщение")
        return

    state = user_orders.get(user_id, {}).get("step")

    if state == "choosing_hookah":
        user_orders[user_id]["hookah"] = text
        user_orders[user_id]["step"] = "address"
        await update.message.reply_text("Укажи адрес доставки (Минск, либо за МКАД в пределах 50км):")
        logger.debug(f"User {user_id} выбрал услугу: {text}")

    elif state == "address":
        user_orders[user_id]["address"] = text
        user_orders[user_id]["step"] = "time"
        await update.message.reply_text("Укажи удобное время доставки (например, 20:00):")
        logger.debug(f"User {user_id} указал адрес: {text}")

    elif state == "time":
        user_orders[user_id]["time"] = text
        user_orders[user_id]["step"] = "phone"
        await update.message.reply_text("Оставь, пожалуйста, свой номер телефона \U0001F4DE:")
        logger.debug(f"User {user_id} указал время: {text}")

    elif state == "phone":
        user_orders[user_id]["phone"] = text
        order = user_orders[user_id]
        summary = (
            f"\u2705 Твой заказ:\n"
            f"• Услуга: {order['hookah']}\n"
            f"• Адрес: {order['address']}\n"
            f"• Время: {order['time']}\n"
            f"• Телефон: {order['phone']}\n\n"
            "Спасибо! Мы свяжемся с тобой в ближайшее время \U0001F64C"
        )
        await update.message.reply_text(summary)

        # Уведомление владельцу
        owner_notification = (
            f"Новый заказ на доставку от @{update.effective_user.username or update.effective_user.first_name}:\n"
            f"Кальян: {order['hookah']}\n"
            f"Адрес: {order['address']}\n"
            f"Время: {order['time']}\n"
            f"Телефон: {order['phone']}"
        )
        try:
            await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=owner_notification)
            metrics["orders_received"] += 1
            logger.info(f"Отправлено уведомление владельцу о новом заказе от user {user_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение владельцу: {e}")

        await save_order(
            user_id=user_id,
            username=update.effective_user.username or "no_username",
            hookah=order['hookah'],
            address=order['address'],
            delivery_time=order['time'],
            phone=order['phone'],
            order_date=today_minsk
        )

        user_orders[user_id]["date"] = today_minsk
        user_orders[user_id]["step"] = "done"

    else:
        await update.message.reply_text("Нажми \U0001F6D2 Заказать кальян, чтобы начать новый заказ.")
        logger.debug(f"User {user_id} ввел сообщение вне состояния оформления заказа")

# =============================
# Регистрация хендлеров
telegram_app.add_handler(CallbackQueryHandler(handle_button_click))
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# =============================
# Webhook endpoint с мониторингом и логированием

@app.route(f"/{WEBHOOK_SECRET}/", methods=["POST"])
@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
async def webhook():
    metrics["webhook_requests_total"] += 1
    logger.info(f"Webhook request from {request.remote_addr}")

    # Проверка токена секрета
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != WEBHOOK_SECRET:
        logger.warning(f"Unauthorized webhook attempt from {request.remote_addr}")
        metrics["webhook_requests_failed"] += 1
        abort(403)

    try:
        update_json = await request.get_json(force=True)
        message_text = update_json.get('message', {}).get('text', 'unknown')
        logger.debug(f"Received update with text: {message_text}")

        update = Update.de_json(update_json, telegram_app.bot)
        logger.info(f"Processing update ID: {update.update_id}")

        await telegram_app.process_update(update)

        metrics["webhook_requests_success"] += 1
        logger.info(f"Successfully processed update ID: {update.update_id}")
        return "ok"

    except Exception as e:
        metrics["webhook_requests_failed"] += 1
        logger.error(f"Error processing update: {str(e)}", exc_info=True)
        return "Error processing update", 500

# =============================
# Проверочные эндпоинты

@app.route("/", methods=["GET"])
async def index():
    return "Telegram hookah bot is running."

@app.route("/health")
async def health():
    try:
        bot_info = await telegram_app.bot.get_me()
        return {"status": "ok", "bot_username": bot_info.username, "metrics": metrics}
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500

# =============================
# Запуск сервера Hypercorn

async def main():
    await init_db()

    webhook_path = f"{WEBHOOK_URL}/{WEBHOOK_SECRET}"
    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(
    url=webhook_path,
    secret_token=WEBHOOK_SECRET,
    allowed_updates=["message", "callback_query"]
    )
    logger.info(f"Webhook set to: {webhook_path}")

    config = Config()
    config.bind = ["0.0.0.0:8080"]
    logger.info("Starting Quart server with Hypercorn...")
    await serve(app, config)

if __name__ == "__main__":
    asyncio.run(main())