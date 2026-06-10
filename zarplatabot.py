import asyncio
import sqlite3
import calendar
import re
from datetime import datetime
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "8897911036:AAGqQCD1P4JN5ZjqNb6vL0qFPDn_Vq4BK1g"
TIMEZONE = pytz.timezone("Asia/Bishkek")

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ---------- Роли ----------
ADMINS = [6490799943, 1321114194]
CASHIERS = [7175908701, 730694198, 986739628, 582234578]

def get_role(user_id):
    if user_id in ADMINS: return "admin"
    if user_id in CASHIERS: return "cashier"
    return None

def check_access(user_id): return get_role(user_id) is not None
def check_permission(user_id, required_role):
    role = get_role(user_id)
    if required_role == "admin": return role == "admin"
    return role in ("admin", "cashier")

# ---------- База данных ----------
conn = sqlite3.connect("salary.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    hourly_rate REAL,
    payment_qr TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS worklogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    date TEXT,
    hours REAL,
    rate_at_time REAL,
    bonus REAL DEFAULT 0,
    penalty REAL DEFAULT 0,
    advance REAL DEFAULT 0
)
""")
conn.commit()

try:
    cursor.execute("SELECT payment_qr FROM employees LIMIT 1")
except sqlite3.OperationalError:
    cursor.execute("ALTER TABLE employees ADD COLUMN payment_qr TEXT")
    conn.commit()

# ---------- FSM ----------
class AddEmployeeStates(StatesGroup):
    enter_name = State()
    enter_rate = State()

class DeleteEmployeeStates(StatesGroup):
    choose = State()
    confirm = State()

class EditRateStates(StatesGroup):
    choose = State()
    enter_new_rate = State()

class EditNameStates(StatesGroup):
    choose = State()
    enter_new_name = State()

class WorkStates(StatesGroup):
    choose = State()
    enter_hours = State()

class BonusStates(StatesGroup):
    choose = State()
    enter_amount = State()

class PenaltyStates(StatesGroup):
    choose = State()
    enter_amount = State()

class AdvanceStates(StatesGroup):
    choose = State()
    enter_amount = State()

class MassReportStates(StatesGroup):
    choosing_start = State()
    choosing_end = State()
    selecting = State()

class QRSetStates(StatesGroup):
    choosing_employee = State()
    waiting_photo = State()

class QRGetStates(StatesGroup):
    choosing_employee = State()

# ---------- Клавиатуры ----------
def get_employees_keyboard(prefix: str):
    cursor.execute("SELECT id, name FROM employees ORDER BY name")
    rows = cursor.fetchall()
    if not rows: return None
    keyboard = []
    for emp_id, name in rows:
        keyboard.append([InlineKeyboardButton(text=name, callback_data=f"{prefix}_{emp_id}")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]])

def get_multi_select_keyboard(selected_employees: dict):
    cursor.execute("SELECT id, name FROM employees ORDER BY name")
    rows = cursor.fetchall()
    if not rows: return None
    keyboard = []
    for emp_id, name in rows:
        checked = "✅ " if selected_employees.get(emp_id) else "☑️ "
        keyboard.append([InlineKeyboardButton(text=f"{checked}{name}", callback_data=f"multi_toggle_{emp_id}")])
    keyboard.append([InlineKeyboardButton(text="✅ ГОТОВО", callback_data="multi_done")])
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ---------- Отмена ----------
@dp.callback_query(lambda c: c.data == "cancel")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Действие отменено.")
    await callback.answer()

@dp.message(Command("cancel"))
async def cancel_text(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    await message.answer("❌ Действие отменено.")

# ---------- Старт и меню ----------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    if not check_access(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/сотрудник"), KeyboardButton(text="/список")],
            [KeyboardButton(text="/удалить"), KeyboardButton(text="/ставка"), KeyboardButton(text="/имя")],
            [KeyboardButton(text="/работа"), KeyboardButton(text="/бонус"), KeyboardButton(text="/штраф"), KeyboardButton(text="/взял")],
            [KeyboardButton(text="/отчет_масс")],
            [KeyboardButton(text="/qr_set"), KeyboardButton(text="/qr_get"), KeyboardButton(text="/help")]
        ],
        resize_keyboard=True
    )
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=keyboard)

@dp.message(Command("help"))
async def help_command(message: types.Message):
    if not check_access(message.from_user.id): return
    role = get_role(message.from_user.id)
    help_lines = [
        "/сотрудник – добавить сотрудника",
        "/список – список сотрудников",
        "/имя – изменить имя",
        "/работа – записать часы",
        "/штраф – добавить штраф",
        "/взял – записать аванс",
        "/отчет_масс – массовый отчёт за период",
        "/qr_get – показать QR-код",
        "/cancel – отменить действие",
    ]
    if role == "admin":
        help_lines.insert(2, "/удалить – удалить сотрудника")
        help_lines.insert(3, "/ставка – изменить ставку")
        help_lines.insert(6, "/бонус – добавить бонус")
        help_lines.insert(9, "/qr_set – привязать QR-код")
    await message.answer("\n".join(help_lines))

# ---------- Добавить сотрудника ----------
@dp.message(Command("сотрудник"))
async def add_employee_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    await state.set_state(AddEmployeeStates.enter_name)
    await message.answer("Введите имя нового сотрудника:", reply_markup=get_cancel_keyboard())

@dp.message(AddEmployeeStates.enter_name)
async def add_employee_name(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым.", reply_markup=get_cancel_keyboard())
        return
    await state.update_data(name=name)
    await state.set_state(AddEmployeeStates.enter_rate)
    await message.answer(f"Имя: {name}\nТеперь введите почасовую ставку (сом/час):", reply_markup=get_cancel_keyboard())

@dp.message(AddEmployeeStates.enter_rate)
async def add_employee_rate(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    try:
        rate = float(message.text.strip())
        if rate <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число (ставку).", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    name = data["name"]
    cursor.execute("INSERT INTO employees (name, hourly_rate) VALUES (?, ?)", (name, rate))
    conn.commit()
    await message.answer(f"✅ Сотрудник {name} добавлен со ставкой {rate} сом/час")
    await state.clear()

# ---------- Удалить сотрудника (админ) ----------
@dp.message(Command("удалить"))
async def delete_employee_start(message: types.Message, state: FSMContext):
    if not check_permission(message.from_user.id, "admin"):
        await message.answer("⛔ Недостаточно прав.")
        return
    await state.clear()
    kb = get_employees_keyboard("del")
    if not kb:
        await message.answer("Список сотрудников пуст.")
        return
    await state.set_state(DeleteEmployeeStates.choose)
    await message.answer("Выберите сотрудника для удаления:", reply_markup=kb)

@dp.callback_query(DeleteEmployeeStates.choose, lambda c: c.data.startswith("del_"))
async def delete_employee_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0])
    await state.set_state(DeleteEmployeeStates.confirm)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="confirm_del_yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    await callback.message.edit_text(f"Удалить {row[0]}? Все его записи будут потеряны.", reply_markup=kb)
    await callback.answer()

@dp.callback_query(DeleteEmployeeStates.confirm, lambda c: c.data == "confirm_del_yes")
async def confirm_delete(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    emp_id = data["employee_id"]
    name = data["employee_name"]
    cursor.execute("DELETE FROM employees WHERE id=?", (emp_id,))
    cursor.execute("DELETE FROM worklogs WHERE employee_id=?", (emp_id,))
    conn.commit()
    await callback.message.edit_text(f"🗑 Сотрудник {name} удалён.")
    await state.clear()
    await callback.answer()

# ---------- Изменить ставку (админ) ----------
@dp.message(Command("ставка"))
async def edit_rate_start(message: types.Message, state: FSMContext):
    if not check_permission(message.from_user.id, "admin"):
        await message.answer("⛔ Недостаточно прав.")
        return
    await state.clear()
    kb = get_employees_keyboard("rate")
    if not kb:
        await message.answer("Список сотрудников пуст.")
        return
    await state.set_state(EditRateStates.choose)
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(EditRateStates.choose, lambda c: c.data.startswith("rate_"))
async def edit_rate_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0])
    await state.set_state(EditRateStates.enter_new_rate)
    await callback.message.edit_text(f"Выбран {row[0]}. Введите новую ставку (сом/час):", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(EditRateStates.enter_new_rate)
async def edit_rate_new_value(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    try:
        new_rate = float(message.text.strip())
        if new_rate <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число (ставку).", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    name = data["employee_name"]
    cursor.execute("UPDATE employees SET hourly_rate=? WHERE id=?", (new_rate, emp_id))
    conn.commit()
    await message.answer(f"✏️ Ставка {name} изменена на {new_rate} сом/час")
    await state.clear()

# ---------- Изменить имя ----------
@dp.message(Command("имя"))
async def edit_name_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    kb = get_employees_keyboard("rename")
    if not kb:
        await message.answer("Список сотрудников пуст.")
        return
    await state.set_state(EditNameStates.choose)
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(EditNameStates.choose, lambda c: c.data.startswith("rename_"))
async def edit_name_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, old_name=row[0])
    await state.set_state(EditNameStates.enter_new_name)
    await callback.message.edit_text(f"Выбран {row[0]}. Введите новое имя:", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(EditNameStates.enter_new_name)
async def edit_name_new_value(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    new_name = message.text.strip()
    if not new_name:
        await message.answer("Имя не может быть пустым.", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    old_name = data["old_name"]
    cursor.execute("SELECT id FROM employees WHERE name=?", (new_name,))
    if cursor.fetchone():
        await message.answer("Такое имя уже существует.", reply_markup=get_cancel_keyboard())
        return
    cursor.execute("UPDATE employees SET name=? WHERE id=?", (new_name, emp_id))
    conn.commit()
    await message.answer(f"✏️ Имя {old_name} изменено на {new_name}")
    await state.clear()

# ---------- Работа (часы) ----------
@dp.message(Command("работа"))
async def work_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    kb = get_employees_keyboard("work")
    if not kb:
        await message.answer("Сначала добавьте сотрудников.")
        return
    await state.set_state(WorkStates.choose)
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(WorkStates.choose, lambda c: c.data.startswith("work_"))
async def work_employee_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name, hourly_rate FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0], rate_at_time=row[1])
    await state.set_state(WorkStates.enter_hours)
    await callback.message.edit_text(f"Выбран {row[0]} (ставка {row[1]} сом/ч).\nВведите часы:", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(WorkStates.enter_hours)
async def work_enter_hours(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    try:
        hours = float(message.text.strip())
        if hours <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число (часы).", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    emp_name = data["employee_name"]
    rate = data["rate_at_time"]
    today = datetime.now(TIMEZONE).date()
    cursor.execute("INSERT INTO worklogs (employee_id, date, hours, rate_at_time) VALUES (?, ?, ?, ?)",
                   (emp_id, today, hours, rate))
    conn.commit()
    await message.answer(f"✅ Записано: {emp_name} — {hours} ч (по ставке {rate} сом/ч)")
    await state.clear()

# ---------- Бонус (админ) ----------
@dp.message(Command("бонус"))
async def bonus_start(message: types.Message, state: FSMContext):
    if not check_permission(message.from_user.id, "admin"):
        await message.answer("⛔ Недостаточно прав.")
        return
    await state.clear()
    kb = get_employees_keyboard("bonus")
    if not kb:
        await message.answer("Сначала добавьте сотрудников.")
        return
    await state.set_state(BonusStates.choose)
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(BonusStates.choose, lambda c: c.data.startswith("bonus_"))
async def bonus_employee_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0])
    await state.set_state(BonusStates.enter_amount)
    await callback.message.edit_text(f"Выбран {row[0]}. Введите сумму бонуса (сом):", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(BonusStates.enter_amount)
async def bonus_enter_amount(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число (сумму).", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    emp_name = data["employee_name"]
    today = datetime.now(TIMEZONE).date()
    cursor.execute("INSERT INTO worklogs (employee_id, date, hours, bonus) VALUES (?, ?, ?, ?)",
                   (emp_id, today, 0, amount))
    conn.commit()
    await message.answer(f"✅ Бонус {amount} сом для {emp_name} добавлен.")
    await state.clear()

# ---------- Штраф ----------
@dp.message(Command("штраф"))
async def penalty_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    kb = get_employees_keyboard("penalty")
    if not kb:
        await message.answer("Сначала добавьте сотрудников.")
        return
    await state.set_state(PenaltyStates.choose)
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(PenaltyStates.choose, lambda c: c.data.startswith("penalty_"))
async def penalty_employee_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0])
    await state.set_state(PenaltyStates.enter_amount)
    await callback.message.edit_text(f"Выбран {row[0]}. Введите сумму штрафа (сом):", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(PenaltyStates.enter_amount)
async def penalty_enter_amount(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число (сумму).", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    emp_name = data["employee_name"]
    today = datetime.now(TIMEZONE).date()
    cursor.execute("INSERT INTO worklogs (employee_id, date, hours, penalty) VALUES (?, ?, ?, ?)",
                   (emp_id, today, 0, amount))
    conn.commit()
    await message.answer(f"❌ Штраф {amount} сом для {emp_name} добавлен.")
    await state.clear()

# ---------- Аванс ----------
@dp.message(Command("взял"))
async def advance_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    kb = get_employees_keyboard("advance")
    if not kb:
        await message.answer("Сначала добавьте сотрудников.")
        return
    await state.set_state(AdvanceStates.choose)
    await message.answer("Выберите сотрудника:", reply_markup=kb)

@dp.callback_query(AdvanceStates.choose, lambda c: c.data.startswith("advance_"))
async def advance_employee_chosen(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[1])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0])
    await state.set_state(AdvanceStates.enter_amount)
    await callback.message.edit_text(f"Выбран {row[0]}. Введите сумму аванса (сом):", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(AdvanceStates.enter_amount)
async def advance_enter_amount(message: types.Message, state: FSMContext):
    if message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    try:
        amount = float(message.text.strip())
        if amount <= 0: raise ValueError
    except:
        await message.answer("Введите положительное число (сумму).", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    emp_name = data["employee_name"]
    today = datetime.now(TIMEZONE).date()
    cursor.execute("INSERT INTO worklogs (employee_id, date, hours, advance) VALUES (?, ?, ?, ?)",
                   (emp_id, today, 0, amount))
    conn.commit()
    await message.answer(f"💸 Аванс {amount} сом для {emp_name} записан.")
    await state.clear()

# ---------- Список сотрудников ----------
@dp.message(Command("список"))
async def list_employees(message: types.Message):
    if not check_access(message.from_user.id): return
    cursor.execute("SELECT name, hourly_rate FROM employees")
    rows = cursor.fetchall()
    if not rows:
        await message.answer("Нет сотрудников.")
        return
    text = "👥 Список сотрудников:\n" + "\n".join(f"- {name}: {rate} сом/час" for name, rate in rows)
    await message.answer(text)

# ---------- Календарь (исправленный) ----------
def build_calendar(year: int, month: int, prefix: str) -> InlineKeyboardMarkup:
    cal = calendar.monthcalendar(year, month)
    month_names = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    title = f"{month_names[month-1]} {year}"
    keyboard = [[InlineKeyboardButton(text=title, callback_data="ignore")]]
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"{prefix}_{year}-{month:02d}-{day:02d}"))
        keyboard.append(row)
    # Навигационные кнопки с префиксом cal_nav
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

@dp.callback_query(lambda c: c.data.startswith("cal_nav_"))
async def calendar_navigation(callback: types.CallbackQuery):
    # Разбираем callback_data: cal_nav_mass_start_2026_6
    data = callback.data
    parts = data.split("_")  # ['cal', 'nav', 'mass', 'start', '2026', '6']
    # Префикс календаря – то, что было передано при создании (например "mass_start")
    prefix = f"{parts[2]}_{parts[3]}"  # "mass_start"
    year = int(parts[4])
    month = int(parts[5])
    new_keyboard = build_calendar(year, month, prefix)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer()

# ---------- Функция генерации отчёта для одного сотрудника ----------
async def generate_employee_report(emp_id, start_date, end_date):
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row: return None, None
    emp_name = row[0]
    # Для отладки – выведем в консоль
    print(f"Запрос отчёта для {emp_name} ({emp_id}) за период {start_date} - {end_date}")
    cursor.execute("""
        SELECT w.date, w.hours, w.rate_at_time, w.bonus, w.penalty, w.advance,
               e.hourly_rate as current_rate
        FROM worklogs w
        JOIN employees e ON w.employee_id = e.id
        WHERE w.employee_id=? AND w.date BETWEEN ? AND ?
        ORDER BY w.date
    """, (emp_id, start_date, end_date))
    rows = cursor.fetchall()
    print(f"Найдено записей: {len(rows)}")
    if not rows:
        return emp_name, "📭 Нет записей за выбранный период."
    total_salary = 0.0
    total_bonus = 0.0
    total_penalty = 0.0
    total_advance = 0.0
    details = []
    for date, hours, rate_at_time, bonus, penalty, advance, current_rate in rows:
        effective_rate = rate_at_time if rate_at_time is not None else current_rate
        salary_part = hours * effective_rate
        total_salary += salary_part
        total_bonus += bonus
        total_penalty += penalty
        total_advance += advance
        if hours > 0:
            details.append(f"{date}: {hours} ч × {effective_rate} сом = {salary_part} сом")
        if bonus > 0:
            details.append(f"{date}: 🎁 бонус +{bonus} сом")
        if penalty > 0:
            details.append(f"{date}: ⚠️ штраф -{penalty} сом")
        if advance > 0:
            details.append(f"{date}: 💸 аванс -{advance} сом")
    final_payout = total_salary + total_bonus - total_penalty - total_advance
    text = f"📊 ОТЧЁТ: {emp_name}\n📅 {start_date} – {end_date}\n\n"
    if details:
        text += "\n".join(details) + "\n\n"
    text += f"💰 Зарплата по часам: {total_salary} сом\n"
    text += f"🎁 Бонусы: {total_bonus} сом\n"
    text += f"⚠️ Штрафы: {total_penalty} сом\n"
    text += f"💸 Авансы: {total_advance} сом\n"
    text += f"✅ ИТОГО К ВЫПЛАТЕ: {final_payout} сом"
    return emp_name, text

# ---------- Массовый отчёт (мультивыбор) ----------
mass_report_selected = {}

@dp.message(Command("отчет_масс"))
async def mass_report_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    today = datetime.now(TIMEZONE)
    await state.set_state(MassReportStates.choosing_start)
    await message.answer("📅 Выберите дату начала:", reply_markup=build_calendar(today.year, today.month, "mass_start"))

@dp.callback_query(MassReportStates.choosing_start, lambda c: c.data.startswith("mass_start_") and not c.data.startswith("cal_nav"))
async def mass_report_choose_start(callback: types.CallbackQuery, state: FSMContext):
    if not check_access(callback.from_user.id): return
    date_str = callback.data.split("_")[2]  # mass_start_2026-06-09 -> берём 3-ю часть
    await state.update_data(start_date=date_str)
    await state.set_state(MassReportStates.choosing_end)
    today = datetime.now(TIMEZONE)
    await callback.message.edit_text(f"📅 Начало: {date_str}\nТеперь выберите дату конца:")
    await callback.message.answer(text="Выберите дату конца:", reply_markup=build_calendar(today.year, today.month, "mass_end"))
    await callback.answer()

@dp.callback_query(MassReportStates.choosing_end, lambda c: c.data.startswith("mass_end_") and not c.data.startswith("cal_nav"))
async def mass_report_choose_end(callback: types.CallbackQuery, state: FSMContext):
    if not check_access(callback.from_user.id): return
    end_date_str = callback.data.split("_")[2]  # mass_end_2026-06-09
    data = await state.get_data()
    start_date_str = data.get("start_date")
    if not start_date_str:
        await callback.message.edit_text("Ошибка: дата начала не выбрана.")
        await callback.answer()
        return
    await state.update_data(start_date=start_date_str, end_date=end_date_str)
    user_id = callback.from_user.id
    mass_report_selected[user_id] = {
        "start": start_date_str,
        "end": end_date_str,
        "selected": {}
    }
    await state.set_state(MassReportStates.selecting)
    kb = get_multi_select_keyboard(mass_report_selected[user_id]["selected"])
    if not kb:
        await callback.message.edit_text("Нет сотрудников.")
        await state.clear()
        await callback.answer()
        return
    await callback.message.edit_text(
        f"📅 Период: {start_date_str} – {end_date_str}\n\n"
        "Выберите сотрудников (нажимайте на имена для отметки).\n"
        "Когда закончите, нажмите «ГОТОВО».",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("multi_toggle_"))
async def multi_toggle(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in mass_report_selected:
        await callback.answer("Сессия устарела, начните заново.")
        return
    emp_id = int(callback.data.split("_")[2])
    if emp_id in mass_report_selected[user_id]["selected"]:
        del mass_report_selected[user_id]["selected"][emp_id]
    else:
        mass_report_selected[user_id]["selected"][emp_id] = True
    kb = get_multi_select_keyboard(mass_report_selected[user_id]["selected"])
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "multi_done")
async def multi_done(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in mass_report_selected:
        await callback.message.edit_text("Сессия устарела. Начните заново командой /отчет_масс")
        await callback.answer()
        return
    data = mass_report_selected[user_id]
    selected_ids = list(data["selected"].keys())
    start_date = data["start"]
    end_date = data["end"]
    if not selected_ids:
        await callback.answer("Не выбрано ни одного сотрудника. Отметьте хотя бы одного.")
        return

    await callback.message.edit_text("🔄 Формирую отчёт...")
    for emp_id in selected_ids:
        emp_name, report_text = await generate_employee_report(emp_id, start_date, end_date)
        if not emp_name: continue
        await callback.message.answer(report_text)
        cursor.execute("SELECT payment_qr FROM employees WHERE id=?", (emp_id,))
        row = cursor.fetchone()
        if row and row[0]:
            await callback.message.answer_photo(photo=row[0], caption=f"🧾 QR‑код для {emp_name}")
        await asyncio.sleep(0.3)
    await callback.message.answer("✅ Отчёт по всем выбранным сотрудникам завершён.")
    del mass_report_selected[user_id]
    await state.clear()
    await callback.answer()

# ---------- QR-коды ----------
@dp.message(Command("qr_set"))
async def qr_set_start(message: types.Message, state: FSMContext):
    if not check_permission(message.from_user.id, "admin"):
        await message.answer("⛔ Недостаточно прав.")
        return
    await state.clear()
    kb = get_employees_keyboard("qr_set")
    if not kb:
        await message.answer("Нет сотрудников.")
        return
    await state.set_state(QRSetStates.choosing_employee)
    await message.answer("Выберите сотрудника, для которого хотите привязать QR‑код:", reply_markup=kb)

@dp.callback_query(QRSetStates.choosing_employee, lambda c: c.data.startswith("qr_set_"))
async def qr_set_employee(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT name FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    await state.update_data(employee_id=emp_id, employee_name=row[0])
    await state.set_state(QRSetStates.waiting_photo)
    await callback.message.edit_text(f"Выбран {row[0]}. Отправьте фото с QR‑кодом.\nДля отмены нажмите кнопку.", reply_markup=get_cancel_keyboard())
    await callback.answer()

@dp.message(QRSetStates.waiting_photo)
async def qr_set_photo(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Отменено.")
        return
    if not message.photo:
        await message.answer("Пожалуйста, отправьте фото.", reply_markup=get_cancel_keyboard())
        return
    data = await state.get_data()
    emp_id = data["employee_id"]
    emp_name = data["employee_name"]
    file_id = message.photo[-1].file_id
    cursor.execute("UPDATE employees SET payment_qr=? WHERE id=?", (file_id, emp_id))
    conn.commit()
    await message.answer(f"✅ QR‑код для {emp_name} сохранён.")
    await state.clear()

@dp.message(Command("qr_get"))
async def qr_get_start(message: types.Message, state: FSMContext):
    if not check_access(message.from_user.id): return
    await state.clear()
    kb = get_employees_keyboard("qr_get")
    if not kb:
        await message.answer("Нет сотрудников.")
        return
    await state.set_state(QRGetStates.choosing_employee)
    await message.answer("Выберите сотрудника, чей QR‑код показать:", reply_markup=kb)

@dp.callback_query(QRGetStates.choosing_employee, lambda c: c.data.startswith("qr_get_"))
async def qr_get_employee(callback: types.CallbackQuery, state: FSMContext):
    emp_id = int(callback.data.split("_")[2])
    cursor.execute("SELECT name, payment_qr FROM employees WHERE id=?", (emp_id,))
    row = cursor.fetchone()
    if not row:
        await callback.message.edit_text("Сотрудник не найден")
        await state.clear()
        return
    name, qr = row
    if not qr:
        await callback.message.edit_text(f"У сотрудника {name} нет QR‑кода. Используйте /qr_set.")
    else:
        await callback.message.delete()
        await callback.message.answer_photo(photo=qr, caption=f"🧾 QR‑код для {name}")
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())