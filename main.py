import os
from flask import Flask, request
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # например, https://your-bot.up.railway.app

app = Flask(__name__)

# In-memory storage (замени на БД в будущем)
user_orders = {}

# Telegram App init
application = Application.builder().token(TOKEN).build()

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("🛒 Заказать кальян")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет 👋! Я помогу тебе заказать кальян с доставкой по Минску.\nНажми кнопку ниже, чтобы начать 👇",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🛒 Заказать кальян":
        await update.message.reply_text("Выберите кальян из списка:\n1. DarkSide Strong 🍇 – 40 BYN\n2. MustHave Citrus 🍋 – 35 BYN\n\nНапиши номер или название.")
        user_orders[update.effective_user.id] = {"step": "choosing_hookah"}
        return

    user_id = update.effective_user.id
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
        await update.message.reply_text("Оставь, пожалуйста, свой номер телефона 📞:")
    elif state == "phone":
        user_orders[user_id]["phone"] = text
        order = user_orders[user_id]
        summary = (
            f"✅ Твой заказ:\n"
            f"• Кальян: {order['hookah']}\n"
            f"• Адрес: {order['address']}\n"
            f"• Время: {order['time']}\n"
            f"• Телефон: {order['phone']}\n\n"
            "Спасибо! Мы свяжемся с тобой в ближайшее время 🙌"
        )
        await update.message.reply_text(summary)
        # Тут можно отправить заказ владельцу бота, например, через context.bot.send_message(chat_id=OWNER_ID, ...)
        user_orders[user_id]["step"] = "done"
    else:
        await update.message.reply_text("Нажми 🛒 Заказать кальян, чтобы начать новый заказ.")

# === Обработчики ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# === Flask Webhook ===
@app.route(f"/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

@app.route("/", methods=["GET"])
def index():
    return "Bot is running."

# === Запуск ===
if __name__ == "__main__":
    # Установка webhook
    webhook_url = f"{WEBHOOK_URL}/{WEBHOOK_SECRET}"
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
	webhook_url=f"{WEBHOOK_URL}/{WEBHOOK_SECRET}",
        secret_token=WEBHOOK_SECRET,
    )
