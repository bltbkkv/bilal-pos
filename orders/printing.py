# orders/printing.py
from escpos.printer import Usb
from .models import Order

def print_escpos(order_id):
    order = Order.objects.get(id=order_id)
    # Set your vendor/product IDs (find via Device Manager or lsusb)
    p = Usb(0x04b8, 0x0e15)  # Example Epson IDs — replace
    p.text("Bilal Fried Chicken POS\n")
    p.text(f"Чек №{order.id}\n")
    p.text(f"Кассир: {order.employee.name if order.employee else '-'}\n")
    p.text(f"Дата: {order.order_time.strftime('%d.%m.%Y %H:%M')}\n")
    p.text("-----------------------------\n")
    for item in order.items.all():
        p.text(f"{item.product.name} x{item.quantity} — {item.quantity * item.price} сом\n")
    p.text("-----------------------------\n")
    p.text(f"Итого: {order.total} сом\n")
    p.cut()
