
import win32ui
from datetime import datetime

PRINTER_NAME = "XP-80"

def print_receipt(order):
    """
    Печатает чек в формате: список блюд с ценами + удалённые позиции.
    order — dict с ключами:
        employee: str
        items: list[{"name": str, "quantity": int, "price": int}]
        deleted_items: list[{"name": str, "quantity": int, "reason": str, "cashier": str}]
        total: int
    """

    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(PRINTER_NAME)
    pdc.StartDoc("Чек по продажам")
    pdc.StartPage()

    # 🔹 Шрифты
    font_normal = win32ui.CreateFont({
        "name": "Arial",
        "height": 32,
        "weight": 400
    })
    font_bold = win32ui.CreateFont({
        "name": "Arial",
        "height": 36,
        "weight": 700
    })

    x, y = 50, 50
    line_height = 100

    def write(line, bold=False, indent=0):
        nonlocal y
        pdc.SelectObject(font_bold if bold else font_normal)
        pdc.TextOut(x + indent, y, line)
        y += line_height

    # 🔹 Заголовок
    write("Bilal Fried Chicken POS", bold=True)
    write(f"Оператор: {order['employee']}")
    write(f"Дата: {datetime.now().strftime('%Y.%m.%d')}")
    write(f"Время: {datetime.now().strftime('%H:%M')}")
    write("--------------------------------")

    # 🔹 Список блюд
    write("Наименование | Кол-во | Цена | Сумма", bold=True)
    total = 0
    for item in order['items']:
        name = item['name']
        qty = item['quantity']
        price = item['price']
        line_total = qty * price
        total += line_total
        write(f"{name} | {qty} | {price} | {line_total}", bold=True)

    write("--------------------------------")
    write(f"Сумма: {total} сом", bold=True)
    write("Способ оплаты: Наличные")

    write("Спасибо за покупку!", bold=True)

    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()


