from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    """
    مدل تنظیمات Pydantic که متغیرها را از فایل .env می‌خواند.
    این کلاس به صورت متمرکز تمام تنظیمات پروژه را مدیریت می‌کند.
    """

    # --- تنظیمات اصلی ربات ---
    # توکن ربات که از BotFather تلگرام دریافت می‌شود
    bot_token: SecretStr = Field(..., alias='BOT_TOKEN')

    # نام ربات برای نمایش در پیام‌ها
    bot_name: str = Field("Diamonds.land", alias='BOT_NAME')

    # --- تنظیمات ادمین ---
    # لیست شناسه‌های کاربری ادمین‌ها (با کاما از هم جدا شوند)
    # مثال: ADMIN_IDS="12345,67890"
    admin_ids: List[int] = Field(..., alias='ADMIN_IDS')

    # --- مسیرهای فایل‌ها و دایرکتوری‌ها ---
    database_path: str = Field("data/bot.db", alias='DATABASE_PATH')
    content_dir: str = Field("content", alias='CONTENT_DIR')
    log_dir: str = Field("logs", alias='LOG_DIR')

    # --- تنظیمات امنیتی ---
    # حداکثر تعداد تلاش برای ورود قبل از قفل شدن
    max_login_attempts: int = Field(5, alias='MAX_LOGIN_ATTEMPTS')

    # مدت زمان قفل شدن کاربر به دقیقه پس از تلاش‌های ناموفق
    login_timeout_minutes: int = Field(10, alias='LOGIN_TIMEOUT_MINUTES')

    # --- تنظیمات عملکردی ---
    auto_approve: bool = Field(False, alias='AUTO_APPROVE')
    debug: bool = Field(False, alias='DEBUG')
    maintenance_mode: bool = Field(False, alias='MAINTENANCE_MODE')

    model_config = SettingsConfigDict(
        env_file='.env',              # نام فایل تنظیمات
        env_file_encoding='utf-8',    # انکودینگ فایل
        extra='ignore'                # نادیده گرفتن متغیرهای اضافی در فایل .env
    )

# ساخت یک نمونه (instance) از کلاس تنظیمات برای استفاده در سایر بخش‌های پروژه
# در هر فایلی که نیاز به تنظیمات داشتید، فقط کافیست بنویسید: from config import settings
settings = Settings()
