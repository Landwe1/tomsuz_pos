from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from datetime import timedelta
from products.models import Product
from .models import Sale, SaleItem, Profile, Store # Added Store model here
import json

@login_required
def pos_screen(request):
    """Handles the mobile-first cashier interface and sale processing."""
    try:
        profile = request.user.profile
        user_store = profile.store
    except Exception:
        return render(request, 'sales/no_store_error.html', {'role': 'UNKNOWN'})

    # If no store is linked, send them to the dashboard to create or link one
    if not user_store:
        if profile.is_owner:
            return redirect('main_dashboard')
        return render(request, 'sales/no_store_error.html', {
            'role': profile.role,
            'username': request.user.username
        })

    products = Product.objects.filter(store=user_store).order_by('name')

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            new_sale = Sale.objects.create(
                cashier=request.user,
                store=user_store, 
                total_amount=data['total_amount'],
                amount_paid=data['amount_paid'],
                change_due=data['change_due'],
                payment_method=data['payment_method']
            )

            for item in data['cart']:
                product = Product.objects.get(id=item['id'], store=user_store)
                SaleItem.objects.create(
                    sale=new_sale,
                    product=product,
                    quantity=item['quantity'],
                    unit_price=item['price']
                )
                
            return JsonResponse({'status': 'success', 'sale_id': new_sale.id})
        except Product.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Product not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return render(request, 'sales/pos_screen.html', {'products': products})

@login_required
def main_dashboard(request):
    """
    The main Owner's Dashboard.
    Handles Store setup (Create or Link) if none exists.
    """
    profile = request.user.profile
    
    if not profile.is_owner:
        return redirect('pos_screen')

    user_store = profile.store

    # --- Choice Logic: Create or Link Store ---
    if not user_store:
        if request.method == "POST":
            action = request.POST.get('action')
            
            if action == "create":
                store_name = request.POST.get('store_name')
                # Create and link new store
                new_store = Store.objects.create(owner=request.user, name=store_name)
                profile.store = new_store
                profile.save()
                return redirect('main_dashboard')
            
            elif action == "link":
                store_id = request.POST.get('store_id')
                try:
                    target_store = Store.objects.get(id=store_id)
                    profile.store = target_store
                    profile.save()
                    return redirect('main_dashboard')
                except (Store.DoesNotExist, ValueError):
                    return render(request, 'sales/store_choice.html', {'error': 'Invalid Store ID.'})

        return render(request, 'sales/store_choice.html')

    # --- Financial Aggregation (Only runs if store exists) ---
    now = timezone.now()
    today = now.date()
    store_sales = Sale.objects.filter(store=user_store)

    today_total = store_sales.filter(timestamp__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    week_total = store_sales.filter(timestamp__gte=now - timedelta(days=7)).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    month_total = store_sales.filter(timestamp__month=now.month, timestamp__year=now.year).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    
    yearly_breakdown = []
    for i in range(5):
        target_year = now.year - i
        total = store_sales.filter(timestamp__year=target_year).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        yearly_breakdown.append({'year': target_year, 'total': float(total)})

    staff_members = Profile.objects.filter(store=user_store)

    context = {
        'store': user_store,
        'today_total': today_total,
        'week_total': week_total,
        'month_total': month_total,
        'yearly_breakdown': yearly_breakdown,
        'staff_members': staff_members,
    }
    
    return render(request, 'sales/dashboard.html', context)

@login_required
def add_cashier(request):
    """View to handle the creation of new cashier accounts by the owner."""
    owner_profile = request.user.profile
    
    if not owner_profile.is_owner:
        return redirect('sales:pos_screen')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        try:
            new_user = User.objects.create_user(username=username, password=password)
            new_user.profile.store = owner_profile.store
            new_user.profile.role = 'CASHIER'
            new_user.profile.save()
            return redirect('main_dashboard')
        except Exception as e:
            return render(request, 'sales/add_cashier.html', {'error': 'Username already exists or invalid data.'})

    return render(request, 'sales/add_cashier.html')

@login_required
def sales_report(request):
    return main_dashboard(request)

@login_required
def sales_history(request):
    profile = request.user.profile
    if not profile.is_owner:
        return redirect('pos_screen')

    user_store = profile.store
    
    # Get dates from the search form, or default to today
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    sales = Sale.objects.filter(store=user_store)

    if start_date and end_date:
        # Filter between the two dates chosen by the owner
        sales = sales.filter(timestamp__date__range=[start_date, end_date])
    else:
        # Default: Show only today's sales if no date is picked
        sales = sales.filter(timestamp__date=timezone.now().date())

    sales = sales.order_by('-timestamp')

    return render(request, 'sales/sales_history.html', {
        'sales': sales,
        'start_date': start_date,
        'end_date': end_date,
        'store': user_store
    })

