import random
import string

from django.conf import settings
from django.db import models
from django.utils import timezone


def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))


class Profile(models.Model):
    """Extends the built-in User with an avatar, referral code, and wallet.
    Created automatically for every user (see accounts/signals.py)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name='profile', on_delete=models.CASCADE
    )
    avatar = models.ImageField(
        upload_to='profiles/avatars/', blank=True, null=True,
        help_text='Profile picture — stored on Cloudinary.'
    )
    referral_code = models.CharField(max_length=12, unique=True, blank=True)
    referred_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='referrals', null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text='The user whose referral code/link this person signed up through.'
    )

    # --- NEW PROFILE FIELDS ---
    phone_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=10,
        choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')],
        blank=True
    )
    bio = models.TextField(max_length=500, blank=True)
    # --------------------------

    # Two-stage referral payout flags — each flips to True exactly once.
    email_bonus_released = models.BooleanField(
        default=False,
        help_text='Stage 1: set once the referred user verifies their email '
                   'and the email bonus has been paid to both sides.'
    )
    first_order_bonus_released = models.BooleanField(
        default=False,
        help_text='Stage 2: set once the referred user completes their first '
                   'paid order and the first-order bonus has been paid to both sides.'
    )

    # Legacy flag — kept for backward compatibility with old data.
    referral_bonus_released = models.BooleanField(default=False)

    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.username} profile'

    def release_email_bonus_if_due(self):
        if not self.referred_by_id or self.email_bonus_released:
            return
        bonus = getattr(settings, 'REFERRAL_EMAIL_BONUS_KES', 0)
        if bonus <= 0:
            self.email_bonus_released = True
            self.save(update_fields=['email_bonus_released'])
            return

        referrer_profile, _ = Profile.objects.get_or_create(user=self.referred_by)
        referrer_profile.credit_wallet(
            bonus, WalletTransaction.Kind.REFERRAL_EMAIL_BONUS,
            description=f'{self.user.username} verified their email',
        )
        self.credit_wallet(
            bonus, WalletTransaction.Kind.REFERRAL_EMAIL_BONUS,
            description='Referral bonus — email verified',
        )
        self.email_bonus_released = True
        self.save(update_fields=['email_bonus_released'])

    def release_first_order_bonus_if_due(self):
        if not self.referred_by_id or self.first_order_bonus_released:
            return
        if not self.email_bonus_released:
            return
        bonus = getattr(settings, 'REFERRAL_FIRST_ORDER_BONUS_KES', 0)
        if bonus <= 0:
            self.first_order_bonus_released = True
            self.save(update_fields=['first_order_bonus_released'])
            return

        referrer_profile, _ = Profile.objects.get_or_create(user=self.referred_by)
        referrer_profile.credit_wallet(
            bonus, WalletTransaction.Kind.REFERRAL_FIRST_ORDER,
            description=f'{self.user.username} completed their first order',
        )
        self.credit_wallet(
            bonus, WalletTransaction.Kind.REFERRAL_FIRST_ORDER,
            description='Referral bonus — first order complete',
        )
        self.first_order_bonus_released = True
        self.save(update_fields=['first_order_bonus_released'])

    def save(self, *args, **kwargs):
        if not self.referral_code:
            code = generate_referral_code()
            while Profile.objects.filter(referral_code=code).exists():
                code = generate_referral_code()
            self.referral_code = code
        super().save(*args, **kwargs)

    def credit_wallet(self, amount, kind, description=''):
        self.wallet_balance = models.F('wallet_balance') + amount
        self.save(update_fields=['wallet_balance'])
        self.refresh_from_db(fields=['wallet_balance'])
        WalletTransaction.objects.create(
            user=self.user, amount=amount, kind=kind, description=description
        )

    def debit_wallet(self, amount, kind, description=''):
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            locked = Profile.objects.select_for_update().get(pk=self.pk)
            if locked.wallet_balance < amount:
                return False
            locked.wallet_balance = models.F('wallet_balance') - amount
            locked.save(update_fields=['wallet_balance'])
        self.refresh_from_db(fields=['wallet_balance'])
        WalletTransaction.objects.create(
            user=self.user, amount=-amount, kind=kind, description=description
        )
        return True

    @property
    def referral_count(self):
        return self.user.referrals.count()


class WalletTransaction(models.Model):
    class Kind(models.TextChoices):
        REFERRAL_EMAIL_BONUS = 'referral_email_bonus', 'Referral bonus — email verified'
        REFERRAL_FIRST_ORDER = 'referral_first_order', 'Referral bonus — first order'
        SPIN_WIN = 'spin_win', 'Daily spin win'
        ADJUSTMENT = 'adjustment', 'Manual adjustment'
        WITHDRAWAL = 'withdrawal', 'Wallet withdrawal'
        WITHDRAWAL_REVERSAL = 'withdrawal_reversal', 'Withdrawal reversed (failed payout)'
        REFERRAL_BONUS = 'referral_bonus', 'Referral bonus (legacy)'
        REFERRAL_SIGNUP_BONUS = 'referral_signup_bonus', 'Welcome bonus (referred, legacy)'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='wallet_transactions',
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — KES {self.amount} ({self.get_kind_display()})'


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed (refunded)'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='withdrawals', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    phone_number = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    mpesa_conversation_id = models.CharField(max_length=100, blank=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — KES {self.amount} withdrawal ({self.status})'

    def mark_success(self, receipt_number=''):
        self.status = self.Status.SUCCESS
        self.mpesa_receipt_number = receipt_number
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'mpesa_receipt_number', 'completed_at'])

    def mark_failed(self, reason=''):
        self.status = self.Status.FAILED
        self.failure_reason = reason[:255]
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'failure_reason', 'completed_at'])
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.credit_wallet(
            self.amount, WalletTransaction.Kind.WITHDRAWAL_REVERSAL,
            description=f'Withdrawal #{self.id} failed — refunded ({reason[:150]})',
        )


class SpinWheelTheme(models.Model):
    label = models.CharField(max_length=100, blank=True, help_text='Just a label for you, e.g. "Festive wheel".')
    image = models.ImageField(upload_to='site/spin-wheel/', help_text='A square image works best — it fills the circular wheel face.')
    is_active = models.BooleanField(
        default=False,
        help_text='Only one wheel image is shown at a time — selecting this one deselects any other.'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'spin wheel image'
        verbose_name_plural = 'spin wheel images'

    def __str__(self):
        return self.label or f'Wheel image #{self.pk}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            SpinWheelTheme.objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()


class SpinPrize(models.Model):
    class Kind(models.TextChoices):
        CASH = 'cash', 'Cash voucher'
        TRANSPORT = 'transport', 'Transport fee'
        DRINKS = 'drinks', 'Drinks'
        SMARTPHONE = 'smartphone', 'Smartphone'
        LAPTOP = 'laptop', 'Laptop'
        SMART_TV = 'smart_tv', 'Smart TV'
        TRY_AGAIN = 'try_again', 'Try again (no prize)'

    label = models.CharField(max_length=100, help_text='Shown on the wheel, e.g. "KES 200 cash voucher".')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    cash_value = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='If set, this amount (KES) is credited to the wallet automatically on a win.'
    )
    weight = models.PositiveIntegerField(
        default=10, help_text='Relative odds — higher weight wins more often. Try_again prizes should carry most of the weight.'
    )
    image = models.ImageField(upload_to='spin/prizes/', blank=True, null=True)
    color = models.CharField(
        max_length=7,
        default='#2FA66B',
        help_text='Hex colour for this slice on the wheel, e.g. #2FA66B (green), #FF8A3D (orange), #E8B93C (gold), #B5541A (rust).',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-weight']

    def __str__(self):
        return self.label


class DailySpin(models.Model):
    class ClaimStatus(models.TextChoices):
        AUTO_CREDITED = 'auto_credited', 'Auto-credited to wallet'
        NOTHING_TO_CLAIM = 'nothing_to_claim', 'No prize (try again)'
        PENDING_CLAIM = 'pending_claim', 'Awaiting claim'
        CLAIMED = 'claimed', 'Claimed — awaiting fulfilment'
        FULFILLED = 'fulfilled', 'Fulfilled'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='spins', on_delete=models.CASCADE)
    prize = models.ForeignKey(SpinPrize, related_name='wins', on_delete=models.PROTECT)
    spin_date = models.DateField(default=timezone.localdate)
    claim_status = models.CharField(max_length=20, choices=ClaimStatus.choices, default=ClaimStatus.NOTHING_TO_CLAIM)
    claim_address = models.ForeignKey(
        'store.DeliveryAddress', null=True, blank=True, on_delete=models.SET_NULL,
        help_text='Where to deliver a physical prize, captured when the user claims it.'
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'spin_date')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.prize.label} ({self.spin_date})'

    def claim(self, address):
        self.claim_address = address
        self.claim_status = self.ClaimStatus.CLAIMED
        self.claimed_at = timezone.now()
        self.save(update_fields=['claim_address', 'claim_status', 'claimed_at'])