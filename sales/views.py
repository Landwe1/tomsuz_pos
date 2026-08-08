import json
from decimal import Decimal
from datetime import timedelta

# Django Core Shortcuts and HTTP
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse

# Django Database and Utils
from django.db import transaction
from django.db.models import Sum, F
from django.utils import timezone

# Django Auth and Messages
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

# Model Imports (Cleaned up from cross-app layers)
from products.models import Product 
from .models import Sale, SaleItem, Profile, Store



# ===================== POS SCREEN =====================

@login_required
def pos_screen(request):
    try:
        profile = request.user.profile
        user_store = profile.store
    except Exception:
        return render(request, 'sales/no_store_error.html', {
            'role': 'CASHIER',
            'user': request.user
        })

    if not user_store:
        if profile.role == 'OWNER':
            return redirect('sales:main_dashboard')
        return render(request, 'sales/no_store_error.html', {
            'role': profile.role,
            'user': request.user
        })

    products = Product.objects.filter(store=user_store).order_by('name')

    if request.method == "POST":
        try:
            data = json.loads(request.body)

            # --- EXTRA PROTECTION: Check for empty values from JS ---
            def to_decimal(value):
                if value is None or str(value).strip() == "":
                    return Decimal('0.00')
                return Decimal(str(value))

            with transaction.atomic():
                new_sale = Sale.objects.create(
                    cashier=request.user,
                    store=user_store,
                    total_amount=to_decimal(data.get('total_amount')),
                    amount_paid=to_decimal(data.get('amount_paid')),
                    change_due=to_decimal(data.get('change_due')),
                    payment_method=data.get('payment_method', 'CASH')
                )

                for item in data.get('cart', []):
                    # select_for_update prevents simultaneous checkout collisions
                    product = Product.objects.select_for_update().get(id=item['id'], store=user_store)
                    charged_price = to_decimal(item.get('price'))
                    requested_qty = Decimal(str(item.get('quantity', 1)))

                    # Price protection
                    if charged_price < product.min_price:
                        raise ValueError(
                            f"Price for {product.name} cannot be lower than K{product.min_price}"
                        )

                    # --- FIXED: INVENTORY DEDUCTION ENGINE ---
                    if product.stock_quantity < requested_qty:
                        raise ValueError(
                            f"Insufficient stock for {product.name}. Only {product.stock_quantity} available."
                        )
                    
                    product.stock_quantity -= requested_qty
                    product.save()
                    # ----------------------------------------

                    SaleItem.objects.create(
                        sale=new_sale,
                        product=product,
                        quantity=requested_qty,
                        unit_price=charged_price
                    )

            return JsonResponse({'status': 'success', 'sale_id': new_sale.id})

        except Product.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Product not found'}, status=404)
        except ValueError as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Server Error: {str(e)}"}, status=400)

    return render(request, 'sales/pos_screen.html', {
        'products': products,
        'store': user_store
    })


# ===================== DASHBOARD =====================



@login_required
def main_dashboard(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'role': 'OWNER'}
    )

    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    user_store = profile.store

    # Store creation logic
    if not user_store:
        if request.method == "POST":
            store_name = request.POST.get('store_name')
            if store_name:
                new_store = Store.objects.create(owner=request.user, name=store_name)
                profile.store = new_store
                profile.save()
                return redirect('sales:main_dashboard')
        return render(request, 'sales/store_choice.html')

    # --- TIME ZONE LOCALIZATION CORRECTION ---
    # timezone.localdate() evaluates date bounds contextually matching 'Africa/Lusaka'
    today = timezone.localdate()
    now_local = timezone.localtime()
    
    store_sales = Sale.objects.filter(store=user_store)

    # 1. Revenue Calculations
    today_total = store_sales.filter(timestamp__date=today).aggregate(
        Sum('total_amount')
    )['total_amount__sum'] or 0

    # Evaluates matching active localized calendar months
    month_total = store_sales.filter(
        timestamp__month=now_local.month,
        timestamp__year=now_local.year
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    # 2. Profit Calculation (Optimized using prefetch_related)
    today_sales = store_sales.filter(timestamp__date=today).prefetch_related('items__product')
    today_profit = sum(sale.get_total_profit() for sale in today_sales)

    # 3. Low Stock Calculation
    low_stock_count = Product.objects.filter(
        store=user_store, 
        stock_quantity__lte=F('low_stock_threshold')
    ).count()

    # 4. Total Stock Value Calculation
    total_inventory_value = Product.objects.filter(store=user_store).aggregate(
        total=Sum(F('stock_quantity') * F('selling_price'))
    )['total'] or 0

    # 5. 7-Day Sales Trend Logic
    start_date = today - timedelta(days=6)
    daily_sales = store_sales.filter(
        timestamp__date__range=[start_date, today]
    ).values('timestamp__date').annotate(total=Sum('total_amount')).order_by('timestamp__date')

    # Map database results to the last 7 days (filling gaps with 0)
    sales_dict = {s['timestamp__date']: s['total'] for s in daily_sales}
    chart_data = [float(sales_dict.get(start_date + timedelta(days=i), 0)) for i in range(7)]
    chart_labels = [(start_date + timedelta(days=i)).strftime('%a') for i in range(7)]

    # 6. Inventory and Staff
    inventory = Product.objects.filter(store=user_store).order_by('stock_quantity')
    staff = User.objects.filter(
        profile__store=user_store
    ).exclude(id=request.user.id).select_related('profile')

    return render(request, 'sales/dashboard.html', {
        'store': user_store,
        'today_total': today_total,
        'month_total': month_total,
        'today_profit': today_profit,
        'low_stock_count': low_stock_count,
        'total_inventory_value': total_inventory_value,
        'chart_data': chart_data,
        'chart_labels': chart_labels,
        'today_date': today.strftime('%d %b %Y'), # Will show 13 Jun 2026 correctly now!
        'inventory': inventory,
        'staff_members': staff,
    })




# ===================== INVENTORY =====================

@login_required
def manage_inventory(request):
    profile = request.user.profile

    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    if request.method == 'POST':
        product = get_object_or_404(
            Product,
            id=request.POST.get('product_id'),
            store=profile.store
        )

        action = request.POST.get('action')

        if action == "restock":
            added_qty_raw = request.POST.get('added_stock') or '0'
            try:
                added_qty = Decimal(str(added_qty_raw))
                product.stock_quantity += added_qty
                messages.success(request, f"Added {added_qty} units to {product.name}")
            except Exception:
                messages.error(request, "Invalid stock quantity entered.")

        elif action == "edit":
            stock = request.POST.get('stock') or '0'
            b_price = request.POST.get('buying_price') or '0'
            s_price = request.POST.get('price') or '0'
            m_price = request.POST.get('min_price') or '0'

            try:
                new_stock = Decimal(str(stock))
                new_buying = Decimal(str(b_price))
                new_selling = Decimal(str(s_price))
                new_min = Decimal(str(m_price))

                if new_min > new_selling:
                    messages.warning(request, f"Warning: Min price for {product.name} is higher than selling price.")

                product.stock_quantity = new_stock
                product.buying_price = new_buying
                product.selling_price = new_selling
                product.min_price = new_min
                
                messages.success(request, f"Updated {product.name} details successfully.")
            except Exception as e:
                messages.error(request, f"Error updating {product.name}: Check your price formats.")

        product.save()
        return redirect('sales:manage_inventory')

    products = Product.objects.filter(store=profile.store).order_by('name')
    return render(request, 'sales/manage_inventory.html', {'products': products})


# ===================== ADD PRODUCT =====================

@login_required
def add_product(request):
    profile = request.user.profile

    if profile.role != 'OWNER':
        messages.error(request, "Unauthorized: Only owners can add products.")
        return redirect('sales:manage_inventory')

    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            b_price = request.POST.get('buying_price') or '0'
            s_price = request.POST.get('price') or '0'       
            m_price = request.POST.get('min_price') or '0'   
            stock = request.POST.get('stock') or '0'
            # Grab the custom threshold, defaulting to 5.00 if left empty
            threshold = request.POST.get('low_stock_threshold') or '5.00'

            if not name:
                messages.error(request, "Product name is required.")
                return redirect('sales:manage_inventory')

            buying_decimal = Decimal(str(b_price))
            selling_decimal = Decimal(str(s_price))
            min_decimal = Decimal(str(m_price))
            stock_decimal = Decimal(str(stock))
            threshold_decimal = Decimal(str(threshold)) # Parsed into decimal safely

            if min_decimal > selling_decimal:
                messages.warning(request, f"Note: Minimum price for {name} is set higher than the selling price.")

            Product.objects.create(
                store=profile.store,
                name=name,
                buying_price=buying_decimal,
                selling_price=selling_decimal,
                min_price=min_decimal,
                stock_quantity=stock_decimal,
                low_stock_threshold=threshold_decimal # Committed to database record
            )
            
            messages.success(request, f"Product '{name}' added successfully.")

        except Exception as e:
            messages.error(request, f"Could not add product: {str(e)}")

    return redirect('sales:manage_inventory')

# ===================== STAFF =====================

@login_required
def manage_staff(request):
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    staff = User.objects.filter(
        profile__store=profile.store
    ).exclude(id=request.user.id).select_related('profile')

    return render(request, 'sales/manage_staff.html', {'staff': staff})


@login_required
def add_cashier(request):
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
        else:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, password=password)

                    user_profile, _ = Profile.objects.get_or_create(user=user)
                    user_profile.store = profile.store
                    user_profile.role = 'CASHIER'
                    user_profile.save()

                messages.success(request, "Cashier added")
                return redirect('sales:manage_staff')

            except Exception as e:
                messages.error(request, str(e))

    return render(request, 'sales/add_cashier.html')


@login_required
def toggle_cashier_status(request, user_id):
    if request.user.profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    cashier = get_object_or_404(
        User, 
        id=user_id, 
        profile__store=request.user.profile.store
    )

    if cashier == request.user:
        messages.error(request, "Cannot disable your own account")
    else:
        cashier.is_active = not cashier.is_active
        cashier.save()
        
        status = "active" if cashier.is_active else "deactivated"
        messages.success(request, f"User {cashier.username} is now {status}.")

    return redirect('sales:manage_staff')


# ===================== SALES =====================

@login_required
def sales_history(request):
    profile = request.user.profile
    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    sales = Sale.objects.filter(store=profile.store).order_by('-timestamp')
    return render(request, 'sales/sales_history.html', {'sales': sales})


@login_required
def delete_sale(request, sale_id):
    profile = request.user.profile

    if profile.role != 'OWNER':
        return redirect('sales:pos_screen')

    sale = get_object_or_404(Sale, id=sale_id, store=profile.store)

    try:
        with transaction.atomic():
            for item in sale.items.all():
                product = item.product
                product.stock_quantity += item.quantity
                product.save()

            sale.delete()
            messages.success(request, "Sale deleted and stock restored")

    except Exception as e:
        messages.error(request, str(e))

    return redirect('sales:sales_history')

