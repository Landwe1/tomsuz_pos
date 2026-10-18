from django.contrib import admin
from .models import MerchantCreditProfile, AssessmentHistory


@admin.register(MerchantCreditProfile)
class MerchantCreditProfileAdmin(admin.ModelAdmin):
    list_display = ('id',)


@admin.register(AssessmentHistory)
class AssessmentHistoryAdmin(admin.ModelAdmin):
    # Only includes basic fields guaranteed to exist
    list_display = ('id', 'assessed_at') if hasattr(AssessmentHistory, 'assessed_at') else ('id',)
    list_filter = ('assessed_at',) if hasattr(AssessmentHistory, 'assessed_at') else ()
    readonly_fields = ()

    def has_add_permission(self, request):
        """Prevents manual creation of audit history entries via admin."""
        return False
