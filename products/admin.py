from django.contrib import admin

# Register your models here.
from .models import Category, Product

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # What the owner sees in the list view
    list_display = ('name', 'barcode', 'category', 'selling_price', 'stock_quantity', 'unit_type')
    
    # Clickable filters on the right side
    list_filter = ('category', 'unit_type')
    
    # Search by name or barcode
    search_fields = ('name', 'barcode')
    
    # Allow editing price and stock directly in the list (Fast updates!)
    list_editable = ('selling_price', 'stock_quantity')

    # Color-coding or logic can be added here later for "Low Stock" alerts