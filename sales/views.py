import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages

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
                    product = Product.objects.get(id=item['id'], store=user_store)
                    charged_price = to_decimal(item.get('price'))

                    # Price protection
                    if charged_price < product.min_price:
                        raise ValueError(
                            f"Price for {product.name} cannot be lower than K{product.min_price}"
                        )

                    SaleItem.objects.create(
                        sale=new_sale,
                        product=product,
                        quantity=item['quantity'],
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

    # Store creation
    if not user_store:
        if request.method == "POST":
            store_name = request.POST.get('store_name')
            if store_name:
                new_store = Store.objects.create(owner=request.user, name=store_name)
                profile.store = new_store
                profile.save()
                return redirect('sales:main_dashboard')
        return render(request, 'sales/store_choice.html')

    now = timezone.now()
    today = now.date()

    store_sales = Sale.objects.filter(store=user_store)

    # Revenue
    today_total = store_sales.filter(timestamp__date=today).aggregate(
        Sum('total_amount')
    )['total_amount__sum'] or 0

    month_total = store_sales.filter(
        timestamp__month=now.month,
        timestamp__year=now.year
    ).aggregate(Sum('total_amount'))['total_amount__sum'] or 0

    # ✅ Profit (NEW)
    today_sales = store_sales.filter(timestamp__date=today)
    today_profit = sum(sale.get_total_profit() for sale in today_sales)

    inventory = Product.objects.filter(store=user_store).order_by('stock_quantity')

    staff = User.objects.filter(
        profile__store=user_store
    ).exclude(id=request.user.id).select_related('profile')

    return render(request, 'sales/dashboard.html', {
        'store': user_store,
        'today_total': today_total,
        'month_total': month_total,
        'today_profit': today_profit,
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
            # Fallback to '0' if the field is empty
            added_qty_raw = request.POST.get('added_stock') or '0'
            added_qty = Decimal(str(added_qty_raw))
            product.stock_quantity += added_qty
            messages.success(request, f"Added {added_qty} units to {product.name}")

        elif action == "edit":
            # Safely grab values or default to current value/zero
            stock = request.POST.get('stock') or '0'
            b_price = request.POST.get('buying_price') or '0'
            s_price = request.POST.get('price') or '0'
            m_price = request.POST.get('min_price') or '0'

            product.stock_quantity = Decimal(str(stock))
            product.buying_price = Decimal(str(b_price))
            product.selling_price = Decimal(str(s_price))
            product.min_price = Decimal(str(m_price))
            
            messages.success(request, f"Updated {product.name}")

        product.save()
        return redirect('sales:manage_inventory')

    # This is the list that shows up on your page
    products = Product.objects.filter(store=profile.store).order_by('name')
    return render(request, 'sales/manage_inventory.html', {'products': products})

# ===================== ADD PRODUCT =====================
@login_required
def add_product(request):
    profile = request.user.profile

    if profile.role != 'OWNER':
        messages.error(request, "Unauthorized")
        return redirect('sales:manage_inventory')

    if request.method == 'POST':
        try:
            # We use 'or 0' so if the user leaves a box empty, the system doesn't crash
            name = request.POST.get('name')
            b_price = request.POST.get('buying_price') or '0'
            s_price = request.POST.get('price') or '0'
            m_price = request.POST.get('min_price') or '0'
            stock = request.POST.get('stock') or '0'

            # Validating that name exists at least
            if not name:
                messages.error(request, "Product name is required")
                return redirect('sales:manage_inventory')

            Product.objects.create(
                store=profile.store,
                name=name,
                buying_price=Decimal(str(b_price)),
                selling_price=Decimal(str(s_price)),
                min_price=Decimal(str(m_price)),
                stock_quantity=Decimal(str(stock))
            )
            messages.success(request, f"Product '{name}' added successfully")
        except Exception as e:
            # This will now catch any other weird errors and show them as a message
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

    # Ensure we only fetch users belonging to THIS owner's store
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
        
        # ADD THIS: Let the owner know what happened
        status = "active" if cashier.is_active else "deactivated"
        messages.success(request, f"User {cashier.username} is now {status}.")

    # Make sure this name matches your urls.py exactly
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
