from django.contrib import admin
from django.db import models
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    MarketingCampaign, MarketingPayout, MarketingProof,
    MarketingShare, MarketingView, WithdrawalRequest,
)
from .views import send_withdrawal_paid_email


# ======================================================================
# Campaign
# ======================================================================
class MarketingShareInline(admin.TabularInline):
    model = MarketingShare
    extra = 0
    readonly_fields = ('user', 'code', 'views', 'earnings', 'created_at', 'last_view_at')
    can_delete = False
    fields = ('user', 'code', 'views', 'earnings', 'created_at', 'last_view_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MarketingCampaign)
class MarketingCampaignAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'media_type', 'product', 'payout_per_view',
        'is_active', 'is_live_flag', 'starts_at', 'share_count', 'view_count',
    )
    list_filter = ('is_active', 'media_type')
    search_fields = ('title', 'description')
    inlines = [MarketingShareInline]
    fieldsets = (
        (None, {'fields': ('title', 'description', 'product')}),
        ('Media', {'fields': ('media_type', 'image', 'video', 'caption_suggestion')}),
        ('Rewards', {'fields': ('payout_per_view',)}),
        ('Schedule', {'fields': ('is_active', 'starts_at', 'ends_at')}),
    )

    def is_live_flag(self, obj):
        return obj.is_live
    is_live_flag.boolean = True
    is_live_flag.short_description = 'Live now?'

    def share_count(self, obj):
        return obj.shares.count()
    share_count.short_description = 'Sharers'

    def view_count(self, obj):
        total = obj.shares.aggregate(s=models.Sum('views'))['s'] or 0
        return total
    view_count.short_description = 'Total views'


# ======================================================================
# Proof review
# ======================================================================
@admin.register(MarketingProof)
class MarketingProofAdmin(admin.ModelAdmin):
    list_display = (
        'share', 'user_link', 'reported_views', 'real_clicks',
        'credited_amount', 'status', 'uploaded_at', 'payout_due_at', 'credited_at',
    )
    list_filter = ('status', 'share__campaign')
    search_fields = ('share__user__username', 'share__code')
    readonly_fields = (
        'share', 'uploaded_at', 'payout_due_at', 'credited_at',
        'credited_amount', 'confirmation_sent_at', 'congrats_sent_at',
        'screenshot_preview',
    )
    fields = (
        'share', 'screenshot_preview', 'reported_views', 'note',
        'status', 'payout_due_at', 'credited_at', 'credited_amount',
        'confirmation_sent_at', 'congrats_sent_at', 'uploaded_at',
    )
    actions = ['reject_selected']

    def user_link(self, obj):
        return obj.share.user.username
    user_link.short_description = 'User'

    def real_clicks(self, obj):
        return obj.share.views
    real_clicks.short_description = 'Real link clicks'

    def screenshot_preview(self, obj):
        if not obj.screenshot:
            return '—'
        return format_html(
            '<a href="{0}" target="_blank"><img src="{0}" style="max-width:640px"></a>',
            obj.screenshot.url,
        )
    screenshot_preview.short_description = 'Screenshot'

    @admin.action(description='Reject selected (deduct any credited amount)')
    def reject_selected(self, request, queryset):
        from decimal import Decimal
        refunded = Decimal('0.00')
        count = 0
        for proof in queryset.select_related('share__campaign'):
            if proof.status == 'rejected':
                continue
            if proof.credited_amount:
                MarketingShare.objects.filter(pk=proof.share_id).update(
                    views=models.F('views') - proof.reported_views,
                    earnings=models.F('earnings') - proof.credited_amount,
                )
                try:
                    payout = MarketingPayout.objects.get(
                        user=proof.share.user, campaign=proof.share.campaign,
                    )
                    MarketingPayout.objects.filter(pk=payout.pk).update(
                        views=models.F('views') - proof.reported_views,
                        amount=models.F('amount') - proof.credited_amount,
                    )
                except MarketingPayout.DoesNotExist:
                    pass
                refunded += proof.credited_amount

            proof.status = 'rejected'
            proof.save(update_fields=['status'])
            count += 1

        self.message_user(
            request,
            f'{count} proof(s) rejected. KES {refunded} deducted from affected shares.',
        )


# ======================================================================
# Withdrawal requests
# ======================================================================
@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'amount', 'phone_number', 'status',
        'requested_at', 'reviewed_at', 'paid_at', 'mpesa_receipt',
    )
    list_filter = ('status', 'requested_at')
    search_fields = ('user__username', 'user__email', 'phone_number', 'mpesa_receipt')
    readonly_fields = ('user', 'amount', 'phone_number', 'requested_at')
    fields = (
        'user', 'amount', 'phone_number', 'requested_at',
        'status', 'reviewed_at', 'reviewed_by',
        'paid_at', 'mpesa_receipt', 'admin_note',
    )
    actions = ['mark_approved', 'mark_paid', 'mark_rejected']

    @admin.action(description='Mark selected as APPROVED (ready to pay)')
    def mark_approved(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='approved',
            reviewed_at=timezone.now(),
            reviewed_by=request.user,
        )
        self.message_user(request, f'{updated} request(s) approved.')

    @admin.action(description='Mark selected as PAID and email the user')
    def mark_paid(self, request, queryset):
        count = 0
        for wr in queryset.filter(status__in=['pending', 'approved']):
            wr.status = 'paid'
            wr.paid_at = timezone.now()
            wr.reviewed_at = wr.reviewed_at or timezone.now()
            wr.reviewed_by = wr.reviewed_by or request.user
            wr.save(update_fields=['status', 'paid_at', 'reviewed_at', 'reviewed_by'])

            try:
                send_withdrawal_paid_email(wr)
            except Exception:
                pass

            count += 1

        self.message_user(request, f'{count} request(s) marked paid.')

    @admin.action(description='Mark selected as REJECTED')
    def mark_rejected(self, request, queryset):
        updated = queryset.filter(status__in=['pending', 'approved']).update(
            status='rejected',
            reviewed_at=timezone.now(),
            reviewed_by=request.user,
        )
        self.message_user(request, f'{updated} request(s) rejected.')


# ======================================================================
# Payout summary
# ======================================================================
@admin.register(MarketingPayout)
class MarketingPayoutAdmin(admin.ModelAdmin):
    list_display = ('user', 'campaign', 'views', 'amount', 'status',
                    'requested_at', 'paid_at')
    list_filter = ('status', 'campaign')
    search_fields = ('user__username', 'user__email')
    actions = ['mark_paid', 'mark_rejected']

    @admin.action(description='Mark selected payouts as PAID')
    def mark_paid(self, request, queryset):
        updated = queryset.update(status='paid', paid_at=timezone.now())
        self.message_user(request, f'{updated} payout(s) marked paid.')

    @admin.action(description='Mark selected payouts as REJECTED')
    def mark_rejected(self, request, queryset):
        updated = queryset.update(status='rejected')
        self.message_user(request, f'{updated} payout(s) rejected.')


# ======================================================================
# Share + view (audit)
# ======================================================================
@admin.register(MarketingShare)
class MarketingShareAdmin(admin.ModelAdmin):
    list_display = ('user', 'campaign', 'code', 'views', 'earnings', 'created_at', 'last_view_at')
    list_filter = ('campaign',)
    search_fields = ('user__username', 'code')
    readonly_fields = ('code', 'views', 'earnings')


@admin.register(MarketingView)
class MarketingViewAdmin(admin.ModelAdmin):
    list_display = ('share', 'fingerprint', 'created_at')
    search_fields = ('share__code', 'share__user__username')
    readonly_fields = ('share', 'fingerprint', 'created_at', 'user_agent', 'referer')
