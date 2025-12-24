from django.contrib import admin
from .models import Product
from .models import Employee

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'is_active')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'role', 'pin')
    search_fields = ('name', 'role', 'pin')
    list_filter = ('role',)