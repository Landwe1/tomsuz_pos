from django.shortcuts import render, redirect, get_object_or_404 # Added get_object_or_404
from django.db.models import Q
from .models import Product

def product_list(request):
    # 1. Handle "Quick Add" form submission
    if request.method == "POST":
        name = request.POST.get('name')
        barcode = request.POST.get('barcode')
        price = request.POST.get('selling_price')
        stock = request.POST.get('stock_quantity')
        
        Product.objects.create(
            name=name,
            barcode=barcode,
            selling_price=price,
            stock_quantity=stock
        )
        return redirect('product_list')

    # 2. Handle Search, Filters, and List display
    query = request.GET.get('q')
    show_low_stock = request.GET.get('low_stock') # For the filter button
    
    products = Product.objects.all().order_by('-id')

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query)
        )
    
    if show_low_stock:
        # Filters for items where stock is 5 or less
        products = products.filter(stock_quantity__lte=5)
        
    return render(request, 'products/product_list.html', {
        'products': products, 
        'query': query,
        'low_stock_mode': show_low_stock
    })

def update_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.name = request.POST.get('name')
        product.barcode = request.POST.get('barcode')
        product.selling_price = request.POST.get('selling_price')
        product.stock_quantity = request.POST.get('stock_quantity')
        product.save()
    return redirect('product_list')

def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
    return redirect('product_list')

