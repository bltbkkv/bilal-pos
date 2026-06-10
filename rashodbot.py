import asyncio
import sqlite3
import re
import calendar
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

API_TOKEN = "8817190540:AAFUL8b3V1eFnFpdfplihBleyAZbYAdAD4E"
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

ALLOWED_USERS = [6490799943, 1321114194, 7175908701, 730694198, 986739628, 582234578, 8965738895]

def is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_USERS

conn = sqlite3.connect("expenses.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount INTEGER,
    category TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# ---------------------- FSM состояния (без изменений) ----------------------
class EditStates(StatesGroup):
    choosing_start_date = State()
    choosing_end_date = State()
    choosing_record = State()
    editing_amount = State()
    editing_category = State()

class DeleteStates(StatesGroup):
    choosing_start_date = State()
    choosing_end_date = State()
    choosing_record = State()
    confirming = State()

# ---------------------- Пагинация (без изменений) ----------------------
user_pages = {}

def get_records_keyboard(user_id: int, action: str, page: int = 0, start_date=None, end_date=None):
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
        cursor.execute(
            "SELECT id, amount, category, timestamp FROM expenses WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp DESC",
            (start_dt, end_dt)
        )
    else:
        cursor.execute("SELECT id, amount, category, timestamp FROM expenses ORDER BY timestamp DESC LIMIT 50")
    rows = cursor.fetchall()
    if not rows:
        return None
    per_page = 10
    total_pages = (len(rows) + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    page_rows = rows[start:end]
    keyboard = []
    for rec_id, amount, category, ts in page_rows:
        date_str = ts[:10] if isinstance(ts, str) else ts.strftime("%Y-%m-%d")
        text = f"{date_str} - {amount} ({category[:20]})"
        keyboard.append([InlineKeyboardButton(text=text, callback_data=f"{action}_rec_{rec_id}")])
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"{action}_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶", callback_data=f"{action}_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_page(user_id: int, action: str) -> int:
    return user_pages.get(user_id, {}).get(action, 0)

def update_page(user_id: int, action: str, page: int):
    if user_id not in user_pages:
        user_pages[user_id] = {}
    user_pages[user_id][action] = page

# ---------------------- Календарь (общий) ----------------------
def build_calendar(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    cal = calendar.monthcalendar(year, month)
    month_names = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
                   "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    title = f"{month_names[month-1]} {year}"
    keyboard = [[InlineKeyboardButton(text=title, callback_data="ignore")]]
    keyboard.append([
        InlineKeyboardButton(text="Пн", callback_data="ignore"),
        InlineKeyboardButton(text="Вт", callback_data="ignore"),
        InlineKeyboardButton(text="Ср", callback_data="ignore"),
        InlineKeyboardButton(text="Чт", callback_data="ignore"),
        InlineKeyboardButton(text="Пт", callback_data="ignore"),
        InlineKeyboardButton(text="Сб", callback_data="ignore"),
        InlineKeyboardButton(text="Вс", callback_data="ignore"),
    ])
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"{prefix}_{year}-{month:02d}-{day:02d}"))
        keyboard.append(row)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    nav_row = [
        InlineKeyboardButton(text="◀ Месяц назад", callback_data=f"cal_nav_{prefix}_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text="Месяц вперёд ▶", callback_data=f"cal_nav_{prefix}_{next_year}_{next_month}")
    ]
    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ---------------------- Вспомогательные функции отчётов ----------------------
def get_shift_range(day_offset: int = 0):
    """Возвращает (start, end) для смены с 8:00 до 4:00 следующего дня."""
    now = datetime.now() - timedelta(days=day_offset)
    start = datetime(now.year, now.month, now.day, 8, 0, 0)
    end = start + timedelta(hours=20)
    return start, end

def format_timestamp(ts):
    if isinstance(ts, str):
        return ts[:19]
    return ts.strftime("%Y-%m-%d %H:%M:%S")

async def make_report(start: datetime, end: datetime) -> list:
    """
    Возвращает список строк (сообщений), готовых к отправке.
    Если отчёт влезает в одно сообщение – возвращает список из одного элемента.
    Иначе разбивает на несколько частей (по деталям).
    """
    cursor.execute("SELECT amount, category, timestamp FROM expenses WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp ASC", (start, end))
    rows = cursor.fetchall()
    if not rows:
        return ["Нет расходов за указанный период."]

    total = sum(r[0] for r in rows)
    categories = {}
    details = []
    for amount, category, ts in rows:
        categories[category] = categories.get(category, 0) + amount
        ts_str = format_timestamp(ts)
        details.append(f"{ts_str} — {category}: {amount}")

    # Формируем шапку
    header = f"📊 Общая сумма: {total}\n\n🗂 Детализация:\n"
    for cat, amt in categories.items():
        header += f"{cat}: {amt}\n"
    header += "\n⏱ По времени:\n"

    # Объединяем шапку + детали
    full_details = header + "\n".join(details)
    # Если сообщение длиннее 4000 символов, разбиваем
    if len(full_details) <= 4000:
        return [full_details]
    else:
        parts = []
        current_part = header
        for line in details:
            if len(current_part) + len(line) + 1 > 4000:
                parts.append(current_part)
                current_part = line + "\n"
            else:
                current_part += line + "\n"
        if current_part:
            parts.append(current_part)
        return parts

# ---------------------- Команды меню ----------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/отчет"), KeyboardButton(text="/период")],
            [KeyboardButton(text="/редактировать"), KeyboardButton(text="/удалить")],
            [KeyboardButton(text="/help")]
        ],
        resize_keyboard=True
    )
    await message.answer("Добро пожаловать! 👋\n\nВыберите действие:", reply_markup=keyboard)

@dp.message(Command("help"))
async def help_command(message: types.Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    text = """
📋 Доступные команды:

/отчет   – расходы за текущую смену (с 8:00 сегодня до 4:00 завтра)
/период  – выбрать произвольный период через календарь

/редактировать – сначала выбрать период, затем запись для изменения
/удалить       – сначала выбрать период, затем запись для удаления

💸 Добавление расходов:
Просто отправьте сообщение с суммой и категорией.
Форматы: 200 курица, курица 200, 250 лед
Можно отправлять несколько строк столбиком.

❗️ О каждом новом расходе оповещаются все участники.
    """
    await message.answer(text)

# ---------------------- Отчёт за текущую смену ----------------------
@dp.message(Command("отчет"))
async def report_shift(message: types.Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    start, end = get_shift_range(day_offset=0)
    parts = await make_report(start, end)
    for part in parts:
        await message.answer(part)

# ---------------------- Отчёт за период (календарь) ----------------------
selected_period_dates = {}

@dp.message(Command("период"))
async def period_start(message: types.Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    today = datetime.now()
    await message.answer("📅 Выберите дату начала:", reply_markup=build_calendar(today.year, today.month, "period_start"))

@dp.callback_query(lambda c: c.data.startswith("period_start_") and not c.data.startswith("cal_nav"))
async def period_choose_start(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id):
        await callback.message.answer("⛔ Нет доступа.")
        return
    user_id = callback.from_user.id
    date_str = callback.data.split("_")[2]
    selected_period_dates[user_id] = {"start": date_str}
    today = datetime.now()
    await callback.message.edit_text(f"📅 Начало: {date_str}\nТеперь выберите дату конца:")
    await callback.message.answer(
        text="Выберите дату конца:",
        reply_markup=build_calendar(today.year, today.month, "period_end")
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("period_end_") and not c.data.startswith("cal_nav"))
async def period_choose_end(callback: types.CallbackQuery):
    if not is_allowed(callback.from_user.id):
        await callback.message.answer("⛔ Нет доступа.")
        return
    user_id = callback.from_user.id
    end_date_str = callback.data.split("_")[2]
    if user_id not in selected_period_dates or "start" not in selected_period_dates[user_id]:
        await callback.message.edit_text("Сначала выберите дату начала.")
        await callback.answer()
        return
    start_date_str = selected_period_dates[user_id]["start"]
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
    parts = await make_report(start_dt, end_dt)
    # Отправляем все части отчёта
    for part in parts:
        await callback.message.answer(part)
    del selected_period_dates[user_id]
    await callback.answer()

# ---------------------- Редактирование, удаление (без изменений) ----------------------
# ... (весь код редактирования/удаления остаётся таким же, как в вашем файле) ...
# Для краткости не переписываю, но в итоговом файле он должен присутствовать полностью.
# Здесь я покажу только добавленную функцию оповещения и изменённый add_expense.

# ---------------------- Оповещение всех пользователей ----------------------
async def notify_all_users(text: str):
    """Отправляет сообщение всем разрешённым пользователям, игнорируя ошибки."""
    for user_id in ALLOWED_USERS:
        try:
            await bot.send_message(user_id, text)
        except Exception:
            pass  # если пользователь не начал диалог, ничего страшного

# ---------------------- Добавление расходов с оповещением ----------------------
def parse_line(line: str):
    line = line.strip()
    if not line:
        return None
    numbers = re.findall(r'\d+', line)
    if not numbers:
        return None
    amount = int(numbers[0])
    category = re.sub(r'\d+', '', line, count=1).strip()
    if not category:
        category = "без категории"
    return amount, category

@dp.message()
async def add_expense(message: types.Message):
    if not is_allowed(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    text = message.text.strip()
    if not text or text.startswith('/'):
        return
    lines = text.splitlines()
    added = []
    errors = []
    for idx, line in enumerate(lines, 1):
        parsed = parse_line(line)
        if parsed is None:
            errors.append(f"Строка {idx}: «{line}» — не удалось распознать")
            continue
        amount, category = parsed
        try:
            cursor.execute("INSERT INTO expenses (amount, category, timestamp) VALUES (?, ?, ?)",
                           (amount, category, datetime.now()))
            conn.commit()
            added.append(f"{amount} ({category})")
        except Exception as e:
            errors.append(f"Строка {idx}: ошибка БД — {str(e)}")
    response = []
    if added:
        added_text = f"✅ Добавлено: {', '.join(added)}"
        response.append(added_text)
        # Оповещаем всех о каждом новом расходе (можно отправить одно общее сообщение со всеми добавленными строками)
        await notify_all_users(f"🆕 Новый расход от {message.from_user.first_name}:\n{added_text}")
    if errors:
        response.append("⚠️ Ошибки:\n" + "\n".join(errors))
    if not added and not errors:
        response.append("❌ Не удалось добавить ни одной записи. Проверьте формат (сумма и категория).")
    await message.answer("\n\n".join(response))

# ---------------------- Навигация по календарю, отмена, игнор ----------------------
@dp.callback_query(lambda c: c.data.startswith("cal_nav_"))
async def calendar_navigation(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    prefix = parts[2]
    year = int(parts[3])
    month = int(parts[4])
    new_keyboard = build_calendar(year, month, prefix)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_dialog(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()

# ---------------------- Запуск ----------------------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())