# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
OWNER_CHAT_ID = int(os.getenv("OWNER_CHAT_ID"))

if WEBHOOK_URL and WEBHOOK_URL.endswith('/'):
    WEBHOOK_URL = WEBHOOK_URL.rstrip('/')

if not all([BOT_TOKEN, WEBHOOK_SECRET, WEBHOOK_URL, OWNER_CHAT_ID]):
    raise RuntimeError("Переменные окружения не заданы корректно!")