from django.contrib import admin
from .models import (
    BackgroundImage, BundleOffer, Category, DeliveryAddress, DeliveryZone,
    Department, Product, ProductImage, ProductOffer, ProductVariant,
    Promotion, SiteLogo,
)


# ---------------------------------------------------------------- catalog

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'theme', 'unit_kind', 'is_active', 'sort_order')
    list_filter = ('theme', 'unit_kind', 'is_active')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'slug')
    list_filter = ('department',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ('size_label', 'size_value', 'size_unit', 'sku', 'price',
              'compare_at_price', 'stock', 'is_active', 'sort_order')
    ordering = ('sort_order', 'price')


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ('image', 'alt_text', 'sort_order')


class ProductOfferInline(admin.TabularInline):
    model = ProductOffer
    extra = 1
    fields = ('text', 'url', 'sort_order', 'is_active')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'department', 'category', 'vendor', 'price_range_display',
        'stock', 'availability', 'is_active', 'is_approved', 'is_featured',
    )
    list_filter = (
        'department', 'category', 'vendor', 'availability', 'is_alcoholic',
        'is_active', 'is_approved', 'is_featured',
    )
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    actions = ['approve_products']
    inlines = [ProductVariantInline, ProductImageInline, ProductOfferInline]
    fieldsets = (
        (None, {
            'fields': (
                'department', 'category', 'vendor', 'is_approved',
                'name', 'slug', 'description', 'image',
            )
        }),
        ('Availability', {
            'fields': ('availability', 'is_active'),
            'description': 'Controls the badge and whether customers can add to cart.',
        }),
        ('Fallback pricing & stock — overridden by variants', {
            'fields': ('price', 'compare_at_price', 'volume_ml', 'stock', 'is_alcoholic'),
            'description': 'Only used if this product has no variants. Add variants below to set per-size pricing.',
        }),
        ('Wholesale / bulk pricing', {
            'fields': ('wholesale_quantity_threshold', 'wholesale_price'),
            'classes': ('collapse',),
        }),
        ('Homepage hero slider', {
            'fields': ('is_featured', 'hero_tagline', 'hero_headline', 'hero_description'),
            'classes': ('collapse',),
        }),
    )

    def price_range_display(self, obj):
        lo, hi = obj.price_range
        if lo is None or hi is None:
            return '—'
        return f'KES {lo}' if lo == hi else f'KES {lo}–{hi}'
    price_range_display.short_description = 'Price'

    @admin.action(description='Approve selected products (make visible in the shop)')
    def approve_products(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} product(s) approved.')


@admin.register(BundleOffer)
class BundleOfferAdmin(admin.ModelAdmin):
    list_display = ('label', 'trigger_product', 'trigger_quantity',
                    'reward_product', 'reward_quantity', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('label',)


# ---------------------------------------------------------------- site chrome

@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ('title', 'kicker', 'tone', 'media_type', 'is_active', 'sort_order')
    list_filter = ('tone', 'media_type', 'is_active')
    search_fields = ('title', 'kicker')


@admin.register(SiteLogo)
class SiteLogoAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_active', 'uploaded_at')
    list_filter = ('is_active',)


@admin.register(BackgroundImage)
class BackgroundImageAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_active', 'uploaded_at')
    list_filter = ('is_active',)


# ---------------------------------------------------------------- delivery

@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('name', 'delivery_fee', 'estimated_minutes', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ('label', 'user', 'building_name', 'area', 'city', 'is_default')
    list_filter = ('is_default', 'city')
    search_fields = ('user__username', 'building_name', 'area', 'phone_number')
    raw_id_fields = ('user',)