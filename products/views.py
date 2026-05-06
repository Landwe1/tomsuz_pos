from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, F, Sum
from .models import Product

def product_list(request):
    # 1. Handle "Quick Add" form submission
    if request.method == "POST":
        name = request.POST.get('name')
        barcode = request.POST.get('barcode')
        price = request.POST.get('selling_price')
        stock = request.POST.get('stock_quantity')
        buying_price = request.POST.get('buying_price') # Added to capture your cost

        Product.objects.create(
            name=name,
            barcode=barcode,
            selling_price=price,
            buying_price=buying_price,
            stock_quantity=stock,
            # Ensure it links to the user's store if applicable
            store=request.user.store if hasattr(request.user, 'store') else None 
        )
        return redirect('product_list')

    # 2. Handle Search, Filters, and List display
    query = request.GET.get('q')
    show_low_stock = request.GET.get('low_stock')
    
    # Filter by store if your system is multi-tenant
    products = Product.objects.all().order_by('-id')

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query)
        )
    
    if show_low_stock:
        # Uses the logic: stock <= low_stock_threshold (usually 5)
        products = products.filter(stock_quantity__lte=F('low_stock_threshold'))

    # --- NEW: Calculation for Total Inventory Value ---
    # We sum up (stock_quantity * selling_price) for all filtered products
    total_inventory_value = sum(product.stock_value for product in products)
    
    # Optional: Calculate total potential profit sitting in stock
    total_potential_profit = sum(product.potential_profit for product in products)
        
    return render(request, 'products/product_list.html', {
        'products': products, 
        'query': query,
        'low_stock_mode': show_low_stock,
        'total_inventory_value': total_inventory_value,
        'total_potential_profit': total_potential_profit,
    })

def update_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.name = request.POST.get('name')
        product.barcode = request.POST.get('barcode')
        product.selling_price = request.POST.get('selling_price')
        product.buying_price = request.POST.get('buying_price') # Added
        product.stock_quantity = request.POST.get('stock_quantity')
        product.save()
    return redirect('product_list')

def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
    return redirect('product_list')
