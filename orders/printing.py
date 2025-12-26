import win32print
import win32ui
from datetime import datetime

# Имя принтера в Windows (проверь в "Принтеры и сканеры")
PRINTER_NAME = "XP-80C (copy 1)"


def print_receipt(order):
    """
    Печатает чек для заказа.
    order — dict с ключами:
        id: int
        employee: str
        items: list[{"name": str, "quantity": int, "price": int}]
        deleted_items: list[{"name": str, "quantity": int, "reason": str, "cashier": str}]
        total: int
    """

    # Создаём контекст печати
    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(PRINTER_NAME)
    pdc.StartDoc(f"Чек №{order['id']}")
    pdc.StartPage()

    # координаты текста
    x, y = 50, 50
    line_height = 80

    def write(line, indent=0):
        nonlocal y
        pdc.TextOut(x + indent, y, line)
        y += line_height

    # Заголовок
    write("Bilal Fried Chicken POS")
    write(f"Чек №{order['id']}")
    write(f"Кассир: {order['employee']}")
    write(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    write("--------------------------------")

    # Основные блюда
    for item in order['items']:
        total = item['quantity'] * item['price']
        write(f"{item['name']} x{item['quantity']} — {total} сом")

    # Удалённые блюда
    if order.get('deleted_items'):
        write("Удалённые позиции:")
        for d in order['deleted_items']:
            write(f"{d['name']} x{d['quantity']} — {d['reason']}")
            write(f"Кассир: {d['cashier']}")

    write("--------------------------------")
    write(f"Итого: {order['total']} сом")
    write("Спасибо за покупку!")

    # Завершаем печать
    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

