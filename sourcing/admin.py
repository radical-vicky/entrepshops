from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from .models import ImportPayment, ImportQuote, ImportRequest


class ImportQuoteInline(admin.StackedInline):
    model = ImportQuote
    extra = 0
    readonly_fields = ('version', 'created_at', 'created_by')
    fields = (
        'version',
        'item_cost', 'shipping_cost', 'customs_cost', 'service_fee',
        'deposit_percent', 'lead_time_days', 'notes',
        'created_at', 'created_by',
    )


class ImportPaymentInline(admin.TabularInline):
    model = ImportPayment
    extra = 0
    readonly_fields = (
        'kind', 'amount', 'phone_number', 'status',
        'mpesa_receipt', 'created_at', 'confirmed_at',
    )
    can_delete = False
    fields = (
        'kind', 'amount', 'phone_number', 'status',
        'mpesa_receipt', 'created_at', 'confirmed_at',
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ImportRequest)
class ImportRequestAdmin(admin.ModelAdmin):
    list_display = (
        'reference', 'title', 'user_link', 'status_pill',
        'quantity', 'paid_display', 'created_at',
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'reference', 'title', 'description',
        'user__username', 'user__email', 'phone_number',
    )
    readonly_fields = (
        'reference', 'user', 'created_at', 'updated_at',
        'reference_image_preview',
        'totals_display',
    )
    inlines = [ImportQuoteInline, ImportPaymentInline]
    fieldsets = (
        ('Reference', {
            'fields': ('reference', 'user', 'created_at', 'updated_at')
        }),
        ('Item', {
            'fields': ('title', 'description', 'reference_url',
                       'reference_image', 'reference_image_preview', 'quantity')
        }),
        ('Contact', {
            'fields': ('business_name', 'phone_number', 'delivery_location')
        }),
        ('Status & totals', {
            'fields': ('status', 'totals_display')
        }),
    )
    actions = ['mark_ordered', 'mark_in_transit', 'mark_arrived', 'mark_completed']

    def user_link(self, obj):
        return obj.user.username
    user_link.short_description = 'User'
    user_link.admin_order_field = 'user__username'

    def status_pill(self, obj):
        tone_colours = {
            'muted':   ('#1A1A1A', '#7F7669'),
            'warning': ('#3D2E10', '#E8B93C'),
            'success': ('#1B3A2A', '#45D68A'),
            'danger':  ('#3D1414', '#F0605C'),
        }
        bg, fg = tone_colours.get(obj.status_tone, tone_colours['muted'])
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;'
            'border-radius:999px;font-size:11px;white-space:nowrap;">{}</span>',
            bg, fg, obj.get_status_display(),
        )
    status_pill.short_description = 'Status'

    def paid_display(self, obj):
        return f'KES {obj.paid_amount} / {obj.total_amount}'
    paid_display.short_description = 'Paid / Total'

    def totals_display(self, obj):
        return format_html(
            '<strong>Paid:</strong> KES {} &nbsp;·&nbsp; '
            '<strong>Total:</strong> KES {} &nbsp;·&nbsp; '
            '<strong>Balance:</strong> KES {}',
            obj.paid_amount, obj.total_amount, obj.balance_due,
        )
    totals_display.short_description = 'Payment summary'

    def reference_image_preview(self, obj):
        if not obj.reference_image:
            return '—'
        return format_html(
            '<a href="{0}" target="_blank"><img src="{0}" style="max-width:400px"></a>',
            obj.reference_image.url,
        )
    reference_image_preview.short_description = 'Reference image'

    @admin.action(description='Mark selected as ORDERED')
    def mark_ordered(self, request, queryset):
        updated = queryset.update(status='ordered', updated_at=timezone.now())
        self.message_user(request, f'{updated} request(s) marked ordered.')

    @admin.action(description='Mark selected as IN TRANSIT')
    def mark_in_transit(self, request, queryset):
        updated = queryset.update(status='in_transit', updated_at=timezone.now())
        self.message_user(request, f'{updated} request(s) marked in transit.')

    @admin.action(description='Mark selected as ARRIVED')
    def mark_arrived(self, request, queryset):
        updated = queryset.update(status='arrived', updated_at=timezone.now())
        self.message_user(request, f'{updated} request(s) marked arrived.')

    @admin.action(description='Mark selected as COMPLETED')
    def mark_completed(self, request, queryset):
        updated = queryset.update(status='completed', updated_at=timezone.now())
        self.message_user(request, f'{updated} request(s) marked completed.')
