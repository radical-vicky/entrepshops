from django.contrib import admin

from store.models import Product

from .models import Vendor, VendorSubscriptionPayment


class VendorProductInline(admin.TabularInline):
    model = Product
    extra = 0
    fields = ('name', 'category', 'price', 'stock', 'is_active', 'is_approved')
    readonly_fields = ('name', 'category', 'price', 'stock')


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'phone_number', 'is_approved', 'subscription_active', 'subscription_expires_at')
    list_filter = ('is_approved',)
    search_fields = ('business_name', 'user__username', 'phone_number')
    inlines = [VendorProductInline]
    actions = ['approve_vendors', 'grant_free_month']

    @admin.display(boolean=True, description='Subscription active')
    def subscription_active(self, obj):
        return obj.subscription_active

    @admin.action(description='Approve selected vendors')
    def approve_vendors(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} vendor(s) approved.')

    @admin.action(description='Grant a free month (e.g. promo, or M-Pesa paid manually)')
    def grant_free_month(self, request, queryset):
        from django.conf import settings
        for vendor in queryset:
            vendor.extend_subscription(settings.VENDOR_SUBSCRIPTION_DAYS)
        self.message_user(request, f'Extended {queryset.count()} vendor(s) by {settings.VENDOR_SUBSCRIPTION_DAYS} days.')


@admin.register(VendorSubscriptionPayment)
class VendorSubscriptionPaymentAdmin(admin.ModelAdmin):
    list_display = ('vendor', 'amount', 'days', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('vendor__business_name', 'checkout_request_id', 'mpesa_receipt_number')
    readonly_fields = ('vendor', 'amount', 'phone_number', 'days', 'checkout_request_id', 'created_at')
    actions = ['mark_paid_manually']

    @admin.action(description='Mark as paid manually (extends subscription)')
    def mark_paid_manually(self, request, queryset):
        count = 0
        for payment in queryset.filter(status=VendorSubscriptionPayment.Status.INITIATED):
            payment.mark_success(receipt_number='MANUAL')
            count += 1
        self.message_user(request, f'{count} payment(s) marked paid and subscription extended.')
