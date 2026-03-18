from django.shortcuts import render
from django.http import  HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import win32ui
from django.views.decorators.http import require_GET
from django.db.models import Q
from collections import defaultdict


from decimal import Decimal
import pytz
from django.utils import timezone
from datetime import datetime
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from django.db.models import Q


import json
from decimal import Decimal

from .models import Product, Order, OrderItem, Employee
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from datetime import datetime
from django.contrib.auth import login




def menu(request):
    emp_id = request.session.get('employee_id')
    employee = Employee.objects.filter(id=emp_id).first() if emp_id else None

    # Берём только активные продукты
    products = Product.objects.filter(is_active=True)

    # Категории тоже формируем только из активных продуктов
    categories = products.values_list('category', flat=True).distinct()

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

    # возвращаем только информацию о заказе, без items
    return JsonResponse({
        'ok': True,
        'order_number': order.receipt_number,
        'status': order.status,
        'total': str(order.total)
    })


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


    PRINTER_CASH = "XP-80"   # кассовый принтер
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
import pytz
from django.utils import timezone
from django.db.models import Sum, F, ExpressionWrapper, DecimalField
from decimal import Decimal
from datetime import datetime
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

BISHKEK_TZ = pytz.timezone("Asia/Bishkek")

@csrf_exempt
def report_by_date(request):
    login_required = not request.session.get('report_access_granted')
    now_bishkek = timezone.now().astimezone(BISHKEK_TZ)

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
            start_dt = BISHKEK_TZ.localize(start_dt)
            end_dt = BISHKEK_TZ.localize(end_dt)
        except Exception:
            start_dt = None
            end_dt = None

        orders = Order.objects.filter(cancelled=False)
        if start_dt and end_dt:
            orders = orders.filter(order_time__range=(start_dt, end_dt))

        total = orders.aggregate(Sum('total'))['total__sum'] or Decimal('0')
        count = orders.count()

        profit = OrderItem.objects.filter(order__in=orders, cancelled=False).aggregate(
            total_profit=Sum(
                ExpressionWrapper(
                    (F('price') - F('product__cost_price')) * F('quantity'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )['total_profit'] or Decimal('0')

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
        # расход ингредиентов (общий для POST и GET)
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

        # --- подсчёт остатков ингредиентов ---
        delivered_lavash_m = D(request.POST.get('delivered_lavash_m') or request.GET.get('delivered_lavash_m') or '0')
        delivered_lavash_l = D(request.POST.get('delivered_lavash_l') or request.GET.get('delivered_lavash_l') or '0')
        delivered_lavash_s = D(request.POST.get('delivered_lavash_s') or request.GET.get('delivered_lavash_s') or '0')
        delivered_bun = D(request.POST.get('delivered_bun') or request.GET.get('delivered_bun') or '0')
        delivered_strips = D(request.POST.get('delivered_strips') or request.GET.get('delivered_strips') or '0')
        delivered_wings = D(request.POST.get('delivered_wings') or request.GET.get('delivered_wings') or '0')

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
            'bun': delivered_bun,
            'strips': delivered_strips,
            'wings': delivered_wings,
        }

        ingredients_rows = []
        for short_key, delivered in supplies_short.items():
            used = usage_by_full_name.get(short_key, Decimal('0'))
            left = delivered - used
            if left < 0:
                left = Decimal('0')
            ingredients_rows.append({
                'name': ING_MAP[short_key],
                'delivered': delivered,
                'used': used,
                'left': left
            })

        # отмены
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
            'ingredients_usage': usage_by_full_name,
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

    # --- GET: собираем отмены по выбранному диапазону ---
    now_bishkek = timezone.now().astimezone(BISHKEK_TZ)

    # Берём параметры из формы (если не выбраны — ставим дефолт)
    start_date = request.GET.get("start") or now_bishkek.date().isoformat()
    end_date = request.GET.get("end") or (now_bishkek + timezone.timedelta(days=1)).date().isoformat()
    start_time = request.GET.get("start_time") or "09:00"
    end_time = request.GET.get("end_time") or "02:00"

    try:
        start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M")
        # 🔹 всегда локализуем в Бишкек
        start_dt = BISHKEK_TZ.localize(start_dt)
        end_dt = BISHKEK_TZ.localize(end_dt)
    except Exception:
        start_dt = now_bishkek.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timezone.timedelta(days=1)


        # --- отмены по диапазону ---
    # --- отмены по диапазону ---
    cancelled_orders = Order.objects.filter(
        cancelled=True,
        cancelled_by__isnull=False,
        cancelled_at__range=(start_dt, end_dt)
    )

    # полностью отменённые блюда

    # полностью отменённые блюда
    cancelled_items = OrderItem.objects.filter(
        cancelled=True,
        cancelled_by__isnull=False
    ).filter(
        Q(cancelled_at__range=(start_dt, end_dt)) |
        Q(cancelled_at__isnull=True, order__order_time__range=(start_dt, end_dt))
    )

    # частично отменённые блюда
    partial_cancelled_items = OrderItem.objects.filter(
        original_quantity__gt=F('quantity'),
        cancelled_by__isnull=False
    ).filter(
        Q(cancelled_at__range=(start_dt, end_dt)) |
        Q(cancelled_at__isnull=True, order__order_time__range=(start_dt, end_dt))
    )

    deleted_items = DeletedItem.objects.filter(
        cashier__isnull=False,
        deleted_at__range=(start_dt, end_dt)
    )

    # --- группировка по кассирам ---
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

    # --- формирование блоков для модалки ---
    cancellations_blocks = []
    for cashier_name in sorted(cancelled_by.keys()):
        data = cancelled_by[cashier_name]
        lines = []

        # группировка блюд по заказу
        items_by_order = defaultdict(list)
        for it in data["items"]:
            items_by_order[it.order_id].append(it)

        # отменённые заказы + их блюда
        for o in data["orders"]:
            lines.append({
                "kind": "order",
                "title": f"Заказ №{o.receipt_number or o.id}",
                "amount": o.total,
                "time": o.cancelled_at,
                "order_id": o.id,
                "operator": getattr(o.cancelled_by, 'name', '-') if o.cancelled_by else '-'
            })
            for it in items_by_order.get(o.id, []):
                amount = (it.price or Decimal('0')) * (it.quantity or 0)
                lines.append({
                    "kind": "item",
                    "title": f"{getattr(it.product, 'name', 'Неизвестно')} x{it.quantity}",
                    "amount": amount,
                    "time": it.cancelled_at,
                    "order_id": o.id,
                    "operator": getattr(it.cancelled_by, 'name', '-') if it.cancelled_by else '-'
                })

        # блюда без отменённого заказа
        orphan_items = [it for it in data["items"] if it.order_id not in [o.id for o in data["orders"]]]
        for it in orphan_items:
            amount = (it.price or Decimal('0')) * (it.quantity or 0)
            lines.append({
                "kind": "item",
                "title": f"{getattr(it.product, 'name', 'Неизвестно')} x{it.quantity}",
                "amount": amount,
                "time": it.cancelled_at,
                "order_id": it.order_id,
                "operator": getattr(it.cancelled_by, 'name', '-') if it.cancelled_by else '-'

            })

        # удалённые позиции
        for di in data["deleted"]:
            lines.append({
                "kind": "deleted",
                "title": f"{di.product_name} x{di.quantity} (удалено)",
                "amount": None,
                "time": di.deleted_at
            })

        # сортировка по времени
        # сортировка по времени
        lines.sort(key=lambda l: l["time"] or timezone.now().astimezone(BISHKEK_TZ), reverse=True)
        cancellations_blocks.append({"cashier": cashier_name, "lines": lines})


    # --- топ отменённых блюд ---
    # --- топ отменённых блюд ---
    cancelled_top_raw = defaultdict(lambda: {"qty": 0, "total": Decimal("0")})

    # полностью отменённые
    for it in cancelled_items:
        name = getattr(it.product, "name", "Неизвестно")
        qty = it.quantity or 0
        price = it.price or Decimal("0")
        cancelled_top_raw[name]["qty"] += qty
        cancelled_top_raw[name]["total"] += price * qty

    # частично отменённые
    for it in partial_cancelled_items:
        name = getattr(it.product, "name", "Неизвестно")
        cancelled_qty = (it.original_quantity or 0) - (it.quantity or 0)
        if cancelled_qty > 0:
            price = it.price or Decimal("0")
            cancelled_top_raw[name]["qty"] += cancelled_qty
            cancelled_top_raw[name]["total"] += price * cancelled_qty

    cancelled_top = [
        {"name": name, "qty": data["qty"], "total": data["total"]}
        for name, data in cancelled_top_raw.items()
    ]
    cancelled_top.sort(key=lambda r: r["total"], reverse=True)

    cancelled_items_log = []

    # полностью отменённые
    for it in cancelled_items:
        amount = (it.price or Decimal('0')) * (it.quantity or 0)
        cancelled_items_log.append({
            "order_id": it.order_id,
            "product": getattr(it.product, 'name', 'Неизвестно'),
            "quantity": it.quantity,
            "amount": amount,
            "time": it.cancelled_at,
            "operator": getattr(it.cancelled_by, 'name', '-') if it.cancelled_by else '-',
            "status": "cancelled"
        })

    # частично отменённые
    for it in partial_cancelled_items:
        cancelled_qty = (it.original_quantity or 0) - (it.quantity or 0)
        amount = (it.price or Decimal('0')) * cancelled_qty
        cancelled_items_log.append({
            "order_id": it.order_id,
            "product": getattr(it.product, 'name', 'Неизвестно'),
            "quantity": cancelled_qty,
            "amount": amount,
            "time": it.cancelled_at,
            "operator": getattr(it.cancelled_by, 'name', '-') if it.cancelled_by else '-',
            "status": "partial"
        })

    return render(request, 'report_by_date.html', {
        'login_required': login_required,
        'cancellations_blocks': cancellations_blocks,
        'cancelled_top': cancelled_top,
        'start_date': start_date,
        'end_date': end_date,
        'start_time': start_time,
        'end_time': end_time,
        'cancelled_items_log': cancelled_items_log,
    })


def orders_list(request):
    """
    Список заказов для кассы: готовятся и вызваны.
    """
    orders = Order.objects.filter(
        status__in=['pending', 'called'],  # показываем оба статуса
        cancelled=False
    ).prefetch_related('items').order_by('order_time')
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
    from django.db.models import Sum, F
    from django.utils import timezone
    from django.http import JsonResponse
    from django.shortcuts import redirect
    import win32ui
    from datetime import datetime

    PRINTER_NAME = "XP-80"

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

        # Вспомогательная функция для переноса длинных названий
        def draw_wrapped_text(pdc, x, y, text, max_width, line_height, font):
            pdc.SelectObject(font)
            words = str(text).split(" ")
            lines = []
            current = ""
            for word in words:
                trial = current + (" " if current else "") + word
                w, _ = pdc.GetTextExtent(trial)
                if w <= max_width:
                    current = trial
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)

            for line in lines:
                pdc.TextOut(x, y, line)
                y += line_height
            return y, len(lines)

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
            # переносим название
            y_before = y
            y, lines_count = draw_wrapped_text(pdc, x_name, y, item["product__name"], x_price - x_name - 10, line_height, font)

            # остальные колонки печатаем на первой строке
            pdc.TextOut(x_price, y_before, f"{item['product__price'] or 0:.0f}")
            pdc.TextOut(x_qty,   y_before, str(item["total_qty"]))
            pdc.TextOut(x_sales, y_before, f"{item['total_sales'] or 0:.0f}")

            # сдвигаем вниз для следующей строки
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
        # 🔹 при оплате переводим заказ в статус "ready"
        order.status = 'ready'
        order.save()

        order.items.filter(is_draft=True).update(is_draft=False)
        return JsonResponse({"ok": True})

    except Order.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Заказ не найден"})



# views.py
def orders_ready_list(request):
    orders = Order.objects.filter(status='ready').prefetch_related('items').order_by('-order_time')
    return render(request, 'orders_ready.html', {'orders': orders})



# ===== Страница редактирования =====
@require_GET
def edit_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    products = Product.objects.all().order_by('category', 'name')
    categories = Product.objects.values_list('category', flat=True).distinct()

    # Активные блюда — только те, что не отменены и количество > 0
    active_items = order.items.filter(cancelled=False, quantity__gt=0).select_related('product')

    cancelled_items = order.items.filter(
        Q(cancelled=True) | Q(quantity=0, is_draft=True)
    ).select_related('product')

    # ⚡ сохраняем baseline в сессии для пересчёта кухни
    request.session['baseline'] = {
        str(it.product.id): it.quantity
        for it in active_items
    }

    return render(request, 'edit_order.html', {
        'order': order,
        'items': active_items,
        'products': products,
        'cancelled_items': cancelled_items,
        'categories': categories,
    })


# ===== API: добавление позиции =====
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

    existing = order.items.filter(product=product, cancelled=False).first()
    if existing:
        # ⚡ не трогаем original_quantity, оно фиксируется только при создании
        existing.quantity += qty
        existing.is_draft = True
        existing.save(update_fields=["quantity", "is_draft"])
    else:
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=qty,
            price=product.price,
            options=[],
            cancelled=False,
            is_new=True,          # новое блюдо
            is_draft=True,
            original_quantity=0,  # baseline = 0
        )

    order.is_paid = False
    order.save(update_fields=["is_paid"])

    items, total = _recalc_and_serialize(order)
    return JsonResponse({'ok': True, 'items': items, 'total': total})



# views.py
import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from .models import Order, OrderItem

@require_POST
def discard_draft(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    try:
        payload = json.loads(request.body or '{}')
    except Exception:
        payload = {}

    diffs = payload.get('diffs', {})
    changed = False

    items_map = { str(it.id): it for it in OrderItem.objects.filter(order=order) }

    for item_id, diff in diffs.items():
        it = items_map.get(item_id)
        if not it:
            continue

        if not (it.is_draft and it.is_new and not it.cancelled):
            continue

        base = int(diff.get('baseline_qty', it.quantity))
        cur = int(diff.get('current_qty', it.quantity))

        if base == cur:
            continue

        changed = True
        if base <= 0:
            it.delete()
        else:
            it.quantity = base
            it.is_draft = False
            it.is_new = False
            it.save(update_fields=["quantity", "is_draft", "is_new"])

    # ⚡ всегда сбрасываем все is_draft
    order.items.filter(is_draft=True).update(is_draft=False)

    items, total = _recalc_and_serialize(order)
    return JsonResponse({
        'ok': True,
        'changed': changed,
        'items': items,
        'total': total,
        'action': 'discard'
    })







@csrf_exempt
@require_POST
def reduce_item_quantity(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    new_qty = int(request.POST.get("quantity", item.quantity - 1))

    emp_id = request.session.get("employee_id")
    emp = Employee.objects.filter(id=emp_id).first()

    if not item.is_draft:
        item.original_quantity = item.quantity

    item.quantity = max(new_qty, 0)
    item.is_new = False
    item.is_draft = False

    if item.quantity == 0:
        # сразу фиксируем отмену
        item.cancelled = True
        item.cancelled_by = emp
        item.cancelled_at = timezone.now()

    item.save(update_fields=[
        "quantity", "original_quantity",
        "is_new", "is_draft",
        "cancelled", "cancelled_by", "cancelled_at"
    ])

    order = item.order
    order.is_paid = False
    order.save(update_fields=["is_paid"])

    items, total = _recalc_and_serialize(order)
    return JsonResponse({'ok': True, 'items': items, 'total': total})






@csrf_exempt
@require_POST
def remove_item_from_order(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)
    emp_id = request.session.get("employee_id")
    emp = Employee.objects.filter(id=emp_id).first()


    if not item.is_draft:
        item.original_quantity = item.quantity

    # фиксируем отмену
    item.quantity = 0
    item.is_new = False
    item.is_draft = False
    item.cancelled = True
    item.cancelled_by = emp
    item.cancelled_at = timezone.now()
    item.save(update_fields=[
        "quantity", "is_new", "is_draft",
        "original_quantity", "cancelled", "cancelled_by", "cancelled_at"
    ])

    order = item.order
    order.is_paid = False
    order.save(update_fields=["is_paid"])

    items, total = _recalc_and_serialize(order)
    return JsonResponse({'ok': True, 'items': items, 'total': total})




@csrf_exempt
@require_POST
def recalc_order_total(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    operator = getattr(order, "employee", None)
    operator_name = getattr(operator, "name", "-") if operator else "-"

    try:
        payload = json.loads(request.body or '{}')
    except Exception:
        payload = {}
    edit_ops_raw = payload.get('edit_ops', {}) or {}

    # нормализация edit_ops → int ключи
    edit_ops = {
        int(pid): {
            "added": int(v.get("added", 0) or 0),
            "removed": int(v.get("removed", 0) or 0),
        }
        for pid, v in edit_ops_raw.items() if str(pid).isdigit()
    }

    # baseline из сессии → int ключи
    session_baseline = request.session.get('baseline', {}) or {}
    prev_map = {int(pid): int(qty or 0) for pid, qty in session_baseline.items() if str(pid).isdigit()}

    delta_items = []
    for it in order.items.filter(cancelled=False, quantity__gt=0).select_related('product'):
        pid = getattr(it.product, 'id', None)
        if pid is None:
            continue
        cur_qty = int(it.quantity or 0)
        prev_qty = int(prev_map.get(pid, getattr(it, "original_quantity", 0) or 0))
        final_diff = max(0, cur_qty - prev_qty)

        to_print = 0
        # 🔹 новое блюдо → печатаем всё количество
        if it.is_new and (it.original_quantity or 0) == 0:
            to_print = cur_qty
        else:
            if pid in edit_ops:
                added = edit_ops[pid]["added"]
                if final_diff > 0:
                    to_print = max(0, min(added, final_diff))
                elif added > 0:
                    to_print = added
            else:
                to_print = final_diff

        if to_print > 0:
            it_copy = it
            it_copy.quantity = to_print
            delta_items.append(it_copy)

        print(
            f"DEBUG item {pid}: cur={cur_qty}, prev={prev_qty}, diff={final_diff}, "
            f"to_print={to_print}, is_new={getattr(it, 'is_new', False)}"
        )

    # печать
    if delta_items:
        print_to_printer(
            "XP-80C (copy 1)",
            order.receipt_number,
            order.order_time,
            delta_items,
            kitchen=True,
            order_type="",
            operator_name=operator_name,
            recalc=True,
            previous_quantities=prev_map,
            edit_ops=edit_ops
        )
        print_to_printer(
            "XP-80",
            order.receipt_number,
            order.order_time,
            delta_items,
            kitchen=False,
            order_type="",
            operator_name=operator_name,
            recalc=True,
            previous_quantities=prev_map,
            edit_ops=edit_ops
        )

    # 🔹 обновляем baseline и сбрасываем is_new
    for it in order.items.filter(cancelled=False):
        it.original_quantity = it.quantity
        it.is_new = False
        it.save(update_fields=["original_quantity", "is_new"])
    request.session['baseline'] = {
        str(it.product.id): int(it.quantity or 0)
        for it in order.items.filter(cancelled=False).select_related('product')
    }

    items, total = _recalc_and_serialize(order)
    return JsonResponse({
        'ok': True,
        'recalc': bool(delta_items),
        'changed': bool(delta_items),
        'items': items,
        'total': total,
        'action': 'recalc'
    })

def _recalc_and_serialize(order):
    items = []
    total = 0
    # Берём только блюда с количеством > 0
    for it in order.items.filter(cancelled=False, quantity__gt=0).select_related('product'):
        line_total = it.quantity * it.price
        total += line_total
        items.append({
            "id": it.id,
            "name": it.product.name,
            "quantity": it.quantity,
            "line_total": line_total,
        })
    return items, total





@csrf_exempt
@require_POST
def order_ready(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = "ready"
    order.save(update_fields=["status"])
    order.items.filter(is_draft=True).update(is_draft=False)
    return JsonResponse({"ok": True})

@csrf_exempt
@require_GET
def order_cancel(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # берём кассира из сессии
    emp_id = request.session.get("employee_id")
    emp = Employee.objects.filter(id=emp_id).first()

    # фиксируем единое время отмены
    cancelled_time = timezone.now()

    # берём все позиции заказа
    cancelled_items = order.items.all()

    # печать чека отмены (до изменения флагов)
    if cancelled_items.exists():
        print_to_printer(
            "XP-80C (copy 1)",
            order.receipt_number,
            order.order_time,
            cancelled_items,
            kitchen=True,
            order_type="Отмена",
            operator_name=emp.name if emp else "-"
        )
        print_to_printer(
            "XP-80",
            order.receipt_number,
            order.order_time,
            cancelled_items,
            kitchen=False,
            order_type="Отмена",
            operator_name=emp.name if emp else "-"
        )

    # помечаем все позиции как отменённые
    cancelled_items.update(
        cancelled=True,
        cancelled_by=emp,
        cancelled_at=cancelled_time
    )

    # проставляем статус и поля отмены у заказа
    order.status = "cancelled"
    order.cancelled = True
    order.cancelled_at = cancelled_time
    order.cancelled_by = emp
    order.save(update_fields=["status", "cancelled", "cancelled_at", "cancelled_by"])

    return JsonResponse({"ok": True})

import pytz

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
import pytz
@csrf_exempt
@require_GET
def order_receipt_reprint(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    print("RAW:", order.order_time, order.order_time.tzinfo, repr(order.order_time))

    items = order.items.filter(cancelled=False)
    operator = getattr(order, "employee", None)
    operator_name = getattr(operator, "name", "-") if operator else "-"

    # ===== FIX: перевод времени в Бишкек (UTC -> Asia/Bishkek) =====
    tz = pytz.timezone("Asia/Bishkek")
    order_dt = order.order_time
    if getattr(order_dt, "tzinfo", None) is None:
        # наивную дату трактуем как UTC и переводим в Бишкек
        order_dt_local = pytz.utc.localize(order_dt).astimezone(tz)
    else:
        # aware-дата (например, UTC) -> перевод напрямую в Бишкек
        order_dt_local = order_dt.astimezone(tz)

    # 🔹 Функция для переноса длинных названий (как в print_receipt_direct)
    def draw_row(pdc, y, name, qty, price, total,
                 x_name, x_qty, x_price, x_total, line_h, font_bold):
        pdc.SelectObject(font_bold)
        max_width = x_qty - x_name - 10
        text = str(name)

        # Разбиваем на токены (по пробелам, дефисам, скобкам)
        tokens, buf = [], []
        for ch in text:
            if ch.isspace() or ch in "-()":
                if buf:
                    tokens.append("".join(buf)); buf = []
                tokens.append(ch)
            else:
                buf.append(ch)
        if buf:
            tokens.append("".join(buf))

        lines, current, i = [], "", 0
        while i < len(tokens):
            tok = tokens[i]
            trial = current + tok
            w, _ = pdc.GetTextExtent(trial)
            if w <= max_width:
                current = trial
                i += 1
            else:
                if not current.strip():
                    # режем слишком длинное слово посимвольно
                    cut = 1
                    while cut <= len(tok) and pdc.GetTextExtent(tok[:cut])[0] <= max_width:
                        cut += 1
                    part = tok[:cut-1] if cut > 1 else tok[:1]
                    lines.append(part)
                    rest = tok[len(part):]
                    if rest:
                        tokens[i] = rest
                    else:
                        i += 1
                else:
                    lines.append(current.strip())
                    current = ""
        if current.strip():
            lines.append(current.strip())

        # 🔹 Название (в несколько строк)
        for idx, line in enumerate(lines):
            pdc.TextOut(x_name, y, line)
            if idx == 0:
                # только на первой строке выводим цифры
                pdc.TextOut(x_qty,   y, f"{int(qty)}")
                pdc.TextOut(x_price, y, f"{int(price)}")
                pdc.TextOut(x_total, y, f"{int(total)}")
            y += line_h

        return y

    # печать полного актуального заказа
    print_to_printer(
        "XP-123",
        order.receipt_number,
        order_dt_local,
        items,
        kitchen=True,
        order_type="",
        operator_name=operator_name,  # передаём функцию в печать
    )
    print_to_printer(
        "XP-80",
        order.receipt_number,
        order_dt_local,
        items,
        kitchen=False,
        order_type="",
        operator_name=operator_name,  # передаём функцию в печать
    )

    return JsonResponse({"ok": True})




from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.shortcuts import get_object_or_404
from .models import Order
  # импортируем функцию





def print_receipt_direct(order):
    import win32ui
    import win32print
    from decimal import Decimal
    import pytz

    # Часовой пояс всегда Бишкек
    tz = pytz.timezone("Asia/Bishkek")
    order_dt = order.order_time
    if getattr(order_dt, "tzinfo", None) is None:
        order_dt = tz.localize(order_dt)
    else:
        order_dt = order_dt.astimezone(tz)

    # Номер заказа
    order_no = getattr(order, "receipt_number", None) or getattr(order, "number", None) or 0

    # Имена принтеров
    PRINTER_CLIENT = "XP-80"
    PRINTER_KITCHEN = "XP-80C (copy 1)"

    # Тип заказа (определим из позиций)
    order_type = ""

    # Шрифты
    font_bold = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 800})
    font_order_no = win32ui.CreateFont({"name": "Consolas", "height": 60, "weight": 800})
    font_order_type = win32ui.CreateFont({"name": "Consolas", "height": 48, "weight": 800})
    font_grand_total = win32ui.CreateFont({"name": "Consolas", "height": 72, "weight": 800})

    # Разметка
    margin_left = 10
    line_h = 28
    x_name = margin_left
    x_qty = margin_left + 250
    x_price = margin_left + 340
    x_total = margin_left + 440
    RIGHT_EDGE = margin_left + 560
    FULL_LINE = "=" * 60

    # Утилиты (кассовый чек)
    def draw_text(pdc, x, y, text, font=font_bold):
        pdc.SelectObject(font)
        pdc.TextOut(x, y, str(text))

    def draw_right(pdc, y, text, x_right, font=font_bold):
        pdc.SelectObject(font)
        w, _ = pdc.GetTextExtent(str(text))
        pdc.TextOut(x_right - w, y, str(text))

    def draw_center(pdc, y, text, size=36):
        font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": 800})
        pdc.SelectObject(font_line)
        w, _ = pdc.GetTextExtent(str(text))
        x_center = (RIGHT_EDGE - margin_left) // 2 - w // 2 + margin_left
        pdc.TextOut(x_center, y, str(text))

    # Перенос строк для длинных наименований (кассовый чек)
    def draw_row(pdc, y, name, qty, price, total):
        pdc.SelectObject(font_bold)
        max_width = x_qty - x_name - 10
        text = str(name)

        tokens, buf = [], []
        for ch in text:
            if ch.isspace() or ch in "-()":
                if buf:
                    tokens.append("".join(buf)); buf = []
                tokens.append(ch)
            else:
                buf.append(ch)
        if buf:
            tokens.append("".join(buf))

        lines, current, i = [], "", 0
        while i < len(tokens):
            tok = tokens[i]
            trial = current + tok
            w, _ = pdc.GetTextExtent(trial)
            if w <= max_width:
                current = trial
                i += 1
            else:
                if not current.strip():
                    cut = 1
                    while cut <= len(tok) and pdc.GetTextExtent(tok[:cut])[0] <= max_width:
                        cut += 1
                    part = tok[:cut-1] if cut > 1 else tok[:1]
                    lines.append(part)
                    rest = tok[len(part):]
                    if rest:
                        tokens[i] = rest
                    else:
                        i += 1
                else:
                    lines.append(current.strip())
                    current = ""
        if current.strip():
            lines.append(current.strip())

        for idx, line in enumerate(lines):
            draw_text(pdc, x_name, y, line)
            if idx == 0:
                draw_text(pdc, x_qty, y, f"{int(qty)}")
                draw_text(pdc, x_price, y, f"{int(price)}")
                draw_text(pdc, x_total, y, f"{int(total)}")
            y += line_h

        return y

    # ===== Клиентский чек =====
    try:
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(PRINTER_CLIENT)
        pdc.StartDoc(f"Клиентский чек №{order_no}")
        y = 0
        pdc.StartPage()

        # Шапка
        draw_center(pdc, y, f"ЗАКАЗ №{order_no}", size=60); y += 70
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_center(pdc, y, "BILAL FRIED CHICKEN", size=36); y += 40
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h

        # Оператор и время
        operator = getattr(order, "employee", None)
        operator_name = getattr(operator, "name", "-") if operator else "-"
        draw_text(pdc, x_name, y, f"Оператор: {operator_name}"); y += line_h
        draw_text(pdc, x_name, y, order_dt.strftime('%Y.%m.%d %H:%M:%S')); y += line_h

        # Определение типа заказа по категориям/названиям
        for item in order.items.filter(cancelled=False):
            product = getattr(item, "product", None)
            if not product:
                continue
            category = getattr(product, "category", None)
            if isinstance(category, str):
                cat_name = (category or "").strip().lower()
            else:
                cat_name = (getattr(category, "name", "") or "").strip().lower()
            prod_name = (getattr(product, "name", "") or "").strip().lower()

            if "доставка" in cat_name or "доставка" in prod_name:
                order_type = "Доставка"; break
            elif "с собой" in cat_name or "с собой" in prod_name:
                order_type = "С собой"
            elif "здесь" in cat_name or "здесь" in prod_name:
                order_type = "Здесь"; break

        # Таблица
        draw_text(pdc, x_name, y, "Наименование")
        draw_text(pdc, x_qty, y, "К-во")
        draw_text(pdc, x_price, y, "Цена")
        draw_text(pdc, x_total, y, "Сумма"); y += line_h
        draw_text(pdc, x_name, y, "-" * 50); y += line_h

        # Строки и итог
        total_sum = Decimal("0")
        for item in order.items.filter(cancelled=False):
            qty = Decimal(item.quantity)
            price = Decimal(item.price or item.product.price)
            line_total = price * qty
            total_sum += line_total
            y = draw_row(pdc, y, item.product.name, qty, price, line_total)

        # Итог
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_text(pdc, x_name, y, "ИТОГО:", font=font_grand_total)
        draw_right(pdc, y, f"{int(total_sum)} сом", RIGHT_EDGE, font=font_grand_total); y += 80
        draw_center(pdc, y, f"{order_type}", size=48); y += 60
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_center(pdc, y, "Оплата: Наличные", size=28); y += line_h
        draw_center(pdc, y, "Спасибо за покупку!", size=36); y += 40
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()
    except Exception as e:
        print(f"Ошибка печати клиентского чека: {e}")

    # ===== Функция Beep =====
    def send_beep(printer_name):
        try:
            hPrinter = win32print.OpenPrinter(printer_name)
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Beep", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            # ESC B n t → 3 сигнала по 500 мс
            win32print.WritePrinter(hPrinter, b'\x1b\x42\x03\x05')
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            win32print.ClosePrinter(hPrinter)
        except Exception as e:
            print(f"Ошибка отправки Beep: {e}")

    # ===== Кухонный чек (исключаем ряд категорий) =====
    try:
        # Собираем позиции с их категориями
        kitchen_items = []
        for item in order.items.filter(cancelled=False):
            product = getattr(item, "product", None)
            if not product:
                continue

            # Название категории
            category = getattr(product, "category", None)
            if isinstance(category, str):
                cat_name = (category or "").strip().lower()
            else:
                cat_name = (getattr(category, "name", "") or "").strip().lower()

            kitchen_items.append((getattr(product, "name", ""), int(item.quantity), cat_name))

        # Если нет позиций — не печатаем
        if not kitchen_items:
            return

        # Категории, которые исключаем из кухонного чека
        excluded_categories = {
            "чай кофе",
            "горячие самсы",
            "десерты",
            "горячие напитки",
            "напитки",
            "соус",
            "макаронсы",
        }

        # Если все позиции из исключаемых — не печатаем
        if all(cat in excluded_categories for _, _, cat in kitchen_items):
            return

        # Печатаем только позиции, которые НЕ входят в исключаемые категории
        printable_items = [
            (name, qty) for name, qty, cat in kitchen_items
            if cat not in excluded_categories
        ]
        if not printable_items:
            return

        # Печать кухонного чека
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(PRINTER_KITCHEN)
        pdc.StartDoc(f"Кухонный чек №{order_no}")

        # Звуковой сигнал до печати
        send_beep(PRINTER_KITCHEN)

        y = 0
        pdc.StartPage()

        # Утилита центрирования (кухонный чек)
        def draw_center_kitchen(pdc, y, text, size=36):
            font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": 800})
            pdc.SelectObject(font_line)
            s = str(text)
            w, _ = pdc.GetTextExtent(s)
            x_center = (RIGHT_EDGE - margin_left) // 2 - w // 2 + margin_left
            pdc.TextOut(x_center, y, s)

        # Центрированный перенос длинных строк (кухонный чек)
        def draw_center_wrap(pdc, y, text, size=43, max_width=RIGHT_EDGE - margin_left):
            font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": 800})
            pdc.SelectObject(font_line)
            s = str(text)

            # Токенизация по словам и разделителям
            tokens, buf = [], []
            for ch in s:
                if ch.isspace() or ch in "-()":
                    if buf:
                        tokens.append("".join(buf)); buf = []
                    tokens.append(ch)
                else:
                    buf.append(ch)
            if buf:
                tokens.append("".join(buf))

            lines, current, i = [], "", 0
            while i < len(tokens):
                tok = tokens[i]
                trial = current + tok
                w, _ = pdc.GetTextExtent(trial)
                if w <= max_width:
                    current = trial
                    i += 1
                else:
                    if not current.strip():
                        cut = 1
                        while cut <= len(tok) and pdc.GetTextExtent(tok[:cut])[0] <= max_width:
                            cut += 1
                        part = tok[:cut-1] if cut > 1 else tok[:1]
                        lines.append(part)
                        rest = tok[len(part):]
                        if rest:
                            tokens[i] = rest
                        else:
                            i += 1
                    else:
                        lines.append(current.strip())
                        current = ""
            if current.strip():
                lines.append(current.strip())

            for line in lines:
                w, _ = pdc.GetTextExtent(line)
                x_center = (RIGHT_EDGE - margin_left) // 2 - w // 2 + margin_left
                pdc.TextOut(x_center, y, line)
                y += size  # шаг вниз равен высоте шрифта

            return y

        # Заголовок
        draw_center_kitchen(pdc, y, "КУХНЯ", size=48); y += 60
        draw_center_kitchen(pdc, y, f"{order_type}", size=54); y += 65
        draw_center_kitchen(pdc, y, f"ЗАКАЗ №{order_no}", size=64); y += 60
        draw_center_kitchen(pdc, y, order_dt.strftime('%d.%m.%Y %H:%M'), size=36); y += 45
        draw_center_kitchen(pdc, y, FULL_LINE, size=32); y += 40

        # Печать блюд (только те, которые не из исключаемых категорий) — с переносом
        for name, qty in printable_items:
            y = draw_center_wrap(pdc, y, f"{name} × {qty}", size=43)
            y += 10  # небольшой дополнительный отступ между блюдами

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
import traceback
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
import pytz
from datetime import datetime

@require_GET
def reprint_receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    try:
        import win32ui
        from decimal import Decimal
        import traceback
        from datetime import datetime
        import pytz

        # ===== FIX: корректное локальное время (через timestamp) =====
        tz = pytz.timezone("Asia/Bishkek")
        order_dt = order.order_time
        try:
            ts = order_dt.timestamp()
        except Exception:
            from calendar import timegm
            if getattr(order_dt, "tzinfo", None) is None:
                ts = timegm(order_dt.utctimetuple())
            else:
                ts = order_dt.timestamp()
        order_dt_local = datetime.fromtimestamp(ts, tz)

        order_no = getattr(order, "receipt_number", None) or 0
        PRINTER_CLIENT = "XP-80"

        # Шрифты
        font_bold = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 800, "charset": 204})
        font_total = win32ui.CreateFont({"name": "Consolas", "height": 36, "weight": 800, "charset": 204})
        font_order_no = win32ui.CreateFont({"name": "Consolas", "height": 60, "weight": 800, "charset": 204})
        font_grand_total = win32ui.CreateFont({"name": "Consolas", "height": 72, "weight": 800, "charset": 204})

        # Разметка
        margin_left = 10
        line_h = 28
        x_name  = margin_left
        x_qty   = margin_left + 250
        x_price = margin_left + 340
        x_total = margin_left + 440
        RIGHT_EDGE = margin_left + 560
        FULL_LINE = "=" * 60  # длинная линия от края до края

        # Утилиты
        def draw_text(pdc, x, y, text, font=font_bold):
            pdc.SelectObject(font)
            pdc.TextOut(x, y, str(text))

        def draw_right(pdc, y, text, x_right, font=font_bold):
            pdc.SelectObject(font)
            w, _ = pdc.GetTextExtent(str(text))
            pdc.TextOut(x_right - w, y, str(text))

        def draw_center(pdc, y, text, size=36):
            font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": 800, "charset": 204})
            pdc.SelectObject(font_line)
            s = str(text)
            w, _ = pdc.GetTextExtent(s)
            x_center = (RIGHT_EDGE - margin_left) // 2 - w // 2 + margin_left
            pdc.TextOut(x_center, y, s)

        def draw_row(pdc, y, name, qty, price, total):
            """
            Рисует строку: сначала название (с переносом),
            затем на новой строке количество, цену и сумму.
            """
            pdc.SelectObject(font_bold)
            max_width = x_qty - x_name - 10
            words = str(name).split(" ")
            lines = []
            current = ""

            for word in words:
                trial = current + (" " if current else "") + word
                w, _ = pdc.GetTextExtent(trial)
                if w <= max_width:
                    current = trial
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)

            # 🔹 Рисуем название (в несколько строк)
            for line in lines:
                draw_text(pdc, x_name, y, line)
                y += line_h

            # 🔹 Рисуем цифры на новой строке
            draw_text(pdc, x_qty,   y, f"{int(qty)}")
            draw_text(pdc, x_price, y, f"{int(price)}")
            draw_text(pdc, x_total, y, f"{int(total)}")
            y += line_h

            return y

        # ===== Печать чека =====
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(PRINTER_CLIENT)
        pdc.StartDoc(f"Клиентский чек №{order_no}")
        pdc.StartPage()

        y = 0
        # Шапка (новый стиль)
        draw_center(pdc, y, f"ЗАКАЗ №{order_no}", size=60); y += 70
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_center(pdc, y, "BILAL FRIED CHICKEN", size=36); y += 40
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h

        operator = getattr(order, "employee", None)
        draw_text(pdc, x_name, y, f"Оператор: {getattr(operator, 'name', '-') if operator else '-'}"); y += line_h
        draw_text(pdc, x_name, y, order_dt_local.strftime('%Y.%m.%d %H:%M:%S')); y += line_h

        draw_text(pdc, x_name,  y, "Наименование")
        draw_text(pdc, x_qty,   y, "К-во")
        draw_text(pdc, x_price, y, "Цена")
        draw_text(pdc, x_total, y, "Сумма"); y += line_h
        draw_text(pdc, x_name, y, FULL_LINE, size=28); y += line_h

        total_sum = Decimal("0")
        for item in order.items.filter(cancelled=False):
            qty   = Decimal(item.quantity)
            price = Decimal(item.price or item.product.price)
            line_total = price * qty
            total_sum += line_total
            y = draw_row(pdc, y, item.product.name, qty, price, line_total)

        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_text(pdc, x_name, y, "ИТОГО:", font=font_grand_total)
        draw_right(pdc, y, f"{int(total_sum)} сом", RIGHT_EDGE, font=font_grand_total); y += 80
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_center(pdc, y, "Оплата: Наличные", size=28); y += line_h
        if getattr(order, "note", None):
            draw_center(pdc, y, f"Комментарий: {order.note}", size=28); y += line_h
        draw_center(pdc, y, "Спасибо за покупку!", size=36); y += 40
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h

        pdc.EndPage()
        pdc.EndDoc()
        pdc.DeleteDC()

        return JsonResponse({'ok': True, 'reprinted': True})

    except Exception as e:
        import traceback
        return JsonResponse({
            'error': f'Ошибка печати клиентского чека: {e}',
            'trace': traceback.format_exc()
        }, status=500)


    except Exception as e:
        import traceback
        return JsonResponse({
            'error': f'Ошибка печати клиентского чека: {e}',
            'trace': traceback.format_exc()
        }, status=500)




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

import win32ui
from decimal import Decimal

# views.py
import json
from decimal import Decimal
import win32ui

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Sum, F

from .models import Order, Product, OrderItem


from decimal import Decimal
import win32ui
import win32print
import pytz

from decimal import Decimal
import pytz
import win32ui
import win32print

from decimal import Decimal
import pytz
import win32ui
import win32print

from decimal import Decimal
import pytz
import win32ui
import win32print
from decimal import Decimal
import pytz
import win32ui
import win32print

def print_to_printer(
    printer_name,
    order_no,
    order_dt,
    items,
    kitchen=False,
    order_type="",
    operator_name="-",
    tz_name="Asia/Bishkek",
    recalc=False,
    previous_quantities=None,
    edit_ops=None,
):
    import win32ui
    import win32print
    from decimal import Decimal
    import pytz

    def to_local(dt):
        tz = pytz.timezone(tz_name)
        if getattr(dt, "tzinfo", None) is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(tz)

    order_dt_local = to_local(order_dt)

    margin_left = 10
    line_h = 28
    x_name = margin_left
    x_qty = margin_left + 250
    x_price = margin_left + 340
    x_total = margin_left + 440
    RIGHT_EDGE = margin_left + 560
    FULL_LINE = "=" * 60

    def draw_center(pdc, y, text, size=36, weight=800):
        font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": weight})
        pdc.SelectObject(font_line)
        s = str(text)
        w, _ = pdc.GetTextExtent(s)
        x_center = (RIGHT_EDGE - margin_left) // 2 - w // 2 + margin_left
        pdc.TextOut(x_center, y, s)

    def draw_text(pdc, x, y, text, size=28, weight=800):
        font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": weight})
        pdc.SelectObject(font_line)
        pdc.TextOut(x, y, str(text))

    def draw_right(pdc, y, text, x_right, size=28, weight=800):
        font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": weight})
        pdc.SelectObject(font_line)
        s = str(text)
        w, _ = pdc.GetTextExtent(s)
        pdc.TextOut(x_right - w, y, s)

    def send_beep(printer_name_):
        try:
            hPrinter = win32print.OpenPrinter(printer_name_)
            hJob = win32print.StartDocPrinter(hPrinter, 1, ("Beep", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)
            # ESC B n t → 3 сигнала по ~500 мс
            win32print.WritePrinter(hPrinter, b'\x1b\x42\x03\x05')
            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)
            win32print.ClosePrinter(hPrinter)
        except Exception as e:
            print(f"Ошибка Beep: {e}")

    # 🔹 Перенос длинных названий (касса, слева с колонками)
    def draw_row(pdc, y, name, qty, price, total):
        font_line = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 800})
        pdc.SelectObject(font_line)
        max_width = x_qty - x_name - 10
        text = str(name)

        tokens, buf = [], []
        for ch in text:
            if ch.isspace() or ch in "-()":
                if buf:
                    tokens.append("".join(buf)); buf = []
                tokens.append(ch)
            else:
                buf.append(ch)
        if buf:
            tokens.append("".join(buf))

        lines, current, i = [], "", 0
        while i < len(tokens):
            tok = tokens[i]
            trial = current + tok
            w, _ = pdc.GetTextExtent(trial)
            if w <= max_width:
                current = trial
                i += 1
            else:
                if not current.strip():
                    cut = 1
                    while cut <= len(tok) and pdc.GetTextExtent(tok[:cut])[0] <= max_width:
                        cut += 1
                    part = tok[:cut-1] if cut > 1 else tok[:1]
                    lines.append(part)
                    rest = tok[len(part):]
                    if rest:
                        tokens[i] = rest
                    else:
                        i += 1
                else:
                    lines.append(current.strip())
                    current = ""
        if current.strip():
            lines.append(current.strip())

        for idx, line in enumerate(lines):
            pdc.TextOut(x_name, y, line)
            if idx == 0:
                pdc.TextOut(x_qty,   y, f"{int(qty)}")
                pdc.TextOut(x_price, y, f"{int(price)}")
                pdc.TextOut(x_total, y, f"{int(total)}")
            y += line_h

        return y

    # 🔹 Перенос длинных названий (кухня, центрирование)
    def draw_center_wrap(pdc, y, text, size=43, weight=800, max_width=RIGHT_EDGE - margin_left):
        font_line = win32ui.CreateFont({"name": "Consolas", "height": size, "weight": weight})
        pdc.SelectObject(font_line)
        s = str(text)

        tokens, buf = [], []
        for ch in s:
            if ch.isspace() or ch in "-()":
                if buf:
                    tokens.append("".join(buf)); buf = []
                tokens.append(ch)
            else:
                buf.append(ch)
        if buf:
            tokens.append("".join(buf))

        lines, current, i = [], "", 0
        while i < len(tokens):
            tok = tokens[i]
            trial = current + tok
            w, _ = pdc.GetTextExtent(trial)
            if w <= max_width:
                current = trial
                i += 1
            else:
                if not current.strip():
                    cut = 1
                    while cut <= len(tok) and pdc.GetTextExtent(tok[:cut])[0] <= max_width:
                        cut += 1
                    part = tok[:cut-1] if cut > 1 else tok[:1]
                    lines.append(part)
                    rest = tok[len(part):]
                    if rest:
                        tokens[i] = rest
                    else:
                        i += 1
                else:
                    lines.append(current.strip())
                    current = ""
        if current.strip():
            lines.append(current.strip())

        for line in lines:
            w, _ = pdc.GetTextExtent(line)
            x_center = (RIGHT_EDGE - margin_left) // 2 - w // 2 + margin_left
            pdc.TextOut(x_center, y, line)
            y += size  # шаг вниз равен высоте шрифта

        return y

    pdc = None
    started_doc = False
    started_page = False

    try:
        pdc = win32ui.CreateDC()
        pdc.CreatePrinterDC(printer_name)
        doc_type = "Кухонный чек" if kitchen else "Клиентский чек"
        pdc.StartDoc(f"{doc_type} №{order_no}")
        started_doc = True
        pdc.StartPage()
        started_page = True

        # ===== КУХНЯ =====
        if kitchen:
            excluded_categories = {
                "чай кофе",
                "горячие напитки",
                "напитки",
                "соус",
                "макаронсы",
            }
            kitchen_items = []

            for it in items:
                prod = getattr(it, "product", None)
                if not prod:
                    continue

                category = getattr(prod, "category", None)
                cat_name = (category or "").strip().lower()
                name = getattr(prod, "name", "") or "Без названия"
                qty_current = int(getattr(it, "quantity", 0) or 0)

                # Отбрасываем исключаемые категории
                if cat_name in excluded_categories:
                    continue

                if qty_current > 0:
                    kitchen_items.append((name, qty_current))

            if not kitchen_items:
                return

            # Звуковой сигнал
            send_beep(printer_name)

            y = 0
            draw_center(pdc, y, "КУХНЯ", size=48); y += 60
            draw_center(pdc, y, f"{order_type}", size=54); y += 65
            draw_center(pdc, y, f"ЗАКАЗ №{order_no}", size=64); y += 60
            draw_center(pdc, y, order_dt_local.strftime("%d.%m.%Y %H:%M"), size=36); y += 45
            draw_center(pdc, y, FULL_LINE, size=32); y += 40

            # Печать блюд с переносом и центрированием
            for name, qty in kitchen_items:
                y = draw_center_wrap(pdc, y, f"{name} × {qty}", size=43)
                y += 10  # небольшой дополнительный отступ между блюдами

            return

        # ===== КАССА =====
        y = 0
        draw_center(pdc, y, f"ЗАКАЗ №{order_no}", size=60); y += 70
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_center(pdc, y, "BILAL FRIED CHICKEN", size=36); y += 40
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h

        draw_text(pdc, x_name, y, f"Оператор: {operator_name}", size=28); y += line_h
        draw_text(pdc, x_name, y, order_dt_local.strftime("%Y.%m.%d %H:%M:%S"), size=28); y += line_h

        draw_text(pdc, x_name, y, "Наименование", size=28)
        draw_text(pdc, x_qty, y, "К-во", size=28)
        draw_text(pdc, x_price, y, "Цена", size=28)
        draw_text(pdc, x_total, y, "Сумма", size=28); y += line_h
        draw_text(pdc, x_name, y, FULL_LINE, size=28); y += line_h

        total_sum = Decimal("0")
        for it in items:
            qty = Decimal(getattr(it, "quantity", 0) or 0)
            price = Decimal(
                getattr(it, "price", None) or
                getattr(getattr(it, "product", None), "price", 0) or 0
            )
            line_total = price * qty
            total_sum += line_total

            name = getattr(getattr(it, "product", None), "name", "Без названия")
            y = draw_row(pdc, y, name, qty, price, line_total)

        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_text(pdc, x_name, y, "ИТОГО:", size=72)
        draw_right(pdc, y, f"{int(total_sum)} сом", RIGHT_EDGE, size=72); y += 80

        draw_center(pdc, y, f"{order_type}", size=48); y += 60
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h
        draw_center(pdc, y, "Оплата: Наличные", size=28); y += line_h
        draw_center(pdc, y, "Спасибо за покупку!", size=36); y += 40
        draw_center(pdc, y, FULL_LINE, size=28); y += line_h

    except Exception as e:
        print(f"Ошибка печати ({'кухня' if kitchen else 'касса'}): {e}")
    finally:
        # Аккуратное закрытие страницы/документа/контекста печати
        try:
            if pdc is not None and started_page:
                pdc.EndPage()
        except Exception:
            pass
        try:
            if pdc is not None and started_doc:
                pdc.EndDoc()
        except Exception:
            pass
        try:
            if pdc is not None:
                pdc.DeleteDC()
        except Exception:
            pass


# ===== Хелперы =====
def _serialize_items(order):
    items = order.items.filter(cancelled=False).select_related('product')
    return [{
        'id': it.id,
        'name': it.product.name,
        'quantity': it.quantity,
        'line_total': float(it.price * it.quantity),
    } for it in items]

def _recalc_and_serialize(order):
    total = sum((it.price * it.quantity) for it in order.items.filter(cancelled=False))
    order.total = total
    order.save(update_fields=["total"])
    return _serialize_items(order), float(total)





@require_GET
def recalc_order_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    try:
        # 🔹 берём только новые блюда или удалённые
        new_items = order.items.filter(is_new=True, cancelled=False)

        # если нет новых блюд → ничего не печатаем
        if not new_items.exists():
            return JsonResponse({'ok': True, 'msg': 'Изменений нет', 'items': [], 'total': order.total})

        # печать на кухню
        print_to_printer("XP-80C (copy 1)", order.receipt_number, order.order_time, new_items, kitchen=True)

        # печать на кассу
        print_to_printer("XP-80", order.receipt_number, order.order_time, new_items, kitchen=False)

        # сбрасываем флаг is_new
        new_items.update(is_new=False)

        return JsonResponse({'ok': True, 'recalc': True, 'items': [
            {
                "id": it.id,
                "name": it.product.name,
                "quantity": it.quantity,
                "line_total": int(it.quantity * (it.price or it.product.price))
            } for it in order.items.filter(cancelled=False)
        ], 'total': int(order.items.filter(cancelled=False).aggregate(total=Sum(F('quantity')*F('price')))['total'] or 0)})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_POST
def print_cancelled_receipt(request):
    import win32ui
    import win32print
    import json
    from collections import defaultdict
    from datetime import datetime, time

    now = timezone.localtime(timezone.now())  # локальное время

    # Принимаем JSON или form-data
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return JsonResponse({"ok": False, "error": "Невалидный JSON"})
    else:
        data = request.POST or request.GET

    # Диапазон
    start_date = data.get("start")
    end_date   = data.get("end")
    start_time = data.get("start_time")
    end_time   = data.get("end_time")

    if start_date and end_date and start_time and end_time:
        try:
            start_dt = timezone.make_aware(datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M"))
            end_dt   = timezone.make_aware(datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M"))
        except Exception:
            # fallback на дефолтный диапазон
            today = now.date()
            start_dt = timezone.make_aware(datetime.combine(today, time(9, 0)))
            end_dt   = timezone.make_aware(datetime.combine(today, time(2, 0))) + timezone.timedelta(days=1)
    else:
        # дефолтный диапазон: 9:00 до 2:00 следующего дня
        today = now.date()
        start_dt = timezone.make_aware(datetime.combine(today, time(9, 0)))
        end_dt   = timezone.make_aware(datetime.combine(today, time(2, 0))) + timezone.timedelta(days=1)

    # Выборка отмен
    cancelled_orders = Order.objects.filter(
        cancelled=True,
        cancelled_at__range=(start_dt, end_dt)
    )
    cancelled_items = OrderItem.objects.filter(
        cancelled=True,
        cancelled_at__range=(start_dt, end_dt)
    )

    # Группировка блюд по заказу
    items_by_order = defaultdict(list)
    for it in cancelled_items:
        items_by_order[it.order_id].append(it)

    # Печать
    printer_name = "XP-80"
    pdc = win32ui.CreateDC()
    pdc.CreatePrinterDC(printer_name)
    pdc.StartDoc("Отменённые заказы и блюда")
    pdc.StartPage()

    font = win32ui.CreateFont({"name": "Consolas", "height": 28, "weight": 800})
    pdc.SelectObject(font)

    x = 0
    line_h = 30
    y = 0

    def draw(text):
        nonlocal y
        pdc.TextOut(x, y, str(text))
        y += line_h

    # Заголовок и период
    draw("=== ОТМЕНЫ ===")
    draw(f"{timezone.localtime(start_dt).strftime('%Y.%m.%d %H:%M:%S')} - {timezone.localtime(end_dt).strftime('%Y.%m.%d %H:%M:%S')}")
    draw("----------------------------------")

    printed_ids = set()

    # Раздел: отменённые заказы
    draw("Отменённые заказы:")
    for order in cancelled_orders:
        cashier_name = getattr(order.cancelled_by, 'name', '-') if order.cancelled_by else '-'
        order_time = timezone.localtime(order.cancelled_at).strftime('%Y.%m.%d %H:%M:%S') if order.cancelled_at else '-'

        draw(f"Заказ №{order.receipt_number or order.id} — {int(order.total or 0)} сом")
        draw(f"Оператор: {cashier_name}")
        draw(f"Время отмены: {order_time}")

        # Позиции внутри заказа
        for it in items_by_order.get(order.id, []):
            it_name = getattr(it.product, 'name', 'Неизвестно')
            qty = it.original_quantity or it.quantity or 0
            amount = int((it.price or 0) * qty)
            it_cashier = getattr(it.cancelled_by, 'name', '-') if it.cancelled_by else '-'
            it_time = timezone.localtime(it.cancelled_at).strftime('%Y.%m.%d %H:%M:%S') if it.cancelled_at else '-'

            draw(f"{it_name} x{qty} — {amount} сом")
            draw(f"Оператор: {it_cashier}")
            draw(f"Время отмены: {it_time}")

        printed_ids.add(order.id)
        draw("----------------------------------")

    # Раздел: блюда без отменённого заказа
    orphan_items = [it for it in cancelled_items if it.order_id not in printed_ids]
    if orphan_items:
        draw("Блюда без отменённого заказа:")
        for it in orphan_items:
            it_name = getattr(it.product, 'name', 'Неизвестно')
            qty = it.original_quantity or it.quantity or 0
            amount = int((it.price or 0) * qty)
            it_cashier = getattr(it.cancelled_by, 'name', '-') if it.cancelled_by else '-'
            it_time = timezone.localtime(it.cancelled_at).strftime('%Y.%m.%d %H:%M:%S') if it.cancelled_at else '-'

            draw(f"{it_name} x{qty} — {amount} сом")
            draw(f"Оператор: {it_cashier}")
            draw(f"Время отмены: {it_time}")
        draw("----------------------------------")

    # Итог
    draw(f"Всего отменённых заказов: {cancelled_orders.count()}")
    draw(f"Всего отменённых блюд: {cancelled_items.count()}")

    pdc.EndPage()
    pdc.EndDoc()
    pdc.DeleteDC()

    return JsonResponse({"ok": True, "printed": True})


from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Order

@csrf_exempt
def mark_delivery(request, order_id):
    if request.method == "POST":
        try:
            order = Order.objects.get(id=order_id)
            order.order_type = "delivery"   # ✅ правильное поле
            order.save()
            return JsonResponse({"ok": True})
        except Order.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Заказ не найден"}, status=404)
    return JsonResponse({"ok": False}, status=400)


# views.py

def kitchen_screen(request):
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

    cooking_orders = Order.objects.filter(
        status='pending',
        cancelled=False,
        order_time__gte=today
    ).order_by('order_time')

    called_orders = Order.objects.filter(
        status='called',
        cancelled=False,
        order_time__gte=today
    ).order_by('order_time')

    return render(request, 'kitchen_screen.html', {
        'cooking_orders': cooking_orders,
        'ready_orders': called_orders,
    })



@csrf_exempt
def update_dish_order(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        category = data.get('category')
        order = data.get('order', [])
        for index, dish_id in enumerate(order):
            Product.objects.filter(id=dish_id, category=category).update(order=index)
        return JsonResponse({'status': 'ok'})

from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone
from .models import OrderItem

def cancelled_report(request):
    # диапазон дат можно брать из GET параметров
    start = request.GET.get("start")
    end = request.GET.get("end")

    if start and end:
        start = timezone.datetime.fromisoformat(start)
        end = timezone.datetime.fromisoformat(end)
    else:
        # по умолчанию — сегодня
        today = timezone.localtime(timezone.now()).date()
        start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    items = OrderItem.objects.filter(
        order__order_time__gte=start,
        order__order_time__lte=end,
        cancelled=True
    ).select_related("order", "product", "cancelled_by")

    grouped = {}
    total_sum = 0
    for it in items:
        order = it.order
        receipt = order.receipt_number or "-"
        cancelled_by = it.cancelled_by.name if it.cancelled_by else "неизвестно"
        cancelled_at = it.cancelled_at or order.order_time
        key = (receipt, cancelled_by, cancelled_at)

        price = it.price or it.product.price or 0
        qty = it.original_quantity or it.quantity or 0
        total = price * qty
        total_sum += total

        if key not in grouped:
            grouped[key] = {"items": [], "order_total": 0}
        grouped[key]["items"].append(f"{it.product.name} × {qty} шт = {total:.2f} сом")
        grouped[key]["order_total"] += total

    return render(request, "report_by_date.html", {
        "grouped": grouped,
        "total_sum": total_sum,
        "start": start,
        "end": end,
    })







from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
import threading

from .sound import announce
from .models import Order


def order_call(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        order.status = 'called'
        order.save()

        num = order.receipt_number or order.id
        threading.Thread(target=announce, args=(num,)).start()

        return JsonResponse({"ok": True, "order": num})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# orders/views.py
import threading
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Order
from .sound import announce_en  # твоя функция английской озвучки

def call_order_english(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        # меняем статус заказа
        order.status = 'called'
        order.save()

        # берём номер для озвучки
        num = order.receipt_number or order.id

        # запускаем озвучку в отдельном потоке
        threading.Thread(target=announce_en, args=(num,)).start()

        return JsonResponse({"ok": True, "order": num})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


from django.shortcuts import render

def reklama_view(request):
    return render(request, "reklama.html")

