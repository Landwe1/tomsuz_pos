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
    
    # 1. Safely get the profile and store
    try:
        profile = request.user.profile
        user_store = profile.store
    except Exception:
        # Fallback if profile is missing entirely
        return render(request, 'sales/no_store_error.html', {
            'role': 'CASHIER', 
            'user': request.user
        })

    # 2. Redirect Owners or show the Setup Required page for Cashiers
    if not user_store:
        if profile.role == 'OWNER':
            return redirect('sales:main_dashboard')
        
        # This matches your dark-themed setup HTML variables
        return render(request, 'sales/no_store_error.html', {
            'role': profile.role,
            'user': request.user  # So {{ user.username }} works
        })

    # 3. GET Method: Show the POS Terminal
    products = Product.objects.filter(store=user_store).order_by('name')

    # 4. POST Method: Process the Sale
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            
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
                    
                    # Create Sale Item (Model logic handles stock deduction)
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

    return render(request, 'sales/pos_screen.html', {
        'products': products,
        'store': user_store
    })
@login_required
def main_dashboard(request):
    """The main Owner's Dashboard with financial data, inventory, and staff."""
    
    # 1. Safely get or create the profile to prevent Error 500
    profile, created = Profile.objects.get_or_create(
        user=request.user, 
        defaults={'role': 'OWNER'}
    )

    # 2. Check role
    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    user_store = profile.store

    # 3. Handle Store Creation
    if not user_store:
        if request.method == "POST":
            action = request.POST.get('action')
            if action == "create":
                store_name = request.POST.get('store_name')
                if store_name:
                    new_store = Store.objects.create(owner=request.user, name=store_name)
                    profile.store = new_store
                    profile.save()
                    return redirect('main_dashboard')
        
        return render(request, 'sales/store_choice.html')

    # --- NEW: Fetch Staff for the Dashboard table ---
    # This finds all users linked to this store and excludes the owner
    staff = User.objects.filter(
        profile__store=user_store
    ).exclude(
        id=request.user.id
    ).select_related('profile')

    # 4. Data Calculations
    now = timezone.now()
    today = now.date()
    store_sales = Sale.objects.filter(store=user_store)

    today_total = store_sales.filter(timestamp__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    month_total = store_sales.filter(timestamp__month=now.month, timestamp__year=now.year).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    inventory = Product.objects.filter(store=user_store).order_by('stock_quantity')

    # 5. Add 'staff' to the context so the template can see it
    context = {
        'store': user_store,
        'today_total': today_total,
        'month_total': month_total,
        'inventory': inventory,
        'staff_members': staff,  # This is the missing piece!
    }
    return render(request, 'sales/dashboard.html', context)

@login_required
def manage_inventory(request):
    profile = request.user.profile
    if not profile.is_owner:
        return redirect('sales:pos_screen')

    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        product = get_object_or_404(Product, id=product_id, store=profile.store)
        
        action = request.POST.get('action') # We'll send this from the button
        
        if action == "restock":
            added_qty = Decimal(request.POST.get('added_stock', 0))
            product.stock_quantity += added_qty
            messages.success(request, f"Added {added_qty} units to {product.name}.")
        
        elif action == "edit":
            product.stock_quantity = Decimal(request.POST.get('stock'))
            product.selling_price = Decimal(request.POST.get('price'))
            messages.success(request, f"Updated {product.name} details.")

        product.save()
        return redirect('sales:manage_inventory')

    products = Product.objects.filter(store=profile.store).order_by('name')
    return render(request, 'sales/manage_inventory.html', {'products': products})


@login_required
def manage_staff(request):
    """Lists all staff members belonging to the owner's store."""
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('pos_screen')
    
    # Get all users who have a profile linked to this specific store
    staff = User.objects.filter(
        profile__store=profile.store
    ).exclude(
        id=request.user.id
    ).select_related('profile')
    
    return render(request, 'sales/manage_staff.html', {'staff': staff})


@login_required
def add_cashier(request):
    """Tool for owners to register new cashier accounts linked to their store."""
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('pos_screen')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')

        if User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' is already taken.")
        else:
            try:
                with transaction.atomic():
                    # 1. Create the User
                    new_user = User.objects.create_user(
                        username=username, 
                        password=password,
                        first_name=first_name,
                        last_name=last_name
                    )
                    
                    # 2. Update or Create the Profile linked to the Owner's store
                    # get_or_create handles cases where signals might have already made a blank profile
                    user_profile, created = Profile.objects.get_or_create(user=new_user)
                    user_profile.store = profile.store
                    user_profile.role = 'CASHIER'
                    user_profile.save()

                messages.success(request, f"Cashier '{username}' added successfully!")
                return redirect('manage_staff')
            except Exception as e:
                messages.error(request, f"Error adding cashier: {str(e)}")

    return render(request, 'sales/add_cashier.html')


@login_required
def toggle_cashier_status(request, user_id):
    """Activates or Suspends a cashier's ability to log in."""
    if request.user.profile.role != 'OWNER':
        return redirect('pos_screen')

    # Ensure the owner can only toggle users in THEIR store
    cashier = get_object_or_404(User, id=user_id, profile__store=request.user.profile.store)
    
    if cashier == request.user:
        messages.error(request, "You cannot suspend your own account!")
    else:
        cashier.is_active = not cashier.is_active
        cashier.save()
        status = "Activated" if cashier.is_active else "Suspended"
        messages.success(request, f"Account for {cashier.username} has been {status}.")

    return redirect('manage_staff')

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

@login_required
def add_product(request):
    profile = request.user.profile
    
    # Check if the user is an OWNER using your profile logic
    if profile.role != 'OWNER':
        messages.error(request, "Unauthorized: Only owners can add products.")
        return redirect('sales:manage_inventory')

    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            price = request.POST.get('price')
            stock = request.POST.get('stock')

            # Basic validation to prevent Decimal errors
            if not name or not price or not stock:
                messages.error(request, "All fields are required.")
                return redirect('sales:manage_inventory')

            # Create the product and link it to the owner's store
            Product.objects.create(
                store=profile.store,
                name=name,
                selling_price=Decimal(str(price)),
                stock_quantity=Decimal(str(stock))
            )
            messages.success(request, f"Product '{name}' added successfully!")
            
        except Exception as e:
            # This captures the error and displays it on the page instead of a 500 error
            messages.error(request, f"System Error: {str(e)}")
            return redirect('sales:manage_inventory')

    return redirect('sales:manage_inventory')



