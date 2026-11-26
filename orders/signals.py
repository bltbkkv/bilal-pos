from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import OrderItem, Order, DrinkInventory, DrinkMovement

def is_drink(product):
    return product.category and product.category.lower() == "Напитки"

@receiver(post_save, sender=OrderItem)
def decrease_drink_stock_on_create(sender, instance, created, **kwargs):
    if created and not instance.order.cancelled and is_drink(instance.product):
        inventory, _ = DrinkInventory.objects.get_or_create(product=instance.product)
        inventory.quantity -= instance.quantity
        inventory.save(update_fields=['quantity'])
        DrinkMovement.objects.create(
            product=instance.product,
            quantity=-instance.quantity,
            movement_type='out',
            order_item=instance,
            note=f"Списание по заказу #{instance.order.receipt_number}"
        )

@receiver(post_delete, sender=OrderItem)
def restore_drink_stock_on_delete(sender, instance, **kwargs):
    if is_drink(instance.product) and not instance.order.cancelled:
        inventory, _ = DrinkInventory.objects.get_or_create(product=instance.product)
        inventory.quantity += instance.quantity
        inventory.save(update_fields=['quantity'])
        DrinkMovement.objects.create(
            product=instance.product,
            quantity=instance.quantity,
            movement_type='in',
            order_item=instance,
            note=f"Восстановление при удалении позиции из заказа #{instance.order.receipt_number}"
        )

@receiver(post_save, sender=Order)
def handle_order_cancellation(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = Order.objects.get(pk=instance.pk)
        except Order.DoesNotExist:
            return
        if old.cancelled != instance.cancelled:
            if instance.cancelled:
                for item in instance.orderitem_set.filter(product__category__iexact="Напитки"):
                    inventory, _ = DrinkInventory.objects.get_or_create(product=item.product)
                    inventory.quantity += item.quantity
                    inventory.save(update_fields=['quantity'])
                    DrinkMovement.objects.create(
                        product=item.product,
                        quantity=item.quantity,
                        movement_type='in',
                        order_item=item,
                        note=f"Возврат при отмене заказа #{instance.receipt_number}"
                    )
            else:
                for item in instance.orderitem_set.filter(product__category__iexact="Напитки"):
                    inventory, _ = DrinkInventory.objects.get_or_create(product=item.product)
                    inventory.quantity -= item.quantity
                    inventory.save(update_fields=['quantity'])
                    DrinkMovement.objects.create(
                        product=item.product,
                        quantity=-item.quantity,
                        movement_type='out',
                        order_item=item,
                        note=f"Списание при восстановлении заказа #{instance.receipt_number}"
                    )