import asyncpg
import os
import logging
from datetime import date
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

db_pool: asyncpg.Pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                hookah TEXT,
                address TEXT,
                delivery_time TEXT,
                phone TEXT,
                order_date DATE NOT NULL
            )
        """)

async def is_limit_reached(user_id: int, order_date: date) -> bool:
    query = """
        SELECT COUNT(*) FROM orders
        WHERE user_id = $1 AND order_date = $2
    """
    async with db_pool.acquire() as conn:
        result = await conn.fetchval(query, user_id, order_date)
        return result > 0

async def save_order(user_id: int, username: str, hookah: str, address: str, delivery_time: str, phone: str, order_date: date):
    query = """
        INSERT INTO orders (user_id, username, hookah, address, delivery_time, phone, order_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """
    async with db_pool.acquire() as conn:
        await conn.execute(query, user_id, username, hookah, address, delivery_time, phone, order_date)

async def get_orders_by_date(query_date: date):
    conn = await asyncpg.connect(dsn=os.getenv("DATABASE_URL"))
    try:
        rows = await conn.fetch("""
            SELECT username, hookah, address, delivery_time, phone 
            FROM orders 
            WHERE order_date = $1
            ORDER BY delivery_time
        """, query_date)
        return rows
    finally:
        await conn.close()

try:
    ...
except Exception as e:
    logger.error(f"DB error: {e}")