from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from .trusted_time import get_true_now_utc

class Employee(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Имя")
    role = models.CharField(max_length=50, null=True, blank=True, verbose_name="Должность")
    pin = models.CharField(max_length=10, null=True, blank=True, verbose_name="PIN-код")
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)  # исправил импорт

    class Meta:
        db_table = "employee"
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"

    def __str__(self):
        return f"{self.name} ({self.role})"

    def save(self, *args, **kwargs):
        # Нормализуем роль: убираем лишние пробелы и приводим к нижнему
        # регистру. Весь остальной код (проверки вида role == "админ" в
        # шаблонах и views) сравнивает именно с нижним регистром, поэтому
        # без этой нормализации "Админ"/"АДМИН"/" админ " считались бы
        # другой ролью и молча теряли админские возможности в интерфейсе.
        if self.role:
            self.role = self.role.strip().lower()
        super().save(*args, **kwargs)


from django.core.exceptions import ValidationError

from django.core.exceptions import ValidationError
from django.db import models

class Product(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True, verbose_name="Название")
    category = models.CharField(max_length=50, null=True, blank=True, verbose_name="Категория")
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, verbose_name="Цена")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Себестоимость")
    created_at = models.DateTimeField(null=True, verbose_name="Дата создания")
    is_active = models.BooleanField(default=True, verbose_name="Показывать в меню")
    image = models.ImageField(upload_to='products/', null=True, blank=True, verbose_name="Фото")

    ingredient_type = models.CharField(
        max_length=50,
        choices=[
            ('lavash_m', 'M-лаваш'),
            ('lavash_l', 'Л-лаваш'),
            ('lavash_s', 'Сырный лаваш'),
            ('bun', 'Булочка'),
            ('strips', 'Стрипсы'),
            ('wings', 'Крылышки'),
        ],
        null=True, blank=True,
        verbose_name="Тип ингредиента (для учёта остатков)",
    )
    ingredient_usage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1,
        help_text="Сколько единиц ингредиента расходуется на одну порцию",
        verbose_name="Расход ингредиента на порцию",
    )
    order = models.PositiveIntegerField(default=0, help_text="Порядок отображения внутри категории", verbose_name="Порядок")

    class Meta:
        db_table = "products"
        verbose_name = "Блюдо"
        verbose_name_plural = "Блюда"

    def __str__(self):
        return f"{self.name} — {self.price} сом (себестоимость: {self.cost_price} сом, прибыль: {self.profit_per_unit()} сом)"

    def profit_per_unit(self):
        if not self.price:
            return 0
        return round(self.price - (self.cost_price or 0), 2)

    def _normalize_category(self):
        """Убирает лишние пробелы и приводит категорию к уже существующему
        написанию без учёта регистра. Если категория "Напитки" уже есть в
        базе, ввод "напитки"/"НАПИТКИ"/"  напитки " автоматически
        превращается в то же самое "Напитки" — вместо создания фактически
        новой, отдельной категории."""
        if not self.category:
            return
        self.category = self.category.strip()
        if not self.category:
            return
        existing = (
            Product.objects
            .filter(category__iexact=self.category)
            .exclude(pk=self.pk)
            .exclude(category=self.category)  # уже точное совпадение — трогать нечего
            .values_list('category', flat=True)
            .first()
        )
        if existing:
            self.category = existing

    def clean(self):
        self._normalize_category()

        # Ограничение на количество уникальных категорий (только активные),
        # сравнение без учёта регистра — иначе "Напитки" и "напитки"
        # считались бы двумя разными категориями и лимит легко обходился.
        categories = (
            Product.objects.filter(is_active=True)
            .exclude(pk=self.pk)
            .values_list('category', flat=True)
            .distinct()
        )
        normalized_existing = {c.strip().lower() for c in categories if c}
        is_new_category = bool(self.category) and self.category.strip().lower() not in normalized_existing
        if not self.pk and is_new_category and len(normalized_existing) >= 12:
            raise ValidationError("Нельзя создать больше 12 категорий")

        # Ограничение на количество блюд внутри одной категории (только активные)
        if not self.pk and self.category and Product.objects.filter(
            category__iexact=self.category, is_active=True
        ).count() >= 100:
            raise ValidationError(f"В категории «{self.category}» нельзя создать больше 100 блюд")

    def save(self, *args, **kwargs):
        # Гарантируем нормализацию категории даже если объект создаётся
        # в обход admin-формы (скриптом, из shell, через будущий API) —
        # там full_clean()/clean() Django не вызывает автоматически.
        self._normalize_category()
        super().save(*args, **kwargs)




class Order(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Черновик'),  # клиент выбрал, но не оплатил
        ('pending_payment', 'Ожидает оплаты'),  # клиент показал номер чека кассиру
        ('paid', 'Оплачен'),  # кассир подтвердил оплату
        ('pending', 'Готовится'),
        ('called', 'Вызван'),
        ('ready', 'Готово'),
        ('cancelled', 'Отменён'),
    ]

    ORDER_TYPE_CHOICES = [
        ('here', 'Здесь'),
        ('takeaway', 'С собой'),
        ('delivery', 'Доставка'),
    ]

    id = models.AutoField(primary_key=True)
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        db_column="employee_id",
        related_name="orders"
    )
    total = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    order_time = models.DateTimeField(default=get_true_now_utc)
    cancelled = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=True)
    note = models.CharField(max_length=200, null=True, blank=True)
    cancelled_by = models.ForeignKey(
        'Employee',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_orders"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    receipt_number = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_column="status"
    )
    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPE_CHOICES,
        default='here',
        db_column="order_type"
    )
    # Скидки. total хранит сумму УЖЕ со скидкой (так отчёты по выручке остаются верными).
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Скидка, сом")
    manual_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Ручная скидка, %")
    discount_note = models.CharField(max_length=200, blank=True, default="", verbose_name="Причина скидки")

    class Meta:
        db_table = "orders"

    def __str__(self):
        return f"Заказ #{self.receipt_number} — {self.total} сом ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            last_order = Order.objects.order_by('-id').first()
            if last_order and last_order.receipt_number:
                self.receipt_number = (last_order.receipt_number % 40) + 1
            else:
                self.receipt_number = 1
        super().save(*args, **kwargs)



class OrderItem(models.Model):
    id = models.AutoField(primary_key=True)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        db_column="order_id",
        related_name="items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        db_column="product_id",
        related_name="order_items"
    )
    quantity = models.IntegerField(null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    cancelled = models.BooleanField(default=False)
    cancelled_by = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL)
    cancelled_at = models.DateTimeField(null=True, blank=True)  # ⏱ время отмены
    created_at = models.DateTimeField(default=get_true_now_utc)
    options = models.JSONField(default=list, blank=True, null=True) # 🔹 добавлено поле для модификаторов ("без овощей")
    is_new = models.BooleanField(default=False)
    is_draft = models.BooleanField(default=False)
    original_quantity = models.IntegerField(default=0)

    def total_price(self):
        return (self.price or self.product.price) * (self.quantity or 0)

    def total_profit(self):
        sell_price = self.price or self.product.price
        cost_price = self.product.cost_price or 0
        return (sell_price - cost_price) * (self.quantity or 0)

    @property
    def line_total(self):
        return self.price * self.quantity

    class Meta:
        db_table = "order_items"


class Supply(models.Model):
    INGREDIENT_CHOICES = [
        ('lavash_m', 'M-лаваш'),
        ('lavash_l', 'Л-лаваш'),
        ('lavash_s', 'Сырный лаваш'),
        ('bun', 'Булочка'),
        ('strips', 'Стрипсы'),
        ('wings', 'Крылышки'),
    ]

    ingredient = models.CharField(max_length=50, choices=INGREDIENT_CHOICES)
    delivered_qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=get_true_now_utc)

    class Meta:
        db_table = "supplies"

    def __str__(self):
        return f"{self.get_ingredient_display()} — {self.delivered_qty}"

class DeletedItem(models.Model):
    id = models.AutoField(primary_key=True)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        db_column="order_id",
        related_name="deleted_items"
    )
    product_name = models.CharField(max_length=100)  # название блюда
    quantity = models.IntegerField(default=1)
    reason = models.CharField(max_length=255, null=True, blank=True)  # причина удаления
    cashier = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="cashier_id",
        related_name="deleted_items"
    )
    deleted_at = models.DateTimeField(default=get_true_now_utc)

    class Meta:
        db_table = "deleted_items"

    def __str__(self):
        return f"{self.product_name} x{self.quantity} — удалено кассиром {self.cashier.name if self.cashier else '-'}"


class DrinkInventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name='inventory')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.product.name}: {self.quantity}"

class DrinkMovement(models.Model):
    MOVEMENT_TYPES = (('in', 'Приход'), ('out', 'Расход'))
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPES)
    created_at = models.DateTimeField(default=get_true_now_utc)
    order_item = models.ForeignKey('OrderItem', null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True, null=True)


class CategoryOrder(models.Model):
    """Порядок отображения категорий в меню. Category в Product — просто
    текстовое поле (не отдельная таблица), поэтому порядок хранится здесь,
    отдельно, без изменения структуры Product."""
    name = models.CharField(max_length=50, unique=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "category_order"
        ordering = ["order"]

    def __str__(self):
        return f"{self.name} ({self.order})"


class Promotion(models.Model):
    """Акция/день скидок. Применяется кассой автоматически.
    Пустые поля = «без ограничения»: нет категории и блюда — на всё меню;
    нет дней недели — каждый день; нет дат — бессрочно."""
    name = models.CharField(max_length=100, verbose_name="Название (попадёт в чек)")
    percent = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Скидка, %")
    category = models.CharField(max_length=50, blank=True, default="", verbose_name="Категория (пусто = всё меню)")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.CASCADE, verbose_name="Только это блюдо")
    weekdays = models.CharField(
        max_length=20, blank=True, default="",
        verbose_name="Дни недели", help_text="Цифры через запятую: 0=пн, 1=вт, 2=ср, 3=чт, 4=пт, 5=сб, 6=вс. Пусто = каждый день",
    )
    date_from = models.DateField(null=True, blank=True, verbose_name="С даты")
    date_to = models.DateField(null=True, blank=True, verbose_name="По дату")
    is_active = models.BooleanField(default=True, verbose_name="Включена")

    class Meta:
        db_table = "promotions"
        verbose_name = "Акция"
        verbose_name_plural = "Акции и дни скидок"

    def __str__(self):
        return f"{self.name} −{self.percent}%"

    def clean(self):
        if self.percent is None or not (0 < self.percent <= 100):
            raise ValidationError("Скидка должна быть от 0 до 100 процентов")
        if self.weekdays:
            parts = [p.strip() for p in self.weekdays.split(",") if p.strip()]
            if not parts or any(not p.isdigit() or int(p) > 6 for p in parts):
                raise ValidationError("Дни недели: цифры 0–6 через запятую")
            self.weekdays = ",".join(parts)
