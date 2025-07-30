import asyncio
import logging
import re
from typing import List, Dict, Any

from aiogram import Bot, Dispatcher, html, F, types
from aiogram.filters import CommandStart, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

# وارد کردن ماژول‌های پروژه
from config import settings
import database as db
import security

# --- تنظیمات اولیه ---

# تنظیم لاگ‌گیری برای دیباگ و مانیتورینگ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(f"{settings.log_dir}/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ساخت نمونه‌های اصلی
bot = Bot(token=settings.bot_token.get_secret_value(), parse_mode="HTML")
dp = Dispatcher()
rate_limiter = security.RateLimiter(
    max_attempts=settings.max_login_attempts,
    timeout_minutes=settings.login_timeout_minutes
)

# --- فیلترها و کلاس‌های کمکی ---

class IsAdmin(BaseFilter):
    """فیلتر برای بررسی اینکه آیا کاربر ادمین است یا خیر"""
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in settings.admin_ids

# --- ماشین وضعیت (FSM) برای ثبت‌نام ---

class RegistrationForm(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_nft = State()
    waiting_for_access_code = State()
    waiting_for_wallet_address = State()

# --- کیبوردهای Inline ---

def get_admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد برای تأیید، رد یا بلاک کردن کاربر توسط ادمین"""
    buttons = [
        [InlineKeyboardButton(text="✅ تأیید", callback_data=f"admin:approve:{user_id}")],
        [InlineKeyboardButton(text="❌ رد", callback_data=f"admin:reject:{user_id}")],
        [InlineKeyboardButton(text="🚫 بلاک", callback_data=f"admin:block:{user_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Handlers ---

# Handler برای دستور /start
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    """نقطه ورود اصلی کاربر به ربات"""
    user_id = message.from_user.id

    # اگر کاربر ادمین است، پیام خوش‌آمدگویی ادمین را نمایش بده
    if user_id in settings.admin_ids:
        await message.answer("سلام ادمین گرامی! به پنل مدیریت خوش آمدید.")
        # اینجا می‌توان دکمه‌های پنل ادمین را نمایش داد
        return

    # بررسی وضعیت کاربر در دیتابیس
    user = await db.get_user(user_id)
    if user:
        if user['status'] == 'approved':
            await message.answer("شما قبلاً تأیید شده‌اید. به بخش آموزش خوش آمدید!")
            # نمایش منوی اصلی آموزشی
        elif user['status'] == 'pending':
            await message.answer("درخواست شما ثبت شده و در انتظار تأیید ادمین است. لطفاً صبور باشید.")
        elif user['status'] in ['rejected', 'blocked']:
            await message.answer("متأسفانه دسترسی شما به ربات امکان‌پذیر نیست.")
    else:
        # شروع فرآیند ثبت‌نام
        await state.set_state(RegistrationForm.waiting_for_full_name)
        await message.answer("به ربات آموزشی خوش آمدید! لطفاً نام و نام خانوادگی خود را (فقط به فارسی) وارد کنید:")

# --- Handlers فرآیند ثبت‌نام ---

@dp.message(RegistrationForm.waiting_for_full_name, F.text)
async def process_full_name(message: Message, state: FSMContext):
    """مرحله اول ثبت‌نام: دریافت نام و نام خانوادگی"""
    # اعتبارسنجی نام فارسی
    persian_pattern = re.compile(r"^[\u0600-\u06FF\s]+$")
    if not persian_pattern.match(message.text):
        await message.answer("لطفاً نام و نام خانوادگی خود را فقط با حروف فارسی وارد کنید.")
        return

    # ذخیره نام در FSM و رفتن به مرحله بعد
    full_name_parts = message.text.split()
    first_name = full_name_parts[0]
    last_name = " ".join(full_name_parts[1:]) if len(full_name_parts) > 1 else ""

    await state.update_data(first_name=first_name, last_name=last_name)
    await state.set_state(RegistrationForm.waiting_for_nft)
    await message.answer("متشکرم. اکنون کد NFT یا تصویر آن را ارسال کنید.")

@dp.message(RegistrationForm.waiting_for_nft, F.text | F.photo)
async def process_nft(message: Message, state: FSMContext):
    """مرحله دوم: دریافت کد یا عکس NFT"""
    if message.photo:
        nft_info = f"photo:{message.photo[-1].file_id}"
    else:
        nft_info = message.text

    await state.update_data(nft_info=nft_info)
    await state.set_state(RegistrationForm.waiting_for_access_code)
    await message.answer("عالی! لطفاً کد دسترسی انحصاری خود را وارد کنید:")

@dp.message(RegistrationForm.waiting_for_access_code, F.text)
async def process_access_code(message: Message, state: FSMContext):
    """مرحله سوم: دریافت و هش کردن کد دسترسی"""
    access_code = message.text
    # در یک پروژه واقعی، این کد باید با لیستی از کدهای معتبر چک شود
    # در اینجا فقط آن را هش می‌کنیم
    hashed_code = security.hash_password(access_code)

    await state.update_data(access_code_hash=hashed_code)
    await state.set_state(RegistrationForm.waiting_for_wallet_address)
    await message.answer("کد شما ثبت شد. در مرحله آخر، آدرس والت خود را وارد کنید:")

@dp.message(RegistrationForm.waiting_for_wallet_address, F.text)
async def process_wallet_address(message: Message, state: FSMContext):
    """مرحله چهارم و نهایی: دریافت آدرس والت و ارسال درخواست به ادمین"""
    await state.update_data(wallet_address=message.text)

    # جمع‌آوری تمام داده‌ها و ثبت در دیتابیس
    user_data = await state.get_data()
    user_data['user_id'] = message.from_user.id

    success = await db.add_pending_user(user_data)
    if not success:
        await message.answer("شما قبلاً درخواست ثبت‌نام داده‌اید. لطفاً منتظر بمانید.")
        await state.clear()
        return

    await message.answer("اطلاعات شما با موفقیت ثبت شد. درخواست شما برای ادمین ارسال گردید.\nپس از تأیید، به شما اطلاع داده خواهد شد.")

    # ارسال نوتیفیکیشن به تمام ادمین‌ها
    admin_notification = f"""
    درخواست ثبت‌نام جدید:

    کاربر: {html.bold(user_data['first_name'] + ' ' + user_data['last_name'])}
    آیدی عددی: {html.code(message.from_user.id)}
    آدرس والت: {html.code(user_data['wallet_address'])}
    اطلاعات NFT: {html.code(user_data['nft_info'])}
    """
    keyboard = get_admin_approval_keyboard(message.from_user.id)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, admin_notification, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Failed to send notification to admin {admin_id}: {e}")

    await state.clear()

# --- Handlers ادمین ---

@dp.callback_query(F.data.startswith("admin:"))
async def admin_action_handler(query: CallbackQuery):
    """پردازش کلیک‌های ادمین روی دکمه‌های تأیید/رد/بلاک"""
    if query.from_user.id not in settings.admin_ids:
        await query.answer("شما دسترسی لازم برای این کار را ندارید.", show_alert=True)
        return

    try:
        _, action, user_id_str = query.data.split(":")
        user_id = int(user_id_str)
    except ValueError:
        await query.answer("خطا در پردازش درخواست.", show_alert=True)
        return

    user = await db.get_user(user_id)
    if not user:
        await query.message.edit_text("این کاربر دیگر در سیستم وجود ندارد.", reply_markup=None)
        await query.answer()
        return

    new_status = ""
    user_message = ""
    if action == "approve":
        new_status = "approved"
        user_message = "✅ درخواست عضویت شما تأیید شد. به ربات خوش آمدید!"
    elif action == "reject":
        new_status = "rejected"
        user_message = "❌ متأسفانه درخواست عضویت شما رد شد."
    elif action == "block":
        new_status = "blocked"
        user_message = "🚫 دسترسی شما به این ربات مسدود شد."

    if new_status:
        await db.update_user_status(user_id, new_status)

        # ویرایش پیام ادمین و حذف دکمه‌ها
        admin_feedback = f"کاربر با شناسه {user_id} با موفقیت {new_status} شد."
        await query.message.edit_text(query.message.text + f"\n\n--- \n<b>نتیجه: {admin_feedback}</b>", reply_markup=None)

        # ارسال پیام به کاربر
        try:
            await bot.send_message(user_id, user_message)
        except Exception as e:
            logger.error(f"Failed to send status update to user {user_id}: {e}")
            await query.answer(f"کاربر {new_status} شد، اما ارسال پیام به او ناموفق بود.", show_alert=True)
        else:
            await query.answer(f"کاربر {new_status} شد و به او اطلاع داده شد.")
    else:
        await query.answer("عملیات نامشخص.", show_alert=True)


# --- تابع اصلی برای اجرای ربات ---

async def main():
    """تابع اصلی برای راه‌اندازی و اجرای ربات"""
    logger.info("Initializing database...")
    await db.init_db()

    logger.info("Starting bot...")
    # حذف آپدیت‌های در صف مانده (برای جلوگیری از اجرای دستورات قدیمی)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")
