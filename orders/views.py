from django.shortcuts import render
from django.http import  HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import win32ui
from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

import json
from decimal import Decimal

from .models import Product, Order, OrderItem, Employee
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from datetime import datetime
from django.contrib.auth import login
from .sound import generate_voice



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
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    emp = Employee.objects.filter(id=data.get('employee_id')).first()
    items = data.get('items', [])
    if not items:
        return HttpResponseBadRequest('No items')

    total = sum(Decimal(str(i['price'])) * int(i['qty']) for i in items)

    # создаём заказ через save(), чтобы сработала логика receipt_number
    order = Order(
        employee=emp,
        total=total,
        note=data.get('note', ''),
        status='pending',
        order_type=data.get('order_type', 'here')
    )
    order.save()

    for i in items:
        product = get_object_or_404(Product, id=int(i['id']))
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=int(i['qty']),
            price=Decimal(str(i['price'])),
            options=i.get('options', [])
        )

    print_receipt_direct(order)

    # возвращаем циклический номер
    return JsonResponse({'ok': True, 'order_number': order.receipt_number, 'status': order.status})





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


    PRINTER_CASH = "XP-80C (copy 2)"   # кассовый принтер
    PRINTER_KITCHEN = "XP-80C (copy 1)"  # кухонный (можно указать другой, если есть)

    def _print_on_printer(printer_name, items_filter=None):
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)
        pdc.StartDoc(f"Чек №{order.id}")
        pdc.StartPage()

        x, y = 50, 50
        line_height = 80

        def write(line, indent=0):
            nonlocal y
            pdc.TextOut(x + indent, y, line)
            y += line_height

        # Заголовок
        write("Bilal Fried Chicken POS")
        write(f"Заказ №{order.id}")
        write(f"Кассир: {order.employee.name if order.employee else '-'}")
        write(f"Дата: {order.order_time.strftime('%d.%m.%Y %H:%M')}")
        write("--------------------------------")

        # Позиции заказа
        items = order.items.filter(cancelled=False)
        if items_filter:
            items = items.exclude(product__category__in=items_filter)

        for item in items:
            opts = f" ({', '.join(item.options)})" if item.options else ""
            write(f"{item.product.name}{opts} x{item.quantity} — {item.line_total:.2f} сом")

        total = sum(i.line_total for i in items)
        write("--------------------------------")
        write(f"Итого: {total:.2f} сом")

        if order.note:
            write(f"Комментарий: {order.note}")

        write("Спасибо за покупку!")

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()

    # 🔹 Печатаем полный чек на кассовом принтере
    try:
        _print_on_printer(PRINTER_CASH)
    except Exception as e:
        print(f"Ошибка печати на кассовом принтере: {e}")

    # 🔹 Печатаем кухонный чек без напитков, соусов и макаронсов
    try:
        _print_on_printer(PRINTER_KITCHEN, items_filter=["Напитки", "Соусы", "Макаронсы"])
    except Exception as e:
        print(f"Ошибка печати на кухонном принтере: {e}")

    return JsonResponse({'ok': True, 'order_id': order.id, 'status': order.status})







def get_employee_id(request):
    pin = request.GET.get('pin')
    try:
        employee = Employee.objects.get(pin=pin)
        request.session['employee_id'] = employee.id  # сохраняем кассира
        return JsonResponse({'id': employee.id})
    except Employee.DoesNotExist:
        return JsonResponse({'error': 'Неверный PIN'}, status=400)

from datetime import datetime
from decimal import Decimal
from collections import defaultdict

from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from .models import Order, OrderItem, DeletedItem

from datetime import datetime
from decimal import Decimal
from collections import defaultdict

from django.db.models import Sum, F, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from .models import Order, OrderItem, DeletedItem


@csrf_exempt
def report_by_date(request):
    login_required = not request.session.get('report_access_granted')

    def get_cashier_name(emp):
        if not emp:
            return "Неизвестный"
        if getattr(emp, 'name', None) and emp.name.strip():
            return emp.name.strip()
        if getattr(emp, 'user', None) and emp.user and getattr(emp.user, 'username', None):
            return emp.user.username.strip()
        return "Неизвестный"

    def D(val):
        s = (val or '').strip().replace(',', '.')
        try:
            return Decimal(s) if s else Decimal('0')
        except Exception:
            return Decimal('0')

    # --- POST (сформировать отчёт) ---
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

        # активные заказы в диапазоне
        orders = Order.objects.filter(cancelled=False)
        if start_dt and end_dt:
            orders = orders.filter(order_time__range=(start_dt, end_dt))

        total = orders.aggregate(Sum('total'))['total__sum'] or Decimal('0')
        count = orders.count()

        # прибыль по неотменённым позициям
        profit = OrderItem.objects.filter(order__in=orders, cancelled=False).aggregate(
            total_profit=Sum(
                ExpressionWrapper(
                    (F('price') - F('product__cost_price')) * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )['total_profit'] or Decimal('0')

        # прибыль по товарам
        items_profit = OrderItem.objects.filter(order__in=orders, cancelled=False).values(
            'product__name',
            'product__price',
            'product__cost_price'
        ).annotate(
            total_qty=Sum('quantity'),
            total_profit=Sum(
                ExpressionWrapper(
                    (F('price') - F('product__cost_price')) * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        ).order_by('-total_profit')

        # расход ингредиентов
        ingredients_usage_qs = (
            OrderItem.objects
            .filter(order__in=orders, cancelled=False)
            .values('product__ingredient_type')
            .annotate(
                used=Sum(
                    ExpressionWrapper(
                        F('quantity') * Coalesce(F('product__ingredient_usage'), Value(0)),
                        output_field=DecimalField(max_digits=12, decimal_places=2)
                    )
                )
            )
        )
        usage_by_full_name = {
            (row['product__ingredient_type'] or '').strip(): (row['used'] or Decimal('0'))
            for row in ingredients_usage_qs
        }

        delivered_lavash_m = D(request.POST.get('delivered_lavash_m'))
        delivered_lavash_l = D(request.POST.get('delivered_lavash_l'))
        delivered_lavash_s = D(request.POST.get('delivered_lavash_s'))
        delivered_bun      = D(request.POST.get('delivered_bun'))
        delivered_strips   = D(request.POST.get('delivered_strips'))
        delivered_wings    = D(request.POST.get('delivered_wings'))

        ING_MAP = {
            'lavash_m': 'М-лаваш',
            'lavash_l': 'Л-лаваш',
            'lavash_s': 'Сырный лаваш',
            'bun': 'Булочка',
            'strips': 'Стрипсы',
            'wings': 'Крылышки',
        }
        supplies_short = {
            'lavash_m': delivered_lavash_m,
            'lavash_l': delivered_lavash_l,
            'lavash_s': delivered_lavash_s,
            'bun':      delivered_bun,
            'strips':   delivered_strips,
            'wings':    delivered_wings,
        }

        usage_short = {}
        ingredients_left = {}
        ingredients_rows = []
        for short_key, full_name in ING_MAP.items():
            used = Decimal(usage_by_full_name.get(full_name, Decimal('0')))
            usage_short[short_key] = used
        for short_key, delivered in supplies_short.items():
            full_name = ING_MAP[short_key]
            used = usage_short.get(short_key, Decimal('0'))
            left = delivered - used
            if left < 0:
                left = Decimal('0')
            ingredients_left[full_name] = {'delivered': delivered, 'used': used, 'left': left}
            ingredients_rows.append({'name': full_name, 'delivered': delivered, 'used': used, 'left': left})

        # отмены: заказы, позиции, удалённые позиции
        cancelled_orders = Order.objects.filter(cancelled=True, cancelled_by__isnull=False)
        cancelled_items = OrderItem.objects.filter(cancelled=True, cancelled_by__isnull=False)
        deleted_items   = DeletedItem.objects.filter(cashier__isnull=False)

        if start_dt and end_dt:
            cancelled_orders = cancelled_orders.filter(cancelled_at__range=(start_dt, end_dt))
            cancelled_items = cancelled_items.filter(cancelled_at__range=(start_dt, end_dt))
            deleted_items   = deleted_items.filter(deleted_at__range=(start_dt, end_dt))

        cancelled_by = defaultdict(lambda: {"orders": [], "items": [], "deleted": []})
        for o in cancelled_orders:
            cashier_name = get_cashier_name(o.cancelled_by)
            cancelled_by[cashier_name]["orders"].append(o)
        for it in cancelled_items:
            cashier_name = get_cashier_name(it.cancelled_by)
            cancelled_by[cashier_name]["items"].append(it)
        for di in deleted_items:
            cashier_name = get_cashier_name(di.cashier)
            cancelled_by[cashier_name]["deleted"].append(di)

        cancellations_blocks = []
        for cashier_name in sorted(cancelled_by.keys()):
            data = cancelled_by[cashier_name]
            lines = []
            for o in data["orders"]:
                lines.append({
                    "kind": "order",
                    "title": f"Заказ №{o.receipt_number or o.id}",
                    "amount": o.total,
                    "time": o.cancelled_at
                })
            for it in data["items"]:
                amount = (it.price or Decimal('0')) * (it.quantity or 0)
                lines.append({
                    "kind": "item",
                    "title": f"{getattr(it.product, 'name', 'Неизвестно')} x{it.quantity}",
                    "amount": amount,
                    "time": it.cancelled_at
                })
            for di in data["deleted"]:
                lines.append({
                    "kind": "deleted",
                    "title": f"{di.product_name} x{di.quantity} (удалено)",
                    "amount": None,
                    "time": di.deleted_at
                })
            lines.sort(key=lambda l: l["time"] or timezone.now(), reverse=True)
            cancellations_blocks.append({"cashier": cashier_name, "lines": lines})

        return render(request, 'report_by_date.html', {
            'orders': orders,
            'total': total,
            'count': count,
            'profit': profit,
            'items_profit': items_profit,
            'ingredients_usage': usage_short,
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
            'login_required': login_required,
            'cancellations_blocks': cancellations_blocks,
        })

    # --- GET (по умолчанию): собираем отмены за текущий день ---
    # Параметры для формы по умолчанию
    now = timezone.now()
    start_date = now.date().isoformat()
    end_date = (now + timezone.timedelta(days=1)).date().isoformat()
    start_time = "09:00"
    end_time = "02:00"

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timezone.timedelta(days=1)

    cancelled_orders = Order.objects.filter(
        cancelled=True,
        cancelled_by__isnull=False,
        cancelled_at__range=(today_start, today_end)
    )
    cancelled_items = OrderItem.objects.filter(
        cancelled=True,
        cancelled_by__isnull=False,
        cancelled_at__range=(today_start, today_end)
    )
    deleted_items = DeletedItem.objects.filter(
        cashier__isnull=False,
        deleted_at__range=(today_start, today_end)
    )

    cancelled_by = defaultdict(lambda: {"orders": [], "items": [], "deleted": []})
    for o in cancelled_orders:
        cashier_name = get_cashier_name(o.cancelled_by)
        cancelled_by[cashier_name]["orders"].append(o)
    for it in cancelled_items:
        cashier_name = get_cashier_name(it.cancelled_by)
        cancelled_by[cashier_name]["items"].append(it)
    for di in deleted_items:
        cashier_name = get_cashier_name(di.cashier)
        cancelled_by[cashier_name]["deleted"].append(di)

    cancellations_blocks = []
    for cashier_name in sorted(cancelled_by.keys()):
        data = cancelled_by[cashier_name]
        lines = []
        for o in data["orders"]:
            lines.append({
                "kind": "order",
                "title": f"Заказ №{o.receipt_number or o.id}",
                "amount": o.total,
                "time": o.cancelled_at
            })
        for it in data["items"]:
            amount = (it.price or Decimal('0')) * (it.quantity or 0)
            lines.append({
                "kind": "item",
                "title": f"{getattr(it.product, 'name', 'Неизвестно')} x{it.quantity}",
                "amount": amount,
                "time": it.cancelled_at
            })
        for di in data["deleted"]:
            lines.append({
                "kind": "deleted",
                "title": f"{di.product_name} x{di.quantity} (удалено)",
                "amount": None,
                "time": di.deleted_at
            })
        lines.sort(key=lambda l: l["time"] or timezone.now(), reverse=True)
        cancellations_blocks.append({"cashier": cashier_name, "lines": lines})

    # Для GET у тебя нет отчётных сумм, но модалка «Отмены» будет заполнена
    return render(request, 'report_by_date.html', {
        'login_required': login_required,
        'cancellations_blocks': cancellations_blocks,
        'start_date': start_date,
        'end_date': end_date,
        'start_time': start_time,
        'end_time': end_time,
    })




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
from datetime import datetime
from django.shortcuts import redirect
from django.http import JsonResponse
from django.db.models import Sum, F
from django.utils import timezone
import win32ui

def report_receipt(request):
    PRINTER_NAME = "XP-80C (copy 2)"

    start_date = request.GET.get('start')
    end_date = request.GET.get('end')
    start_time = request.GET.get('start_time') or '00:00'
    end_time = request.GET.get('end_time') or '23:59'

    try:
        start_dt_naive = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt_naive   = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
        start_dt = timezone.make_aware(start_dt_naive)
        end_dt   = timezone.make_aware(end_dt_naive)
    except Exception:
        start_dt = end_dt = None

    orders = Order.objects.all()

    # Активные заказы
    active_orders = orders.filter(cancelled=False)
    if start_dt and end_dt:
        active_orders = active_orders.filter(order_time__range=(start_dt, end_dt))

    total = active_orders.aggregate(Sum('total'))['total__sum'] or 0
    count = active_orders.count()

    # 📊 Продажи по товарам
    items_sales = (
        OrderItem.objects.filter(order__in=active_orders, cancelled=False)
        .values("product__name", "product__price")
        .annotate(
            total_qty=Sum("quantity"),
            total_sales=Sum(F("price") * F("quantity")),
        )
        .order_by("-total_sales")
    )

    # Итоговые суммы
    grand_sales = sum([i["total_sales"] or 0 for i in items_sales])

    try:
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(PRINTER_NAME)
        pdc.StartDoc("Отчёт по товарам")
        pdc.StartPage()

        font = win32ui.CreateFont({
            "name": "Consolas",
            "height": 28,
            "weight": 700
        })
        pdc.SelectObject(font)

        # координаты колонок
        x_name   = 10
        x_price  = 250
        x_qty    = 380
        x_sales  = 480   # 🔥 сдвинули левее, чтобы не обрезалось

        y = 20
        line_height = 28

        # Заголовок
        pdc.TextOut(x_name, y, "Mediar Fried Chicken POS"); y += line_height
        pdc.TextOut(x_name, y, "Отчёт по товарам"); y += line_height
        pdc.TextOut(x_name, y, f"{start_date or '-'} {start_time} — {end_date or '-'} {end_time}"); y += line_height
        pdc.TextOut(x_name, y, f"Количество заказов: {count}"); y += line_height

        # Итоговые суммы сразу сверху
        pdc.TextOut(x_name, y, f"Общая сумма продаж: {grand_sales:.0f} сом"); y += line_height
        y += line_height

        # Шапка таблицы
        pdc.TextOut(x_name,   y, "Товар")
        pdc.TextOut(x_price,  y, "Цена")
        pdc.TextOut(x_qty,    y, "Кол-во")
        pdc.TextOut(x_sales,  y, "Продажи")
        y += line_height

        # Данные по товарам
        for item in items_sales:
            pdc.TextOut(x_name,   y, str(item["product__name"]))
            pdc.TextOut(x_price,  y, f"{item['product__price'] or 0:.0f}")
            pdc.TextOut(x_qty,    y, str(item["total_qty"]))
            pdc.TextOut(x_sales,  y, f"{item['total_sales'] or 0:.0f}")
            y += line_height

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()
    except Exception as e:
        return JsonResponse({'error': f'Ошибка печати отчёта: {e}'}, status=500)

    return redirect("report_by_date")







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





def employee_login(request):
    pin = request.GET.get("pin")
    try:
        employee = Employee.objects.get(pin=pin)
        if employee.user:
            login(request, employee.user)  # вход в Django‑пользователя
        request.session["employee_id"] = employee.id

        if employee.role == "админ" and employee.user and employee.user.is_staff:
            return redirect("/admin/")

        return redirect(f"/menu/?emp={employee.id}")
    except Employee.DoesNotExist:
        return JsonResponse({"error": "Неверный PIN"}, status=400)

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Order, OrderItem, Employee


def cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.cancelled = True

    # берём кассира из сессии
    emp_id = request.session.get("employee_id")
    emp = Employee.objects.filter(id=emp_id).first()
    order.cancelled_by = emp
    order.cancelled_at = timezone.now()  # ✅ фикс: время отмены

    order.save()
    return JsonResponse({'ok': True, 'order_cancelled': True})


from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Order, OrderItem, Employee

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import OrderItem, Employee

def cancel_order_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    item.cancelled = True

    # берём кассира из сессии
    emp_id = request.session.get("employee_id")
    emp = Employee.objects.filter(id=emp_id).first()

    item.cancelled_by = emp
    item.cancelled_at = timezone.now()   # ✅ фикс: время отмены блюда
    item.save()

    return JsonResponse({"ok": True, "item_cancelled": True})


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
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
import json
from .models import Order, Product, OrderItem

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

    # 🔄 Если блюдо уже есть в заказе — увеличиваем количество
    existing = order.items.filter(product=product, cancelled=False).first()
    if existing:
        existing.quantity += qty
        existing.save()
    else:
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

    # 🔄 Обновляем список блюд
    items = [{
        "id": it.id,
        "name": it.product.name,
        "quantity": it.quantity,
        "line_total": float(it.price * it.quantity),
    } for it in order.items.filter(cancelled=False)]

    total = sum(it["line_total"] for it in items)

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
    import win32ui
    from decimal import Decimal
    import pytz

    tz = pytz.timezone("Asia/Bishkek")
    order_dt = order.order_time
    if getattr(order_dt, "tzinfo", None) is None:
        order_dt = tz.localize(order_dt)
    else:
        order_dt = order_dt.astimezone(tz)

    order_no = getattr(order, "receipt_number", None) or getattr(order, "number", None) or 0

    PRINTER_CLIENT = "XP-80C (copy 2)"
    PRINTER_KITCHEN = "XP-80C (copy 2)"

    font_bold = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 800})
    font_total = win32ui.CreateFont({"name": "Consolas", "height": 36, "weight": 800})
    font_order_no = win32ui.CreateFont({"name": "Consolas", "height": 60, "weight": 800})
    font_order_type = win32ui.CreateFont({"name": "Consolas", "height": 48, "weight": 800})

    margin_left = 10
    line_h = 28
    x_name = margin_left
    x_qty = margin_left + 250
    x_price = margin_left + 340
    x_total = margin_left + 440
    RIGHT_EDGE = margin_left + 560

    def draw_text(pdc, x, y, text, font=font_bold):
        pdc.SelectObject(font)
        pdc.TextOut(x, y, str(text))

    def draw_right(pdc, y, text, x_right, font=font_bold):
        pdc.SelectObject(font)
        w, _ = pdc.GetTextExtent(str(text))
        pdc.TextOut(x_right - w, y, str(text))

    def draw_row(pdc, y, name, qty, price, total):
        pdc.SelectObject(font_bold)
        max_width = x_qty - x_name - 10
        name_str = str(name)
        while pdc.GetTextExtent(name_str)[0] > max_width:
            name_str = name_str[:-1]
        draw_text(pdc, x_name, y, name_str)
        draw_text(pdc, x_qty, y, f"{int(qty)}")
        draw_text(pdc, x_price, y, f"{int(price)}")
        draw_text(pdc, x_total, y, f"{int(total)}")
        return y + line_h

    # ===== Клиентский чек =====
    try:
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(PRINTER_CLIENT)
        pdc.StartDoc(f"Клиентский чек №{order_no}")
        y = 0
        pdc.StartPage()

        draw_text(pdc, x_name, y, f"ЗАКАЗ №{order_no}", font=font_order_no); y += 70
        draw_text(pdc, x_name, y, "=============================="); y += line_h
        draw_text(pdc, x_name, y, "MEDIAR FRIED CHICKEN 🍗🥤"); y += line_h
        draw_text(pdc, x_name, y, "ул. Алма-Атинская 295/1"); y += line_h
        draw_text(pdc, x_name, y, "Мбанк: 0555181618"); y += line_h
        draw_text(pdc, x_name, y, "=============================="); y += line_h

        operator = getattr(order, "employee", None)
        draw_text(pdc, x_name, y, f"Оператор: {getattr(operator, 'name', '-') if operator else '-'}"); y += line_h
        draw_text(pdc, x_name, y, order_dt.strftime('%Y.%m.%d %H:%M:%S')); y += line_h

        # 🔥 определяем тип заказа
        order_type = ""
        for item in order.items.filter(cancelled=False):
            product = getattr(item, "product", None)
            if not product:
                continue
            category = getattr(product, "category", None)
            cat_name = (getattr(category, "name", "") or "").strip().lower()
            prod_name = (getattr(product, "name", "") or "").strip().lower()

            if "доставка" in cat_name or "доставка" in prod_name:
                order_type = "Доставка"
                break
            elif "с собой" in cat_name or "с собой" in prod_name:
                order_type = "С собой"
            elif "здесь" in cat_name or "здесь" in prod_name:
                order_type = "здесь"
                break

        draw_text(pdc, x_name, y, "Наименование")
        draw_text(pdc, x_qty, y, "К-во")
        draw_text(pdc, x_price, y, "Цена")
        draw_text(pdc, x_total, y, "Сумма"); y += line_h
        draw_text(pdc, x_name, y, "--------------------------------------"); y += line_h

        total_sum = Decimal("0")
        for item in order.items.filter(cancelled=False):
            qty = Decimal(item.quantity)
            price = Decimal(item.price or item.product.price)
            line_total = price * qty
            total_sum += line_total
            y = draw_row(pdc, y, item.product.name, qty, price, line_total)

        draw_text(pdc, x_name, y, "=============================="); y += line_h
        draw_text(pdc, x_name, y, "ИТОГО:", font=font_total)
        draw_right(pdc, y, f"{int(total_sum)} сом", RIGHT_EDGE, font=font_total); y += 42

        # 🔥 теперь тип заказа печатаем всегда под ИТОГО
        draw_text(pdc, x_name, y, f"Тип заказа: {order_type}", font=font_order_type); y += 60

        draw_text(pdc, x_name, y, "=============================="); y += line_h
        draw_text(pdc, x_name, y, "Оплата: Наличные"); y += line_h
        draw_text(pdc, x_name, y, "Спасибо за покупку! 🍗🥤"); y += line_h
        draw_text(pdc, x_name, y, "=============================="); y += line_h

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()
    except Exception as e:
        print(f"Ошибка печати клиентского чека: {e}")

    # ===== Кухонный чек =====
    try:
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(PRINTER_KITCHEN)
        pdc.StartDoc(f"Кухонный чек №{order_no}")
        y = 0
        pdc.StartPage()

        def draw_text_kitchen(pdc, x, y, text, size=30):
            font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": 800})
            pdc.SelectObject(font_line)
            pdc.TextOut(x, y, str(text))

        draw_text_kitchen(pdc, margin_left, y, f"ЗАКАЗ №{order_no}", size=48); y += 40
        draw_text_kitchen(pdc, margin_left, y, order_dt.strftime('%d.%m.%Y %H:%M'), size=26); y += 35

        draw_text_kitchen(pdc, margin_left, y, f"Тип заказа: {order_type}", size=42); y += 45

        draw_text_kitchen(pdc, margin_left, y, "--------------------", size=26); y += 30

        kitchen_items = []
        for item in order.items.filter(cancelled=False):
            category = getattr(item.product, "category", None)
            cat_name = (getattr(category, "name", "") if category else "").strip().lower()
            if "макаронсы" in cat_name or "напитки" in cat_name:
                continue
            kitchen_items.append((item.product.name, item.quantity))

        if not kitchen_items:
            draw_text_kitchen(pdc, margin_left, y, "Нет блюд для кухни", size=28); y += 35
        else:
            for product_name, qty in kitchen_items:
                dish_line = f"{product_name} x{int(qty)}"
                draw_text_kitchen(pdc, margin_left, y, dish_line, size=40)
                y += 35

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()
    except Exception as e:
        print(f"Ошибка печати кухонного чека: {e}")










def print_receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    print_receipt_direct(order)   # печать чека
    order.status = 'pending'      # 🔹 оставляем заказ в списке "Заказы"
    order.save()
    return JsonResponse({'ok': True, 'order_id': order.id, 'status': order.status})


from django.views.decorators.http import require_GET
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Order

@require_GET
def reprint_receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # 🔹 проверяем, что пользователь авторизован и есть связанный Employee
    if not request.user.is_authenticated or not hasattr(request.user, "employee"):
        return JsonResponse({'error': 'Нет прав'}, status=403)

    role = (request.user.employee.role or "").lower()

    try:
        if role in ["кассир", "админ"]:
            try:
                import win32ui
                from decimal import Decimal
                import pytz

                tz = pytz.timezone("Asia/Bishkek")
                order_dt = order.order_time
                if getattr(order_dt, "tzinfo", None) is None:
                    order_dt = tz.localize(order_dt)
                else:
                    order_dt = order_dt.astimezone(tz)

                # ✅ используем receipt_number
                order_no = getattr(order, "receipt_number", None) or 0

                PRINTER_CLIENT = "XP-80C (copy 2)"

                font_bold = win32ui.CreateFont({
                    "name": "Consolas",
                    "height": 28,
                    "weight": 800
                })

                font_total = win32ui.CreateFont({
                    "name": "Consolas",
                    "height": 36,
                    "weight": 800
                })

                font_order_no = win32ui.CreateFont({
                    "name": "Consolas",
                    "height": 60,
                    "weight": 800
                })

                margin_left = 10
                line_h = 28
                x_name  = margin_left
                x_qty   = margin_left + 250
                x_price = margin_left + 340
                x_total = margin_left + 440
                RIGHT_EDGE = margin_left + 560

                def draw_text(pdc, x, y, text, font=font_bold):
                    pdc.SelectObject(font)
                    pdc.TextOut(x, y, str(text))

                def draw_right(pdc, y, text, x_right, font=font_bold):
                    pdc.SelectObject(font)
                    w, _ = pdc.GetTextExtent(str(text))
                    pdc.TextOut(x_right - w, y, str(text))

                def draw_row(pdc, y, name, qty, price, total):
                    pdc.SelectObject(font_bold)
                    max_width = x_qty - x_name - 10
                    name_str = str(name)
                    while pdc.GetTextExtent(name_str)[0] > max_width:
                        name_str = name_str[:-1]
                    draw_text(pdc, x_name,  y, name_str)
                    draw_text(pdc, x_qty,   y, f"{int(qty)}")
                    draw_text(pdc, x_price, y, f"{int(price)}")
                    draw_text(pdc, x_total, y, f"{int(total)}")
                    return y + line_h

                # ===== Печать клиентского чека =====
                pdc = win32ui.CreateDC()
                pdc.CreatePrinterDC(PRINTER_CLIENT)
                pdc.StartDoc(f"Клиентский чек №{order_no}")

                y = 0
                pdc.StartPage()

                # 🔥 крупный жирный номер заказа в самом верху
                draw_text(pdc, x_name, y, f"ЗАКАЗ №{order_no}", font=font_order_no); y += 70

                draw_text(pdc, x_name, y, "=============================="); y += line_h
                draw_text(pdc, x_name, y, "MEDIAR FRIED CHICKEN 🍗🥤"); y += line_h
                draw_text(pdc, x_name, y, "ул. Алма-Атинская 295/1"); y += line_h
                draw_text(pdc, x_name, y, "Мбанк: 0555181618"); y += line_h
                draw_text(pdc, x_name, y, "=============================="); y += line_h

                operator = getattr(order, "employee", None)
                draw_text(pdc, x_name, y, f"Оператор: {getattr(operator, 'name', '-') if operator else '-'}"); y += line_h
                draw_text(pdc, x_name, y, order_dt.strftime('%Y.%m.%d %H:%M:%S')); y += line_h

                draw_text(pdc, x_name,  y, "Наименование")
                draw_text(pdc, x_qty,   y, "К-во")
                draw_text(pdc, x_price, y, "Цена")
                draw_text(pdc, x_total, y, "Сумма"); y += line_h
                draw_text(pdc, x_name, y, "--------------------------------------"); y += line_h

                total_sum = Decimal("0")
                for item in order.items.filter(cancelled=False):
                    qty   = Decimal(item.quantity)
                    price = Decimal(item.price or item.product.price)
                    line_total = price * qty
                    total_sum += line_total
                    y = draw_row(pdc, y, item.product.name, qty, price, line_total)

                draw_text(pdc, x_name, y, "=============================="); y += line_h
                draw_text(pdc, x_name, y, "ИТОГО:", font=font_total)
                draw_right(pdc, y, f"{int(total_sum)} сом", RIGHT_EDGE, font=font_total); y += 42
                draw_text(pdc, x_name, y, "=============================="); y += line_h
                draw_text(pdc, x_name, y, "Оплата: Наличные"); y += line_h
                if getattr(order, "note", None):
                    draw_text(pdc, x_name, y, f"Комментарий: {order.note}"); y += line_h
                draw_text(pdc, x_name, y, "Спасибо за покупку! 🍗🥤"); y += line_h
                draw_text(pdc, x_name, y, "=============================="); y += line_h

                pdc.EndPage()
                pdc.EndDoc()
                pdc.DeleteDC()

            except Exception as e:
                return JsonResponse({'error': f'Ошибка печати клиентского чека: {e}'}, status=500)

        else:
            return JsonResponse({'error': 'Нет прав'}, status=403)

    except Exception as e:
        return JsonResponse({'error': f'Ошибка печати: {e}'}, status=500)

    return JsonResponse({'ok': True, 'reprinted': True})







def call_order(request, order_id):
    try:
        print(f"🔊 Вызов для заказа №{order_id}")
        generate_voice(order_id)
        return JsonResponse({"ok": True, "order_id": order_id})
    except Exception as e:
        print(f"❌ Ошибка вызова: {e}")
        return JsonResponse({"ok": False, "error": str(e)})



@csrf_exempt
@require_POST
def create_order_view(request):
    """
    Создание нового заказа из корзины.
    Ожидает JSON: { employee_id, items: [{id, qty, price}], note }
    """
    try:
        data = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    emp = Employee.objects.filter(id=data.get("employee_id")).first()
    items = data.get("items", [])
    if not items:
        return JsonResponse({"ok": False, "error": "No items"}, status=400)

    total = sum(Decimal(str(i["price"])) * int(i["qty"]) for i in items)

    # создаём заказ — receipt_number проставится автоматически в save()
    order = Order(
        employee=emp,
        total=total,
        note=data.get("note", ""),
        status="pending",
        order_type=data.get("order_type", "here")
    )
    order.save()  # 🔹 важно вызвать save(), чтобы сработала логика циклической нумерации

    for i in items:
        product = get_object_or_404(Product, id=int(i["id"]))
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=int(i["qty"]),
            price=Decimal(str(i["price"])),
            options=i.get("options", [])
        )

    return JsonResponse({
        "ok": True,
        "order_number": order.receipt_number,  # 🔹 теперь возвращаем циклический номер
        "status": order.status
    })

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import OrderItem, Employee

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import OrderItem

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import OrderItem

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import OrderItem

def reduce_order_item_quantity(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)

    try:
        new_qty = int(request.POST.get("quantity"))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "invalid_quantity"})

    if new_qty <= 0:
        item.delete()  # или item.cancelled = True, если хочешь помечать отмену
    else:
        item.quantity = new_qty
        item.save()

    order = item.order

    # 👉 вот здесь вставляется твой блок
    items = [{
        "id": it.id,
        "name": it.product.name,
        "quantity": it.quantity,
        "line_total": float(it.line_total),  # теперь работает
    } for it in order.items.filter(cancelled=False)]

    return JsonResponse({"ok": True, "items": items, "total": float(order.total)})



import subprocess
import os

def announce_order(order):
    items = ", ".join([item.product.name for item in order.items.all()])
    text = f"Заказ номер {order.receipt_number}. {items}"

    # путь к sound.py внутри папки orders
    script_path = os.path.join(os.path.dirname(__file__), "sound.py")
    subprocess.Popen(["python", script_path, text])


