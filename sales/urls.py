from django.urls import path
from . import views

app_name = 'sales'  # This is important for namespacing your URLs

urlpatterns = [
    # The POS terminal for making sales
    path('pos/', views.pos_screen, name='pos_screen'),
    
    # The Owner's Dashboard (Money + Staff)
    path('dashboard/', views.main_dashboard, name='main_dashboard'),
    
    # Detailed reports (Redirected to dashboard for now)
    path('report/', views.main_dashboard, name='sales_report'),
    
    # The tool to add new cashiers
    path('add-cashier/', views.add_cashier, name='add_cashier'),
    
    path('transactions/history/', views.sales_history, name='sales_history'),
    path('history/', views.sales_history, name='sales_history'),
    path('delete-sale/<int:sale_id>/', views.delete_sale, name='delete_sale'),
    path('manage-inventory/', views.manage_inventory, name='manage_inventory'),
    path('staff/', views.staff_management, name='staff_management'),
    path('staff/toggle/<int:user_id>/', views.toggle_staff_status, name='toggle_staff_status'),
]