from django.urls import path

from .views import (
    MerchantCreditScoreView,
    RecalculateCreditScoreView,
    credit_dashboard_view,
    lender_dashboard_view,
    lender_merchant_detail_view,
)

app_name = 'credit_scoring'

urlpatterns = [
    # ============================================================================
    # MERCHANT HTML TEMPLATE ROUTES
    # ============================================================================
    path('dashboard/', credit_dashboard_view, name='dashboard'),
    path('dashboard/', credit_dashboard_view, name='merchant_dashboard'),

    # ============================================================================
    # LENDER HTML TEMPLATE ROUTES & ALIASES
    # ============================================================================
    # Primary Lender Portal Routes
    path('lender/portal/', lender_dashboard_view, name='lender_dashboard'),
    path('lender/portal/', lender_dashboard_view, name='lender-dashboard'),

    # URL Aliases to catch direct navigation or legacy links
    path('lenders/', lender_dashboard_view, name='lenders-shortcut'),
    path('lender/', lender_dashboard_view, name='lender-shortcut'),
    path('lenders/portal/', lender_dashboard_view, name='lenders-portal-shortcut'),

    # Lender Merchant Audit Detail View
    path('lender/merchant/<int:store_id>/', lender_merchant_detail_view, name='lender_merchant_detail'),
    path('lender/merchant/<int:store_id>/', lender_merchant_detail_view, name='lender-merchant-detail'),

    # ============================================================================
    # REST API ROUTES
    # ============================================================================
    path('api/my-score/', MerchantCreditScoreView.as_view(), name='api-my-score'),
    path('api/recalculate/', RecalculateCreditScoreView.as_view(), name='api-recalculate-score'),
]
