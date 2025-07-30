import asyncio
import logging
import re
from typing import List, Dict, Any

from aiogram import Bot, Dispatcher, html, F, types
from aiogram.filters import CommandStart, BaseFilter, Command
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

class PromoteUserForm(StatesGroup):
    waiting_for_user_id = State()

class AddContentForm(StatesGroup):
    waiting_for_category = State()
    waiting_for_subcategory = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_file = State()
    waiting_for_premium_choice = State()
    waiting_for_password = State()
    waiting_for_confirmation = State()

class AddCategoryForm(StatesGroup):
    waiting_for_parent = State() # Used for subcategories
    waiting_for_name = State()

class SupportForm(StatesGroup):
    waiting_for_message = State()

class ReplyForm(StatesGroup):
    waiting_for_reply = State()

class BroadcastForm(StatesGroup):
    waiting_for_message = State()

class PremiumContentForm(StatesGroup):
    waiting_for_password = State()

# --- کیبوردهای Inline ---

def get_admin_approval_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """کیبورد برای تأیید، رد یا بلاک کردن کاربر توسط ادمین"""
    buttons = [
        [InlineKeyboardButton(text="✅ تأیید", callback_data=f"admin:approve:{user_id}")],
        [InlineKeyboardButton(text="❌ رد", callback_data=f"admin:reject:{user_id}")],
        [InlineKeyboardButton(text="🚫 بلاک", callback_data=f"admin:block:{user_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """کیبورد اصلی پنل مدیریت ادمین"""
    buttons = [
        [
            InlineKeyboardButton(text="👤 مدیریت کاربران", callback_data="admin:users:menu"),
            InlineKeyboardButton(text="📚 مدیریت محتوا", callback_data="admin:content:menu")
        ],
        [
            InlineKeyboardButton(text="💬 ارتباط با کاربران", callback_data="admin:comms:menu"),
            InlineKeyboardButton(text="📊 آمار ربات", callback_data="admin:stats")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_users_keyboard() -> InlineKeyboardMarkup:
    """کیبورد بخش مدیریت کاربران"""
    buttons = [
        [
            InlineKeyboardButton(text="⏳ کاربران در انتظار", callback_data="admin:users:list:pending"),
            InlineKeyboardButton(text="🚫 کاربران بلاک‌شده", callback_data="admin:users:list:blocked")
        ],
        [
            InlineKeyboardButton(text="👑 ارتقا به ادمین", callback_data="admin:users:promote")
        ],
        [
            InlineKeyboardButton(text="⬅️ بازگشت به پنل", callback_data="admin:panel:main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_content_keyboard() -> InlineKeyboardMarkup:
    """کیبورد بخش مدیریت محتوا"""
    buttons = [
        [
            InlineKeyboardButton(text="➕ افزودن محتوا", callback_data="admin:content:add:start"),
            InlineKeyboardButton(text="✏️ ویرایش/حذف محتوا", callback_data="admin:content:edit:start")
        ],
        [
            InlineKeyboardButton(text="🗂 مدیریت دسته‌بندی‌ها", callback_data="admin:categories:menu")
        ],
        [
            InlineKeyboardButton(text="⬅️ بازگشت به پنل", callback_data="admin:panel:main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_categories_keyboard() -> InlineKeyboardMarkup:
    """کیبورد بخش مدیریت دسته‌بندی‌ها."""
    buttons = [
        [
            InlineKeyboardButton(text="➕ افزودن دسته‌بندی اصلی", callback_data="admin:categories:add_main"),
        ],
        [
            InlineKeyboardButton(text="➕ افزودن زیرمجموعه", callback_data="admin:categories:add_sub"),
        ],
        [
            InlineKeyboardButton(text="⬅️ بازگشت به مدیریت محتوا", callback_data="admin:content:menu")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_comms_keyboard() -> InlineKeyboardMarkup:
    """کیبورد بخش ارتباط با کاربران."""
    buttons = [
        [
            InlineKeyboardButton(text="📨 ارسال پیام گروهی (Broadcast)", callback_data="admin:comms:broadcast"),
        ],
        [
            InlineKeyboardButton(text="🎫 مشاهده تیکت‌های پشتیبانی", callback_data="admin:support:list_open"),
        ],
        [
            InlineKeyboardButton(text="⬅️ بازگشت به پنل", callback_data="admin:panel:main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Handlers ---

# Handler برای دستور /start
@dp.message(CommandStart())
async def command_start_handler(message: Message, state: FSMContext):
    """نقطه ورود اصلی کاربر به ربات"""
    user_id = message.from_user.id

    # اگر کاربر ادمین است، پنل مدیریت را نمایش بده
    if user_id in settings.admin_ids:
        await admin_panel_handler(message)
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

@dp.message(Command("panel"), IsAdmin())
async def admin_panel_handler(message: Message):
    """نمایش پنل اصلی مدیریت."""
    await message.answer("به پنل مدیریت خوش آمدید. لطفاً یک گزینه را انتخاب کنید:", reply_markup=get_admin_panel_keyboard())

@dp.callback_query(F.data == "admin:panel:main")
async def admin_panel_callback_handler(query: CallbackQuery):
    """CB-Handler: نمایش پنل اصلی مدیریت (برای دکمه‌های بازگشت)."""
    await query.answer()
    await query.message.edit_text(
        "به پنل مدیریت خوش آمدید. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_admin_panel_keyboard()
    )

@dp.callback_query(F.data == "admin:stats", IsAdmin())
async def admin_stats_handler(query: CallbackQuery):
    """CB-Handler: نمایش آمار ربات."""
    await query.answer("در حال محاسبه آمار...")
    stats = await db.get_stats()

    # برای نمایش بهتر، هر وضعیت را در خط جداگانه با ایموجی نمایش می‌دهیم
    stats_text = f"""
📊 **آمار کلی ربات**

- 👤 **تعداد کل کاربران ثبت‌شده:** {stats.get('total', 0)}
- ✅ **تأیید شده:** {stats.get('approved', 0)}
- ⏳ **در انتظار تأیید:** {stats.get('pending', 0)}
- 🚫 **بلاک شده:** {stats.get('blocked', 0)}
- ❌ **رد شده:** {stats.get('rejected', 0)}
- 👑 **ادمین:** {stats.get('admin', 0)}
"""

    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به پنل", callback_data="admin:panel:main")]
    ])

    await query.message.edit_text(stats_text, reply_markup=back_button)


@dp.callback_query(F.data == "admin:users:menu")
async def admin_users_menu_handler(query: CallbackQuery):
    """CB-Handler: نمایش منوی مدیریت کاربران."""
    await query.answer()
    await query.message.edit_text(
        "بخش مدیریت کاربران. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_admin_users_keyboard()
    )

@dp.callback_query(F.data.startswith("admin:users:list:"))
async def admin_list_users_handler(query: CallbackQuery):
    """CB-Handler: نمایش لیست کاربران بر اساس وضعیت."""
    status = query.data.split(":")[-1]
    await query.answer(f"در حال دریافت لیست کاربران {status}...")

    users = await db.get_users_by_status(status)

    if not users:
        text = f"هیچ کاربری با وضعیت '{status}' یافت نشد."
    else:
        text = f"لیست کاربران با وضعیت '{status}':\n\n"
        for user in users:
            text += f"- {html.bold(user['first_name'])} {html.bold(user['last_name'])} (ID: {html.code(user['user_id'])})\n"

    back_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به مدیریت کاربران", callback_data="admin:users:menu")]
    ])
    await query.message.edit_text(text, reply_markup=back_button)


@dp.callback_query(F.data == "admin:users:promote")
async def admin_promote_user_start(query: CallbackQuery, state: FSMContext):
    """شروع فرآیند ارتقا کاربر به ادمین."""
    await query.answer()
    await state.set_state(PromoteUserForm.waiting_for_user_id)
    await query.message.edit_text("لطفاً شناسه عددی کاربری که می‌خواهید به ادمین ارتقا دهید را وارد کنید:")

@dp.message(PromoteUserForm.waiting_for_user_id, F.text)
async def process_promote_user_id(message: Message, state: FSMContext):
    """پردازش شناسه کاربر برای ارتقا."""
    if not message.text.isdigit():
        await message.answer("شناسه کاربری باید یک عدد باشد. لطفاً دوباره تلاش کنید.")
        return

    user_id = int(message.text)
    user = await db.get_user(user_id)

    if not user:
        await message.answer(f"کاربری با شناسه {user_id} یافت نشد. لطفاً شناسه را بررسی کرده و مجدداً ارسال کنید.")
        return

    if user['status'] == 'admin':
        await message.answer(f"کاربر {user_id} در حال حاضر ادمین است.")
        await state.clear()
        # نمایش مجدد پنل
        await admin_panel_handler(message)
        return

    # ارتقا کاربر
    await db.update_user_status(user_id, 'admin')
    # افزودن به لیست ادمین‌های فعال در کانفیگ (مهم)
    settings.admin_ids.append(user_id)

    await state.clear()
    await message.answer(f"✅ کاربر {html.bold(user['first_name'])} (ID: {html.code(user_id)}) با موفقیت به سطح ادمین ارتقا یافت.")

    # ارسال پیام به کاربر جدید ادمین شده
    try:
        await bot.send_message(user_id, "👑 شما توسط ادمین اصلی به سطح ادمین ارتقا یافتید. لطفاً از دستور /panel برای دسترسی به پنل مدیریت استفاده کنید.")
    except Exception as e:
        logger.error(f"Failed to notify new admin {user_id}: {e}")

    # نمایش مجدد پنل
    await admin_panel_handler(message)


@dp.callback_query(F.data == "admin:content:menu")
async def admin_content_menu_handler(query: CallbackQuery):
    """CB-Handler: نمایش منوی مدیریت محتوا."""
    await query.answer()
    await query.message.edit_text(
        "بخش مدیریت محتوا. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_admin_content_keyboard()
    )

# --- Add Content FSM Handlers ---

@dp.callback_query(F.data == "admin:content:add:start")
async def content_add_start(query: CallbackQuery, state: FSMContext):
    """شروع فرآیند افزودن محتوای جدید: انتخاب دسته‌بندی اصلی."""
    await query.answer()
    categories = await db.get_categories()
    if not categories:
        await query.message.edit_text(
            "هیچ دسته‌بندی‌ای یافت نشد. لطفاً ابتدا از بخش «مدیریت دسته‌بندی‌ها» یک دسته‌بندی ایجاد کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin:content:menu")]])
        )
        return

    buttons = [
        [InlineKeyboardButton(text=cat['name'], callback_data=f"content:add:cat:{cat['id']}")] for cat in categories
    ]
    buttons.append([InlineKeyboardButton(text="❌ لغو عملیات", callback_data="admin:cancel_fsm")])

    await state.set_state(AddContentForm.waiting_for_category)
    await query.message.edit_text(
        "1/6: لطفاً دسته‌بندی اصلی محتوا را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(F.data == "admin:cancel_fsm")
async def cancel_fsm_handler(query: CallbackQuery, state: FSMContext):
    """لغو عملیات FSM و بازگشت به پنل اصلی."""
    await query.answer("عملیات لغو شد.")
    await state.clear()
    await query.message.delete()
    await admin_panel_handler(query.message)

@dp.callback_query(AddContentForm.waiting_for_category, F.data.startswith("content:add:cat:"))
async def content_add_category_chosen(query: CallbackQuery, state: FSMContext):
    """مرحله 1.5: انتخاب زیرمجموعه (در صورت وجود)."""
    await query.answer()
    category_id = int(query.data.split(":")[-1])
    await state.update_data(category_id=category_id)

    subcategories = await db.get_categories(parent_id=category_id)
    if not subcategories:
        # اگر زیرمجموعه‌ای وجود نداشت، مستقیم به مرحله بعد برو
        await state.set_state(AddContentForm.waiting_for_title)
        await query.message.edit_text("2/6: لطفاً عنوان محتوا را وارد کنید:")
        return

    buttons = [
        [InlineKeyboardButton(text=cat['name'], callback_data=f"content:add:subcat:{cat['id']}")] for cat in subcategories
    ]
    buttons.append([InlineKeyboardButton(text="Skip", callback_data="content:add:subcat:0")]) # 0 means no subcategory
    buttons.append([InlineKeyboardButton(text="❌ لغو عملیات", callback_data="admin:cancel_fsm")])

    await state.set_state(AddContentForm.waiting_for_subcategory)
    await query.message.edit_text(
        "اختیاری: لطفاً زیرمجموعه را انتخاب کنید یا از این مرحله بگذرید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(AddContentForm.waiting_for_subcategory, F.data.startswith("content:add:subcat:"))
async def content_add_subcategory_chosen(query: CallbackQuery, state: FSMContext):
    """ادامه فرآیند پس از انتخاب (یا عدم انتخاب) زیرمجموعه."""
    await query.answer()
    subcategory_id = int(query.data.split(":")[-1])
    if subcategory_id != 0:
        await state.update_data(category_id=subcategory_id) # Override the main category with the subcategory

    await state.set_state(AddContentForm.waiting_for_title)
    await query.message.edit_text("2/6: لطفاً عنوان محتوا را وارد کنید:")

@dp.message(AddContentForm.waiting_for_title, F.text)
async def content_add_title(message: Message, state: FSMContext):
    """مرحله 2: دریافت عنوان."""
    await state.update_data(title=message.text)
    await state.set_state(AddContentForm.waiting_for_description)
    await message.answer("3/6: لطفاً توضیحات محتوا را وارد کنید (می‌توانید بنویسید 'ندارد'):")

@dp.message(AddContentForm.waiting_for_description, F.text)
async def content_add_description(message: Message, state: FSMContext):
    """مرحله 3: دریافت توضیحات."""
    await state.update_data(description=message.text if message.text.lower() != 'ندارد' else None)
    await state.set_state(AddContentForm.waiting_for_file)
    await message.answer("4/6: لطفاً فایل محتوا (عکس، ویدیو یا داکیومنت) را ارسال کنید:")

@dp.message(AddContentForm.waiting_for_file, F.photo | F.video | F.document)
async def content_add_file(message: Message, state: FSMContext):
    """مرحله 4: دریافت فایل."""
    file_id = ""
    file_type = ""
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        file_type = 'video'
    elif message.document:
        file_id = message.document.file_id
        file_type = 'document'

    await state.update_data(file_id=file_id, file_type=file_type)
    await state.set_state(AddContentForm.waiting_for_premium_choice)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="بله", callback_data="content:add:premium:yes"),
            InlineKeyboardButton(text="خیر", callback_data="content:add:premium:no")
        ],
        [InlineKeyboardButton(text="❌ لغو عملیات", callback_data="admin:cancel_fsm")]
    ])
    await message.answer("5/6: آیا این محتوا رمزدار (Premium) باشد؟", reply_markup=keyboard)

@dp.callback_query(AddContentForm.waiting_for_premium_choice, F.data.startswith("content:add:premium:"))
async def content_add_premium_choice(query: CallbackQuery, state: FSMContext):
    """مرحله 5: انتخاب رمزدار بودن و دریافت رمز در صورت نیاز."""
    await query.answer()
    choice = query.data.split(":")[-1]
    if choice == 'yes':
        await state.update_data(is_premium=1)
        await state.set_state(AddContentForm.waiting_for_password)
        await query.message.edit_text("لطفاً رمز عبور برای این محتوا را وارد کنید:")
    else:
        await state.update_data(is_premium=0, access_password_hash=None)
        await state.set_state(AddContentForm.waiting_for_confirmation)
        # مستقیم به مرحله تایید برو
        await content_add_show_confirmation(query.message, state)


@dp.message(AddContentForm.waiting_for_password, F.text)
async def content_add_password(message: Message, state: FSMContext):
    """دریافت رمز و رفتن به مرحله تایید نهایی."""
    password_hash = security.hash_password(message.text)
    await state.update_data(access_password_hash=password_hash)
    await state.set_state(AddContentForm.waiting_for_confirmation)
    await content_add_show_confirmation(message, state)

async def content_add_show_confirmation(message: Message, state: FSMContext):
    """نمایش خلاصه اطلاعات برای تایید نهایی."""
    data = await state.get_data()

    text = f"""
    **مرور و تأیید نهایی**

    - **عنوان:** {data['title']}
    - **توضیحات:** {data.get('description', 'ندارد')}
    - **نوع فایل:** {data['file_type']}
    - **رمزدار:** {'بله' if data['is_premium'] else 'خیر'}

    لطفاً اطلاعات بالا را تأیید می‌کنید؟
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تأیید و ذخیره", callback_data="content:add:confirm")],
        [InlineKeyboardButton(text="❌ لغو", callback_data="admin:cancel_fsm")]
    ])
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(AddContentForm.waiting_for_confirmation, F.data == "content:add:confirm")
async def content_add_confirm(query: CallbackQuery, state: FSMContext):
    """ذخیره نهایی محتوا در دیتابیس."""
    await query.answer("در حال ذخیره...")
    content_data = await state.get_data()

    content_id = await db.add_content(content_data)

    if content_id:
        await query.message.edit_text(f"✅ محتوای '{content_data['title']}' با موفقیت اضافه شد.")
    else:
        await query.message.edit_text("❌ خطایی در افزودن محتوا رخ داد. لطفاً دوباره تلاش کنید.")

    await state.clear()
    # نمایش پنل اصلی
    await admin_panel_handler(query.message)


# --- Category Management Handlers ---

@dp.callback_query(F.data == "admin:categories:menu")
async def admin_categories_menu_handler(query: CallbackQuery):
    """CB-Handler: نمایش منوی مدیریت دسته‌بندی‌ها."""
    await query.answer()
    await query.message.edit_text(
        "بخش مدیریت دسته‌بندی‌ها. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_admin_categories_keyboard()
    )

@dp.callback_query(F.data == "admin:categories:add_main")
async def category_add_main_start(query: CallbackQuery, state: FSMContext):
    """شروع فرآیند افزودن دسته‌بندی اصلی."""
    await query.answer()
    await state.set_state(AddCategoryForm.waiting_for_name)
    await state.update_data(parent_id=None)
    await query.message.edit_text("لطفاً نام دسته‌بندی اصلی جدید را وارد کنید:")

@dp.callback_query(F.data == "admin:categories:add_sub")
async def category_add_sub_start(query: CallbackQuery, state: FSMContext):
    """شروع فرآیند افزودن زیرمجموعه: انتخاب دسته‌بندی والد."""
    await query.answer()
    categories = await db.get_categories() # فقط دسته‌بندی‌های اصلی
    if not categories:
        await query.message.edit_text(
            "هیچ دسته‌بندی اصلی‌ای برای ساخت زیرمجموعه یافت نشد. لطفاً ابتدا یک دسته‌بندی اصلی ایجاد کنید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin:categories:menu")]])
        )
        return

    buttons = [[InlineKeyboardButton(text=cat['name'], callback_data=f"category:add:parent:{cat['id']}")] for cat in categories]
    buttons.append([InlineKeyboardButton(text="❌ لغو", callback_data="admin:cancel_fsm")])

    await state.set_state(AddCategoryForm.waiting_for_parent)
    await query.message.edit_text(
        "لطفاً دسته‌بندی والد برای زیرمجموعه جدید را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@dp.callback_query(AddCategoryForm.waiting_for_parent, F.data.startswith("category:add:parent:"))
async def category_add_parent_chosen(query: CallbackQuery, state: FSMContext):
    """والد انتخاب شد، اکنون نام زیرمجموعه را بپرس."""
    await query.answer()
    parent_id = int(query.data.split(":")[-1])
    await state.update_data(parent_id=parent_id)
    await state.set_state(AddCategoryForm.waiting_for_name)
    await query.message.edit_text("لطفاً نام زیرمجموعه جدید را وارد کنید:")

@dp.message(AddCategoryForm.waiting_for_name, F.text)
async def category_add_name_process(message: Message, state: FSMContext):
    """نام دسته‌بندی/زیرمجموعه را پردازش و ذخیره می‌کند."""
    data = await state.get_data()
    parent_id = data.get('parent_id')
    category_name = message.text

    category_id = await db.add_category(name=category_name, parent_id=parent_id)

    if category_id:
        if parent_id:
            await message.answer(f"✅ زیرمجموعه '{category_name}' با موفقیت ایجاد شد.")
        else:
            await message.answer(f"✅ دسته‌بندی اصلی '{category_name}' با موفقیت ایجاد شد.")
    else:
        await message.answer(f"❌ خطایی در ایجاد دسته‌بندی رخ داد (احتمالاً نام تکراری است).")

    await state.clear()
    await message.answer(
        "بازگشت به منوی مدیریت محتوا...",
    )
    await admin_content_menu_handler(message)


# --- Support System Handlers ---

class IsApprovedUser(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        user = await db.get_user(message.from_user.id)
        return user and user['status'] == 'approved'

# --- User-facing Content Browsing Handlers ---

@dp.message(Command("menu"), IsApprovedUser())
async def user_menu_start(message: Message):
    """نمایش منوی اصلی محتوا به کاربر."""
    await browse_categories_handler(message)

async def browse_categories_handler(message: Message, parent_id: int = None, is_callback: bool = False):
    """یک تابع کمکی برای نمایش دسته‌بندی‌ها یا زیرمجموعه‌ها."""
    categories = await db.get_categories(parent_id=parent_id)

    if not categories and parent_id is None:
        text = "در حال حاضر هیچ محتوایی برای نمایش وجود ندارد."
        await message.answer(text)
        return

    buttons = []
    if categories:
        # اگر دسته‌بندی وجود دارد، دکمه‌های آنها را بساز
        for cat in categories:
            buttons.append([InlineKeyboardButton(text=f"📁 {cat['name']}", callback_data=f"user:browse:cat:{cat['id']}")])

    if parent_id is not None:
        # اگر در زیرمجموعه هستیم، محتوای این سطح را هم نمایش بده
        content_items = await db.get_content_by_category(parent_id)
        for item in content_items:
            buttons.append([InlineKeyboardButton(text=f"📄 {item['title']}", callback_data=f"user:view:content:{item['id']}")])

        # دکمه بازگشت به سطح بالاتر
        # برای پیدا کردن والدِ والد، باید یک کوئری دیگر به دیتابیس بزنیم (برای سادگی فعلاً به منوی اصلی برمیگردد)
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت به منوی اصلی", callback_data="user:browse:cat:root")])

    text = "لطفاً یک دسته‌بندی یا محتوا را انتخاب کنید:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if is_callback:
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("user:browse:cat:"))
async def user_browse_category_callback(query: CallbackQuery):
    """CB-Handler: برای مرور دسته‌بندی‌ها."""
    await query.answer()
    cat_id_str = query.data.split(":")[-1]

    if cat_id_str == "root":
        await browse_categories_handler(query.message, parent_id=None, is_callback=True)
    else:
        category_id = int(cat_id_str)
        await browse_categories_handler(query.message, parent_id=category_id, is_callback=True)

@dp.callback_query(F.data.startswith("user:view:content:"))
async def user_view_content_callback(query: CallbackQuery, state: FSMContext):
    """CB-Handler: برای نمایش یک محتوای خاص."""
    await query.answer()
    content_id = int(query.data.split(":")[-1])

    content = await db.get_content_details(content_id)
    if not content:
        await query.message.answer("متأسفانه این محتوا یافت نشد.")
        return

    # --- منطق دسترسی ---
    has_access = False
    if not content['is_premium']:
        has_access = True
    else:
        # اینجا می‌توان منطق بررسی دسترسی کاربر خاص به محتوای پرمیوم را اضافه کرد
        # has_access = await db.check_user_content_access(query.from_user.id, content_id)
        # فعلا برای سادگی، فرض می‌کنیم برای محتوای پرمیوم همیشه رمز پرسیده می‌شود
        await state.set_state(PremiumContentForm.waiting_for_password)
        await state.update_data(content_id=content_id)
        await query.message.answer(f"این محتوا ({html.bold(content['title'])}) رمزدار است. لطفاً رمز عبور را وارد کنید:")
        return

    if has_access:
        await send_protected_content(query.from_user.id, content)
    else:
        await query.message.answer("شما به این محتوا دسترسی ندارید.")

@dp.message(PremiumContentForm.waiting_for_password, F.text)
async def premium_content_password_handler(message: Message, state: FSMContext):
    """پردازش رمز وارد شده برای محتوای پرمیوم."""
    data = await state.get_data()
    content_id = data['content_id']
    content = await db.get_content_details(content_id)

    if security.check_password(message.text, content['access_password_hash']):
        await message.answer("رمز صحیح است. در حال ارسال محتوا...")
        await send_protected_content(message.from_user.id, content)
        await state.clear()
    else:
        await message.answer("رمز وارد شده اشتباه است. لطفاً دوباره تلاش کنید یا عملیات را لغو کنید.")
        # برای جلوگیری از brute-force، می‌توان اینجا از rate limiter استفاده کرد

async def send_protected_content(user_id: int, content: Dict[str, Any]):
    """تابع کمکی برای ارسال محتوا با `protect_content=True`."""
    caption = f"**{content['title']}**\n\n{content.get('description', '')}"
    try:
        if content['file_type'] == 'photo':
            await bot.send_photo(user_id, content['file_id'], caption=caption, protect_content=True)
        elif content['file_type'] == 'video':
            await bot.send_video(user_id, content['file_id'], caption=caption, protect_content=True)
        elif content['file_type'] == 'document':
            await bot.send_document(user_id, content['file_id'], caption=caption, protect_content=True)
    except Exception as e:
        logger.error(f"Failed to send protected content {content['id']} to user {user_id}: {e}")
        # Optionally send a message to the user that sending failed
        await bot.send_message(user_id, "خطایی در ارسال محتوا رخ داد. لطفاً به پشتیبانی اطلاع دهید.")


@dp.message(Command("support"), IsApprovedUser())
async def support_start(message: Message, state: FSMContext):
    """شروع فرآیند ارسال پیام به پشتیبانی."""
    await state.set_state(SupportForm.waiting_for_message)
    await message.answer("لطفاً پیام خود را برای تیم پشتیبانی بنویسید:")

@dp.message(SupportForm.waiting_for_message, F.text)
async def support_process_message(message: Message, state: FSMContext):
    """پردازش پیام کاربر و ارسال آن برای ادمین‌ها."""
    user = await db.get_user(message.from_user.id)
    # ایجاد تیکت و ذخیره اولین پیام
    ticket_id = await db.create_support_ticket(message.from_user.id, message.text)

    await state.clear()
    await message.answer("پیام شما با موفقیت برای پشتیبانی ارسال شد. منتظر پاسخ بمانید.")

    # اطلاع‌رسانی به ادمین‌ها
    notification_text = f"""
🎫 **تیکت پشتیبانی جدید**
**از طرف:** {html.bold(user['first_name'])} (ID: {html.code(user['user_id'])})
**تیکت ID:** {html.code(ticket_id)}

**پیام:**
{html.quote(message.text)}
    """
    reply_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 پاسخ به کاربر", callback_data=f"admin:support:reply:{ticket_id}")],
        [InlineKeyboardButton(text="✅ بستن تیکت", callback_data=f"admin:support:close:{ticket_id}")]
    ])

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, notification_text, reply_markup=reply_keyboard)
        except Exception as e:
            logger.error(f"Failed to send support notification to admin {admin_id}: {e}")

@dp.callback_query(F.data == "admin:comms:menu")
async def admin_comms_menu_handler(query: CallbackQuery):
    """CB-Handler: نمایش منوی ارتباطات."""
    await query.answer()
    await query.message.edit_text(
        "بخش ارتباط با کاربران. لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=get_admin_comms_keyboard()
    )

@dp.callback_query(F.data == "admin:comms:broadcast")
async def broadcast_start(query: CallbackQuery, state: FSMContext):
    """شروع فرآیند ارسال پیام گروهی."""
    await query.answer()
    await state.set_state(BroadcastForm.waiting_for_message)
    await query.message.edit_text("لطفاً پیامی که می‌خواهید برای تمام کاربران ارسال شود را وارد کنید (متن، عکس، ویدیو یا فایل):")

@dp.message(BroadcastForm.waiting_for_message, F.text | F.photo | F.video | F.document)
async def broadcast_process(message: Message, state: FSMContext):
    """پردازش و ارسال پیام گروهی."""
    await state.clear()
    await message.answer("درحال ارسال پیام برای کاربران...")

    user_ids = await db.get_all_approved_user_ids()

    successful_sends = 0
    failed_sends = 0

    for user_id in user_ids:
        try:
            # copy_message برای ارسال هر نوع پیامی (متن، عکس و...) مناسب است
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=message.reply_markup
            )
            successful_sends += 1
            await asyncio.sleep(0.1) # جلوگیری از اسپم و محدودیت تلگرام
        except Exception as e:
            failed_sends += 1
            logger.error(f"Broadcast failed for user {user_id}: {e}")

    report_text = f"""
    **گزارش ارسال پیام گروهی**

    - ✅ **ارسال موفق:** {successful_sends}
    - ❌ **ارسال ناموفق:** {failed_sends}
    """
    await message.answer(report_text)
    await admin_comms_menu_handler(message)


@dp.callback_query(F.data == "admin:support:list_open")
async def admin_list_open_tickets(query: CallbackQuery):
    """CB-Handler: نمایش لیست تیکت‌های باز پشتیبانی."""
    await query.answer("در حال دریافت تیکت‌های باز...")
    open_tickets = await db.get_open_tickets()

    if not open_tickets:
        text = "هیچ تیکت پشتیبانی بازی وجود ندارد."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin:comms:menu")]])
    else:
        text = "لیست تیکت‌های باز:\n"
        buttons = []
        for ticket in open_tickets:
            user_info = f"{ticket['first_name']} (ID: {ticket['user_id']})"
            text += f"\n- **تیکت #{ticket['id']}** از {user_info}\n"
            text += f"  *{html.quote(ticket['first_message'][:50])}...*\n"
            buttons.append([InlineKeyboardButton(text=f"💬 پاسخ به تیکت #{ticket['id']}", callback_data=f"admin:support:reply:{ticket['id']}")])
        buttons.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin:comms:menu")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await query.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("admin:support:reply:"))
async def admin_reply_start(query: CallbackQuery, state: FSMContext):
    """شروع فرآیند پاسخ به یک تیکت."""
    ticket_id = int(query.data.split(":")[-1])
    await state.set_state(ReplyForm.waiting_for_reply)
    await state.update_data(ticket_id=ticket_id)
    await query.answer()
    await query.message.edit_text(f"در حال پاسخ به تیکت #{ticket_id}. لطفاً پیام خود را بنویسید:")

@dp.message(ReplyForm.waiting_for_reply, F.text)
async def admin_reply_process(message: Message, state: FSMContext):
    """پردازش پاسخ ادمین و ارسال آن به کاربر."""
    data = await state.get_data()
    ticket_id = data['ticket_id']

    # پیدا کردن کاربر صاحب تیکت
    user_id = await db.get_ticket_owner(ticket_id)
    if not user_id:
        await message.answer("خطا: کاربر این تیکت یافت نشد.")
        await state.clear()
        return

    # ذخیره پیام ادمین در دیتابیس
    await db.add_support_message(ticket_id, message.from_user.id, message.text)

    await state.clear()
    await message.answer(f"پیام شما برای کاربر تیکت #{ticket_id} ارسال شد.")

    # ارسال پیام به کاربر
    try:
        reply_text = f"پاسخ پشتیبانی به تیکت شما:\n\n{html.quote(message.text)}"
        await bot.send_message(user_id, reply_text)
    except Exception as e:
        logger.error(f"Failed to send reply to user {user_id} for ticket {ticket_id}: {e}")
        await message.answer("پیام در دیتابیس ذخیره شد، اما ارسال به کاربر ناموفق بود.")

    # نمایش مجدد پنل ارتباطات
    await message.answer("بازگشت به پنل...", reply_markup=get_admin_comms_keyboard())


@dp.callback_query(F.data.startswith("admin:support:close:"))
async def admin_close_ticket_handler(query: CallbackQuery):
    """CB-Handler: بستن یک تیکت پشتیبانی."""
    ticket_id = int(query.data.split(":")[-1])
    await db.close_ticket(ticket_id)
    await query.answer("تیکت با موفقیت بسته شد.", show_alert=True)
    await query.message.edit_text(query.message.text + "\n\n**-- تیکت بسته شد --**", reply_markup=None)


@dp.callback_query(F.data.startswith("admin:approve:") | F.data.startswith("admin:reject:") | F.data.startswith("admin:block:"))
async def admin_user_action_handler(query: CallbackQuery):
    """پردازش کلیک‌های ادمین روی دکمه‌های تأیید/رد/بلاک کاربر"""
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
