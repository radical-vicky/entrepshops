from django.conf import settings
from django.db import models
from django.utils import timezone


class Vendor(models.Model):
    """A third-party seller renting shelf space on the platform. Needs an
    active (non-expired) subscription to list or keep products live —
    see subscription_active below."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name='vendor_profile', on_delete=models.CASCADE)
    business_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20)
    is_approved = models.BooleanField(
        default=False,
        help_text='Admin sign-off before this vendor can list products publicly, even with a paid subscription.'
    )
    subscription_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.business_name

    @property
    def subscription_active(self):
        return bool(self.subscription_expires_at and self.subscription_expires_at > timezone.now())

    @property
    def can_sell(self):
        """Both gates have to be open: admin approval AND a paid, current subscription."""
        return self.is_approved and self.subscription_active

    def extend_subscription(self, days):
        """Stacks onto any remaining time rather than resetting it, so
        renewing a few days early doesn't waste the days still owed."""
        base = self.subscription_expires_at if self.subscription_active else timezone.now()
        self.subscription_expires_at = base + timezone.timedelta(days=days)
        self.save(update_fields=['subscription_expires_at'])


class VendorSubscriptionPayment(models.Model):
    class Status(models.TextChoices):
        INITIATED = 'initiated', 'Initiated'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    vendor = models.ForeignKey(Vendor, related_name='subscription_payments', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    phone_number = models.CharField(max_length=20)
    days = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIATED)
    checkout_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.vendor.business_name} — KES {self.amount} ({self.status})'

    def mark_success(self, receipt_number=''):
        self.status = self.Status.SUCCESS
        self.mpesa_receipt_number = receipt_number
        self.save(update_fields=['status', 'mpesa_receipt_number'])
        self.vendor.extend_subscription(self.days)
