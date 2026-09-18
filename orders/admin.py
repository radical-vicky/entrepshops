from django.contrib import admin

from .models import Order, OrderItem, Review, Rider, RiderTip


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'unit_price', 'quantity')


@admin.register(Rider)
class RiderAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone_number', 'vehicle', 'is_active', 'user')
    list_filter = ('is_active', 'vehicle')
    search_fields = ('name', 'phone_number', 'user__username')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'rider', 'total', 'created_at')
    list_filter = ('status', 'rider', 'created_at')
    search_fields = ('id', 'user__username', 'phone_number')
    inlines = [OrderItemInline]
    readonly_fields = (
        'subtotal', 'delivery_fee', 'total', 'created_at', 'updated_at',
        'assigned_at', 'out_for_delivery_at', 'delivered_at',
    )
    actions = ['mark_out_for_delivery', 'mark_delivered']

    def save_model(self, request, obj, form, change):
        # If the rider was just set/changed from the admin form, route
        # through assign_rider() so the status + timestamp stay in sync
        # rather than silently drifting out of step with a raw field edit.
        if change and 'rider' in form.changed_data and obj.rider_id:
            super().save_model(request, obj, form, change)
            obj.assign_rider(obj.rider)
        else:
            super().save_model(request, obj, form, change)

    @admin.action(description='Mark selected orders as out for delivery')
    def mark_out_for_delivery(self, request, queryset):
        count = 0
        for order in queryset:
            order.mark_out_for_delivery()
            count += 1
        self.message_user(request, f'{count} order(s) marked out for delivery.')

    @admin.action(description='Mark selected orders as delivered')
    def mark_delivered(self, request, queryset):
        count = 0
        for order in queryset:
            order.mark_delivered()
            count += 1
        self.message_user(request, f'{count} order(s) marked delivered.')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('product__name', 'user__username', 'comment')


@admin.register(RiderTip)
class RiderTipAdmin(admin.ModelAdmin):
    list_display = ('order', 'amount', 'phone_number', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('order__id', 'phone_number', 'checkout_request_id')
    readonly_fields = ('order', 'amount', 'phone_number', 'checkout_request_id', 'status', 'created_at')
