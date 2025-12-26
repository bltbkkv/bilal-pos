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
    receipt_number = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_column="status"
    )
    order_type = models.CharField(  # 🔹 добавлено поле для "здесь/с собой/доставка"
        max_length=20,
        choices=ORDER_TYPE_CHOICES,
        default='here',
        db_column="order_type"
    )

    class Meta:
        db_table = "orders"

    def __str__(self):
        return f"Заказ #{self.id} — {self.total} сом ({self.get_status_display()})"


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
    created_at = models.DateTimeField(auto_now_add=True)
    options = models.JSONField(default=list, blank=True, null=True) # 🔹 добавлено поле для модификаторов ("без овощей")

    def total_price(self):
        return (self.price or self.product.price) * (self.quantity or 0)

    def total_profit(self):
        sell_price = self.price or self.product.price
        cost_price = self.product.cost_price or 0
        return (sell_price - cost_price) * (self.quantity or 0)

    class Meta:
        db_table = "order_items"

    @property
    def line_total(self):
        return (self.quantity or 0) * (self.price or 0)

    def __str__(self):
        opts = f" ({', '.join(self.options)})" if self.options else ""
        return f"{self.product.name}{opts} x{self.quantity} — {self.line_total} сом"

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

