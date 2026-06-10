import os
import django
import re
import asyncio
from datetime import datetime, timedelta
import dateparser
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from django.utils import timezone
from asgiref.sync import sync_to_async
import calendar

# --- Django setup ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from orders.models import OrderItem, Order, Supply

ALLOWED_USERS = [6490799943, 1321114194, 7175908701, 730694198, 986739628, 582234578]
API_TOKEN = "8724426419:AAEMXearRVaGL_1Mvn2Zc2sMkXBDX2xcEbE"
ADMIN_CHAT_ID = [1321114194]

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

bishkek_tz = pytz.timezone("Asia/Bishkek")

# --- FSM для отчёта за период ---
class PeriodReportStates(StatesGroup):
    waiting_start = State()
    waiting_end = State()

# ---------------------- Календарь ----------------------
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
    keyboard.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_period")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.callback_query(lambda c: c.data == "cancel_period")
async def cancel_period(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("❌ Выбор периода отменён.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cal_nav_"))
async def calendar_navigation(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    prefix = parts[2]
    year = int(parts[3])
    month = int(parts[4])
    new_keyboard = build_calendar(year, month, prefix)
    try:
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    except Exception as e:
        if "message is not modified" not in str(e):
            raise
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ignore")
async def ignore_callback(callback: types.CallbackQuery):
    await callback.answer()

# --- Парсер дат/времени (исходный, для /сегодня, /вчера и т.д.) ---
def parse_date_range(text: str):
    now = timezone.localtime(timezone.now(), bishkek_tz)
    today = now.date()
    text = text.lower()

    match = re.search(r"с (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}) по (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", text)
    if match:
        start = dateparser.parse(match.group(1), languages=["ru"])
        end = dateparser.parse(match.group(2), languages=["ru"])
    elif "смена" in text and re.search(r"\d{2}\.\d{2}\.\d{4}", text):
        date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
        base_date = dateparser.parse(date_match.group(0), languages=["ru"])
        start = datetime.combine(base_date.date(), datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((base_date + timedelta(days=1)).date(), datetime.strptime("09:00", "%H:%M").time())
    elif "смена сегодня" in text:
        base_date = today
        start = datetime.combine(base_date, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((base_date + timedelta(days=1)), datetime.strptime("09:00", "%H:%M").time())
    elif "смена вчера" in text:
        base_date = today - timedelta(days=1)
        start = datetime.combine(base_date, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((base_date + timedelta(days=1)), datetime.strptime("09:00", "%H:%M").time())
    elif "сегодня" in text:
        start = datetime.combine(today, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((today + timedelta(days=1)), datetime.strptime("09:00", "%H:%M").time())
    elif "вчера" in text:
        d = today - timedelta(days=1)
        start = datetime.combine(d, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((d + timedelta(days=1)), datetime.strptime("09:00", "%H:%M").time())
    else:
        start = datetime.combine(today, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((today + timedelta(days=1)), datetime.strptime("09:00", "%H:%M").time())

    if start.tzinfo is None:
        start = bishkek_tz.localize(start)
    else:
        start = start.astimezone(bishkek_tz)
    if end.tzinfo is None:
        end = bishkek_tz.localize(end)
    else:
        end = end.astimezone(bishkek_tz)

    return start, end

# --- Функции работы с БД (без изменений) ---
@sync_to_async
def get_sales(start, end):
    items = OrderItem.objects.filter(
        order__order_time__gte=start,
        order__order_time__lte=end,
        order__cancelled=False,
        quantity__gt=0,
        product__price__gt=0
    ).exclude(product__name__iregex=r"(?i)доставка").select_related("product")
    stats = {}
    total_sum = 0
    for item in items:
        name = item.product.name
        quantity = item.quantity or 0
        price = item.price or item.product.price or 0
        total = price * quantity
        total_sum += total
        key = name
        if key not in stats:
            stats[key] = {"quantity": 0, "total": 0, "price": price}
        stats[key]["quantity"] += quantity
        stats[key]["total"] += total
    delivery_items = OrderItem.objects.filter(
        order__order_time__gte=start,
        order__order_time__lte=end,
        order__cancelled=False,
        quantity__gt=0,
        product__name__iregex=r"(?i)доставка"
    ).select_related("product")
    for d in delivery_items:
        name = d.product.name
        quantity = d.quantity or 0
        price = d.price or d.product.price or 0
        total = price * quantity
        key = f"{name} ({price} сом)"
        if key not in stats:
            stats[key] = {"quantity": 0, "total": 0, "price": price}
        stats[key]["quantity"] += quantity
        stats[key]["total"] += total
    return total_sum, stats

@sync_to_async
def get_cancelled(start, end):
    items = OrderItem.objects.filter(
        order__order_time__gte=start,
        order__order_time__lte=end,
        order__cancelled=True,
        quantity__gt=0,
        product__price__gt=0
    ).select_related("order", "product", "order__cancelled_by")
    grouped = {}
    total_sum = 0
    for item in items:
        order = item.order
        receipt = order.receipt_number or "-"
        cancelled_by = order.cancelled_by.name if order.cancelled_by else "неизвестно"
        cancelled_at = order.cancelled_at or order.order_time
        cancelled_at = cancelled_at.astimezone(bishkek_tz)
        key = (receipt, cancelled_by, cancelled_at)
        price = item.price or item.product.price or 0
        quantity = item.quantity or 0
        total = price * quantity
        total_sum += total
        if key not in grouped:
            grouped[key] = {"items": [], "order_total": 0}
        grouped[key]["items"].append(f"  - {item.product.name} × {quantity} шт = {total:.2f} сом")
        grouped[key]["order_total"] += total
    return total_sum, grouped

@sync_to_async
def get_deleted_items(start, end):
    items = OrderItem.objects.filter(
        order__order_time__gte=start,
        order__order_time__lte=end,
        cancelled=True
    ).select_related("order", "product", "cancelled_by")
    result = []
    total_sum = 0
    for item in items:
        quantity = item.original_quantity or 0
        unit_price = item.price or item.product.price or 0
        total = unit_price * quantity
        total_sum += total
        cashier = item.cancelled_by.name if item.cancelled_by else "неизвестно"
        cancelled_at = item.cancelled_at or item.order.order_time
        cancelled_at = cancelled_at.astimezone(bishkek_tz)
        result.append(
            f"- {item.product.name} × {quantity} шт = {total:.2f} сом | "
            f"Кассир: {cashier} | "
            f"Время: {cancelled_at.strftime('%d.%m.%Y %H:%M')}"
        )
    return total_sum, result

@sync_to_async
def save_supply(text: str):
    pairs = re.findall(r"(\w+)\s+([\d\.]+)", text)
    saved = []
    for ingr_type, qty in pairs:
        Supply.objects.create(ingredient=ingr_type, delivered_qty=qty)
        saved.append(f"{ingr_type}: {qty}")
    return saved

@sync_to_async
def get_ingredients_left():
    today = datetime.now(bishkek_tz).date()
    supplies = Supply.objects.filter(created_at__date=today)
    delivered = {}
    for s in supplies:
        delivered[s.ingredient] = delivered.get(s.ingredient, 0) + float(s.delivered_qty)
    used = {}
    items = OrderItem.objects.filter(order__order_time__date=today, cancelled=False).select_related("product")
    for it in items:
        if it.product.ingredient_type:
            usage = float(it.product.ingredient_usage or 1)
            used[it.product.ingredient_type] = used.get(it.product.ingredient_type, 0) + usage * (it.quantity or 0)
    left = {}
    for ingr, qty in delivered.items():
        left[ingr] = qty - used.get(ingr, 0)
    return delivered, used, left

# --- Основная логика ответа (без изменений) ---
async def ai_reply(user_text: str) -> str:
    start, end = parse_date_range(user_text)
    if "отмен" in user_text.lower():
        total_sum, grouped = await get_cancelled(start, end)
        if not grouped:
            return f"❌ Нет отменённых заказов за период {start.strftime('%d.%m.%Y %H:%M')} — {end.strftime('%d.%m.%Y %H:%M')}"
        lines = []
        for (receipt, cancelled_by, cancelled_at), data in grouped.items():
            lines.append(f"Заказ #{receipt} | Отменил: {cancelled_by} | Время: {cancelled_at.strftime('%d.%m.%Y %H:%M')}")
            lines.extend(data["items"])
            lines.append(f"  Сумма заказа: {data['order_total']:.2f} сом\n")
        reply = f"""
❌ Отменённые заказы за период {start.strftime('%d.%m.%Y %H:%M')} — {end.strftime('%d.%m.%Y %H:%M')}
(Время указано по Бишкеку)

Общая сумма отменённых: {total_sum:.2f} сом

{chr(10).join(lines)}
"""
        return reply.strip()
    elif "удалён" in user_text.lower():
        total_sum, deleted_items = await get_deleted_items(start, end)
        if not deleted_items:
            return f"🗑 Нет удалённых блюд за период {start.strftime('%d.%m.%Y %H:%M')} — {end.strftime('%d.%m.%Y %H:%M')}"
        reply = f"""
🗑 Удалённые блюда за период {start.strftime('%d.%m.%Y %H:%M')} — {end.strftime('%d.%m.%Y %H:%M')}
(Время указано по Бишкеку)

Общая сумма удалённых: {total_sum:.2f} сом

{chr(10).join(deleted_items)}
"""
        return reply.strip()
    else:
        total_sum, stats = await get_sales(start, end)
        sorted_items = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)
        top_text = "\n".join([
            f"{name}: {data['quantity']} шт × {data['price']} сом = {data['total']} сом"
            for name, data in sorted_items
        ]) or "Нет продаж"
        reply = f"""
📊 Продажи за период {start.strftime('%d.%m.%Y %H:%M')} — {end.strftime('%d.%m.%Y %H:%M')}
(Время указано по Бишкеку)

Общая сумма: {total_sum} сом

Топ блюда:
{top_text}
"""
        return reply.strip()

# ---------------------- Отчёт за период через календарь (с 8:00 до 4:00) ----------------------
@dp.message(Command("отчет_период"))
async def cmd_period_report(message: types.Message, state: FSMContext):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await state.set_state(PeriodReportStates.waiting_start)
    today = datetime.now(bishkek_tz)
    await message.answer("📅 Выберите дату начала:", reply_markup=build_calendar(today.year, today.month, "start"))

@dp.callback_query(PeriodReportStates.waiting_start, lambda c: c.data.startswith("start_"))
async def process_start_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split("_")[1]  # YYYY-MM-DD
    await state.update_data(start_date=date_str)
    await state.set_state(PeriodReportStates.waiting_end)
    today = datetime.now(bishkek_tz)
    await callback.message.edit_text(f"📅 Начало: {date_str}\nТеперь выберите дату конца:")
    await callback.message.answer("Выберите дату конца:", reply_markup=build_calendar(today.year, today.month, "end"))
    await callback.answer()

@dp.callback_query(PeriodReportStates.waiting_end, lambda c: c.data.startswith("end_"))
async def process_end_date(callback: types.CallbackQuery, state: FSMContext):
    end_date_str = callback.data.split("_")[1]  # YYYY-MM-DD
    data = await state.get_data()
    start_date_str = data.get("start_date")
    if not start_date_str:
        await callback.message.edit_text("Ошибка: дата начала не выбрана. Попробуйте /отчет_период заново.")
        await state.clear()
        return
    # Преобразуем даты в период с 8:00 до 4:00 следующего дня
    # Начало: start_date в 8:00
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    start_dt = datetime.combine(start_dt.date(), datetime.strptime("08:00", "%H:%M").time())
    # Конец: end_date+1 день в 4:00
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1)
    end_dt = datetime.combine(end_dt.date(), datetime.strptime("04:00", "%H:%M").time())
    start_dt = bishkek_tz.localize(start_dt)
    end_dt = bishkek_tz.localize(end_dt)
    total_sum, stats = await get_sales(start_dt, end_dt)
    sorted_items = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)
    top_text = "\n".join([
        f"{name}: {data['quantity']} шт × {data['price']} сом = {data['total']} сом"
        for name, data in sorted_items
    ]) or "Нет продаж"
    reply = f"""
📊 Продажи за период {start_dt.strftime('%d.%m.%Y %H:%M')} — {end_dt.strftime('%d.%m.%Y %H:%M')}
(с 8:00 до 4:00 следующего дня)

Общая сумма: {total_sum} сом

Топ блюда:
{top_text}
"""
    await callback.message.edit_text(reply)
    await state.clear()
    await callback.answer()

# ---------------------- Автоматический отчёт в 09:00 за вчерашнюю смену (9:00 – 9:00) ----------------------
async def send_daily_shift_report():
    yesterday = (datetime.now(bishkek_tz) - timedelta(days=1)).date()
    start = datetime.combine(yesterday, datetime.strptime("09:00", "%H:%M").time())
    end = datetime.combine(yesterday + timedelta(days=1), datetime.strptime("09:00", "%H:%M").time())
    start = bishkek_tz.localize(start)
    end = bishkek_tz.localize(end)
    total_sum, stats = await get_sales(start, end)
    sorted_items = sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True)
    top_text = "\n".join([
        f"{name}: {data['quantity']} шт × {data['price']} сом = {data['total']} сом"
        for name, data in sorted_items
    ]) or "Нет продаж"
    report = f"""
📊 ЕЖЕДНЕВНЫЙ ОТЧЁТ за СМЕНУ {yesterday.strftime('%d.%m.%Y')}
(с 9:00 до 9:00)

Общая сумма: {total_sum} сом

Топ блюда:
{top_text}
"""
    for admin_id in ADMIN_CHAT_ID:
        try:
            await bot.send_message(admin_id, report)
        except Exception as e:
            print(f"Не удалось отправить админу {admin_id}: {e}")

async def daily_report_scheduler():
    while True:
        now = datetime.now(bishkek_tz)
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await send_daily_shift_report()

# ---------------------- Telegram обработчики ----------------------
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/сегодня"), KeyboardButton(text="/вчера")],
            [KeyboardButton(text="/отмены"), KeyboardButton(text="/удалённые")],
            [KeyboardButton(text="/остатки"), KeyboardButton(text="/отчет_период")]
        ],
        resize_keyboard=True
    )
    await message.answer("Добро пожаловать! 👋\n\nВыберите действие:", reply_markup=keyboard)

@dp.message(Command("сегодня"))
async def report_today(message: types.Message):
    reply = await ai_reply("сегодня")
    await message.answer(reply)

@dp.message(Command("вчера"))
async def report_yesterday(message: types.Message):
    reply = await ai_reply("вчера")
    await message.answer(reply)

@dp.message(Command("отмены"))
async def report_cancelled(message: types.Message):
    reply = await ai_reply("отмены")
    await message.answer(reply)

@dp.message(Command("удалённые"))
async def report_deleted(message: types.Message):
    reply = await ai_reply("удалённые")
    await message.answer(reply)

@dp.message(Command("остатки"))
async def report_stocks(message: types.Message):
    delivered, used, left = await get_ingredients_left()
    lines = []
    for ingr, qty in left.items():
        lines.append(f"{ingr}: осталось {qty:.2f}")
    await message.answer("\n".join(lines))

@dp.message(lambda m: m.text and m.text.lower().startswith("пришло"))
async def handle_delivery(message: types.Message):
    saved = await save_supply(message.text)
    await message.answer("Запомнил приход:\n" + "\n".join(saved))

@dp.message(lambda m: m.text and "остатки" in m.text.lower())
async def handle_leftovers(message: types.Message):
    delivered, used, left = await get_ingredients_left()
    lines = []
    for ingr, qty in left.items():
        lines.append(f"{ingr}: осталось {qty:.2f}")
    await message.answer("\n".join(lines))

@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return
    reply = await ai_reply(message.text.strip())
    max_len = 4000
    for i in range(0, len(reply), max_len):
        await message.answer(reply[i:i+max_len])

# --- Запуск ---
async def main():
    asyncio.create_task(daily_report_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())