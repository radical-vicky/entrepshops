from django.contrib import admin
from django.utils.html import format_html

from .models import DailySpin, Profile, SpinPrize, SpinWheelTheme, WalletTransaction, WithdrawalRequest


@admin.register(SpinWheelTheme)
class SpinWheelThemeAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'label', 'is_active', 'uploaded_at')
    list_editable = ('is_active',)
    list_filter = ('is_active',)
    ordering = ('-uploaded_at',)
    actions = ['make_active']

    def thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:50px;width:50px;object-fit:cover;border-radius:50%;">', obj.image.url)
        return '(no image)'
    thumbnail.short_description = 'Preview'

    @admin.action(description='Set as the active wheel image')
    def make_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one image to activate.', level='error')
            return
        theme = queryset.first()
        theme.is_active = True
        theme.save()
        self.message_user(request, f'"{theme}" is now the active wheel image.')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'referral_code', 'referred_by', 'referral_bonus_released', 'referral_count', 'wallet_balance')
    list_filter = ('referral_bonus_released',)
    search_fields = ('user__username', 'referral_code')
    readonly_fields = ('referral_code', 'wallet_balance')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'kind', 'description', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = ('user__username', 'description')


@admin.register(SpinPrize)
class SpinPrizeAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'label', 'kind', 'cash_value', 'weight', 'is_active')
    list_editable = ('weight', 'is_active')
    list_filter = ('kind', 'is_active')

    def thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;width:40px;object-fit:cover;border-radius:6px;">', obj.image.url)
        return '—'
    thumbnail.short_description = ''


@admin.register(DailySpin)
class DailySpinAdmin(admin.ModelAdmin):
    list_display = ('user', 'prize', 'spin_date', 'claim_status', 'claim_address', 'created_at')
    list_filter = ('spin_date', 'prize', 'claim_status')
    search_fields = ('user__username',)
    actions = ['mark_fulfilled']

    @admin.action(description='Mark selected prizes as fulfilled (delivered)')
    def mark_fulfilled(self, request, queryset):
        updated = queryset.filter(claim_status=DailySpin.ClaimStatus.CLAIMED).update(
            claim_status=DailySpin.ClaimStatus.FULFILLED
        )
        self.message_user(request, f'{updated} prize(s) marked fulfilled.')


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'phone_number', 'status', 'mpesa_receipt_number', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'phone_number', 'mpesa_conversation_id', 'mpesa_receipt_number')
    readonly_fields = ('user', 'amount', 'phone_number', 'mpesa_conversation_id', 'created_at')
    actions = ['mark_paid_manually', 'mark_failed_and_refund']

    @admin.action(description='Mark as paid manually (e.g. sent via M-Pesa app while B2C isn\'t set up yet)')
    def mark_paid_manually(self, request, queryset):
        count = 0
        for withdrawal in queryset.filter(status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING]):
            withdrawal.mark_success(receipt_number='MANUAL')
            count += 1
        self.message_user(request, f'{count} withdrawal(s) marked paid.')

    @admin.action(description='Mark as failed and refund the wallet')
    def mark_failed_and_refund(self, request, queryset):
        count = 0
        for withdrawal in queryset.filter(status__in=[WithdrawalRequest.Status.PENDING, WithdrawalRequest.Status.PROCESSING]):
            withdrawal.mark_failed('Manually marked failed by admin')
            count += 1
        self.message_user(request, f'{count} withdrawal(s) failed and refunded.')
