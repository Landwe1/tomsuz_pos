import uuid
import json
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from sales.models import Store  # Adjust import according to your app structure


class MerchantCreditProfile(models.Model):
    RISK_TIERS = [
        ('LOW', 'Low Risk (Preferred Borrower)'),
        ('MEDIUM', 'Moderate Risk (Standard Terms)'),
        ('HIGH', 'High Risk (Requires Collateral / Guarantee)'),
        ('VERY_HIGH', 'Very High Risk (Unfavorable Metrics)'),
    ]

    OWNERSHIP_TYPES = [
        ('SOLE_PROP', 'Sole Proprietorship'),
        ('PARTNERSHIP', 'Partnership'),
        ('LIMITED', 'Private Limited Company (Ltd)'),
        ('INFORMAL', 'Informal Enterprise / Cooperative'),
    ]

    # --- Core Relationship ---
    store = models.OneToOneField(
        Store, 
        on_delete=models.CASCADE, 
        related_name='credit_profile'
    )
    
    # --- Section 1.4.1 (3): Self-Reported / Static Financial Profile ---
    business_age_years = models.DecimalField(
        max_digits=4, decimal_places=1, default=1.0,
        help_text="Operating age of the business in years."
    )
    number_of_employees = models.IntegerField(default=1)
    ownership_structure = models.CharField(
        max_length=20, choices=OWNERSHIP_TYPES, default='SOLE_PROP'
    )
    total_assets = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_liabilities = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    is_zra_registered = models.BooleanField(
        default=False, 
        help_text="Tax compliance / ZRA TPIN registration status."
    )
    has_physical_premises = models.BooleanField(
        default=True,
        help_text="Whether the business operates from a fixed physical location."
    )

    # --- Section 1.4.1 (4): POS Engine Calculated Metrics (30/60/90 Days) ---
    avg_monthly_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    avg_gross_margin = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        help_text="Gross margin percentage (0-100%)."
    )
    sales_volatility_index = models.DecimalField(
        max_digits=6, decimal_places=4, default=0.0000,
        help_text="Standard deviation of daily revenue relative to mean daily sales."
    )
    active_days_last_90_days = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(90)]
    )
    monthly_transaction_count = models.IntegerField(default=0)
    inventory_turnover_ratio = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.00,
        help_text="Cost of Goods Sold / Average Inventory Value."
    )

    # --- Section 1.4.1 (5): Loan & Repayment Behaviour ---
    existing_loan_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Current outstanding debt obligations across all lenders."
    )
    past_defaults_count = models.IntegerField(
        default=0,
        help_text="Number of defaulted loans in past 36 months."
    )
    delinquent_days_max = models.IntegerField(
        default=0,
        help_text="Maximum days past due on past loan installments."
    )
    successful_repayments_count = models.IntegerField(
        default=0,
        help_text="Number of fully repaid loan cycles."
    )

    # --- Machine Learning Engine Outputs ---
    credit_score = models.IntegerField(
        default=300,
        validators=[MinValueValidator(300), MaxValueValidator(850)],
        help_text="Calculated Business Credit Score (Scale: 300 - 850)."
    )
    probability_of_default = models.DecimalField(
        max_digits=5, decimal_places=4, default=1.0000,
        help_text="Raw ML output: Probability of Default (PD) between 0.0000 and 1.0000."
    )
    risk_tier = models.CharField(max_length=15, choices=RISK_TIERS, default='HIGH')
    max_recommended_loan = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Estimated maximum safe loan capacity based on monthly cash flows."
    )

    # --- System Metadata & Audit ---
    ml_model_version = models.CharField(
        max_length=50, default="v1.0-RandomForest",
        help_text="Version of the deployed ML model used for inference."
    )
    feature_importance_json = models.TextField(
        blank=True, null=True,
        help_text="JSON payload storing key driver factors for this merchant's score."
    )
    last_updated = models.DateTimeField(auto_now=True)

    def calculate_debt_to_income_ratio(self):
        """Helper method: Annualized Debt Service to Revenue."""
        if self.avg_monthly_revenue > 0:
            return float((self.existing_loan_balance / 12) / self.avg_monthly_revenue)
        return 0.0

    def __str__(self):
        return f"{self.store.name} | Score: {self.credit_score} ({self.get_risk_tier_display()})"


class CreditAssessmentLog(models.Model):
    """
    Section 1.4.1 (10): Historical audit log of every score assessment run.
    Ensures research evaluation, auditability, and model tracking over time.
    """
    profile = models.ForeignKey(
        MerchantCreditProfile, 
        on_delete=models.CASCADE, 
        related_name='assessment_logs'
    )
    assessed_at = models.DateTimeField(auto_now_add=True)
    assigned_score = models.IntegerField()
    probability_of_default = models.DecimalField(max_digits=5, decimal_places=4)
    risk_tier = models.CharField(max_length=15)
    recommended_loan = models.DecimalField(max_digits=12, decimal_places=2)
    model_algorithm_used = models.CharField(max_length=50)
    input_snapshot_json = models.TextField(
        help_text="Snapshot of feature vector passed to ML model."
    )

    class Meta:
        ordering = ['-assessed_at']

    def __str__(self):
        return f"Log #{self.id} - {self.profile.store.name} - Score {self.assigned_score} ({self.assessed_at.strftime('%Y-%m-%d')})"


class CreditReportExport(models.Model):
    """
    Section 1.4.1 (12): Stores generated financial health statements for bank/lender submission.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='credit_reports')
    generated_at = models.DateTimeField(auto_now_add=True)
    score_at_generation = models.IntegerField(default=300)
    report_pdf = models.FileField(upload_to='credit_reports/', null=True, blank=True)
    verification_hash = models.CharField(max_length=64, editable=False)

    def save(self, *args, **kwargs):
        if not self.verification_hash and self.store:
            import hashlib
            raw_string = f"{self.store.id}-{self.generated_at}-{self.score_at_generation}-{uuid.uuid4()}"
            self.verification_hash = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Report {self.id.hex[:8]} - {self.store.name} ({self.generated_at.strftime('%Y-%m-%d')})"


class AssessmentHistory(models.Model):
    merchant_profile = models.ForeignKey(
        'MerchantCreditProfile', 
        on_delete=models.CASCADE, 
        related_name='assessment_history'
    )
    credit_score = models.IntegerField()
    risk_category = models.CharField(max_length=20)
    prob_default = models.FloatField(blank=True, null=True)
    assessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Assessment Histories"
        ordering = ['-assessed_at']

    def __str__(self):
        return f"{self.merchant_profile.store.name} - {self.credit_score} ({self.assessed_at.strftime('%Y-%m-%d')})"

