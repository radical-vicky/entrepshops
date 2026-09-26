from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class ImportRequest(models.Model):
    """A business customer's request to source a product from abroad.
    Customer submits the details, admin researches and quotes, customer
    pays a 50% deposit, admin orders, tracking updates happen here."""

    class Status(models.TextChoices):
        SUBMITTED = 'submitted', 'Submitted'
        QUOTED = 'quoted', 'Quoted'
        AWAITING_DEPOSIT = 'awaiting_deposit', 'Awaiting deposit'
        ORDERED = 'ordered', 'Ordered'
        IN_TRANSIT = 'in_transit', 'In transit'
        ARRIVED = 'arrived', 'Arrived'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    # Reference number shown to the customer and used everywhere
    reference = models.CharField(max_length=20, unique=True, db_index=True)

    # Owner
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='import_requests',
    )

    # What they want
    title = models.CharField(max_length=200, help_text='Short name of what you need.')
    description = models.TextField(help_text='Specs, quantity, brand, model, any details.')
    reference_url = models.URLField(
        blank=True,
        help_text='Optional link to the exact item (Alibaba, Amazon, manufacturer page).',
    )
    reference_image = models.ImageField(
        upload_to='sourcing/requests/%Y/%m/', blank=True, null=True,
        help_text='Optional photo or screenshot of the item.',
    )

    # Business info (asked at submit time)
    business_name = models.CharField(max_length=150, blank=True)
    phone_number = models.CharField(
        max_length=20,
        help_text='M-Pesa number for the deposit prompt, format 2547XXXXXXXX.',
    )
    delivery_location = models.CharField(
        max_length=200, blank=True,
        help_text='Where you want the item delivered, e.g. Nairobi CBD.',
    )
    quantity = models.PositiveIntegerField(default=1)

    # Status
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SUBMITTED,
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.reference} — {self.title}'

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        """Generates a short, unique, human-friendly reference like IMP-7K3M9."""
        import secrets
        alphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'  # no I, L, O, 0, 1
        while True:
            suffix = ''.join(secrets.choice(alphabet) for _ in range(6))
            ref = f'IMP-{suffix}'
            if not ImportRequest.objects.filter(reference=ref).exists():
                return ref

    def get_absolute_url(self):
        return reverse('sourcing:request_detail', args=[self.reference])

    # ------------------------------------------------------------------
    # Quote helpers
    # ------------------------------------------------------------------
    @property
    def active_quote(self):
        return self.quotes.order_by('-version').first()

    @property
    def deposit_amount(self):
        q = self.active_quote
        if not q:
            return Decimal('0.00')
        return q.deposit_amount

    @property
    def is_paid_in_full(self):
        return self.paid_amount >= self.total_amount and self.total_amount > 0

    @property
    def total_amount(self):
        q = self.active_quote
        return q.total if q else Decimal('0.00')

    @property
    def paid_amount(self):
        return self.payments.filter(status='confirmed').aggregate(
            s=models.Sum('amount')
        )['s'] or Decimal('0.00')

    @property
    def balance_due(self):
        return max(Decimal('0.00'), self.total_amount - self.paid_amount)

    @property
    def status_tone(self):
        """CSS tone for the status pill."""
        return {
            'submitted': 'muted',
            'quoted': 'warning',
            'awaiting_deposit': 'warning',
            'ordered': 'success',
            'in_transit': 'success',
            'arrived': 'success',
            'completed': 'success',
            'cancelled': 'danger',
        }.get(self.status, 'muted')

    @property
    def is_active(self):
        return self.status not in (self.Status.COMPLETED, self.Status.CANCELLED)


class ImportQuote(models.Model):
    """A price quote on a request. Multiple versions possible if the
    customer negotiates or specs change. Only the latest is shown to the
    customer. Built by admin, itemised."""

    request = models.ForeignKey(
        ImportRequest, on_delete=models.CASCADE, related_name='quotes',
    )
    version = models.PositiveIntegerField(default=1)

    # Itemised pricing in KES
    item_cost = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customs_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Notes shown to the customer
    lead_time_days = models.PositiveIntegerField(
        default=30,
        help_text='Estimated days from deposit to arrival.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Any extra info — warranty, condition, source country, etc.',
    )

    # Payment terms
    deposit_percent = models.PositiveIntegerField(
        default=50,
        help_text='Percent of the total that is due as a deposit.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='created_quotes',
    )

    class Meta:
        ordering = ['-version']
        unique_together = [('request', 'version')]

    def __str__(self):
        return f'{self.request.reference} v{self.version}'

    def save(self, *args, **kwargs):
        if not self.version or self.version == 1:
            latest = ImportQuote.objects.filter(request=self.request).order_by('-version').first()
            if latest:
                self.version = latest.version + 1
        super().save(*args, **kwargs)

    @property
    def total(self):
        return (
            self.item_cost
            + self.shipping_cost
            + self.customs_cost
            + self.service_fee
        )

    @property
    def deposit_amount(self):
        return (self.total * Decimal(self.deposit_percent) / Decimal(100)).quantize(Decimal('0.01'))

    @property
    def balance_amount(self):
        return self.total - self.deposit_amount


class ImportPayment(models.Model):
    """A payment against a request — deposit or balance. Tied to an M-Pesa
    STK push and updated by the Daraja callback."""

    class Kind(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit (50%)'
        BALANCE = 'balance', 'Balance'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    request = models.ForeignKey(
        ImportRequest, on_delete=models.CASCADE, related_name='payments',
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.DEPOSIT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # M-Pesa details
    merchant_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    checkout_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    mpesa_receipt = models.CharField(max_length=40, blank=True)
    result_code = models.CharField(max_length=10, blank=True)
    result_description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.request.reference} — {self.kind} — KES {self.amount}'

    def mark_confirmed(self, receipt=''):
        self.status = self.Status.CONFIRMED
        self.mpesa_receipt = receipt or self.mpesa_receipt
        self.confirmed_at = timezone.now()
        self.save(update_fields=['status', 'mpesa_receipt', 'confirmed_at'])
