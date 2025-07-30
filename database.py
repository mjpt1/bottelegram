import aiosqlite
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# وارد کردن نمونه تنظیمات برای دسترسی به مسیر دیتابیس
from config import settings

# تنظیم یک لاگر برای این ماژول
logger = logging.getLogger(__name__)

async def init_db():
    """
    دیتابیس و جداول اولیه را در صورت عدم وجود ایجاد می‌کند.
    این تابع باید در هنگام شروع به کار ربات یک بار فراخوانی شود.
    """
    try:
        async with aiosqlite.connect(settings.database_path) as db:
            # ایجاد جدول کاربران
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    access_code_hash TEXT,
                    wallet_address TEXT,
                    nft_info TEXT,
                    status TEXT NOT NULL DEFAULT 'pending', -- وضعیت‌ها: pending, approved, rejected, blocked, admin
                    join_date TEXT NOT NULL
                )
            """)
            # در آینده می‌توان جداول دیگر (محتوا، دسته‌بندی‌ها، لاگ‌ها و...) را نیز به همین شکل اضافه کرد
            # CREATE TABLE IF NOT EXISTS content (...)

            await db.commit()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """
    اطلاعات یک کاربر را بر اساس شناسه کاربری تلگرام او بازیابی می‌کند.
    اگر کاربر وجود نداشته باشد، None برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        return dict(user) if user else None

async def add_pending_user(user_data: Dict[str, Any]) -> bool:
    """
    یک کاربر جدید با اطلاعات کامل و وضعیت 'pending' را در دیتابیس ثبت می‌کند.
    """
    join_date = datetime.now().isoformat()
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                """
                INSERT INTO users (user_id, first_name, last_name, access_code_hash, wallet_address, nft_info, status, join_date)
                VALUES (:user_id, :first_name, :last_name, :access_code_hash, :wallet_address, :nft_info, 'pending', :join_date)
                """,
                {**user_data, "join_date": join_date}
            )
            await db.commit()
            logger.info(f"New pending user added: {user_data['user_id']}")
            return True
        except aiosqlite.IntegrityError:
            # این خطا زمانی رخ می‌دهد که user_id تکراری باشد
            logger.warning(f"Attempt to add duplicate user: {user_data['user_id']}")
            return False

async def update_user_status(user_id: int, status: str):
    """
    وضعیت یک کاربر را به‌روزرسانی می‌کند (مثلاً: 'approved', 'rejected', 'blocked', 'admin').
    """
    allowed_statuses = ['approved', 'rejected', 'blocked', 'admin', 'pending']
    if status not in allowed_statuses:
        logger.error(f"Attempt to set invalid status '{status}' for user {user_id}")
        return

    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        await db.commit()
    logger.info(f"User {user_id} status updated to '{status}'.")

async def get_users_by_status(status: str) -> List[Dict[str, Any]]:
    """
    لیستی از تمام کاربرانی که وضعیت مشخصی دارند را برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT user_id, first_name, last_name FROM users WHERE status = ?", (status,))
        users = await cursor.fetchall()
        return [dict(user) for user in users]

async def get_all_approved_user_ids() -> List[int]:
    """
    شناسه کاربری تمام کاربران تایید شده و ادمین را برای ارسال پیام گروهی برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE status IN ('approved', 'admin')")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def get_stats() -> Dict[str, int]:
    """
    آمار کلی تعداد کاربران بر اساس وضعیت آن‌ها را محاسبه می‌کند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("""
            SELECT
                status,
                COUNT(*) as count
            FROM users
            GROUP BY status
        """)
        rows = await cursor.fetchall()
        stats = {
            'total': 0, 'approved': 0, 'pending': 0,
            'blocked': 0, 'rejected': 0, 'admin': 0
        }
        for row in rows:
            stats[row[0]] = row[1]
            stats['total'] += row[1]
        return stats
