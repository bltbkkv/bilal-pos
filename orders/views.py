from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, FileResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from django.utils import timezone
from django.db import models
from django.db.models import Sum
import io, json
import win32print
import win32ui
from django.views.decorators.http import require_GET
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from .models import Supply
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
import os
from reportlab.lib.units import mm

import json
from decimal import Decimal

from .models import Product, Order, OrderItem, Employee
from django.shortcuts import redirect
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from datetime import datetime, time
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.contrib.auth import login
from django.conf import settings




def menu(request):
    emp_id = request.session.get('employee_id')
    employee = Employee.objects.filter(id=emp_id).first() if emp_id else None

    categories = Product.objects.values_list('category', flat=True).distinct()
    products = Product.objects.all()
    return render(request, 'menu.html', {
        'employee': employee,
        'categories': categories,
        'products': products
    })


@csrf_exempt
@require_POST
def submit_order(request):
    """
    Expect JSON: { employee_id, items: [{id, name, price, qty, options}], note, order_type }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    emp = Employee.objects.filter(id=data.get('employee_id')).first()
    items = data.get('items', [])
    if not items:
        return HttpResponseBadRequest('No items')

    total = sum(Decimal(str(i['price'])) * int(i['qty']) for i in items)

    # заказ создаётся со статусом "Готовится"
    order = Order.objects.create(
        employee=emp,
        total=total,
        note=data.get('note', ''),
        status='pending',
        order_type=data.get('order_type', 'here')  # 🔹 сохраняем тип заказа
    )

    for i in items:
        product = get_object_or_404(Product, id=int(i['id']))
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=int(i['qty']),
            price=Decimal(str(i['price'])),
            options=i.get('options', [])  # 🔹 сохраняем модификаторы
        )

    return JsonResponse({'ok': True, 'order_id': order.id, 'status': order.status})



def mark_order_ready(request, order_id):
    """
    Переводим заказ в статус 'Готово'
    """
    order = get_object_or_404(Order, id=order_id)
    order.status = 'ready'
    order.save()
    return JsonResponse({'ok': True, 'order_id': order.id, 'status': order.status})

def print_receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    buffer = io.BytesIO()

    # 🔹 Подключаем кириллический шрифт
    font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'ttf', 'DejaVuSans.ttf')
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    font_name = "DejaVu"
    font_size = 10

    # 🔹 Собираем все строки для измерения ширины
    lines = [
        "Bilal Fried Chicken POS",
        "Адрес: Бишкек, Чуйская область",
        "Тел: +996 XXX XX-XX-XX",
        f"Чек №{order.id}",
        f"Кассир: {order.employee.name if order.employee else '-'}",
        f"Дата: {order.order_time.strftime('%d.%m.%Y %H:%M')}",
        f"Тип заказа: {order.get_order_type_display()}",
    ]

    active_items = order.items.filter(cancelled=False)
    for item in active_items:
        opts = f" ({', '.join(item.options)})" if item.options else ""
        lines.append(f"{item.product.name}{opts} x{item.quantity} — {item.line_total:.2f} сом")

    total_active = sum(i.line_total for i in active_items)
    lines.append(f"Итого: {total_active:.2f} сом")

    if order.note:
        lines.append(f"Комментарий: {order.note}")

    lines.append("Спасибо за покупку!")

    # 🔹 Расчёт высоты страницы
    lines_count = len(lines)
    height = max(400, 100 + lines_count * 25)  # минимум 400 мм

    # 🔹 Расчёт ширины страницы (автоматически)
    max_text_width = max(pdfmetrics.stringWidth(line, font_name, font_size) for line in lines)
    width = max(80 * mm, max_text_width + 40)  # минимум 80 мм, плюс отступ

    # 🔹 Генерация PDF
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFont(font_name, font_size)

    # 🔹 Начальная координата
    y = height - 40

    # 🔹 Вывод строк
    for line in lines:
        if y < 50:
            c.showPage()
            y = height - 40
            c.setFont(font_name, font_size)
        c.drawString(20, y, line)
        y -= 20

    c.showPage()
    c.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=False, filename=f"receipt_{order.id}.pdf")





def get_employee_id(request):
    pin = request.GET.get('pin')
    try:
        employee = Employee.objects.get(pin=pin)
        request.session['employee_id'] = employee.id  # сохраняем кассира
        return JsonResponse({'id': employee.id})
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Неверный PIN'}, status=400)

@csrf_exempt
def report_by_date(request):
    login_required = not request.session.get('report_access_granted')

    if request.method == 'POST':
        if login_required:
            password = request.POST.get('password')
            if password == '28062006':
                request.session['report_access_granted'] = True
                login_required = False
            else:
                return render(request, 'report_by_date.html', {
                    'login_required': True,
                    'login_error': 'Неверный пароль'
                })

        # фильтры
        start_date = request.POST.get('start')
        end_date = request.POST.get('end')
        start_time = request.POST.get('start_time') or '00:00'
        end_time = request.POST.get('end_time') or '23:59'

        try:
            start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
        except Exception:
            start_dt = None
            end_dt = None

        orders = Order.objects.all()
        if start_dt and end_dt:
            orders = orders.filter(order_time__range=(start_dt, end_dt))

        total = orders.aggregate(Sum('total'))['total__sum'] or 0
        count = orders.count()

        # общая прибыль
        profit = OrderItem.objects.filter(order__in=orders).aggregate(
            total_profit=Sum(
                ExpressionWrapper(
                    (F('price') - F('product__cost_price')) * F('quantity'),
                    output_field=DecimalField()
                )
            )
        )['total_profit'] or 0

        # прибыль по каждому товару
        items_profit = OrderItem.objects.filter(order__in=orders, cancelled=False).values(
            'product__name',
            'product__price',
            'product__cost_price'
        ).annotate(
            total_qty=Sum('quantity'),
            total_profit=Sum(
                ExpressionWrapper(
                    (F('price') - F('product__cost_price')) * F('quantity'),
                    output_field=DecimalField()
                )
            )
        ).order_by('-total_profit')

        # расход ингредиентов: исключаем отменённые позиции и считаем как Decimal
        ingredients_usage_qs = (
            OrderItem.objects
            .filter(order__in=orders, cancelled=False)
            .values('product__ingredient_type')
            .annotate(
                used=Sum(
                    ExpressionWrapper(
                        F('quantity') * F('product__ingredient_usage'),
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    )
                )
            )
        )
        usage_dict = {
            row['product__ingredient_type']: (row['used'] or Decimal('0'))
            for row in ingredients_usage_qs
        }

        # ввод поставок
        delivered_lavash_m = Decimal(request.POST.get('delivered_lavash_m') or 0)
        delivered_lavash_l = Decimal(request.POST.get('delivered_lavash_l') or 0)
        delivered_lavash_s = Decimal(request.POST.get('delivered_lavash_s') or 0)
        delivered_bun = Decimal(request.POST.get('delivered_bun') or 0)
        delivered_strips = Decimal(request.POST.get('delivered_strips') or 0)
        delivered_wings = Decimal(request.POST.get('delivered_wings') or 0)

        # соответствие коротких ключей реальным названиям ingredient_type (кириллица!)
        ING_MAP = {
            'lavash_m': 'М-лаваш',         # кириллическая "М"
            'lavash_l': 'Л-лаваш',
            'lavash_s': 'Сырный лаваш',
            'bun': 'Булочка',
            'strips': 'Стрипсы (кг)',
            'wings': 'Крылышки (шт)',
        }

        supplies_short = {
            'lavash_m': delivered_lavash_m,
            'lavash_l': delivered_lavash_l,
            'lavash_s': delivered_lavash_s,
            'bun': delivered_bun,
            'strips': delivered_strips,
            'wings': delivered_wings,
        }

        # считаем остатки строго по тем же именам, что в usage_dict
        ingredients_left = {}
        ingredients_rows = []
        for short_key, delivered in supplies_short.items():
            name = ING_MAP[short_key]
            used = Decimal(usage_dict.get(name, Decimal('0')))
            left = delivered - used
            # 🔹 Заполняем оба словаря
            ingredients_left[name] = {
                'delivered': delivered,
                'used': used,
                'left': left
            }
            ingredients_rows.append({
                'name': name,
                'delivered': delivered,
                'used': used,
                'left': left
            })

        return render(request, 'report_by_date.html', {
            'orders': orders,
            'total': total,
            'count': count,
            'profit': profit,
            'items_profit': items_profit,
            'ingredients_usage': usage_dict,
            'ingredients_left': ingredients_left,
            'ingredients_rows': ingredients_rows,
            'delivered_lavash_m': delivered_lavash_m,
            'delivered_lavash_l': delivered_lavash_l,
            'delivered_lavash_s': delivered_lavash_s,
            'delivered_bun': delivered_bun,
            'delivered_strips': delivered_strips,
            'delivered_wings': delivered_wings,
            'start_date': start_date,
            'end_date': end_date,
            'start_time': start_time,
            'end_time': end_time,
            'login_required': login_required
        })

    return render(request, 'report_by_date.html', {'login_required': login_required})



def orders_list(request):
    """
    Список заказов, которые готовятся.
    """
    orders = Order.objects.filter(status='pending', cancelled=False).prefetch_related('items').order_by('order_time')
    return render(request, 'orders.html', {'orders': orders})

def logout(request):
    # очищаем только кассира
    if "employee_id" in request.session:
        del request.session["employee_id"]
    return redirect("menu")


def report_receipt(request):
    # 🔹 Подключаем кириллический шрифт
    font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'ttf', 'DejaVuSans.ttf')
    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
    font_name = "DejaVu"
    font_size = 10

    # 🔹 Получаем фильтры
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    start_time = request.GET.get('start_time') or '00:00'
    end_time = request.GET.get('end_time') or '23:59'

    try:
        start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
    except Exception:
        start_dt = None
        end_dt = None

    orders = Order.objects.all()
    if start_dt and end_dt:
        orders = orders.filter(order_time__range=(start_dt, end_dt))

    active_orders = orders.filter(cancelled=False)
    cancelled_orders = orders.filter(cancelled=True)
    cancelled_items = OrderItem.objects.filter(order__in=active_orders, cancelled=True)

    total = active_orders.aggregate(Sum('total'))['total__sum'] or 0
    count = active_orders.count()

    # 🔹 Собираем все строки для измерения ширины
    lines = [
        "Bilal Fried Chicken POS",
        "Отчёт по датам",
        f"{start_date} {start_time} — {end_date} {end_time}",
        f"Количество заказов: {count}",
        f"Общая сумма: {total:.2f} сом",
    ]

    for o in active_orders:
        lines.append(f"Заказ №{o.id} — {o.total:.2f} сом ({o.order_time.strftime('%d.%m.%Y %H:%M')})")

    if cancelled_orders.exists():
        lines.append("❌ Отменённые заказы:")
        for o in cancelled_orders:
            lines.append(f"Заказ №{o.id} — {o.total:.2f} сом (отменён в {o.order_time.strftime('%d.%m.%Y %H:%M')})")
            for item in o.items.all():
                opts = f" ({', '.join(item.options)})" if item.options else ""
                lines.append(f"  {item.product.name}{opts} x{item.quantity} — {item.line_total:.2f} сом")

    if cancelled_items.exists():
        lines.append("❌ Отменённые блюда:")
        for item in cancelled_items:
            opts = f" ({', '.join(item.options)})" if item.options else ""
            lines.append(f"{item.product.name}{opts} x{item.quantity} — ОТМЕНЕНО в {item.created_at.strftime('%d.%m.%Y %H:%M')}")

    # 🔹 Расчёт высоты страницы (динамический)
    lines_count = len(lines)
    height = max(400, 100 + lines_count * 25 + 300)

    # 🔹 Расчёт ширины страницы (автоматически)
    max_text_width = max(pdfmetrics.stringWidth(line, font_name, font_size) for line in lines)
    width = max(80 * mm, max_text_width + 40)  # минимум 80 мм, плюс отступ

    # 🔹 Генерация PDF
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFont(font_name, font_size)

    y = height - 40
    for line in lines:
        if y < 50:
            c.showPage()
            y = height - 40
            c.setFont(font_name, font_size)
        c.drawString(20, y, line)
        y -= 20

    c.showPage()
    c.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=False, filename="report_receipt.pdf")



def employee_login(request):
    pin = request.GET.get("pin")
    try:
        employee = Employee.objects.get(pin=pin)
        request.session["employee_id"] = employee.id

        # если кассир — админ и связан с User
        if employee.role == "админ" and employee.user and employee.user.is_staff:
            login(request, employee.user)  # 🔐 вход в Django‑пользователя
            return redirect("/admin/")

        return redirect(f"/menu/?emp={employee.id}")
    except Employee.DoesNotExist:
        return JsonResponse({"error": "Неверный PIN"}, status=400)



def reports(request):
    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    summary = Order.objects.filter(order_time__gte=start).aggregate(total=Sum('total'))
    top_products = (OrderItem.objects
                    .values('product__name')
                    .annotate(sum_qty=Sum('quantity'))
                    .order_by('-sum_qty')[:5])
    return render(request, 'reports.html', {
        'day_total': summary['total'] or Decimal('0.00'),
        'top_products': top_products,
    })

def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.cancelled = True
    order.save()
    return JsonResponse({'ok': True})

def cancel_order_item(request, item_id):
    try:
        item = OrderItem.objects.get(id=item_id)
        item.cancelled = True
        item.save()

        order = item.order
        # Проверка: если все блюда отменены → отменяем весь заказ
        all_cancelled = not order.items.filter(cancelled=False).exists()
        if all_cancelled:
            order.cancelled = True
            order.save()
            return JsonResponse({"ok": True, "order_cancelled": True})

        return JsonResponse({"ok": True, "order_cancelled": False})
    except OrderItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Блюдо не найдено"})


def toggle_paid(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        order.is_paid = not order.is_paid
        order.save()
        return JsonResponse({"ok": True, "is_paid": order.is_paid})
    except Order.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Заказ не найден"})

def mark_ready(request, order_id):
    try:
        order = Order.objects.get(id=order_id)
        order.status = 'ready'
        order.save()
        return JsonResponse({"ok": True})
    except Order.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Заказ не найден"})


# views.py
def orders_ready_list(request):
    orders = Order.objects.filter(status='ready').prefetch_related('items').order_by('-order_time')
    return render(request, 'orders_ready.html', {'orders': orders})



def edit_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    products = Product.objects.all().order_by('category', 'name')
    categories = Product.objects.values_list('category', flat=True).distinct()
    # показываем только неотменённые позиции
    items = order.items.filter(cancelled=False).select_related('product')

    return render(request, 'edit_order.html', {
        'order': order,
        'items': items,
        'products': products,
        'categories': categories,
    })

# views.py

def _serialize_items(order):
    items = order.items.filter(cancelled=False).select_related('product')
    return [{
        'id': it.id,
        'name': it.product.name,
        'quantity': it.quantity,
        'line_total': str(it.price * it.quantity)
    } for it in items]

def _recalc_and_serialize(order):
    total = sum((it.price * it.quantity) for it in order.items.filter(cancelled=False))
    order.total = total
    order.save()
    return _serialize_items(order), str(total)
@csrf_exempt
@require_POST
def add_item_to_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    product_id = data.get('product_id')
    qty = int(data.get('qty') or 1)
    if qty <= 0:
        return JsonResponse({'ok': False, 'error': 'Некорректное количество'})

    product = get_object_or_404(Product, id=product_id)

    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=qty,
        price=product.price,
        options=[],
        cancelled=False
    )

    # 🔹 Сбрасываем оплату при изменении заказа
    order.is_paid = False
    order.save()

    items, total = _recalc_and_serialize(order)
    return JsonResponse({'ok': True, 'items': items, 'total': total})

@csrf_exempt
@require_POST
def remove_item_from_order(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    item.cancelled = True
    item.save()

    order = item.order

    # 🔹 Сбрасываем оплату при изменении заказа
    order.is_paid = False
    order.save()

    items, total = _recalc_and_serialize(order)
    return JsonResponse({'ok': True, 'items': items, 'total': total})
@csrf_exempt
@require_POST
def recalc_order_total(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    items, total = _recalc_and_serialize(order)
    return JsonResponse({'ok': True, 'items': items, 'total': total})

def print_receipt_direct(order):
    import win32print
    import win32ui

    printer2 = "POS-58(copy of 5)"
    printer1 = "POS-58(copy of 4)"

    def _print_on_printer(printer_name, items_filter=None):
        hPrinter = win32print.OpenPrinter(printer_name)
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)

        font_height = 24
        line_spacing = font_height + 6
        margin_left = 10

        lines = [
            "Bilal Fried Chicken POS",
            f"Заказ №{order.id}",
            f"Кассир: {order.employee.name if order.employee else '-'}",
            f"Дата: {order.order_time.strftime('%d.%m.%Y %H:%M')}",
            "---------------------------"
        ]

        items = order.items.filter(cancelled=False)
        if items_filter:
            items = items.exclude(product__category__iexact=items_filter)  # 🔹 безопаснее по регистру

        for item in items:
            line = f"{item.product.name} x{item.quantity} = {item.price * item.quantity:.2f} сом"
            if len(line) > 40:
                line = line[:37] + "..."
            lines.append(line)

        lines.append("---------------------------")
        total = sum(i.price * i.quantity for i in items)
        lines.append(f"ИТОГО: {total:.2f} сом")
        lines.append("Спасибо за покупку!")

        pdc.StartDoc(f"Чек заказа №{order.id}")
        pdc.StartPage()
        font = win32ui.CreateFont({
            "name": "Arial",
            "height": font_height,
            "weight": 600
        })
        pdc.SelectObject(font)

        y = margin_left
        for line in lines:
            pdc.TextOut(margin_left, y, line)
            y += line_spacing

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()

    # 🔹 Печатаем полный чек на первом принтере
    try:
        _print_on_printer(printer1)
    except Exception as e:
        print(f"Ошибка печати на {printer1}: {e}")

    # 🔹 Печатаем чек без напитков на втором принтере
    try:
        _print_on_printer(printer2, items_filter="Напитки")
    except Exception as e:
        print(f"Ошибка печати на {printer2}: {e}")





def print_receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    print_receipt_direct(order)   # печать чека
    order.status = 'pending'      # 🔹 оставляем заказ в списке "Заказы"
    order.save()
    return JsonResponse({'ok': True, 'order_id': order.id, 'status': order.status})




@require_GET
def reprint_receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    print_receipt_direct(order)  # 🔹 просто печатаем чек
    return JsonResponse({'ok': True, 'reprinted': True})


