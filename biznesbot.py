import os
import django
import asyncio
from datetime import datetime, timedelta
import dateparser
import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from django.utils import timezone
from asgiref.sync import sync_to_async


# --- Django setup ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from orders.models import OrderItem, Order

ALLOWED_USERS = [1321114194, 7175908701, 730694198, 8580214119, 8168353886]  # твой Telegram ID и ID доверенных людей
API_TOKEN = "8767542736:AAGrUfDficLOXZ_-8z-c1UgNjdm664w8ZTQ"
ADMIN_CHAT_ID = [1321114194]

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

bishkek_tz = pytz.timezone("Asia/Bishkek")

# --- Парсер дат/времени ---
def parse_date_range(text: str):
    now = timezone.localtime(timezone.now(), bishkek_tz)
    today = now.date()
    text = text.lower()

    # точный промежуток: с 28.01.2026 09:00 по 29.01.2026 02:00
    match = re.search(r"с (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}) по (\d{2}\.\d{2}\.\d{4} \d{2}:\d{2})", text)
    if match:
        start = dateparser.parse(match.group(1), languages=["ru"])
        end = dateparser.parse(match.group(2), languages=["ru"])

    # смена: отчёт за смену 28.01.2026
    elif "смена" in text and re.search(r"\d{2}\.\d{2}\.\d{4}", text):
        date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
        base_date = dateparser.parse(date_match.group(0), languages=["ru"])
        start = datetime.combine(base_date.date(), datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((base_date + timedelta(days=1)).date(), datetime.strptime("02:00", "%H:%M").time())

    # смена сегодня
    elif "смена сегодня" in text:
        base_date = today
        start = datetime.combine(base_date, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((base_date + timedelta(days=1)), datetime.strptime("02:00", "%H:%M").time())

    # смена вчера
    elif "смена вчера" in text:
        base_date = today - timedelta(days=1)
        start = datetime.combine(base_date, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((base_date + timedelta(days=1)), datetime.strptime("02:00", "%H:%M").time())

    # обычные запросы: сегодня, вчера
    elif "сегодня" in text:
        start = datetime.combine(today, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((today + timedelta(days=1)), datetime.strptime("02:00", "%H:%M").time())
    elif "вчера" in text:
        d = today - timedelta(days=1)
        start = datetime.combine(d, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((d + timedelta(days=1)), datetime.strptime("02:00", "%H:%M").time())
    else:
        # ⚡️ по умолчанию: смена текущего дня
        start = datetime.combine(today, datetime.strptime("09:00", "%H:%M").time())
        end = datetime.combine((today + timedelta(days=1)), datetime.strptime("02:00", "%H:%M").time())

    # переводим в Бишкек
    if start.tzinfo is None:
        start = bishkek_tz.localize(start)
    else:
        start = start.astimezone(bishkek_tz)

    if end.tzinfo is None:
        end = bishkek_tz.localize(end)
    else:
        end = end.astimezone(bishkek_tz)

    return start, end





# --- Продажи ---
@sync_to_async
def get_sales(start, end):
    items = OrderItem.objects.filter(
        order__order_time__gte=start,
        order__order_time__lte=end,
        order__cancelled=False,
        quantity__gt=0,
        product__price__gt=0
    ).select_related("product")
    stats = {}
    total_sum = 0
    for item in items:
        name = item.product.name
        quantity = item.quantity or 0
        price = item.price or item.product.price or 0
        total = price * quantity
        total_sum += total
        if name not in stats:
            stats[name] = {"quantity": 0, "total": 0, "price": price}
        stats[name]["quantity"] += quantity
        stats[name]["total"] += total
    return total_sum, stats

# --- Отменённые заказы ---
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

# --- Удалённые блюда (OrderItem.cancelled=True) ---
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
        quantity = item.original_quantity or 0   # ✅ используем original_quantity
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

# --- Ответ ---
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
        top_text = "\n".join([
            f"{name}: {data['quantity']} шт × {data['price']} сом = {data['total']} сом"
            for name, data in stats.items()
        ]) or "Нет продаж"
        reply = f"""
📊 Продажи за период {start.strftime('%d.%m.%Y %H:%M')} — {end.strftime('%d.%m.%Y %H:%M')}
(Время указано по Бишкеку)

Общая сумма: {total_sum} сом

Топ блюда:
{top_text}
"""
        return reply.strip()

import re
from datetime import date
from asgiref.sync import sync_to_async
from orders.models import Supply, OrderItem

# --- Сохранение прихода ---
@sync_to_async
def save_supply(text: str):
    pairs = re.findall(r"(\w+)\s+([\d\.]+)", text)
    saved = []
    for ingr_type, qty in pairs:
        Supply.objects.create(ingredient=ingr_type, delivered_qty=qty)
        saved.append(f"{ingr_type}: {qty}")
    return saved
# --- Подсчёт остатков ---
@sync_to_async
def get_ingredients_left():
    today = date.today()
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


# обработка текста, начинающегося с "пришло"
@dp.message(lambda m: m.text and m.text.lower().startswith("пришло"))
async def handle_delivery(message: types.Message):
    saved = await save_supply(message.text)
    await message.answer("Запомнил приход:\n" + "\n".join(saved))

# обработка текста, содержащего "остатки"
@dp.message(lambda m: m.text and "остатки" in m.text.lower())
async def handle_leftovers(message: types.Message):
    delivered, used, left = await get_ingredients_left()
    lines = []
    for ingr, qty in left.items():
        lines.append(f"{ingr}: осталось {qty:.2f}")
    await message.answer("\n".join(lines))

THRESHOLDS = {
    "lavash_m": 20,
    "lavash_l": 20,
    "lavash_s": 20,
    "bun": 20,
    "strips": 2,
    "wings": 2,
}

async def check_stocks_periodically():
    while True:
        delivered, used, left = await get_ingredients_left()
        for ingr, qty in left.items():
            threshold = THRESHOLDS.get(ingr)
            if threshold is not None and qty < threshold:
                for admin_id in ADMIN_CHAT_ID:  # перебираем список
                    await bot.send_message(
                        admin_id,
                        f"⚠️ Остаток {ingr} меньше порога: {qty:.2f}"
                    )
        await asyncio.sleep(3600)
 # проверка раз в час


# --- Telegram ---
async def start_handler(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="/сегодня"), types.KeyboardButton(text="/вчера")],
            [types.KeyboardButton(text="/отмены"), types.KeyboardButton(text="/удалённые")],
            [types.KeyboardButton(text="/остатки")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "Добро пожаловать! 👋\n\nВыберите действие:",
        reply_markup=keyboard
    )

dp.message.register(start_handler, Command("start"))

# --- Хэндлеры для коротких кнопок ---
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


@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id not in ALLOWED_USERS:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return

    user_text = message.text.strip()
    reply = await ai_reply(user_text)
    max_len = 4000
    for i in range(0, len(reply), max_len):
        await message.answer(reply[i:i+max_len])




# --- Запуск ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
