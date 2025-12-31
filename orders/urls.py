from django.urls import path
from . import views
import os
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def shutdown(request):
    os._exit(0)  # мгновенно завершает сервер
    return JsonResponse({"ok": True})


urlpatterns = [
    # главное меню
    path('menu/', views.menu, name='menu'),

    # оформление заказа
    path('orders/submit/', views.submit_order, name='submit_order'),

    # список заказов
    path('orders/', views.orders_list, name='orders_list'),

    # смена статуса заказа на "Готово"
    path('orders/<int:order_id>/ready/', views.mark_order_ready, name='mark_order_ready'),

    # печать чека (основной маршрут)
    path('orders/<int:order_id>/receipt/', views.print_receipt_view, name='print_receipt'),

    # печать чека (альтернативный маршрут для совместимости)
    path('orders/receipt/<int:order_id>/', views.print_receipt_view, name='print_receipt_alt'),

    # отчёты
    path('reports/', views.reports, name='reports'),
    path('report/by-date/', views.report_by_date, name='report_by_date'),

    # получение ID сотрудника по PIN
    path('employee/get-id/', views.get_employee_id, name='get_employee_id'),
path('logout/', views.logout, name='logout'),
path('report/receipt/', views.report_receipt, name='report_receipt'),
path('orders/<int:order_id>/cancel/', views.cancel_order, name='cancel_order'),
    path('order-items/<int:item_id>/cancel/', views.cancel_order_item, name='cancel_order_item'),
path("orders/<int:order_id>/toggle-paid/", views.toggle_paid, name="toggle_paid"),
    path('orders/ready/', views.orders_ready_list, name='orders_ready_list'),
    path('orders/<int:order_id>/edit/', views.edit_order, name='edit_order'),
    path('orders/<int:order_id>/add-item/', views.add_item_to_order, name='add_item_to_order'),
    path('order-items/<int:item_id>/remove/', views.remove_item_from_order, name='remove_item_from_order'),
    path('orders/<int:order_id>/recalc/', views.recalc_order_total, name='recalc_order_total'),
path('orders/<int:order_id>/receipt/reprint/', views.reprint_receipt_view, name='reprint_receipt'),
path('orders/<int:order_id>/call/', views.call_order, name='call_order'),
path('order-items/<int:item_id>/reduce/', views.reduce_order_item_quantity, name='reduce_order_item_quantity'),
path("shutdown/", shutdown),

]
