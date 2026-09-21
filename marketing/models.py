import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class MarketingCampaign(models.Model):
    """A piece of marketing content the admin publishes for users to
    download and share. One new campaign per day is the expected cadence."""

    class MediaType(models.TextChoices):
        IMAGE = 'image', 'Image'
        VIDEO = 'video', 'Video'

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, help_text='Shown to users under the media, optional.')
    product = models.ForeignKey(
        'store.Product', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='marketing_campaigns',
        help_text='The product this campaign promotes. Shared links land here.'
    )
    media_type = models.CharField(max_length=10, choices=MediaType.choices, default=MediaType.IMAGE)
    image = models.ImageField(upload_to='marketing/images/', blank=True, null=True)
    video = models.FileField(upload_to='marketing/videos/', blank=True, null=True)
    caption_suggestion = models.TextField(
        blank=True,
        help_text='Suggested WhatsApp caption. Users can copy this with one tap.',
    )
    payout_per_view = models.DecimalField(
        max_digits=6, decimal_places=2, default=50,
        help_text='KES paid to the sharer for each unique view of their link.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Turn off to stop new shares and stop counting views.',
    )
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True,
        help_text='Leave blank to keep it running until you turn it off.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def is_live(self):
        now = timezone.now()
        if not self.is_active or now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    @property
    def landing_url(self):
        """Where the shared link ultimately lands — the product page if
        there is one, otherwise the shop home."""
        if self.product:
            return self.product.get_absolute_url()
        return reverse('store:home')


class MarketingShare(models.Model):
    """A single user's tracked share of a single campaign. The unique code
    is what goes in the short link they post to WhatsApp."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='marketing_shares',
    )
    campaign = models.ForeignKey(
        MarketingCampaign, on_delete=models.CASCADE,
        related_name='shares',
    )
    code = models.CharField(max_length=16, unique=True, db_index=True)
    views = models.PositiveIntegerField(default=0)
    earnings = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_view_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('user', 'campaign')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} → {self.campaign} ({self.views} views)'

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        while True:
            code = secrets.token_urlsafe(6)  # 8 chars
            if not MarketingShare.objects.filter(code=code).exists():
                return code

    @property
    def share_url_path(self):
        return reverse('marketing:redirect', args=[self.code])


class MarketingView(models.Model):
    """One row per unique view of a share link. Deduplicated by a hash of
    IP + user-agent + campaign so refreshing the same visitor doesn't
    inflate the view count."""

    share = models.ForeignKey(
        MarketingShare, on_delete=models.CASCADE, related_name='view_rows',
    )
    fingerprint = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=300, blank=True)
    referer = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = [('share', 'fingerprint')]
        ordering = ['-created_at']
        indexes = [models.Index(fields=['share', 'fingerprint'])]


class MarketingPayout(models.Model):
    """Earnings summary per user, paid out manually (via M-Pesa or wallet
    credit). One row per (user, campaign)."""

    class Status(models.TextChoices):
        ACCRUING = 'accruing', 'Accruing'
        REQUESTED = 'requested', 'Payout requested'
        PAID = 'paid', 'Paid'
        REJECTED = 'rejected', 'Rejected'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='marketing_payouts',
    )
    campaign = models.ForeignKey(
        MarketingCampaign, on_delete=models.CASCADE,
        related_name='payouts',
    )
    views = models.PositiveIntegerField(default=0)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACCRUING)
    requested_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [('user', 'campaign')]
        ordering = ['-requested_at', '-id']

    def __str__(self):
        return f'{self.user} — {self.campaign} — KES {self.amount}'