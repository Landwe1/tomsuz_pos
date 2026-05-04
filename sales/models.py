from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
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
    PAYMENT_METHODS = [('CASH', 'Cash'), ('MOMO', 'Mobile Money (MTN/Airtel)'), ('CREDIT', 'Store Credit / Debt')]
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
    def get_total_profit(self):
        return sum(item.profit for item in self.items.all())

class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    # Recommended: track the min_price allowed at the time of sale
    min_price_allowed = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    @property
    def profit(self):
        return self.subtotal - (self.cost_price * self.quantity)

    def save(self, *args, **kwargs):
        # 1. Check if the price is below the allowed minimum
        if self.unit_price < self.product.min_price:
            raise ValueError(f"Price cannot be lower than K{self.product.min_price}")

        # 2. Calculate subtotal
        self.subtotal = self.unit_price * self.quantity

        # 3. Handle New Items
        if not self.pk:
            self.cost_price = self.product.buying_price
            self.min_price_allowed = self.product.min_price # Snapshot of the rule
            
            # 4. Stock Management
            if self.product.stock_quantity >= self.quantity:
                self.product.stock_quantity -= self.quantity
                self.product.save()
            else:
                raise ValueError("Not enough stock available")

        super().save(*args, **kwargs)

# --- REFINED SIGNALS ---
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

