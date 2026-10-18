from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from products.models import Product


class Store(models.Model):
    """The central business entity."""
    name = models.CharField(max_length=100)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_store')
    address = models.TextField(blank=True, null=True)
    logo = models.ImageField(upload_to='store_logos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    USER_ROLES = [
        ('OWNER', 'Shop Owner'),
        ('CASHIER', 'Cashier'),
        ('LENDER', 'Lender / Loan Officer'),  # <--- Added
        ('ADMIN', 'System Administrator'),    # <--- Added
    ]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='staff', null=True, blank=True)
    role = models.CharField(max_length=10, choices=USER_ROLES, default='CASHIER')

    def __str__(self):
        store_name = self.store.name if self.store else 'No Store'
        return f"{self.user.username} ({self.get_role_display()}) - {store_name}"

    @property
    def is_owner(self):
        return self.role == 'OWNER'

    @property
    def is_lender(self):
        return self.role == 'LENDER' or self.user.is_staff

class Sale(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'), 
        ('MOMO', 'Mobile Money (MTN/Airtel)'), 
        ('CREDIT', 'Store Credit / Debt')
    ]
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sales', null=True, blank=True)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    change_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    is_synced = models.BooleanField(default=True)
    offline_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        store_name = self.store.name if self.store else "Unassigned Store"
        return f"Sale #{self.id} - {store_name} - K{self.total_amount}"

    def update_total_amount(self):
        """Recalculates the master aggregate checkout price from line items."""
        aggregate = self.items.aggregate(total=models.Sum('subtotal'))
        self.total_amount = aggregate['total'] or Decimal('0.00')
        
        if self.amount_paid:
            self.change_due = max(Decimal('0.00'), self.amount_paid - self.total_amount)
            
        Sale.objects.filter(pk=self.pk).update(
            total_amount=self.total_amount,
            change_due=self.change_due
        )

    def get_total_profit(self):
        return sum(item.profit for item in self.items.all())


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    min_price_allowed = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    @property
    def profit(self):
        return self.subtotal - (self.cost_price * self.quantity)

    def save(self, *args, **kwargs):
        # 1. Price Guardrails
        if self.unit_price < self.product.min_price:
            raise ValueError(f"Price (K{self.unit_price}) cannot be lower than minimum allowed (K{self.product.min_price}).")

        self.subtotal = self.unit_price * self.quantity

        # 2. Atomic Stock Adjustment
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product_id)

            if not self.pk:
                self.cost_price = product.buying_price
                self.min_price_allowed = product.min_price
                stock_delta = self.quantity
            else:
                original_qty = SaleItem.objects.values_list('quantity', flat=True).get(pk=self.pk)
                stock_delta = self.quantity - original_qty

            if product.stock_quantity < stock_delta:
                raise ValueError(
                    f"Insufficient stock for {product.name}. "
                    f"Requested adjustment: {stock_delta}, Available: {product.stock_quantity}"
                )

            product.stock_quantity -= stock_delta
            product.save(update_fields=['stock_quantity'])
            
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Restores product stock when line item is deleted."""
        with transaction.atomic():
            product = Product.objects.select_for_update().get(pk=self.product_id)
            product.stock_quantity += self.quantity
            product.save(update_fields=['stock_quantity'])
            super().delete(*args, **kwargs)


# --- SIGNALS ---

@receiver(post_save, sender=SaleItem)
@receiver(post_delete, sender=SaleItem)
def update_sale_financial_summary(sender, instance, **kwargs):
    """Updates total calculation on parent sale without triggering recursive signals."""
    if instance.sale_id:
        instance.sale.update_total_amount()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()

