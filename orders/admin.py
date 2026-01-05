from django.contrib import admin
from .models import Product
from .models import Employee

from django.contrib import admin
from django.core.exceptions import ValidationError
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_active')

    def save_model(self, request, obj, form, change):
        # Ограничение на количество уникальных категорий
        categories = Product.objects.values_list('category', flat=True).distinct()
        if not change and obj.category not in categories and len(categories) >= 12:
            raise ValidationError("Нельзя создать больше 12 категорий")

        # Ограничение на количество блюд внутри одной категории
        if not change and Product.objects.filter(category=obj.category).count() >= 24:
            raise ValidationError(f"В категории «{obj.category}» нельзя создать больше 24 блюд")

        super().save_model(request, obj, form, change)



@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'role', 'pin')
    search_fields = ('name', 'role', 'pin')
    list_filter = ('role',)

