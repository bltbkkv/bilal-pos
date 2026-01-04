from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Employee(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    role = models.CharField(max_length=50, null=True, blank=True)
    pin = models.CharField(max_length=10, null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)  # исправил импорт

    class Meta:
        db_table = "employee"

    def __str__(self):
        return f"{self.name} ({self.role})"


class Product(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    category = models.CharField(max_length=50, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(null=True)
    is_active = models.BooleanField(default=True)
    image = models.ImageField(upload_to='products/', null=True, blank=True)

    ingredient_type = models.CharField(max_length=50, choices=[('lavash_m', 'M-лаваш'), ('lavash_l', 'Л-лаваш'),
                                                               ('lavash_s', 'Сырный лаваш'), ('bun', 'Булочка'),
                                                               ('strips', 'Стрипсы'), ('wings', 'Крылышки'), ],
                                       null=True, blank=True)
    ingredient_usage = models.DecimalField(max_digits=5, decimal_places=2, default=1,
                                           help_text="Сколько единиц ингредиента расходуется на одну порцию")

    class Meta:
        db_table = "products"

    def __str__(self):
        return f"{self.name} — {self.price} сом (себестоимость: {self.cost_price} сом, прибыль: {self.profit_per_unit()} сом)"

    def profit_per_unit(self):
        if not self.price:
            return 0
        return round(self.price - (self.cost_price or 0), 2)



class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Готовится'),
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
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        db_column="employee_id",
        related_name="orders"
    )
    total = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    order_time = models.DateTimeField(auto_now_add=True)
    cancelled = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=True)
    note = models.CharField(max_length=200, null=True, blank=True)
    cancelled_by = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    # 🔹 исправлено: убран default=0, чтобы save() сам проставлял номер
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

    class Meta:
        db_table = "orders"

    def __str__(self):
        return f"Заказ #{self.receipt_number} — {self.total} сом ({self.get_status_display()})"

    # 🔹 логика циклической нумерации
    def save(self, *args, **kwargs):
        if not self.receipt_number:  # только при создании нового заказа
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
    created_at = models.DateTimeField(auto_now_add=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

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
    deleted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "deleted_items"

    def __str__(self):
        return f"{self.product_name} x{self.quantity} — удалено кассиром {self.cashier.name if self.cashier else '-'}"

