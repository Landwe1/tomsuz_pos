from django.shortcuts import render

def landing_page(request):
    # This renders the "Welcome to TomSuz" screen
    return render(request, 'landing.html')