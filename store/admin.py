from django.contrib import admin
from django.utils.html import format_html

from .models import BackgroundImage, BundleOffer, Category, DeliveryAddress, DeliveryZone, Department, Product, Promotion, SiteLogo


@admin.register(SiteLogo)
class SiteLogoAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'label', 'is_active', 'uploaded_at')
    list_editable = ('is_active',)
    list_filter = ('is_active',)
    ordering = ('-uploaded_at',)
    actions = ['make_active']

    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:40px;width:auto;max-width:140px;object-fit:contain;background:#111;padding:4px;">',
                obj.image.url,
            )
        return '(no image)'
    thumbnail.short_description = 'Preview'

    @admin.action(description='Set as the active logo')
    def make_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one image to activate.', level='error')
            return
        logo = queryset.first()
        logo.is_active = True
        logo.save()
        self.message_user(request, f'"{logo}" is now the active logo.')


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'title', 'kicker', 'tone', 'media_type', 'voucher_code', 'sort_order', 'is_active')
    list_editable = ('sort_order', 'is_active')
    list_filter = ('tone', 'media_type', 'is_active')
    search_fields = ('title', 'kicker', 'voucher_code')
    fieldsets = (
        (None, {'fields': ('kicker', 'title', 'description', 'voucher_code', 'tone')}),
        ('Media', {
            'fields': ('media_type', 'image', 'video', 'video_url'),
            'description': 'Pick a Media type, then fill in the matching field below it. For video, upload a file OR paste a direct MP4 link — an uploaded file takes priority if both are set.',
        }),
        ('Call to action', {'fields': ('cta_label', 'cta_url')}),
        ('Visibility', {'fields': ('is_active', 'sort_order')}),
    )

    def thumbnail(self, obj):
        if obj.media_type == Promotion.MediaType.IMAGE and obj.image:
            return format_html('<img src="{}" style="height:50px;width:80px;object-fit:cover;border-radius:6px;">', obj.image.url)
        if obj.media_type == Promotion.MediaType.VIDEO and obj.video_source:
            return format_html('<span style="opacity:.6">▶ video</span>')
        return '—'
    thumbnail.short_description = 'Preview'


@admin.register(BackgroundImage)
class BackgroundImageAdmin(admin.ModelAdmin):
    list_display = ('thumbnail', 'label', 'is_active', 'uploaded_at')
    list_editable = ('is_active',)
    list_filter = ('is_active',)
    ordering = ('-uploaded_at',)
    actions = ['make_active']

    def thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:60px;width:100px;object-fit:cover;border-radius:6px;">',
                obj.image.url,
            )
        return '(no image)'
    thumbnail.short_description = 'Preview'

    @admin.action(description='Set as the active background')
    def make_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Select exactly one image to activate.', level='error')
            return
        bg = queryset.first()
        bg.is_active = True
        bg.save()
        self.message_user(request, f'"{bg}" is now the active background.')


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'delivery_fee', 'estimated_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'theme', 'is_active', 'sort_order')
    list_editable = ('sort_order', 'is_active')
    list_filter = ('theme', 'is_active')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'slug')
    list_filter = ('department',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'vendor', 'price', 'compare_at_price', 'stock', 'is_active', 'is_approved', 'is_featured')
    list_filter = ('category', 'vendor', 'is_alcoholic', 'is_active', 'is_approved', 'is_featured')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    actions = ['approve_products']
    fieldsets = (
        (None, {'fields': ('category', 'vendor', 'is_approved', 'name', 'slug', 'description', 'image')}),
        ('Pricing & stock', {'fields': ('price', 'compare_at_price', 'volume_ml', 'stock', 'is_alcoholic', 'is_active')}),
        ('Wholesale / bulk pricing', {
            'fields': ('wholesale_quantity_threshold', 'wholesale_price'),
            'description': 'Optional — automatically switches to this per-unit price once a customer\'s quantity in the cart meets the threshold.',
        }),
        ('Homepage hero slider', {
            'fields': ('is_featured', 'hero_tagline', 'hero_headline', 'hero_description'),
            'description': 'Mark up to a few products as featured to show them in the homepage hero slider, with real product photos.',
        }),
    )

    @admin.action(description='Approve selected products (make visible in the shop)')
    def approve_products(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} product(s) approved.')


@admin.register(BundleOffer)
class BundleOfferAdmin(admin.ModelAdmin):
    list_display = ('label', 'trigger_product', 'trigger_quantity', 'reward_product', 'reward_quantity', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('label',)


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'building_name', 'area', 'city', 'has_gps', 'is_default')
    list_filter = ('city', 'is_default')
    search_fields = ('user__username', 'building_name', 'area')
    readonly_fields = ('maps_link',)

    def maps_link(self, obj):
        if obj.has_gps:
            from django.utils.html import format_html
            return format_html('<a href="{}" target="_blank">Open in Google Maps</a>', obj.maps_url)
        return 'No GPS captured'
    maps_link.short_description = 'GPS location'
