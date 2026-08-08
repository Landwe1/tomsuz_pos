from django.db import models
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
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
    USER_ROLES = [('OWNER', 'Shop Owner'), ('CASHIER', 'Cashier')]
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='staff', null=True, blank=True)
    role = models.CharField(max_length=10, choices=USER_ROLES, default='CASHIER')

    def __str__(self):
        return f"{self.user.username} ({self.role}) - {self.store.name if self.store else 'No Store'}"

    @property
    def is_owner(self):
        return self.role == 'OWNER'


class Sale(models.Model):
    PAYMENT_METHODS = [
        ('CASH', 'Cash'), 
        ('MOMO', 'Mobile Money (MTN/Airtel)'), 
        ('CREDIT', 'Store Credit / Debt')
    ]
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='sales', null=True, blank=True)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    change_due = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH')
    is_synced = models.BooleanField(default=True)
    offline_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        store_name = self.store.name if self.store else "Unassigned Store"
        return f"Sale #{self.id} - {store_name} - K{self.total_amount}"

    def update_total_amount(self):
        """Recalculates the master aggregate checkout price from row entries."""
        aggregate = self.items.aggregate(total=models.Sum('subtotal'))
        self.total_amount = aggregate['total'] or 0.00
        # Automatically adjust change due if payment parameters are explicitly filled
        if self.amount_paid:
            self.change_due = self.amount_paid - self.total_amount
        self.save(update_fields=['total_amount', 'change_due'])

    def get_total_profit(self):
        return sum(item.profit for item in self.items.all())


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    min_price_allowed = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    @property
    def profit(self):
        return self.subtotal - (self.cost_price * self.quantity)

    def save(self, *args, **kwargs):
        # 1. Financial Guardrails
        if self.unit_price < self.product.min_price:
            raise ValueError(f"Price cannot be lower than K{self.product.min_price}")

        self.subtotal = self.unit_price * self.quantity

        # 2. Prevent concurrent race conditions using atomic transaction locks
        with transaction.atomic():
            # Refresh product stock directly from database with row lock
            product = Product.objects.select_for_update().get(pk=self.product_id)

            if not self.pk:
                # Flow A: Fresh New Sale
                self.cost_price = product.buying_price
                self.min_price_allowed = product.min_price
                stock_delta = self.quantity
            else:
                # Flow B: Handling Updated Sale Items (e.g., changing quantity from 2 to 5)
                original = SaleItem.objects.get(pk=self.pk)
                stock_delta = self.quantity - original.quantity

            # Verify stock bounds against the relative delta change
            if product.stock_quantity >= stock_delta:
                product.stock_quantity -= stock_delta
                product.save(update_fields=['stock_quantity'])
                self.product = product  # Synchronize model memory reference
            else:
                raise ValueError(f"Not enough stock available for {product.name}. Requested adjustment: {stock_delta}, Available: {product.stock_quantity}")

            super().save(*args, **kwargs)


# --- REFINED AUTOMATION SIGNALS & LIFECYCLE HOOKS ---

@receiver(post_save, sender=SaleItem)
@receiver(post_delete, sender=SaleItem)
def update_sale_financial_summary(sender, instance, **kwargs):
    """Triggers total calculation updates on parent sale whenever line items change."""
    if instance.sale:
        instance.sale.update_total_amount()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

