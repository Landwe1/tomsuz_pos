from django.contrib import admin
from django.utils import timezone
from django.db.models import Sum
from .models import Store, Profile, Sale, SaleItem # Added Store and Profile

# --- NEW REGISTRATIONS FOR MULTI-TENANCY ---

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    # Changed 'location' to 'address' to match yours models.py
    list_display = ('name', 'owner', 'address', 'created_at') 
    search_fields = ('name', 'address', 'owner__username')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'role')
    list_filter = ('store', 'role')

# --- YOUR EXISTING SALES LOGIC (UPDATED) ---

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ('subtotal',)
    fields = ('product', 'quantity', 'unit_price', 'subtotal')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    # Added 'store' to the list display and filter
    list_display = ('id', 'timestamp', 'store', 'cashier', 'total_amount', 'payment_method', 'is_synced')
    list_filter = ('timestamp', 'store', 'payment_method', 'is_synced', 'cashier')
    search_fields = ('id', 'cashier__username', 'store__name')
    inlines = [SaleItemInline]
    
    readonly_fields = ('timestamp', 'total_amount', 'change_due', 'offline_id')

    fieldsets = (
        ('Sale Info', {
            'fields': ('store', 'cashier', 'payment_method', 'is_synced') # Added store here
        }),
        ('Financials', {
            'fields': ('total_amount', 'amount_paid', 'change_due', 'timestamp')
        }),
    )

    def changelist_view(self, request, extra_context=None):
        today = timezone.now().date()
        today_total = Sale.objects.filter(
            timestamp__date=today
        ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

        extra_context = extra_context or {}
        extra_context['today_total'] = today_total
        
        return super().changelist_view(request, extra_context=extra_context)