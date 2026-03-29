from django.db import models

class Category(models.Model):
    # Added store so each shop has its own categories (e.g., "Grocery", "Hardware")
    store = models.ForeignKey('sales.Store', on_delete=models.CASCADE, related_name='categories', null=True)
    name = models.CharField(max_length=100)
    
    class Meta:
        verbose_name_plural = "Categories"
        # Prevent duplicate category names within the SAME shop
        unique_together = ('store', 'name')

    def __str__(self):
        return f"{self.name} ({self.store.name if self.store else 'Global'})"


class Product(models.Model):
    UNIT_CHOICES = [
        ('PC', 'Piece / Item'),
        ('KG', 'Kilogram (kg)'),
        ('PK', 'Packet / Bundle'),
        ('LT', 'Litre (L)'),
    ]

    # CRITICAL: Every product must belong to a specific store
    store = models.ForeignKey('sales.Store', on_delete=models.CASCADE, related_name='inventory', null=True)
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Linked category must also belong to the same store
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    
    barcode = models.CharField(max_length=50, null=True, blank=True, help_text="Leave blank for loose items")
    unit_type = models.CharField(max_length=2, choices=UNIT_CHOICES, default='PC')
    
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    selling_price = models.DecimalField(max_digits=10, decimal_places=2) 
    
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Use decimals for KG items (e.g., 0.5)")
    low_stock_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)
    
    # Useful for tracking when stock was last added
    last_restocked = models.DateTimeField(auto_now=True)

    def __str__(self):
        identifier = self.barcode if self.barcode else "No Barcode"
        return f"{self.name} - {self.store.name if self.store else 'No Store'}"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

