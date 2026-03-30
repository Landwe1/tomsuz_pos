from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('sales:main_dashboard') # Sends them to the POS after login
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})