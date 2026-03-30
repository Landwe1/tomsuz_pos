from django.urls import path
from . import views

# This 'app_name' must match what you use in your redirects
app_name = 'accounts' 

urlpatterns = [
    path('login/', views.login_view, name='login'),
    # Add other paths like logout or register here later
]