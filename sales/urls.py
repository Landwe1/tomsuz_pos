from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # The POS terminal for making sales
    path('pos/', views.pos_screen, name='pos_screen'),
    
    # The Owner's Dashboard
    path('dashboard/', views.main_dashboard, name='main_dashboard'),
    
    # Detailed reports
    path('report/', views.main_dashboard, name='sales_report'),
    
    # The tool to add new cashiers
    path('add-cashier/', views.add_cashier, name='add_cashier'),
    
    # History and Deletion
    path('history/', views.sales_history, name='sales_history'),
    path('delete-sale/<int:sale_id>/', views.delete_sale, name='delete_sale'),
    
    # Inventory Management
    path('manage-inventory/', views.manage_inventory, name='manage_inventory'),
    
    # Staff Management (Fixed these names to match your views.py)
    path('staff/', views.manage_staff, name='manage_staff'),
    path('staff/toggle/<int:user_id>/', views.toggle_cashier_status, name='toggle_cashier_status'),
]