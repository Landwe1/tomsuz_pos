import json
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages

# Models
from products.models import Product
from .models import Sale, SaleItem, Profile, Store

@login_required
def pos_screen(request):
    """Handles the mobile-first cashier interface and sale processing."""
    try:
        profile = request.user.profile
        user_store = profile.store
    except Exception:
        return render(request, 'sales/no_store_error.html', {'role': 'UNKNOWN'})

    if not user_store:
        if profile.role == 'OWNER':
            return redirect('main_dashboard')
        return render(request, 'sales/no_store_error.html', {
            'role': profile.role,
            'username': request.user.username
        })

    products = Product.objects.filter(store=user_store).order_by('name')

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            
            # Use a transaction to ensure both Sale and SaleItems are saved correctly
            with transaction.atomic():
                # Create the Sale record
                new_sale = Sale.objects.create(
                    cashier=request.user,
                    store=user_store, 
                    total_amount=Decimal(str(data['total_amount'])),
                    amount_paid=Decimal(str(data['amount_paid'])),
                    change_due=Decimal(str(data['change_due'])),
                    payment_method=data['payment_method']
                )

                for item in data['cart']:
                    product = Product.objects.get(id=item['id'], store=user_store)
                    
                    # Create the Sale Item (Model logic handles stock deduction)
                    SaleItem.objects.create(
                        sale=new_sale,
                        product=product,
                        quantity=item['quantity'],
                        unit_price=Decimal(str(item['price']))
                    )
                
            return JsonResponse({'status': 'success', 'sale_id': new_sale.id})
        except Product.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Product not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return render(request, 'sales/pos_screen.html', {'products': products})

@login_required
def main_dashboard(request):
    """The main Owner's Dashboard with financial data and inventory."""
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('pos_screen')

    user_store = profile.store

    if not user_store:
        if request.method == "POST":
            action = request.POST.get('action')
            if action == "create":
                store_name = request.POST.get('store_name')
                new_store = Store.objects.create(owner=request.user, name=store_name)
                profile.store = new_store
                profile.save()
                return redirect('main_dashboard')
        return render(request, 'sales/store_choice.html')

    now = timezone.now()
    today = now.date()
    store_sales = Sale.objects.filter(store=user_store)

    today_total = store_sales.filter(timestamp__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    month_total = store_sales.filter(timestamp__month=now.month, timestamp__year=now.year).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    inventory = Product.objects.filter(store=user_store).order_by('stock_quantity')

    context = {
        'store': user_store,
        'today_total': today_total,
        'month_total': month_total,
        'inventory': inventory,
    }
    return render(request, 'sales/dashboard.html', context)

@login_required
def manage_inventory(request):
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        new_stock = request.POST.get('stock')
        new_price = request.POST.get('price')
        
        product = Product.objects.get(id=product_id, store=profile.store)
        product.stock_quantity = Decimal(str(new_stock))
        product.selling_price = Decimal(str(new_price))
        product.save()
        
        messages.success(request, f"Updated {product.name} successfully!")
        return redirect('sales:manage_inventory')

    products = Product.objects.filter(store=profile.store).order_by('name')
    return render(request, 'sales/manage_inventory.html', {'products': products})

@login_required
def manage_staff(request):
    if request.user.profile.role != 'OWNER':
        return redirect('sales:pos_screen')
    
    staff = User.objects.filter(profile__store=request.user.profile.store).exclude(id=request.user.id)
    return render(request, 'sales/manage_staff.html', {'staff': staff})

@login_required
def add_cashier(request):
    """Tool for owners to register new cashier accounts."""
    if request.user.profile.role != 'OWNER':
        return redirect('sales:pos_screen')
    
    # Logic for creating new cashier goes here
    return render(request, 'sales/add_cashier.html')

@login_required
def toggle_cashier_status(request, user_id):
    if request.user.profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    cashier = get_object_or_404(User, id=user_id, profile__store=request.user.profile.store)
    
    if cashier == request.user:
        messages.error(request, "You cannot suspend your own account!")
    else:
        cashier.is_active = not cashier.is_active
        cashier.save()
        status = "Activated" if cashier.is_active else "Suspended"
        messages.success(request, f"Account for {cashier.username} has been {status}.")

    return redirect('sales:manage_staff')

@login_required
def sales_history(request):
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('pos_screen')

    user_store = profile.store
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    sales = Sale.objects.filter(store=user_store)

    if start_date and end_date:
        sales = sales.filter(timestamp__date__range=[start_date, end_date])
    else:
        sales = sales.filter(timestamp__date=timezone.now().date())

    sales = sales.order_by('-timestamp')

    return render(request, 'sales/sales_history.html', {
        'sales': sales,
        'start_date': start_date,
        'end_date': end_date,
        'store': user_store
    })

@login_required
def delete_sale(request, sale_id):
    """Deletes a sale and returns all items to the inventory stock."""
    profile = request.user.profile
    if not profile.is_owner:
        messages.error(request, "Access denied. Only owners can delete sales.")
        return redirect('sales:pos_screen')

    sale = get_object_or_404(Sale, id=sale_id, store=profile.store)

    try:
        with transaction.atomic():
            # Return items to stock before deleting the sale record
            for item in sale.items.all():
                product = item.product
                product.stock_quantity += item.quantity
                product.save()

            sale.delete()
            messages.success(request, f"Sale #{sale_id} deleted and inventory restored.")
    except Exception as e:
        messages.error(request, f"Error deleting sale: {str(e)}")

    return redirect('sales:sales_history')


