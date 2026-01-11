from django.contrib import admin
from .models import Product
from .models import Employee

from django.contrib import admin
from django.core.exceptions import ValidationError
from .models import Product

# admin.py
from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_active")
    actions = ["soft_delete"]

    def delete_model(self, request, obj):
        # вместо удаления просто скрываем
        obj.is_active = False
        obj.save()

    def delete_queryset(self, request, queryset):
        queryset.update(is_active=False)

    def soft_delete(self, request, queryset):
        queryset.update(is_active=False)
    soft_delete.short_description = "Скрыть выбранные блюда"




@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'role', 'pin')
    search_fields = ('name', 'role', 'pin')
    list_filter = ('role',)

