from django.conf import settings
from django.db import models
from django.utils import timezone


class Vendor(models.Model):
    """A third-party seller. New vendors get a 30-day free trial during
    which they can list products without paying a subscription fee. After
    the trial, they must subscribe to keep adding new listings — existing
    products and orders remain untouched."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vendor_profile',
    )
    business_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)

    is_approved = models.BooleanField(
        default=True,
        help_text='Admin can uncheck to hide all of this vendor\'s products.',
    )

    # --- Trial ---
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    # --- Paid subscription ---
    subscription_expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Set when the vendor pays for a subscription period.',
    )

    # --- Commission ---
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Percent of each sale kept by the platform. 0 = vendor keeps everything.'
    )

    # --- Balances ---
    balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Earnings awaiting withdrawal.',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.business_name

    # ------------------------------------------------------------------
    # Trial / subscription state
    # ------------------------------------------------------------------
    @property
    def on_trial(self):
        if not self.trial_ends_at:
            return False
        return timezone.now() < self.trial_ends_at

    @property
    def has_active_subscription(self):
        if not self.subscription_expires_at:
            return False
        return timezone.now() < self.subscription_expires_at

    @property
    def can_list_products(self):
        """True if the vendor can add NEW products right now. Existing
        products and orders are not gated by this."""
        if not self.is_approved:
            return False
        return self.on_trial or self.has_active_subscription

    @property
    def trial_days_left(self):
        if not self.on_trial:
            return 0
        delta = self.trial_ends_at - timezone.now()
        return max(0, delta.days)

    @property
    def subscription_days_left(self):
        if not self.has_active_subscription:
            return 0
        delta = self.subscription_expires_at - timezone.now()
        return max(0, delta.days)

    @property
    def status_label(self):
        if not self.is_approved:
            return 'Suspended'
        if self.has_active_subscription:
            return f'Subscribed ({self.subscription_days_left}d left)'
        if self.on_trial:
            return f'Trial ({self.trial_days_left}d left)'
        return 'Trial expired'

    @property
    def status_tone(self):
        """CSS tone for the dashboard badge."""
        if not self.is_approved:
            return 'danger'
        if self.has_active_subscription:
            return 'success'
        if self.on_trial:
            return 'warning'
        return 'muted'

    # ------------------------------------------------------------------
    # Product helpers
    # ------------------------------------------------------------------
    @property
    def product_count(self):
        return self.products.count()

    @property
    def requires_review(self):
        """First 3 products a vendor creates need admin approval. After
        that, new products auto-approve."""
        return self.product_count < 3
