from django.db import models


class Category(models.Model):
    store = models.ForeignKey('sales.Store', on_delete=models.CASCADE, related_name='categories', null=True)
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name_plural = "Categories"
        unique_together = ('store', 'name')

    def __str__(self):
        return f"{self.name} ({self.store.name if self.store else 'Global'})"


class ActiveProductManager(models.Manager):
    """Custom manager that only returns active (non-deleted) products by default."""
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


class Product(models.Model):
    UNIT_CHOICES = [
        ('PC', 'Piece / Item'),
        ('KG', 'Kilogram (kg)'),
        ('PK', 'Packet / Bundle'),
        ('LT', 'Litre (L)'),
    ]

    # --- TENANCY INTEGRATION ---
    store = models.ForeignKey('sales.Store', on_delete=models.CASCADE, related_name='inventory', null=True)
    
    # --- CORE DETAILS ---
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    barcode = models.CharField(max_length=50, null=True, blank=True, help_text="Leave blank for loose items")
    unit_type = models.CharField(max_length=2, choices=UNIT_CHOICES, default='PC')
    
    # --- SOFT DELETE FLAG ---
    is_active = models.BooleanField(default=True, help_text="Designates whether this product is active. Uncheck instead of deleting.")

    # --- PRICE SECTION ---
    buying_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    selling_price = models.DecimalField(max_digits=10, decimal_places=2) 
    min_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00, 
        help_text="Minimum allowed selling price"
    )

    # --- INVENTORY TRACKING ---
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Use decimals for KG items")
    low_stock_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)
    
    # --- TIMESTAMPS ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_restocked = models.DateTimeField(auto_now=True)

    # --- CUSTOM MANAGERS (Must be inside Product class, not ActiveProductManager) ---
    objects = ActiveProductManager()    # Default: returns only active products
    all_objects = models.Manager()      # Fallback: returns all products (including deleted) when needed

    def __str__(self):
        return f"{self.name} - {self.store.name if self.store else 'No Store'}"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def stock_value(self):
        if self.stock_quantity and self.selling_price:
            return self.stock_quantity * self.selling_price
        return 0.00

    @property
    def potential_profit(self):
        if self.stock_quantity and self.selling_price and self.buying_price:
            return self.stock_quantity * (self.selling_price - self.buying_price)
        return 0.00

