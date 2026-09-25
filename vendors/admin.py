from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = (
        'business_name',
        'user_link',
        'status_badge',
        'product_count',
        'balance_display',
        'trial_ends_display',
        'subscription_expires_display',
        'is_approved',
        'created_at',
    )
    list_filter = ('is_approved', 'created_at')
    search_fields = (
        'business_name',
        'user__username',
        'user__email',
        'phone_number',
    )
    readonly_fields = (
        'user', 'created_at',
        'trial_started_at', 'trial_ends_at',
        'subscription_expires_at',
        'balance_display',
        'trial_status_display',
    )
    fieldsets = (
        ('Business', {
            'fields': ('user', 'business_name', 'phone_number', 'description')
        }),
        ('Approval', {
            'fields': ('is_approved',),
            'description': 'Uncheck to hide all this vendor\'s products from the storefront.'
        }),
        ('Trial', {
            'fields': ('trial_started_at', 'trial_ends_at', 'trial_status_display'),
            'description': 'New vendors get 30 days free. Extend by editing trial_ends_at.'
        }),
        ('Paid subscription', {
            'fields': ('subscription_expires_at',),
            'description': 'Set this when the vendor pays for a subscription period.'
        }),
        ('Earnings', {
            'fields': ('commission_percent', 'balance', 'balance_display'),
        }),
        ('Meta', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )
    actions = ['extend_trial_30_days', 'suspend_vendors', 'reinstate_vendors']

    # --------------------------------------------------------------
    # List columns
    # --------------------------------------------------------------
    def user_link(self, obj):
        return obj.user.username
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'

    def status_badge(self, obj):
        tone = obj.status_tone
        colours = {
            'success': ('#1B3A2A', '#45D68A'),
            'warning': ('#3D2E10', '#E8B93C'),
            'danger':  ('#3D1414', '#F0605C'),
            'muted':   ('#1A1A1A', '#7F7669'),
        }
        bg, fg = colours.get(tone, colours['muted'])
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:999px;font-size:11px;white-space:nowrap;">{}</span>',
            bg, fg, obj.status_label,
        )
    status_badge.short_description = 'Status'

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'

    def balance_display(self, obj):
        return f'KES {obj.balance}'
    balance_display.short_description = 'Balance'

    def trial_ends_display(self, obj):
        if not obj.trial_ends_at:
            return '—'
        if obj.on_trial:
            return f'{obj.trial_days_left}d left'
        return f'ended {obj.trial_ends_at:%d %b %Y}'
    trial_ends_display.short_description = 'Trial'

    def subscription_expires_display(self, obj):
        if not obj.subscription_expires_at:
            return '—'
        if obj.has_active_subscription:
            return f'{obj.subscription_days_left}d left'
        return f'expired {obj.subscription_expires_at:%d %b %Y}'
    subscription_expires_display.short_description = 'Subscription'

    def trial_status_display(self, obj):
        if not obj.trial_ends_at:
            return 'No trial on record.'
        if obj.on_trial:
            return f'On trial — {obj.trial_days_left} day(s) remaining.'
        return f'Trial ended on {obj.trial_ends_at:%d %b %Y}.'
    trial_status_display.short_description = 'Trial status'

    # --------------------------------------------------------------
    # Actions
    # --------------------------------------------------------------
    @admin.action(description='Extend trial by 30 days (from today)')
    def extend_trial_30_days(self, request, queryset):
        from datetime import timedelta
        now = timezone.now()
        count = 0
        for vendor in queryset:
            base = vendor.trial_ends_at if vendor.trial_ends_at and vendor.trial_ends_at > now else now
            vendor.trial_ends_at = base + timedelta(days=30)
            if not vendor.trial_started_at:
                vendor.trial_started_at = now
            vendor.save(update_fields=['trial_started_at', 'trial_ends_at'])
            count += 1
        self.message_user(request, f'{count} vendor(s) given another 30 days.')

    @admin.action(description='Suspend selected vendors (hide their products)')
    def suspend_vendors(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f'{updated} vendor(s) suspended.')

    @admin.action(description='Reinstate selected vendors')
    def reinstate_vendors(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} vendor(s) reinstated.')

    # --------------------------------------------------------------
    # Read-only enforcement: user can't be changed after creation.
    # --------------------------------------------------------------
    def has_add_permission(self, request):
        # Vendors are created via the public trial signup, not from admin.
        # You can still create one manually if you need to by removing this.
        return True

    def get_readonly_fields(self, request, obj=None):
        # If editing an existing vendor, lock the user FK.
        if obj is not None:
            return self.readonly_fields + ('user',)
        return self.readonly_fields
