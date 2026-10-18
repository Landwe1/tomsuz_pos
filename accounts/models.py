from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    class Role(models.TextChoices):
        SHOP_OWNER = 'SHOP_OWNER', 'Shop Owner'
        CASHIER = 'CASHIER', 'Cashier'
        LENDER = 'LENDER', 'Lender / Financial Institution'
        ADMIN = 'ADMIN', 'Administrator'

    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='account_profile'
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)
    
    # Optional field for Lenders
    institution_name = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


# Automatic profile creation when a User is created
@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Fixed accessor to match related_name='account_profile'
        if hasattr(instance, 'account_profile'):
            instance.account_profile.save()

