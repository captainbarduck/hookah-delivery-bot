import asyncio
import os
import logging
from quart import Quart, request, abort
from dotenv import load_dotenv
from hypercorn.config import Config
from hypercorn.asyncio import serve

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

from datetime import datetime
import pytz

# Загрузка переменных окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID"))

# Remove trailing slash from WEBHOOK_URL if present
if WEBHOOK_URL and WEBHOOK_URL.endswith('/'):
    WEBHOOK_URL = WEBHOOK_URL.rstrip('/')

# Проверка
if not all([BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL, OWNER_CHAT_ID]):
    raise RuntimeError("Переменные окружения не заданы корректно!")

# Логгирование
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Определение часового пояса
MINSK_TZ = pytz.timezone("Europe/Minsk")
today_minsk = datetime.now(MINSK_TZ).date()

# Quart-приложение для асинхронной поддержки
app = Quart(__name__)

# Telegram-приложение
telegram_app = (
    Application.builder()
    .token(BOT_TOKEN)
    .build()
)

# Хранилище заказов в памяти
user_orders = {}

# === Хендлеры ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"chat_id: {update.effective_chat.id}")

    keyboard = [[InlineKeyboardButton("\U0001F6D2 Заказать кальян", callback_data="order_hookah")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привет! Я помогу тебе заказать кальян с доставкой по Минску.\nНажми кнопку ниже, чтобы начать \U0001F447",
        reply_markup=reply_markup
    )

async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # подтверждение Telegram
    if query.data == "order_hookah":
        user_id = query.from_user.id
        await query.message.reply_text(
            "Выберите нужную услугу:\n1. Аренда одного кальяна на сутки – 30 BYN\n(в комплект входит: кальян, одна лёгкая забивка, калауд, щипцы, плитка для розжига угля, мундштуки)\n2. Дополнительные сутки аренды – 15 BYN\n3. Дополнительная забивка табака (+уголь) – 12 BYN\n\n * Доставка оплачивается отдельно: привезти и забрать кальян – 20 BYN\n * При доставке за МКАД считается стоимость доставки + 0.5BYN/км от МКАД до точки доставки\n\nНапишите количество кальянов и дней аренды. Укажи дополнительную информацию по забивкам и доставке за МКАД, если требуется"
        )
        user_orders[user_id] = {"step": "choosing_hookah"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"DEBUG: user_id={user_id}, last_order_date={user_orders.get(user_id, {}).get('date')}, today={today_minsk}")
    text = update.message.text
    user_id = update.effective_user.id
    today_minsk = datetime.now(MINSK_TZ).date()
    
    if user_id in user_orders:
        last_order_date = user_orders[user_id].get("date")
        if last_order_date == today_minsk:
            await update.message.reply_text(
                "Сегодня вы уже оставляли заказ. Лимит заказов в сутки: 1"
            )
            return

    if text == "\U0001F6D2 Заказать кальян":
        await update.message.reply_text("Выберите нужную услугу:\n1. Аренда одного кальяна на сутки – 30 BYN\n(в комплект входит: кальян, одна лёгкая забивка, калауд, щипцы, плитка для розжига угля, мундштуки)\n2. Дополнительные сутки аренды – 15 BYN\n3. Дополнительная забивка табака (+уголь) – 12 BYN\n\n * Доставка оплачивается отдельно: привезти и забрать кальян – 20 BYN\n * При доставке за МКАД считается стоимость доставки + 0.5BYN/км от МКАД до точки доставки\n\nНапишите количество кальянов и дней аренды. Укажи дополнительную информацию по забивкам и доставке за МКАД, если требуется")
        user_orders[user_id] = {"step": "choosing_hookah"}
        return

    state = user_orders.get(user_id, {}).get("step")

    if state == "choosing_hookah":
        user_orders[user_id]["hookah"] = text
        user_orders[user_id]["step"] = "address"
        await update.message.reply_text("Укажи адрес доставки (Минск, либо за МКАД в пределах 50км):")

    elif state == "address":
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
            f"• Услуга: {order['hookah']}\n"
            f"• Адрес: {order['address']}\n"
            f"• Время: {order['time']}\n"
            f"• Телефон: {order['phone']}\n\n"
            "Спасибо! Мы свяжемся с тобой в ближайшее время \U0001F64C"
        )
        await update.message.reply_text(summary)

        # Уведомление о новом заказе
        owner_notification = (
            f"Новый заказ на доставку от @{update.effective_user.username or update.effective_user.first_name}:\n"
            f"Кальян: {order['hookah']}\n"
            f"Адрес: {order['address']}\n"
            f"Время: {order['time']}\n"
            f"Телефон: {order['phone']}"
        )
        try:
            await context.bot.send_message(chat_id=OWNER_CHAT_ID, text=owner_notification)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение владельцу: {e}")

        user_orders[user_id]["date"] = today_minsk
        user_orders[user_id]["step"] = "done"

    else:
        await update.message.reply_text("Нажми \U0001F6D2 Заказать кальян, чтобы начать новый заказ.")

# Регистрация хендлеров
telegram_app.add_handler(CallbackQueryHandler(handle_button_click))
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === Webhook эндпоинт ===
@app.route(f"/{WEBHOOK_SECRET}/", methods=["POST"])
@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
async def webhook():
    logger.info(f"Received webhook request from {request.remote_addr}")
    
    # Verify secret token
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != WEBHOOK_SECRET:
        logger.warning(f"Unauthorized webhook attempt from {request.remote_addr}")
        abort(403)
    
    try:
        # Get and parse update
        update_json = await request.get_json(force=True)
        message_text = update_json.get('message', {}).get('text', 'unknown')
        logger.info(f"Received update with text: {message_text}")
        
        # Process update
        update = Update.de_json(update_json, telegram_app.bot)
        logger.info(f"Processing update ID: {update.update_id}")
        
        await telegram_app.process_update(update)
        logger.info(f"Successfully processed update ID: {update.update_id}")
        return "ok"
        
    except Exception as e:
        logger.error(f"Error processing update: {str(e)}", exc_info=True)
        return "Error processing update", 500

# Проверочный GET-запрос
@app.route("/", methods=["GET"])
async def index():
    return "Telegram hookah bot is running."

@app.route("/health")
async def health():
    try:
        # Check if bot can get its info
        bot_info = await telegram_app.bot.get_me()
        return {
            "status": "healthy",
            "bot_username": bot_info.username,
            "webhook_mode": True
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}, 500

# === Lifecycle hooks ===
@app.before_serving
async def startup():
    logger.info("Application startup...")

@app.after_serving
async def shutdown():
    logger.info("Application shutdown...")
    await telegram_app.stop()
    await telegram_app.shutdown()

# === Запуск ===
if __name__ == "__main__":
    async def init_app():
        try:
            # Initialize and start the application
            await telegram_app.initialize()
            await telegram_app.start()
            
            # Set up webhook
            webhook_path = f"{WEBHOOK_URL.rstrip('/')}/{WEBHOOK_SECRET}"
            logger.info(f"Setting webhook to: {webhook_path}")
            
            # Get current webhook info
            webhook_info = await telegram_app.bot.get_webhook_info()
            if webhook_info.url:
                logger.info(f"Found existing webhook: {webhook_info.url}")
                await telegram_app.bot.delete_webhook(drop_pending_updates=True)
                logger.info("Deleted existing webhook and dropped pending updates")
            
            # Set new webhook with validation
            try:
                result = await telegram_app.bot.set_webhook(
                    url=webhook_path,
                    secret_token=WEBHOOK_SECRET,
                    allowed_updates=['message', 'callback_query']
                )
                logger.info(f"Webhook setup result: {result}")
                
                # Verify webhook setup
                webhook_info = await telegram_app.bot.get_webhook_info()
                logger.info(f"Webhook info: {webhook_info.to_dict()}")
                
                if not webhook_info.url:
                    raise RuntimeError("Webhook setup failed - no webhook URL set")
            except Exception as e:
                logger.error(f"Failed to set webhook: {e}")
                raise
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            raise

    async def run_app():
        try:
            # Run initialization first
            await init_app()
            
            # Configure and start Hypercorn
            port = int(os.environ.get("PORT", 8080))
            logger.info(f"Starting Hypercorn server on port {port}")
            
            config = Config()
            config.bind = [f"0.0.0.0:{port}"]
            config.accesslog = "-"  # Log to stdout
            config.errorlog = "-"   # Log errors to stdout
            config.worker_class = "asyncio"
            config.debug = True if os.getenv("DEBUG") else False
            config.use_reloader = False  # Disable reloader to prevent double initialization
            
            await serve(app, config)
        except Exception as e:
            logger.error(f"Failed to run application: {e}")
            raise

    # Run everything in the main event loop
    asyncio.run(run_app())
