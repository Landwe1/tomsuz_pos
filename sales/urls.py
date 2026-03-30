from django.urls import path
from . import views

app_name = 'sales'  # This is important for namespacing your URLs

urlpatterns = [
    # The POS terminal for making sales
    path('pos/', views.pos_screen, name='pos_screen'),
    
    # The Owner's Dashboard (Money + Staff)
    path('dashboard/', views.main_dashboard, name='main_dashboard'),
    
    # Detailed reports (Redirected to dashboard for now)
    path('report/', views.sales_report, name='sales_report'),
    
    # The tool to add new cashiers
    path('add-cashier/', views.add_cashier, name='add_cashier'),
    
    path('transactions/history/', views.sales_history, name='sales_history'),
    path('history/', views.sales_history, name='sales_history'),
]