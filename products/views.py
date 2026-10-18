from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, F
from .models import Product


def get_user_store(user):
    """Helper to safely retrieve the store associated with the logged-in user."""
    if hasattr(user, 'profile') and user.profile.store:
        return user.profile.store
    elif hasattr(user, 'store'):
        return user.store
    return None


def product_list(request):
    user_store = get_user_store(request.user)

    # 1. Handle "Quick Add" form submission
    if request.method == "POST":
        name = request.POST.get('name')
        barcode = request.POST.get('barcode')
        price = request.POST.get('selling_price')
        stock = request.POST.get('stock_quantity')
        buying_price = request.POST.get('buying_price')

        Product.objects.create(
            name=name,
            barcode=barcode,
            selling_price=price,
            buying_price=buying_price,
            stock_quantity=stock,
            store=user_store,  # Securely tie to the logged-in user's store
            is_active=True
        )
        return redirect('product_list')

    # 2. Handle Search, Filters, and List display (Restricted to user's store & active products)
    products = Product.objects.filter(is_active=True)
    if user_store:
        products = products.filter(store=user_store)
    
    products = products.order_by('-id')

    query = request.GET.get('q')
    show_low_stock = request.GET.get('low_stock')

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query)
        )
    
    if show_low_stock:
        products = products.filter(stock_quantity__lte=F('low_stock_threshold'))

    # Calculations for inventory metrics
    total_inventory_value = sum(product.stock_value for product in products)
    total_potential_profit = sum(product.potential_profit for product in products)
        
    return render(request, 'products/product_list.html', {
        'products': products, 
        'query': query,
        'low_stock_mode': show_low_stock,
        'total_inventory_value': total_inventory_value,
        'total_potential_profit': total_potential_profit,
    })


def update_product(request, pk):
    user_store = get_user_store(request.user)
    
    # Ensure the product belongs to the user's store
    if user_store:
        product = get_object_or_404(Product, pk=pk, store=user_store, is_active=True)
    else:
        product = get_object_or_404(Product, pk=pk, is_active=True)

    if request.method == "POST":
        product.name = request.POST.get('name')
        product.barcode = request.POST.get('barcode')
        product.selling_price = request.POST.get('selling_price')
        product.buying_price = request.POST.get('buying_price')
        product.stock_quantity = request.POST.get('stock_quantity')
        product.save()
        
    return redirect('product_list')


def delete_product(request, pk):
    user_store = get_user_store(request.user)
    
    # Ensure the product belongs to the user's store
    if user_store:
        product = get_object_or_404(Product, pk=pk, store=user_store, is_active=True)
    else:
        product = get_object_or_404(Product, pk=pk, is_active=True)

    if request.method == "POST":
        # --- SAFE SOFT DELETE ---
        # Hides product from inventory and POS, but preserves old receipts and profit logs
        product.is_active = False
        product.save(update_fields=['is_active'])
        
    return redirect('product_list')

