from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

from .models import Product, Employee


class PickerTextInput(forms.TextInput):
    """Текстовое поле для категории/должности + ВИДИМЫЙ выпадающий список
    сверху для выбора уже существующего значения одним кликом.

    Раньше подсказка была только через HTML5 datalist — она едва заметна
    (маленькая стрелочка сбоку поля), и человек, не знающий про эту
    возможность, просто печатал заново вручную, легко ошибаясь в регистре.
    Теперь есть обычный, привычный <select> — увидеть и выбрать из него
    можно, даже не зная о существовании подсказок.

    Финальное значение поля всё равно остаётся обычным текстом (выбор из
    списка просто подставляет текст в поле ввода), поэтому вписать новое
    значение по-прежнему можно — просто напечатав его. Модель на сохранении
    дополнительно подчищает регистр/пробелы, так что даже ручная опечатка
    в написании уже существующей категории не создаст дубликат."""

    def __init__(self, choices_callable, attrs=None):
        super().__init__(attrs)
        self.choices_callable = choices_callable

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        text_id = attrs.get('id', f'id_{name}')
        attrs.setdefault('autocomplete', 'off')
        attrs['placeholder'] = 'или впишите новое значение сюда'
        attrs['style'] = 'width: 100%; padding: 6px; box-sizing: border-box;'
        input_html = super().render(name, value, attrs, renderer)

        choices = self.choices_callable()
        select_options = ''.join(f'<option value="{c}">{c}</option>' for c in choices)
        select_html = (
            f'<select onchange="if(this.value){{'
            f"document.getElementById('{text_id}').value = this.value;"
            f'this.selectedIndex = 0;'
            f"}}\" style=\"display:block; width:100%; padding:6px; margin-bottom:6px; "
            f'box-sizing:border-box;">'
            f'<option value="">— выбрать из уже существующих —</option>'
            f'{select_options}'
            f'</select>'
        )

        return mark_safe(select_html + input_html)


def _existing_categories():
    return sorted(
        Product.objects
        .exclude(category__isnull=True)
        .exclude(category='')
        .values_list('category', flat=True)
        .distinct()
    )


def _existing_roles():
    return sorted(
        Employee.objects
        .exclude(role__isnull=True)
        .exclude(role='')
        .values_list('role', flat=True)
        .distinct()
    )


class ProductAdminForm(forms.ModelForm):
    class Meta:
        model = Product
        # Явно перечисляем поля вместо '__all__' — order и created_at
        # управляются не вручную (order — перетаскиванием в самом меню,
        # created_at нигде в приложении не используется), показывать их
        # в форме только сбивает с толку.
        fields = [
            'name', 'category', 'price', 'image', 'is_active',
            'cost_price', 'ingredient_type', 'ingredient_usage',
        ]
        widgets = {
            'category': PickerTextInput(_existing_categories),
        }


class EmployeeAdminForm(forms.ModelForm):
    class Meta:
        model = Employee
        # user (привязка к логину) — техническое поле, обычному менеджеру,
        # добавляющему сотрудника, трогать его незачем.
        fields = ['name', 'role', 'pin']
        widgets = {
            'role': PickerTextInput(_existing_roles),
        }


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ("name", "category", "price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "category")
    actions = ["soft_delete"]

    # Форма разбита на понятный минимум сразу и редко нужные поля —
    # свёрнутым блоком ниже, чтобы не пугать длинной формой при
    # обычном добавлении блюда.
    fieldsets = (
        (None, {
            "fields": ("name", "category", "price", "image", "is_active"),
        }),
        ("Дополнительно (для учёта себестоимости и остатков ингредиентов)", {
            "classes": ("collapse",),
            "fields": ("cost_price", "ingredient_type", "ingredient_usage"),
        }),
    )

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
    form = EmployeeAdminForm
    list_display = ('id', 'name', 'role', 'pin')
    search_fields = ('name', 'role', 'pin')
    list_filter = ('role',)



from .models import Promotion

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "percent", "category", "product", "weekdays", "date_from", "date_to", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active",)
