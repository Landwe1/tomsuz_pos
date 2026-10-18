from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.utils import timezone
from django.db.models import Sum

from .models import Store, Profile, Product, Sale, SaleItem


# --- MULTI-TENANCY CORE MODULE REGISTRATIONS ---

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'address', 'created_at')
    search_fields = ('name', 'address', 'owner__username')
    list_select_related = ('owner',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'store', 'role')
    list_filter = ('store', 'role')
    search_fields = ('user__username', 'store__name')
    list_select_related = ('user', 'store')


# --- SAFE APP REGISTRATION OVERRIDE CONTROLLER ---

try:
    admin.site.unregister(Product)
except NotRegistered:
    pass


# --- PRODUCT & INVENTORY MANAGEMENT ---

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'store', 'stock_quantity', 'buying_price', 
        'selling_price', 'min_price', 'low_stock_threshold', 'is_low_stock'
    )
    list_filter = ('store', 'created_at')
    search_fields = ('name', 'store__name')
    readonly_fields = ('created_at', 'updated_at')
    list_select_related = ('store',)

    fieldsets = (
        ('Identity & Tenancy', {
            'fields': ('store', 'name')
        }),
        ('Inventory Levels', {
            'fields': ('stock_quantity', 'low_stock_threshold')
        }),
        ('Pricing Matrices (ZMW)', {
            'fields': ('buying_price', 'selling_price', 'min_price')
        }),
        ('System Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at')
        }),
    )

    def get_queryset(self, request):
        """Isolates product lists based on staff multi-tenancy associations."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            return qs.filter(store=request.user.profile.store)
        except AttributeError:
            return qs.none()

    def save_model(self, request, obj, form, change):
        """Automatically sets store multi-tenancy context for store managers adding stock."""
        if not request.user.is_superuser and not obj.store_id:
            try:
                obj.store = request.user.profile.store
            except AttributeError:
                pass
        super().save_model(request, obj, form, change)


# --- TRANSACTIONAL INLINES & SALES SYSTEM ---

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ('subtotal',)
    fields = ('product', 'quantity', 'unit_price', 'subtotal')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Filters product dropdown options to the tenant's own store stock."""
        if db_field.name == "product" and not request.user.is_superuser:
            try:
                kwargs["queryset"] = Product.objects.filter(store=request.user.profile.store)
            except AttributeError:
                kwargs["queryset"] = Product.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'timestamp', 'store', 'cashier', 
        'total_amount', 'payment_method', 'is_synced'
    )
    list_filter = ('timestamp', 'store', 'payment_method', 'is_synced', 'cashier')
    search_fields = ('id', 'cashier__username', 'store__name')
    inlines = [SaleItemInline]
    readonly_fields = ('timestamp', 'total_amount', 'change_due', 'offline_id')
    list_select_related = ('store', 'cashier')

    fieldsets = (
        ('Sale Info', {
            'fields': ('store', 'cashier', 'payment_method', 'is_synced', 'offline_id')
        }),
        ('Financials', {
            'fields': ('total_amount', 'amount_paid', 'change_due', 'timestamp')
        }),
    )

    def get_queryset(self, request):
        """Prevents shop managers from viewing ledger transaction balances from competing properties."""
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        try:
            return qs.filter(store=request.user.profile.store)
        except AttributeError:
            return qs.none()

    def changelist_view(self, request, extra_context=None):
        """Computes dynamic rolling daily financial aggregates inside the active view dashboard."""
        today = timezone.localdate()
        base_query = Sale.objects.filter(timestamp__date=today)

        if not request.user.is_superuser:
            try:
                base_query = base_query.filter(store=request.user.profile.store)
            except AttributeError:
                base_query = base_query.none()

        today_total = base_query.aggregate(Sum('total_amount'))['total_amount__sum'] or 0

        extra_context = extra_context or {}
        extra_context['today_total'] = today_total

        return super().changelist_view(request, extra_context=extra_context)

