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
            await db.execute("PRAGMA foreign_keys = ON;")

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

            # جدول دسته‌بندی‌ها
            await db.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    parent_id INTEGER,
                    FOREIGN KEY (parent_id) REFERENCES categories (id) ON DELETE CASCADE
                )
            """)

            # جدول محتوا
            await db.execute("""
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    file_id TEXT NOT NULL,
                    file_type TEXT NOT NULL, -- e.g., 'photo', 'video', 'document'
                    category_id INTEGER NOT NULL,
                    is_premium INTEGER NOT NULL DEFAULT 0, -- 0 for false, 1 for true
                    access_password_hash TEXT,
                    added_date TEXT NOT NULL,
                    FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE CASCADE
                )
            """)

            # جدول دسترسی کاربر به محتوای خاص
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_content_access (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content_id INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                    FOREIGN KEY (content_id) REFERENCES content (id) ON DELETE CASCADE,
                    UNIQUE(user_id, content_id)
                )
            """)

            # جدول تیکت‌های پشتیبانی
            await db.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open', -- 'open', 'closed'
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                )
            """)

            # جدول پیام‌های پشتیبانی
            await db.execute("""
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL, -- Can be a user or an admin
                    message_text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (ticket_id) REFERENCES support_tickets (id) ON DELETE CASCADE
                )
            """)

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

async def delete_content(content_id: int) -> bool:
    """
    یک محتوا را از دیتابیس حذف می‌کند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("DELETE FROM content WHERE id = ?", (content_id,))
        await db.commit()
        # rowcount will be 1 if a row was deleted, 0 otherwise.
        return cursor.rowcount > 0

async def update_content_field(content_id: int, field: str, value: Any) -> bool:
    """
    یک فیلد خاص از یک محتوا را به‌روزرسانی می‌کند.
    """
    # A simple whitelist of editable fields to prevent SQL injection
    allowed_fields = ["title", "description"]
    if field not in allowed_fields:
        logger.error(f"Attempt to update a non-allowed field: {field}")
        return False

    sql = f"UPDATE content SET {field} = ? WHERE id = ?"
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(sql, (value, content_id))
        await db.commit()
        return cursor.rowcount > 0

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

# --- Category Management Functions ---

async def add_category(name: str, parent_id: Optional[int] = None) -> Optional[int]:
    """
    یک دسته‌بندی یا زیرمجموعه جدید اضافه می‌کند.
    ID دسته‌بندی جدید را برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            cursor = await db.execute(
                "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
                (name, parent_id)
            )
            await db.commit()
            return cursor.lastrowid
        except aiosqlite.IntegrityError:
            logger.warning(f"Category '{name}' already exists.")
            return None

async def get_categories(parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    لیست دسته‌بندی‌ها (یا زیرمجموعه‌های یک دسته‌بندی) را برمی‌گرداند.
    """
    sql = "SELECT * FROM categories WHERE parent_id IS ?" if parent_id is not None else "SELECT * FROM categories WHERE parent_id IS NULL"
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(sql, (parent_id,) if parent_id is not None else ())
        categories = await cursor.fetchall()
        return [dict(cat) for cat in categories]

async def delete_category(category_id: int) -> bool:
    """
    یک دسته‌بندی را حذف می‌کند. به لطف ON DELETE CASCADE، تمام زیرمجموعه‌ها و محتوای آن نیز حذف می‌شوند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        await db.commit()
        return cursor.rowcount > 0

async def update_category_name(category_id: int, new_name: str) -> bool:
    """
    نام یک دسته‌بندی را به‌روزرسانی می‌کند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            cursor = await db.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, category_id))
            await db.commit()
            return cursor.rowcount > 0
        except aiosqlite.IntegrityError:
            logger.warning(f"Category name '{new_name}' likely already exists.")
            return False

async def get_category_parent(category_id: int) -> Optional[int]:
    """
     شناسه والد یک دسته‌بندی را برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("SELECT parent_id FROM categories WHERE id = ?", (category_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

# --- Content Management Functions ---

async def add_content(data: Dict[str, Any]) -> Optional[int]:
    """
    یک محتوای جدید به دیتابیس اضافه می‌کند.
    """
    data['added_date'] = datetime.now().isoformat()
    # اطمینان از اینکه کلیدهای اختیاری وجود دارند
    data.setdefault('description', None)
    data.setdefault('is_premium', 0)
    data.setdefault('access_password_hash', None)

    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO content (title, description, file_id, file_type, category_id, is_premium, access_password_hash, added_date)
            VALUES (:title, :description, :file_id, :file_type, :category_id, :is_premium, :access_password_hash, :added_date)
            """,
            data
        )
        await db.commit()
        logger.info(f"Content '{data['title']}' added with ID: {cursor.lastrowid}")
        return cursor.lastrowid

async def get_content_by_category(category_id: int) -> List[Dict[str, Any]]:
    """
    تمام محتواهای یک دسته‌بندی خاص را برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT id, title, file_type FROM content WHERE category_id = ?", (category_id,))
        content_list = await cursor.fetchall()
        return [dict(item) for item in content_list]

async def get_content_details(content_id: int) -> Optional[Dict[str, Any]]:
    """
    جزئیات کامل یک محتوا را بر اساس ID آن برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM content WHERE id = ?", (content_id,))
        content = await cursor.fetchone()
        return dict(content) if content else None

async def assign_content_to_user(user_id: int, content_id: int) -> bool:
    """
    دسترسی یک محتوای خاص را به یک کاربر خاص می‌دهد.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        try:
            await db.execute(
                "INSERT INTO user_content_access (user_id, content_id) VALUES (?, ?)",
                (user_id, content_id)
            )
            await db.commit()
            logger.info(f"Assigned content {content_id} to user {user_id}.")
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Content {content_id} is already assigned to user {user_id}.")
            return False

async def check_user_content_access(user_id: int, content_id: int) -> bool:
    """
    بررسی می‌کند که آیا کاربر به محتوای خاصی دسترسی دارد یا خیر.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute(
            "SELECT 1 FROM user_content_access WHERE user_id = ? AND content_id = ?",
            (user_id, content_id)
        )
        return await cursor.fetchone() is not None

# --- Support Ticket Functions ---

async def create_support_ticket(user_id: int, first_message: str) -> int:
    """
    یک تیکت پشتیبانی جدید برای کاربر ایجاد کرده و اولین پیام را ثبت می‌کند.
    ID تیکت جدید را برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        now = datetime.now().isoformat()
        # Create ticket
        cursor = await db.execute(
            "INSERT INTO support_tickets (user_id, status, created_at) VALUES (?, 'open', ?)",
            (user_id, now)
        )
        ticket_id = cursor.lastrowid
        # Add first message
        await db.execute(
            "INSERT INTO support_messages (ticket_id, sender_id, message_text, timestamp) VALUES (?, ?, ?, ?)",
            (ticket_id, user_id, first_message, now)
        )
        await db.commit()
        logger.info(f"Created new support ticket with ID {ticket_id} for user {user_id}.")
        return ticket_id

async def add_support_message(ticket_id: int, sender_id: int, message_text: str):
    """
    یک پیام جدید به تیکت پشتیبانی اضافه می‌کند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute(
            "INSERT INTO support_messages (ticket_id, sender_id, message_text, timestamp) VALUES (?, ?, ?, ?)",
            (ticket_id, sender_id, message_text, datetime.now().isoformat())
        )
        await db.commit()
        logger.info(f"Added message to ticket {ticket_id} from sender {sender_id}.")

async def get_open_tickets() -> List[Dict[str, Any]]:
    """
    لیست تمام تیکت‌های باز را به همراه آخرین پیامشان برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT
                t.id,
                t.user_id,
                u.first_name,
                u.last_name,
                (SELECT message_text FROM support_messages WHERE ticket_id = t.id ORDER BY timestamp ASC LIMIT 1) as first_message
            FROM support_tickets t
            JOIN users u ON t.user_id = u.user_id
            WHERE t.status = 'open'
        """
        cursor = await db.execute(query)
        tickets = await cursor.fetchall()
        return [dict(ticket) for ticket in tickets]

async def get_ticket_owner(ticket_id: int) -> Optional[int]:
    """
    صاحب (کاربر) یک تیکت را پیدا می‌کند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        cursor = await db.execute("SELECT user_id FROM support_tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def close_ticket(ticket_id: int):
    """
    وضعیت یک تیکت را به 'closed' تغییر می‌دهد.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        await db.execute("UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
        await db.commit()
        logger.info(f"Closed ticket {ticket_id}.")

async def get_ticket_messages(ticket_id: int) -> List[Dict[str, Any]]:
    """
    تمام پیام‌های یک تیکت خاص را برمی‌گرداند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT sender_id, message_text, timestamp FROM support_messages WHERE ticket_id = ? ORDER BY timestamp ASC",
            (ticket_id,)
        )
        messages = await cursor.fetchall()
        return [dict(msg) for msg in messages]

async def search_users(query: str) -> List[Dict[str, Any]]:
    """
    کاربران را بر اساس شناسه کاربری یا نام جستجو می‌کند.
    """
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row

        # اگر کوئری یک عدد باشد، آن را به عنوان user_id جستجو کن
        if query.isdigit():
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (int(query),))
        else:
            # در غیر این صورت، نام و نام خانوادگی را جستجو کن
            search_query = f"%{query}%"
            cursor = await db.execute(
                "SELECT * FROM users WHERE first_name LIKE ? OR last_name LIKE ?",
                (search_query, search_query)
            )

        users = await cursor.fetchall()
        return [dict(user) for user in users]
