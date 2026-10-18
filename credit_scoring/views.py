import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404, redirect, render

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserProfile
from sales.models import Store
from .models import CreditAssessmentLog, MerchantCreditProfile
from .serializers import MerchantCreditProfileSerializer
from .services import calculate_store_credit_score


def is_lender_or_admin(user):
    """Helper function to verify if user has lender or staff/admin privileges safely."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True

    # Safely check UserProfile role without crashing
    try:
        if hasattr(user, 'account_profile') and user.account_profile:
            role = getattr(user.account_profile, 'role', None)
            lender_role = getattr(UserProfile.Role, 'LENDER', 'LENDER')
            admin_role = getattr(UserProfile.Role, 'ADMIN', 'ADMIN')
            return role in [lender_role, admin_role]
    except Exception:
        return False
    return False


def is_shop_owner(user):
    """Helper function to verify if user is a shop owner or staff."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    try:
        if hasattr(user, 'account_profile') and user.account_profile:
            owner_role = getattr(UserProfile.Role, 'SHOP_OWNER', 'SHOP_OWNER')
            return getattr(user.account_profile, 'role', None) == owner_role
    except Exception:
        return False
    return True


# ============================================================================
# API ENDPOINTS (For REST Clients / Frontend Frameworks)
# ============================================================================


class MerchantCreditScoreView(APIView):
    """API endpoint for shop owners to view their credit score and loan eligibility metrics."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        if not is_shop_owner(user):
            return Response(
                {"error": "Access restricted. Only store owners can view credit profile metrics."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get store associated with owner
        store = getattr(user, 'owned_store', None) or Store.objects.filter(owner=user).first()
        if not store:
            return Response(
                {"error": "No store associated with this owner account."},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            credit_profile = store.credit_profile
        except MerchantCreditProfile.DoesNotExist:
            credit_profile = calculate_store_credit_score(store)

        if not getattr(credit_profile, 'credit_score', None):
            credit_profile = calculate_store_credit_score(store)

        serializer = MerchantCreditProfileSerializer(credit_profile)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RecalculateCreditScoreView(APIView):
    """Explicit endpoint to force a manual recalculation of the credit score."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user

        if not is_shop_owner(user):
            return Response(
                {"error": "Access restricted to store owners."},
                status=status.HTTP_403_FORBIDDEN
            )

        store = getattr(user, 'owned_store', None) or Store.objects.filter(owner=user).first()
        if not store:
            return Response(
                {"error": "No store associated with this account."},
                status=status.HTTP_404_NOT_FOUND
            )

        profile = calculate_store_credit_score(store)
        serializer = MerchantCreditProfileSerializer(profile)
        return Response(
            {
                "message": "Credit score recalculated successfully.",
                "data": serializer.data
            },
            status=status.HTTP_200_OK
        )


# ============================================================================
# MERCHANT TEMPLATE VIEWS (For Store Owners)
# ============================================================================


@login_required
def credit_dashboard_view(request):
    """Renders the Credit Score & Loan Readiness dashboard for store owners."""
    user = request.user

    if not is_shop_owner(user):
        messages.error(request, "Access restricted. Only store owners can view credit metrics.")
        return redirect('sales:pos_screen')

    store = getattr(user, 'owned_store', None) or Store.objects.filter(owner=user).first()
    if not store:
        messages.error(request, "No store assigned to your account.")
        return redirect('sales:pos_screen')

    if request.method == 'POST':
        credit_profile = calculate_store_credit_score(store)
        messages.success(request, "Your credit score and loan metrics have been updated!")
        return redirect('credit_scoring:merchant_dashboard')

    try:
        credit_profile = store.credit_profile
    except MerchantCreditProfile.DoesNotExist:
        credit_profile = calculate_store_credit_score(store)

    feature_importance = {}
    if getattr(credit_profile, 'feature_importance_json', None):
        try:
            feature_importance = json.loads(credit_profile.feature_importance_json)
        except (json.JSONDecodeError, TypeError):
            feature_importance = {}

    context = {
        'store': store,
        'profile': credit_profile,
        'feature_importance': feature_importance,
    }
    return render(request, 'credit_scoring/dashboard.html', context)


# ============================================================================
# LENDER TEMPLATE VIEWS (For Financial Institutions)
# ============================================================================


@login_required
@user_passes_test(is_lender_or_admin, login_url='/')
def lender_dashboard_view(request):
    """Renders a portal for lenders to review all registered merchants and risk tiers instantly."""
    
    # 1. Quickly ensure any store missing a profile gets a default shell (no heavy calculations on GET)
    existing_store_ids = MerchantCreditProfile.objects.values_list('store_id', flat=True)
    new_stores = Store.objects.exclude(id__in=existing_store_ids)
    
    for store in new_stores:
        MerchantCreditProfile.objects.get_or_create(
            store=store,
            defaults={
                'credit_score': 0,
                'risk_tier': 'UNASSESSED',
                'probability_of_default': 0.0,
                'max_recommended_loan': 0.0
            }
        )

    # 2. Fetch profiles efficiently with select_related
    profiles = (
        MerchantCreditProfile.objects
        .select_related('store', 'store__owner')
        .order_by('-credit_score')
    )

    context = {
        'merchant_profiles': profiles
    }
    return render(request, 'credit_scoring/lender_dashboard.html', context)


@login_required
@user_passes_test(is_lender_or_admin, login_url='/')
def lender_merchant_detail_view(request, store_id):
    """Lender Audit Detail View: Displays credit risk breakdown and ML feature factors."""
    store = get_object_or_404(Store, id=store_id)

    # Recalculate or retrieve current profile safely
    try:
        profile = calculate_store_credit_score(store)
    except Exception:
        profile = getattr(store, 'credit_profile', None)

    credit_score = getattr(profile, 'credit_score', 0) if profile else 0
    probability_of_default = getattr(profile, 'probability_of_default', 0.0) if profile else 0.0
    risk_tier = getattr(profile, 'risk_tier', 'Unassessed') if profile else 'Unassessed'

    # Explainability factors
    feature_importance = {}
    if profile and getattr(profile, 'feature_importance_json', None):
        try:
            feature_importance = json.loads(profile.feature_importance_json)
        except (json.JSONDecodeError, TypeError):
            feature_importance = {}

    # Historical audit logs from CreditAssessmentLog
    recent_assessments = []
    if profile:
        recent_assessments = CreditAssessmentLog.objects.filter(
            profile=profile
        ).order_by('-assessed_at')[:5]

    context = {
        'profile': profile,
        'store': store,
        'owner': getattr(store, 'owner', None),
        'credit_score': credit_score,
        'probability_of_default': round((probability_of_default or 0.0) * 100, 2),
        'risk_tier': risk_tier,
        'feature_importance': feature_importance,
        'recent_assessments': recent_assessments,
    }

    return render(request, 'credit_scoring/lender_merchant_detail.html', context)

