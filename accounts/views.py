from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
from .models import UserProfile
from sales.models import Store  # Adjust import according to your app structure


def login_view(request):
    """Handles user login and redirects based on UserProfile role."""
    if request.user.is_authenticated:
        return redirect('sales:main_dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Get or create profile
            profile, _ = UserProfile.objects.get_or_create(user=user)
            
            # Route directly based on user role
            if profile.role == UserProfile.Role.SHOP_OWNER:
                return redirect('sales:main_dashboard')
            
            elif profile.role == UserProfile.Role.CASHIER:
                return redirect('sales:pos_screen')
            
            elif profile.role == UserProfile.Role.LENDER:
                return redirect('credit_scoring:lender_dashboard')
            
            elif profile.role == UserProfile.Role.ADMIN:
                return redirect('admin:index')
            
            return redirect('sales:main_dashboard')
    else:
        form = AuthenticationForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def register_view(request):
    """Handles new merchant/user registration and assigns default roles and stores."""
    if request.user.is_authenticated:
        return redirect('sales:main_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        store_name = request.POST.get('store_name')
        role = request.POST.get('role', UserProfile.Role.SHOP_OWNER)  # Default to shop owner

        # Basic validation
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'accounts/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken. Please choose another.")
            return render(request, 'accounts/register.html')

        try:
            # 1. Create the base User
            user = User.objects.create_user(username=username, email=email, password=password)
            
            # 2. Update or create their UserProfile and assign role
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save()

            # 3. If shop owner, create their store
            if role == UserProfile.Role.SHOP_OWNER and store_name:
                Store.objects.create(name=store_name, owner=user)

            messages.success(request, "Account created successfully! You can now log in.")
            return redirect('accounts:login')

        except Exception as e:
            messages.error(request, f"An error occurred during registration: {e}")
            return render(request, 'accounts/register.html')

    return render(request, 'accounts/register.html')
