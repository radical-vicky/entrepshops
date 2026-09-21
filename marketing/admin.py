from django.db import models
from django.contrib import admin
from django.utils.html import format_html

from .models import MarketingCampaign, MarketingPayout, MarketingShare, MarketingView


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
    list_display = ('title', 'media_type', 'product', 'payout_per_view',
                    'is_active', 'is_live_flag', 'starts_at', 'share_count', 'view_count')
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


@admin.register(MarketingPayout)
class MarketingPayoutAdmin(admin.ModelAdmin):
    list_display = ('user', 'campaign', 'views', 'amount', 'status',
                    'requested_at', 'paid_at')
    list_filter = ('status', 'campaign')
    search_fields = ('user__username', 'user__email')
    actions = ['mark_paid', 'mark_rejected']

    @admin.action(description='Mark selected payouts as PAID')
    def mark_paid(self, request, queryset):
        from django.utils import timezone
        updated = queryset.update(status='paid', paid_at=timezone.now())
        self.message_user(request, f'{updated} payout(s) marked paid.')

    @admin.action(description='Mark selected payouts as REJECTED')
    def mark_rejected(self, request, queryset):
        updated = queryset.update(status='rejected')
        self.message_user(request, f'{updated} payout(s) rejected.')


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