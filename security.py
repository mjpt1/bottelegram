import time
import bcrypt
from collections import defaultdict
from datetime import timedelta
from typing import DefaultDict, List

# --- توابع کار با رمز عبور ---

def hash_password(password: str) -> str:
    """
    یک رمز عبور رشته‌ای را دریافت کرده و با استفاده از bcrypt آن را هش می‌کند.

    Args:
        password (str): رمز عبور خام.

    Returns:
        str: رشته هش شده و آماده برای ذخیره در دیتابیس.
    """
    # برای هش کردن، رشته‌ها باید به بایت تبدیل شوند
    password_bytes = password.encode('utf-8')
    # تولید salt و هش کردن رمز
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    # برگرداندن نسخه رشته‌ای و قابل ذخیره‌سازی
    return hashed_bytes.decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    """
    بررسی می‌کند که آیا رمز عبور وارد شده با نسخه هش شده آن مطابقت دارد یا خیر.

    Args:
        password (str): رمز عبور خامی که کاربر وارد کرده.
        hashed_password (str): نسخه هش شده‌ای که در دیتابیس ذخیره شده.

    Returns:
        bool: اگر رمزها مطابقت داشتند True، در غیر این صورت False.
    """
    try:
        password_bytes = password.encode('utf-8')
        hashed_password_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_password_bytes)
    except (ValueError, TypeError):
        # اگر فرمت هش ذخیره شده نامعتبر باشد، برای جلوگیری از کرش برنامه False برمی‌گردانیم
        return False


# --- کلاس محدودکننده نرخ درخواست (Rate Limiter) ---

class RateLimiter:
    """
    یک کلاس ساده برای محدود کردن تعداد درخواست‌های یک کاربر در یک بازه زمانی مشخص.
    این کلاس از یک دیکشنری در حافظه برای نگهداری زمان تلاش‌های هر کاربر استفاده می‌کند.
    """
    def __init__(self, max_attempts: int, timeout_minutes: int):
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_minutes * 60
        # ساختار دیکشنری: {user_id: [timestamp1, timestamp2, ...]}
        self._attempts: DefaultDict[int, List[float]] = defaultdict(list)

    def _cleanup_old_attempts(self, user_id: int):
        """تلاش‌های قدیمی که از بازه زمانی تعریف‌شده خارج شده‌اند را پاک می‌کند."""
        now = time.time()
        if user_id in self._attempts:
            valid_attempts = [t for t in self._attempts[user_id] if now - t < self.timeout_seconds]
            if valid_attempts:
                self._attempts[user_id] = valid_attempts
            else:
                del self._attempts[user_id]

    def check(self, user_id: int) -> bool:
        """
        بررسی می‌کند که آیا کاربر مجاز به تلاش مجدد است یا خیر.
        اگر مجاز بود، تلاش فعلی را ثبت کرده و True برمی‌گرداند.
        در غیر این صورت، False برمی‌گرداند.
        """
        self._cleanup_old_attempts(user_id)

        if len(self._attempts.get(user_id, [])) >= self.max_attempts:
            return False

        self._attempts[user_id].append(time.time())
        return True

    def get_wait_time(self, user_id: int) -> timedelta:
        """
        زمان باقی‌مانده تا کاربر بتواند دوباره تلاش کند را محاسبه می‌کند.
        اگر کاربر محدود نشده باشد، زمان صفر را برمی‌گرداند.
        """
        self._cleanup_old_attempts(user_id)
        attempts = self._attempts.get(user_id, [])
        if len(attempts) >= self.max_attempts:
            first_attempt_time = attempts[0]
            time_to_wait = (first_attempt_time + self.timeout_seconds) - time.time()
            if time_to_wait > 0:
                return timedelta(seconds=int(time_to_wait))
        return timedelta(seconds=0)
