import json

from rest_framework import serializers
from .models import CreditAssessmentLog, MerchantCreditProfile


class MerchantCreditProfileSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    store_owner_name = serializers.SerializerMethodField()
    risk_tier_display = serializers.CharField(source='get_risk_tier_display', read_only=True)
    probability_of_default_pct = serializers.SerializerMethodField()
    feature_importance = serializers.SerializerMethodField()

    class Meta:
        model = MerchantCreditProfile
        fields = [
            'id',
            'store',
            'store_name',
            'store_owner_name',
            'credit_score',
            'risk_tier',
            'risk_tier_display',
            'probability_of_default',
            'probability_of_default_pct',
            'max_recommended_loan',
            'avg_monthly_revenue',
            'avg_gross_margin',
            'sales_volatility_index',
            'active_days_last_90_days',
            'monthly_transaction_count',
            'inventory_turnover_ratio',
            'business_age_years',
            'number_of_employees',
            'ownership_structure',
            'total_assets',
            'total_liabilities',
            'is_zra_registered',
            'existing_loan_balance',
            'past_defaults_count',
            'delinquent_days_max',
            'ml_model_version',
            'feature_importance',
            'last_updated',
        ]
        read_only_fields = [
            'id',
            'credit_score',
            'risk_tier',
            'probability_of_default',
            'max_recommended_loan',
            'avg_monthly_revenue',
            'avg_gross_margin',
            'sales_volatility_index',
            'active_days_last_90_days',
            'monthly_transaction_count',
            'inventory_turnover_ratio',
            'ml_model_version',
            'last_updated',
        ]

    def get_store_owner_name(self, obj):
        if hasattr(obj.store, 'owner') and obj.store.owner:
            owner = obj.store.owner
            full_name = owner.get_full_name() if callable(getattr(owner, 'get_full_name', None)) else ''
            return full_name if full_name.strip() else getattr(owner, 'username', 'Unknown')
        return 'Unassigned'

    def get_probability_of_default_pct(self, obj):
        if obj.probability_of_default is not None:
            return round(float(obj.probability_of_default) * 100.0, 2)
        return 0.0

    def get_feature_importance(self, obj):
        if getattr(obj, 'feature_importance_json', None):
            try:
                return json.loads(obj.feature_importance_json)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}


class CreditAssessmentLogSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='profile.store.name', read_only=True)

    class Meta:
        model = CreditAssessmentLog
        fields = [
            'id',
            'profile',
            'store_name',
            'assigned_score',
            'probability_of_default',
            'risk_tier',
            'recommended_loan',
            'model_algorithm_used',
            'input_snapshot_json',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

